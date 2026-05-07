import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from google.cloud import documentai

from .classify import FileType, classify

PARSED_DIR = Path("data/parsed")

_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".pdf": "application/pdf",
}


def file_id(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def extract(path: str | Path, output_dir: Path | None = None) -> Path:
    path = Path(path)
    ftype = classify(path)
    fid = file_id(path)

    print(f"[classify] {path.name} → {ftype.value}")

    if ftype == FileType.PDF_TEXT:
        pages = _extract_pdfplumber(path)
        extractor = "pdfplumber"
    else:
        mime = _MIME_TYPES[path.suffix.lower()]
        pages = _extract_docai(path, mime)
        extractor = "google-document-ai"

    output = {
        "file_id": fid,
        "source_uri": f"file://{path.resolve()}",
        "file_type": ftype.value,
        "extractor": extractor,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
    }

    out_dir = output_dir if output_dir is not None else PARSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{fid}.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"[extract] wrote {out_path} ({len(pages)} pages, {sum(len(p['text']) for p in pages):,} chars total)")
    return out_path


def _extract_pdfplumber(path: Path) -> list[dict]:
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            words = [
                {"text": w["text"], "x0": w["x0"], "y0": w["top"], "x1": w["x1"], "y1": w["bottom"]}
                for w in (page.extract_words() or [])
            ]
            pages.append({"page": i + 1, "text": text, "words": words})
            print(f"  page {i + 1}: {len(text):,} chars, {len(words)} words")
    return pages


def _extract_docai(path: Path, mime_type: str) -> list[dict]:
    project = os.environ["DOCAI_PROJECT_ID"]
    location = os.environ.get("DOCAI_LOCATION", "us")
    processor = os.environ["DOCAI_PROCESSOR_ID"]

    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    name = client.processor_path(project, location, processor)

    raw = path.read_bytes()
    print(f"  calling Document AI ({mime_type}, {len(raw):,} bytes)...")
    response = client.process_document(
        request=documentai.ProcessRequest(
            name=name,
            raw_document=documentai.RawDocument(content=raw, mime_type=mime_type),
        )
    )
    doc = response.document

    pages = []
    for i, page in enumerate(doc.pages):
        blocks = [
            {
                "text": _layout_text(doc.text, block.layout),
                "confidence": round(block.layout.confidence, 4),
                "bbox": [{"x": v.x, "y": v.y} for v in block.layout.bounding_poly.normalized_vertices],
            }
            for block in page.blocks
        ]
        full_text = "\n".join(b["text"] for b in blocks)
        pages.append({"page": i + 1, "text": full_text, "blocks": blocks})
        print(f"  page {i + 1}: {len(full_text):,} chars, {len(blocks)} blocks")
    return pages


def _layout_text(full_text: str, layout) -> str:
    return "".join(
        full_text[int(seg.start_index): int(seg.end_index)]
        for seg in layout.text_anchor.text_segments
    )