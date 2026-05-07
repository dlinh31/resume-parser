from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BulletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    text: str
    position: int


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    company_raw: str
    company_canonical: str
    title: str
    location_raw: str | None
    location_canonical: str | None
    is_remote: bool
    start_date_raw: str | None
    start_date_iso: str | None
    end_date_raw: str | None
    end_date_iso: str | None
    is_current: bool
    position: int
    bullets: list[BulletOut]


class EducationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    institution: str
    degree: str | None
    field: str | None
    gpa: str | None
    graduation_date_raw: str | None
    graduation_date_iso: str | None
    is_expected: bool
    honors: list[Any] | None
    courses: list[Any] | None
    position: int


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    technologies: list[Any] | None
    links: list[Any] | None
    position: int
    bullets: list[BulletOut]


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    canonical: str
    raw: str
    category: str | None


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    file_id: str
    source_uri: str
    normalizer_version: int
    normalized_at: datetime
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    contact_linkedin: str | None
    contact_github: str | None
    contact_website: str | None
    experiences: list[ExperienceOut]
    education: list[EducationOut]
    projects: list[ProjectOut]
    skills: list[SkillOut]


class UploadResponse(BaseModel):
    job_id: str | None
    file_id: str
    status: str | None = None


class JobOut(BaseModel):
    job_id: str
    file_id: str | None
    status: str
    created_at: str
    finished_at: str | None
    error: str | None
