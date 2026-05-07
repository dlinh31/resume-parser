"""FastAPI server: async job-based resume upload and processing."""

import asyncio
import hashlib
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from openai import OpenAI
from psycopg2.pool import ThreadedConnectionPool

from .jobs import Job, create_job, get_job, update_job
from .llm.claude import ClaudeAdapter
from .pipeline import run_pipeline

_pool: ThreadedConnectionPool | None = None
_adapter: ClaudeAdapter | None = None
_openai_client: OpenAI | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _adapter, _openai_client
    load_dotenv()
    _pool = ThreadedConnectionPool(minconn=2, maxconn=10, dsn=os.environ["DATABASE_URL"])
    _adapter = ClaudeAdapter()
    _openai_client = OpenAI()
    yield
    _pool.closeall()


app = FastAPI(lifespan=lifespan)


def _get_conn():
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@app.post("/resumes", status_code=202)
async def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    raw_bytes = await file.read()
    fid = hashlib.sha256(raw_bytes).hexdigest()[:12]

    conn = _pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT file_id FROM resume WHERE file_id = %s", (fid,))
            exists = cur.fetchone() is not None
    finally:
        _pool.putconn(conn)

    if exists:
        return JSONResponse(
            status_code=200,
            content={"job_id": None, "file_id": fid, "status": "already_indexed"},
        )

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(raw_bytes)
    tmp.flush()
    tmp.close()
    raw_path = Path(tmp.name)

    job = create_job()
    background_tasks.add_task(_run_job, job["job_id"], raw_path)
    return {"job_id": job["job_id"], "file_id": fid}


async def _run_job(job_id: str, raw_path: Path) -> None:
    update_job(job_id, status="processing")
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, _run_pipeline_sync, job_id, raw_path)
        update_job(job_id, status="done", file_id=result["file_id"])
    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
    finally:
        raw_path.unlink(missing_ok=True)


def _run_pipeline_sync(job_id: str, raw_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as work_dir:
        conn = _pool.getconn()
        try:
            return run_pipeline(
                raw_path,
                Path(work_dir),
                _adapter,
                conn,
                _openai_client,
            )
        finally:
            _pool.putconn(conn)


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> Job:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/resumes/{file_id}")
def get_resume(file_id: str, conn=Depends(_get_conn)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, file_id, source_uri, normalizer_version, normalized_at,"
            " contact_name, contact_email, contact_phone,"
            " contact_linkedin, contact_github, contact_website"
            " FROM resume WHERE file_id = %s",
            (file_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Resume not found")
        cols = [d[0] for d in cur.description]
        resume = dict(zip(cols, row))
        resume_id = resume.pop("id")

        cur.execute(
            "SELECT company_raw, company_canonical, title, location_raw, is_remote,"
            " start_date_raw, end_date_raw, is_current, position"
            " FROM experience WHERE resume_id = %s ORDER BY position",
            (resume_id,),
        )
        exp_cols = [d[0] for d in cur.description]
        resume["experiences"] = [dict(zip(exp_cols, r)) for r in cur.fetchall()]

        cur.execute(
            "SELECT institution, degree, field, gpa, graduation_date_raw, is_expected, position"
            " FROM education WHERE resume_id = %s ORDER BY position",
            (resume_id,),
        )
        edu_cols = [d[0] for d in cur.description]
        resume["education"] = [dict(zip(edu_cols, r)) for r in cur.fetchall()]

        cur.execute(
            "SELECT name, technologies, links, position"
            " FROM project WHERE resume_id = %s ORDER BY position",
            (resume_id,),
        )
        proj_cols = [d[0] for d in cur.description]
        resume["projects"] = [dict(zip(proj_cols, r)) for r in cur.fetchall()]

        cur.execute(
            "SELECT s.canonical, rs.raw, rs.category"
            " FROM resume_skill rs JOIN skill s ON s.id = rs.skill_id"
            " WHERE rs.resume_id = %s",
            (resume_id,),
        )
        skill_cols = [d[0] for d in cur.description]
        resume["skills"] = [dict(zip(skill_cols, r)) for r in cur.fetchall()]

    return resume


def main():
    import uvicorn
    uvicorn.run("resume_parser.server:app", host="0.0.0.0", port=8000, reload=False)
