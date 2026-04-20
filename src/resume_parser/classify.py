from enum import Enum
from pathlib import Path

import pdfplumber

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
_MIN_CHARS_PER_PAGE = 100


class FileType(str, Enum):
    PDF_TEXT = "pdf_text"
    PDF_SCANNED = "pdf_scanned"
    IMAGE = "image"


def classify(path: str | Path) -> FileType:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in _IMAGE_SUFFIXES:
        return FileType.IMAGE

    if suffix == ".pdf":
        return _classify_pdf(path)

    raise ValueError(f"Unsupported file type: {suffix!r}")


def _classify_pdf(path: Path) -> FileType:
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return FileType.PDF_SCANNED
        total = sum(len(p.extract_text() or "") for p in pdf.pages)
        avg = total / len(pdf.pages)
    return FileType.PDF_TEXT if avg >= _MIN_CHARS_PER_PAGE else FileType.PDF_SCANNED
