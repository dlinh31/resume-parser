# resume-parser

A batch ingestion pipeline that turns resume files (PDF, image) into structured, queryable data. It classifies each file, extracts raw text and layout, segments the resume into labeled sections via LLM, and extracts typed fields (experience, education, projects, skills) — stored in PostgreSQL for downstream resume-tailoring use.

## Stages

1. **Classify** — detect `pdf_text`, `pdf_scanned`, or `image`
2. **Extract** — pull raw text + word positions via pdfplumber (text PDFs) or Google Document AI (scanned/images)
3. **Segment** — LLM call to label resume sections with confidence scores
4. **Field Extract** — LLM call to parse typed fields from each section
5. **Normalize** — canonicalize dates, companies, and skills
6. **Index** — compute embeddings and write to PostgreSQL + pgvector

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
- `OPENAI_API_KEY`, `DATABASE_URL` — for stages 5 and 6

## Usage

Start the server:

```bash
serve
```

Runs on `http://0.0.0.0:8000`.

### Upload a resume

```
POST /resumes
Content-Type: multipart/form-data

file: <resume file>
```

Returns `202` with `{ "job_id": "...", "file_id": "..." }`. Duplicate uploads return `200` with `{ "job_id": null, "file_id": "...", "status": "already_indexed" }`.

### Poll job status

```
GET /jobs/{job_id}
```

Returns job status: `pending`, `processing`, `done`, or `failed`.

### Get resume data

```
GET /resumes/{file_id}
```

Returns the full parsed resume — contact info, experiences, education, projects, and skills.
