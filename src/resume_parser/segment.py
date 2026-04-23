import json
from datetime import datetime, timezone
from pathlib import Path

from .llm.base import LLMAdapter


def _assemble_text(parsed: dict) -> str:
    """Concatenate page texts; add page markers for multi-page resumes."""
    pages = parsed["pages"]
    if len(pages) == 1:
        return pages[0]["text"]
    return "\n\n".join(f"--- page {p['page']} ---\n{p['text']}" for p in pages)


def segment(
    parsed_path: Path,
    segmented_dir: Path,
    adapter: LLMAdapter,
    *,
    force: bool = False,
) -> dict:
    segmented_dir.mkdir(exist_ok=True)

    with open(parsed_path) as f:
        parsed = json.load(f)

    file_id = parsed["file_id"]
    out_path = segmented_dir / f"{file_id}.json"

    if out_path.exists() and not force:
        print(f"[skip] {file_id} already segmented")
        return {"file_id": file_id, "status": "skipped"}

    text = _assemble_text(parsed)
    result = adapter.segment_resume(text)

    output = {
        "file_id": file_id,
        "source_uri": parsed["source_uri"],
        "segmented_at": datetime.now(timezone.utc).isoformat(),
        "model": result.model,
        "sections": [
            {
                "section_type": s.section_type,
                "raw_header": s.raw_header,
                "text": s.text,
                "llm_confidence": s.llm_confidence,
                "header_score": s.header_score,
                "confidence": s.confidence,
            }
            for s in result.sections
        ],
    }

    out_path.write_text(json.dumps(output, indent=2))
    low_conf = [s for s in result.sections if s.confidence < 0.7]
    print(
        f"[ok] {file_id}: {len(result.sections)} sections"
        + (f", {len(low_conf)} low-confidence" if low_conf else "")
        + f" → {out_path}"
    )
    return {"file_id": file_id, "status": "ok", "sections": len(result.sections)}
