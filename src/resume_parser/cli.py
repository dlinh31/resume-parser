#!/usr/bin/env python3
import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from .extract import extract
from .field_extract import extract as field_extract
from .llm.claude import ClaudeAdapter
from .normalize import normalize
from .segment import segment

SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
_DEFAULT_SEGMENTED = Path("segmented")
_DEFAULT_EXTRACTED = Path("extracted")
_DEFAULT_NORMALIZED = Path("normalized")


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


def extract_main() -> None:
    """
    Usage:
        extract segmented/                    # process all segmented JSON files
        extract segmented/abc123.json         # single file
        extract segmented/ --force            # re-extract even if output exists
        extract segmented/ --extracted-dir extracted/
    """
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(extract_main.__doc__)
        sys.exit(0 if args else 1)

    force = "--force" in args
    args = [a for a in args if a != "--force"]

    extracted_dir = _DEFAULT_EXTRACTED
    if "--extracted-dir" in args:
        idx = args.index("--extracted-dir")
        extracted_dir = Path(args[idx + 1])
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
        print("No segmented JSON files found.")
        sys.exit(1)

    adapter = ClaudeAdapter()
    print(f"Extracting {len(targets)} file(s) → {extracted_dir}/\n")

    ok = skipped = failed = 0
    for path in targets:
        try:
            result = field_extract(path, extracted_dir, adapter, force=force)
            if result["status"] == "skipped":
                skipped += 1
            else:
                ok += 1
        except Exception as e:
            print(f"[error] {path.name}: {e}")
            failed += 1

    print(f"\nFinished: {ok} extracted, {skipped} skipped, {failed} failed")


def normalize_main() -> None:
    """
    Usage:
        normalize extracted/                    # process all extracted JSON files
        normalize extracted/abc123.json         # single file
        normalize extracted/ --force            # re-normalize even if output exists
        normalize extracted/ --normalized-dir normalized/
    """
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(normalize_main.__doc__)
        sys.exit(0 if args else 1)

    force = "--force" in args
    args = [a for a in args if a != "--force"]

    normalized_dir = _DEFAULT_NORMALIZED
    if "--normalized-dir" in args:
        idx = args.index("--normalized-dir")
        normalized_dir = Path(args[idx + 1])
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
        print("No extracted JSON files found.")
        sys.exit(1)

    print(f"Normalizing {len(targets)} file(s) → {normalized_dir}/\n")

    ok = skipped = failed = 0
    for path in targets:
        try:
            result = normalize(path, normalized_dir, force=force)
            if result["status"] == "skipped":
                skipped += 1
            else:
                ok += 1
        except Exception as e:
            print(f"[error] {path.name}: {e}")
            failed += 1

    print(f"\nFinished: {ok} normalized, {skipped} skipped, {failed} failed")


def index_main() -> None:
    """
    Usage:
        index normalized/                 # process all normalized JSON files
        index normalized/abc123.json      # single file
        index normalized/ --force         # delete and re-insert even if already indexed
    """
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(index_main.__doc__)
        sys.exit(0 if args else 1)

    force = "--force" in args
    args = [a for a in args if a != "--force"]

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
        print("No normalized JSON files found.")
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.")
        sys.exit(1)

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("OPENAI_API_KEY is not set.")
        sys.exit(1)

    import psycopg2
    from openai import OpenAI
    from .index import index as do_index

    conn = psycopg2.connect(database_url)
    openai_client = OpenAI(api_key=openai_api_key)

    print(f"Indexing {len(targets)} file(s)...\n")

    ok = skipped = failed = 0
    for path in targets:
        try:
            result = do_index(path, conn, openai_client, force=force)
            if result["status"] == "skipped":
                skipped += 1
            else:
                ok += 1
        except Exception as e:
            print(f"[error] {path.name}: {e}")
            traceback.print_exc()
            failed += 1

    conn.close()
    print(f"\nFinished: {ok} indexed, {skipped} skipped, {failed} failed")
