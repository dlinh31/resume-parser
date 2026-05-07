import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..llm.base import LLMAdapter, SectionSegment, SegmentResult


def extract(
    segmented_path: Path,
    extracted_dir: Path,
    adapter: LLMAdapter,
    *,
    force: bool = False,
) -> dict:
    extracted_dir.mkdir(exist_ok=True)

    with open(segmented_path) as f:
        segmented = json.load(f)

    file_id = segmented["file_id"]
    out_path = extracted_dir / f"{file_id}.json"

    if out_path.exists() and not force:
        print(f"[skip] {file_id} already extracted")
        return {"file_id": file_id, "status": "skipped"}

    segment_result = SegmentResult(
        sections=[
            SectionSegment(
                section_type=s["section_type"],
                raw_header=s["raw_header"],
                text=s["text"],
                llm_confidence=s["llm_confidence"],
                header_score=s["header_score"],
                confidence=s["confidence"],
            )
            for s in segmented["sections"]
        ],
        model=segmented["model"],
    )

    result = adapter.extract(segment_result)

    def _contact_dict(c):
        return asdict(c) if c else None

    output = {
        "file_id": file_id,
        "source_uri": segmented["source_uri"],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "model": result.model,
        "contact": _contact_dict(result.contact),
        "experiences": [asdict(e) for e in result.experiences],
        "education": [asdict(e) for e in result.education],
        "projects": [asdict(p) for p in result.projects],
        "skill_groups": [asdict(sg) for sg in result.skill_groups],
        "awards": [asdict(a) for a in result.awards],
        "other_sections": [asdict(o) for o in result.other_sections],
    }

    out_path.write_text(json.dumps(output, indent=2))
    print(
        f"[ok] {file_id}: "
        f"{len(result.experiences)} exp, "
        f"{len(result.education)} edu, "
        f"{len(result.projects)} proj, "
        f"{len(result.skill_groups)} skill_groups"
        + (f", {len(result.other_sections)} other" if result.other_sections else "")
        + f" → {out_path}"
    )
    return {"file_id": file_id, "status": "ok"}
