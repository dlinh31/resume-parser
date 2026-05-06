"""Stage 6: embed bullets and write normalized records to PostgreSQL."""

import json
from pathlib import Path

from openai import OpenAI


def _upsert_skill(cur, canonical: str) -> int:
    # ON CONFLICT DO UPDATE (no-op) forces RETURNING to fire on both insert and conflict
    cur.execute(
        "INSERT INTO skill (canonical) VALUES (%s)"
        " ON CONFLICT (canonical) DO UPDATE SET canonical = EXCLUDED.canonical"
        " RETURNING id",
        (canonical,),
    )
    return cur.fetchone()[0]


def _embed(client: OpenAI, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(map(str, embedding)) + "]"


def index(
    normalized_path: Path,
    conn,
    openai_client: OpenAI,
    *,
    force: bool = False,
) -> dict:
    with open(normalized_path) as f:
        data = json.load(f)

    file_id = data["file_id"]

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM resume WHERE file_id = %s", (file_id,))
            existing = cur.fetchone()

            if existing and not force:
                print(f"[skip] {file_id} already indexed")
                return {"file_id": file_id, "status": "skipped"}

            if existing:
                cur.execute("DELETE FROM resume WHERE file_id = %s", (file_id,))

            contact = data.get("contact") or {}
            cur.execute(
                """
                INSERT INTO resume (
                    file_id, source_uri, normalizer_version, normalized_at,
                    contact_name, contact_email, contact_phone,
                    contact_linkedin, contact_github, contact_website
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    file_id,
                    data["source_uri"],
                    data.get("normalizer_version", 1),
                    data["normalized_at"],
                    contact.get("name"),
                    contact.get("email"),
                    contact.get("phone"),
                    contact.get("linkedin"),
                    contact.get("github"),
                    contact.get("website"),
                ),
            )
            resume_id = cur.fetchone()[0]

            bullet_texts: list[str] = []
            # (experience_id | None, project_id | None, position)
            bullet_parents: list[tuple] = []

            for pos, exp in enumerate(data.get("experiences", [])):
                cur.execute(
                    """
                    INSERT INTO experience (
                        resume_id, company_raw, company_canonical, title,
                        location_raw, location_canonical, is_remote,
                        start_date_raw, start_date_iso,
                        end_date_raw, end_date_iso,
                        is_current, position
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (
                        resume_id,
                        exp["company"], exp["company_canonical"], exp["title"],
                        exp.get("location"), exp.get("location_canonical"),
                        exp.get("is_remote", False),
                        exp.get("start_date"), exp.get("start_date_iso"),
                        exp.get("end_date"), exp.get("end_date_iso"),
                        exp.get("is_current", False), pos,
                    ),
                )
                exp_id = cur.fetchone()[0]
                for bpos, text in enumerate(exp.get("bullets", [])):
                    bullet_texts.append(text)
                    bullet_parents.append((exp_id, None, bpos))

            for pos, edu in enumerate(data.get("education", [])):
                cur.execute(
                    """
                    INSERT INTO education (
                        resume_id, institution, degree, field, gpa,
                        graduation_date_raw, graduation_date_iso, is_expected,
                        honors, courses, position
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        resume_id,
                        edu["institution"], edu.get("degree"), edu.get("field"), edu.get("gpa"),
                        edu.get("graduation_date"), edu.get("graduation_date_iso"),
                        edu.get("is_expected", False),
                        json.dumps(edu["honors"]) if edu.get("honors") else None,
                        json.dumps(edu["courses"]) if edu.get("courses") else None,
                        pos,
                    ),
                )

            for pos, proj in enumerate(data.get("projects", [])):
                cur.execute(
                    """
                    INSERT INTO project (resume_id, name, technologies, links, position)
                    VALUES (%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (
                        resume_id, proj["name"],
                        json.dumps(proj["technologies"]) if proj.get("technologies") else None,
                        json.dumps(proj["links"]) if proj.get("links") else None,
                        pos,
                    ),
                )
                proj_id = cur.fetchone()[0]
                for bpos, text in enumerate(proj.get("bullets", [])):
                    bullet_texts.append(text)
                    bullet_parents.append((None, proj_id, bpos))

            # one OpenAI call per resume — all bullets batched together
            embeddings = _embed(openai_client, bullet_texts)

            for (exp_id, proj_id, bpos), text, emb in zip(bullet_parents, bullet_texts, embeddings):
                cur.execute(
                    """
                    INSERT INTO bullet (experience_id, project_id, text, embedding, position)
                    VALUES (%s,%s,%s,%s::vector,%s)
                    """,
                    (exp_id, proj_id, text, _vec(emb), bpos),
                )

            for skill in data.get("skills", []):
                skill_id = _upsert_skill(cur, skill["canonical"])
                cur.execute(
                    """
                    INSERT INTO resume_skill (resume_id, skill_id, raw, category)
                    VALUES (%s,%s,%s,%s) ON CONFLICT (resume_id, skill_id) DO NOTHING
                    """,
                    (resume_id, skill_id, skill["raw"], skill.get("category")),
                )

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
                cur.execute(
                    """
                    INSERT INTO other_section (resume_id, section_type, raw_header, raw_text, position)
                    VALUES (%s,%s,%s,%s,%s)
                    """,
                    (resume_id, stype, header, text, pos),
                )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    n_exp_bullets = sum(1 for e, p, _ in bullet_parents if e is not None)
    n_proj_bullets = sum(1 for e, p, _ in bullet_parents if p is not None)
    print(
        f"[ok] {file_id}: "
        f"{len(data.get('experiences', []))} exp ({n_exp_bullets} bullets), "
        f"{len(data.get('projects', []))} proj ({n_proj_bullets} bullets), "
        f"{len(data.get('skills', []))} skills"
    )
    return {"file_id": file_id, "status": "ok"}
