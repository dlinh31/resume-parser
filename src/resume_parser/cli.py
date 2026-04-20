#!/usr/bin/env python3
"""
Usage:
    ingest raw/resumes/resume.pdf
    ingest raw/resumes/*.pdf
    ingest raw/resumes/          # process entire directory
"""
import sys
from pathlib import Path

from .extract import extract

SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    paths: list[Path] = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            paths.extend(f for f in sorted(p.iterdir()) if f.suffix.lower() in SUPPORTED)
        elif p.is_file():
            paths.append(p)
        else:
            print(f"[skip] not found: {arg}")

    if not paths:
        print("No supported files found.")
        sys.exit(1)

    print(f"Processing {len(paths)} file(s)...\n")
    ok, failed = 0, 0
    for path in paths:
        try:
            out = extract(path)
            print(f"[done] → {out}\n")
            ok += 1
        except Exception as e:
            print(f"[error] {path.name}: {e}\n")
            failed += 1

    print(f"Finished: {ok} ok, {failed} failed")


if __name__ == "__main__":
    main()
