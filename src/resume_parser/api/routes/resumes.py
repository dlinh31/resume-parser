import asyncio
import hashlib
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from openai import OpenAI
from sqlalchemy.orm import Session

from ..deps import get_adapter, get_openai, get_session
from ..schemas import ResumeOut, UploadResponse
from ...db.models import Resume
from ...jobs import create_job, update_job
from ...llm.claude import ClaudeAdapter
from ...pipeline.run import run_pipeline

router = APIRouter()


@router.post("/resumes", status_code=202, response_model=UploadResponse)
async def upload_resume(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    raw_bytes = await file.read()
    fid = hashlib.sha256(raw_bytes).hexdigest()[:12]

    if session.query(Resume).filter_by(file_id=fid).first():
        return JSONResponse(
            status_code=200,
            content={"job_id": None, "file_id": fid, "status": "already_indexed"},
        )

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(raw_bytes)
    tmp.flush()
    tmp.close()

    job = create_job()
    background_tasks.add_task(
        _run_job,
        job["job_id"],
        Path(tmp.name),
        request.app.state.SessionLocal,
        request.app.state.adapter,
        request.app.state.openai_client,
    )
    return {"job_id": job["job_id"], "file_id": fid}


async def _run_job(
    job_id: str,
    raw_path: Path,
    SessionLocal,
    adapter: ClaudeAdapter,
    openai_client: OpenAI,
) -> None:
    update_job(job_id, status="processing")
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            _run_pipeline_sync,
            raw_path,
            SessionLocal,
            adapter,
            openai_client,
        )
        update_job(job_id, status="done", file_id=result["file_id"])
    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
    finally:
        raw_path.unlink(missing_ok=True)


def _run_pipeline_sync(
    raw_path: Path,
    SessionLocal,
    adapter: ClaudeAdapter,
    openai_client: OpenAI,
) -> dict:
    with tempfile.TemporaryDirectory() as work_dir:
        session = SessionLocal()
        try:
            return run_pipeline(raw_path, Path(work_dir), adapter, session, openai_client)
        finally:
            session.close()


@router.get("/resumes/{file_id}", response_model=ResumeOut)
def get_resume(file_id: str, session: Session = Depends(get_session)):
    resume = session.query(Resume).filter_by(file_id=file_id).first()
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume
