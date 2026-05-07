from fastapi import APIRouter, HTTPException

from ...jobs import get_job
from ..schemas import JobOut

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job_status(job_id: str) -> JobOut:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
