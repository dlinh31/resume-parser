"""End-to-end pipeline orchestrator: chains stages 1–6 for a single file."""

import json
import tempfile
from pathlib import Path

from openai import OpenAI
from sqlalchemy.orm import Session

from .extract import extract, file_id as compute_file_id
from .field_extract import extract as field_extract
from .index import index
from .normalize import normalize
from .segment import segment
from ..db.models import Resume


def run_pipeline(
    raw_path: Path,
    work_dir: Path,
    adapter,
    session: Session,
    openai_client: OpenAI,
) -> dict:
    fid = compute_file_id(raw_path)

    if session.query(Resume).filter_by(file_id=fid).first():
        return {"file_id": fid, "status": "already_indexed"}

    parsed_dir = work_dir / "parsed"
    segmented_dir = work_dir / "segmented"
    extracted_dir = work_dir / "extracted"
    normalized_dir = work_dir / "normalized"

    parsed_path = extract(raw_path, output_dir=parsed_dir)

    parsed_data = json.loads(parsed_path.read_text())
    parsed_data["source_uri"] = f"upload://{fid}"
    parsed_path.write_text(json.dumps(parsed_data, indent=2))

    segment(parsed_path, segmented_dir, adapter)
    field_extract(segmented_dir / f"{fid}.json", extracted_dir, adapter)
    normalize(extracted_dir / f"{fid}.json", normalized_dir)
    result = index(normalized_dir / f"{fid}.json", session, openai_client)

    if result["status"] == "ok":
        resume = session.query(Resume).filter_by(file_id=fid).one()
        resume.pdf_bytes = raw_path.read_bytes()
        session.commit()

    return {"file_id": fid, "status": result["status"]}
