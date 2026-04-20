#!/usr/bin/env python3
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from .extract import extract
from .llm.claude import ClaudeAdapter
from .segment import segment

SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
_DEFAULT_SEGMENTED = Path("segmented")


def ingest_main() -> None:
    """
    Usage:
        ingest raw/resumes/resume.pdf
        ingest raw/resumes/*.pdf
        ingest raw/resumes/          # process entire directory
    """
    args = sys.argv[1:]
    if not args:
        print(ingest_main.__doc__)
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


def segment_main() -> None:
    """
    Usage:
        segment parsed/                   # process all parsed JSON files
        segment parsed/abc123.json        # single file
        segment parsed/ --force           # re-segment even if output exists
        segment parsed/ --segmented-dir segmented/
    """
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(segment_main.__doc__)
        sys.exit(0 if args else 1)

    force = "--force" in args
    args = [a for a in args if a != "--force"]

    segmented_dir = _DEFAULT_SEGMENTED
    if "--segmented-dir" in args:
        idx = args.index("--segmented-dir")
        segmented_dir = Path(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    targets: list[Path] = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            targets.extend(sorted(p.glob("*.json")))
        elif p.is_file() and p.suffix == ".json":
            targets.append(p)
        else:
            print(f"[skip] not found or not a JSON file: {arg}")

    if not targets:
        print("No parsed JSON files found.")
        sys.exit(1)

    adapter = ClaudeAdapter()
    print(f"Segmenting {len(targets)} file(s) → {segmented_dir}/\n")

    ok = skipped = failed = 0
    for path in targets:
        try:
            result = segment(path, segmented_dir, adapter, force=force)
            if result["status"] == "skipped":
                skipped += 1
            else:
                ok += 1
        except Exception as e:
            print(f"[error] {path.name}: {e}")
            failed += 1

    print(f"\nFinished: {ok} segmented, {skipped} skipped, {failed} failed")
