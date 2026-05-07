"""Stage 6: embed bullets and write normalized records to PostgreSQL via SQLAlchemy."""

import json
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..db.models import (
    Bullet, Education, Experience, OtherSection,
    Project, Resume, ResumeSkill, Skill,
)


def _embed(client: OpenAI, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


def _upsert_skill(session: Session, canonical: str) -> int:
    stmt = pg_insert(Skill).values(canonical=canonical)
    stmt = stmt.on_conflict_do_update(
        index_elements=["canonical"],
        set_={"canonical": stmt.excluded.canonical},
    ).returning(Skill.id)
    return session.execute(stmt).scalar_one()


def index(
    normalized_path: Path,
    session: Session,
    openai_client: OpenAI,
    *,
    force: bool = False,
) -> dict:
    with open(normalized_path) as f:
        data = json.load(f)

    file_id = data["file_id"]

    existing = session.query(Resume).filter_by(file_id=file_id).first()
    if existing and not force:
        print(f"[skip] {file_id} already indexed")
        return {"file_id": file_id, "status": "skipped"}

    if existing:
        session.delete(existing)
        session.flush()

    contact = data.get("contact") or {}
    resume = Resume(
        file_id=file_id,
        source_uri=data["source_uri"],
        normalizer_version=data.get("normalizer_version", 1),
        normalized_at=datetime.fromisoformat(data["normalized_at"]),
        contact_name=contact.get("name"),
        contact_email=contact.get("email"),
        contact_phone=contact.get("phone"),
        contact_linkedin=contact.get("linkedin"),
        contact_github=contact.get("github"),
        contact_website=contact.get("website"),
    )
    session.add(resume)
    session.flush()

    bullet_texts: list[str] = []
    bullet_parents: list[tuple[str, int, int]] = []  # (kind, parent_id, position)

    for pos, exp_data in enumerate(data.get("experiences", [])):
        exp = Experience(
            resume_id=resume.id,
            company_raw=exp_data["company"],
            company_canonical=exp_data["company_canonical"],
            title=exp_data["title"],
            location_raw=exp_data.get("location"),
            location_canonical=exp_data.get("location_canonical"),
            is_remote=exp_data.get("is_remote", False),
            start_date_raw=exp_data.get("start_date"),
            start_date_iso=exp_data.get("start_date_iso"),
            end_date_raw=exp_data.get("end_date"),
            end_date_iso=exp_data.get("end_date_iso"),
            is_current=exp_data.get("is_current", False),
            position=pos,
        )
        session.add(exp)
        session.flush()
        for bpos, text in enumerate(exp_data.get("bullets", [])):
            bullet_texts.append(text)
            bullet_parents.append(("experience", exp.id, bpos))

    for pos, edu_data in enumerate(data.get("education", [])):
        session.add(Education(
            resume_id=resume.id,
            institution=edu_data["institution"],
            degree=edu_data.get("degree"),
            field=edu_data.get("field"),
            gpa=edu_data.get("gpa"),
            graduation_date_raw=edu_data.get("graduation_date"),
            graduation_date_iso=edu_data.get("graduation_date_iso"),
            is_expected=edu_data.get("is_expected", False),
            honors=edu_data.get("honors") or None,
            courses=edu_data.get("courses") or None,
            position=pos,
        ))

    for pos, proj_data in enumerate(data.get("projects", [])):
        proj = Project(
            resume_id=resume.id,
            name=proj_data["name"],
            technologies=proj_data.get("technologies") or None,
            links=proj_data.get("links") or None,
            position=pos,
        )
        session.add(proj)
        session.flush()
        for bpos, text in enumerate(proj_data.get("bullets", [])):
            bullet_texts.append(text)
            bullet_parents.append(("project", proj.id, bpos))

    embeddings = _embed(openai_client, bullet_texts)

    for (kind, parent_id, bpos), text, emb in zip(bullet_parents, bullet_texts, embeddings):
        session.add(Bullet(
            experience_id=parent_id if kind == "experience" else None,
            project_id=parent_id if kind == "project" else None,
            text=text,
            embedding=emb,
            position=bpos,
        ))

    for skill_data in data.get("skills", []):
        skill_id = _upsert_skill(session, skill_data["canonical"])
        stmt = pg_insert(ResumeSkill).values(
            resume_id=resume.id,
            skill_id=skill_id,
            raw=skill_data["raw"],
            category=skill_data.get("category"),
        ).on_conflict_do_nothing()
        session.execute(stmt)

    other_rows: list[tuple[str, str | None, str]] = []
    for award in data.get("awards", []):
        parts = [award["name"]]
        if award.get("issuer"):
            parts.append(f"({award['issuer']})")
        if award.get("date"):
            parts.append(f"— {award['date']}")
        other_rows.append(("awards", "Awards", " ".join(parts)))
    for sec in data.get("other_sections", []):
        other_rows.append((sec["section_type"], sec.get("raw_header"), sec["text"]))

    for pos, (stype, header, text) in enumerate(other_rows):
        session.add(OtherSection(
            resume_id=resume.id,
            section_type=stype,
            raw_header=header,
            raw_text=text,
            position=pos,
        ))

    session.commit()

    n_exp = sum(1 for k, _, _ in bullet_parents if k == "experience")
    n_proj = sum(1 for k, _, _ in bullet_parents if k == "project")
    print(
        f"[ok] {file_id}: "
        f"{len(data.get('experiences', []))} exp ({n_exp} bullets), "
        f"{len(data.get('projects', []))} proj ({n_proj} bullets), "
        f"{len(data.get('skills', []))} skills"
    )
    return {"file_id": file_id, "status": "ok"}
