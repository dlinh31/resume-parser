# resume-parser

A batch ingestion pipeline that turns resume files (PDF, image) into structured, queryable data. It classifies each file, extracts raw text and layout, segments the resume into labeled sections via LLM, and extracts typed fields (experience, education, projects, skills) from each section — all stored as JSON for downstream resume-tailoring use.

Scope is ingestion only — no generation, no user-facing app.

## Stages

1. **Classify** — detect `pdf_text`, `pdf_scanned`, or `image`
2. **Extract** — pull raw text + word positions via pdfplumber (text PDFs) or Google Document AI (scanned/images)
3. **Segment** — LLM call to label resume sections with confidence scores
4. **Field Extract** — LLM call to parse typed fields from each section
5. **Normalize** — canonicalize dates, companies, and skills *(not yet implemented)*
6. **Index** — compute embeddings and write to PostgreSQL + pgvector *(not yet implemented)*

Each stage persists output to disk so any stage can be re-run independently.

## Install

```bash
pip install -e .
```

## Configuration

Copy `.env.example` to `.env`. Required variables:

- `ANTHROPIC_API_KEY` — for stages 3 and 4
- `LLM_MODEL` — optional Claude model override (default: `claude-haiku-4-5-20251001`)
- `DOCAI_PROJECT_ID`, `DOCAI_PROCESSOR_ID`, `DOCAI_LOCATION` — for scanned PDFs and images only
- `GOOGLE_APPLICATION_CREDENTIALS` — path to GCP service account JSON, for scanned/image path only
- `OPENAI_API_KEY`, `DATABASE_URL` — for stage 6 (not yet implemented)

Text-only PDFs only need `ANTHROPIC_API_KEY`.

## Usage

Stages 1 and 2 run together under `ingest`:

```bash
ingest data/raw/resumes/           # entire directory
ingest data/raw/resumes/foo.pdf    # single file
```

Stage 3 — segment into labeled sections:

```bash
segment data/parsed/               # all files
segment data/parsed/abc123.json    # single file
segment data/parsed/ --force       # re-run even if output exists
segment data/parsed/ --segmented-dir path/to/out/
```

Stage 4 — extract structured fields:

```bash
extract data/segmented/            # all files
extract data/segmented/abc123.json # single file
extract data/segmented/ --force    # re-run even if output exists
extract data/segmented/ --extracted-dir path/to/out/
```

Full pipeline end to end:

```bash
ingest data/raw/resumes/
segment data/parsed/
extract data/segmented/
```

All commands are idempotent — files with existing output are skipped unless `--force` is passed.
