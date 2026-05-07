"""In-memory job store for tracking async pipeline jobs."""

import threading
import uuid
from datetime import datetime, timezone
from typing import Literal, TypedDict


JobStatus = Literal["pending", "processing", "done", "failed"]


class Job(TypedDict):
    job_id: str
    file_id: str | None
    status: JobStatus
    created_at: str
    finished_at: str | None
    error: str | None


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job() -> Job:
    job_id = str(uuid.uuid4())
    job: Job = {
        "job_id": job_id,
        "file_id": None,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
    }
    with _lock:
        _jobs[job_id] = job
    return job


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id not in _jobs:
            return
        _jobs[job_id].update(kwargs)
        if kwargs.get("status") in ("done", "failed") and not _jobs[job_id].get("finished_at"):
            _jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)
