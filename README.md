# resume-parser

A pipeline that ingests resume files (PDF, image), parses and structures them with LLMs, and stores results in PostgreSQL. Exposed as an async HTTP API.

## Stack

- **Extraction:** pdfplumber (text PDFs), Google Document AI (scanned PDFs + images)
- **LLM:** Claude via Anthropic SDK (`claude-haiku-4-5-20251001` by default)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536-dim, stored with pgvector)
- **Database:** PostgreSQL + pgvector, via SQLAlchemy ORM
- **Migrations:** Alembic
- **API:** FastAPI, async job pattern

## Project structure

```
src/resume_parser/
  api/
    app.py          # FastAPI app + lifespan
    deps.py         # dependency injection
    routes/
      resumes.py    # POST /resumes, GET /resumes/{file_id}
      jobs.py       # GET /jobs/{job_id}
    schemas.py      # Pydantic response models
  db/
    models.py       # SQLAlchemy ORM models
    session.py      # engine + session factory
  pipeline/
    classify.py     # stage 1: detect pdf_text / pdf_scanned / image
    extract.py      # stage 2: extract text + layout
    segment.py      # stage 3: LLM section segmentation
    field_extract.py# stage 4: LLM field extraction
    normalize.py    # stage 5: date/company/skill canonicalization
    index.py        # stage 6: embed bullets, write to PostgreSQL
    run.py          # end-to-end orchestrator
  llm/
    base.py         # LLMAdapter ABC + dataclasses
    claude.py       # ClaudeAdapter implementation
  jobs.py           # in-memory async job store
  main.py           # uvicorn entry point
alembic/            # database migrations
```

## Setup

**1. Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

**2. Configure environment**

```bash
cp .env.example .env
# fill in values
```

Required variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN, e.g. `postgresql://user:pass@localhost/resume_parser` |
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | OpenAI API key (embeddings) |
| `DOCAI_PROJECT_ID` | Google Cloud project ID |
| `DOCAI_PROCESSOR_ID` | Document AI processor ID |
| `DOCAI_LOCATION` | Processor location (default: `us`) |

**3. Run database migrations**

Fresh database:
```bash
alembic upgrade head
```

Existing database (stamp current state):
```bash
.venv/bin/alembic stamp 001
```

## Running

```bash
source .venv/bin/activate
serve
```

Or without activating: `.venv/bin/serve`

Server starts on `http://0.0.0.0:8000`.

## API

### `POST /resumes`

Upload a resume for async processing. Returns a job ID immediately.

```bash
curl -X POST http://localhost:8000/resumes \
  -F "file=@resume.pdf"
```

```json
{"job_id": "abc-123", "file_id": "a1b2c3d4e5f6"}
```

If the file was already processed (same content hash), returns `200` with `"status": "already_indexed"`.

### `GET /jobs/{job_id}`

Poll job status.

```json
{
  "job_id": "abc-123",
  "status": "done",
  "file_id": "a1b2c3d4e5f6",
  "created_at": "2026-05-07T15:00:00+00:00",
  "finished_at": "2026-05-07T15:00:45+00:00",
  "error": null
}
```

Status values: `pending` → `processing` → `done` | `failed`

### `GET /resumes/{file_id}`

Retrieve a parsed resume with all structured fields.

```json
{
  "file_id": "a1b2c3d4e5f6",
  "contact_name": "Jane Smith",
  "experiences": [...],
  "education": [...],
  "projects": [...],
  "skills": [...]
}
```

## Pipeline stages

| Stage | File | Description |
|---|---|---|
| 1 | `classify.py` | Detect file type (text PDF, scanned PDF, image) |
| 2 | `extract.py` | Extract text and layout |
| 3 | `segment.py` | LLM call to identify resume sections |
| 4 | `field_extract.py` | LLM call to extract structured fields |
| 5 | `normalize.py` | Canonicalize dates, companies, skills, locations |
| 6 | `index.py` | Embed bullets with OpenAI, write all records to PostgreSQL |
