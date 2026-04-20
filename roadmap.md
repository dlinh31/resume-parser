# Resume Parser — Roadmap

## Project Goal

A batch pipeline that ingests resume files (PDF, image), parses and structures them, and stores results in PostgreSQL for downstream resume-tailoring use. Scope: ingestion only — no generation, no user-facing app.

---

## Current State (as of 2026-04-20)

**Stages 1–3 are fully implemented and verified.** All 31 test resumes in `raw/resumes/` parse successfully. Output JSON files land in `parsed/`. Stage 3 adapter + segmentation logic is wired and ready to run against `parsed/`.

### What exists

```
src/resume_parser/
  __init__.py
  classify.py        ✅ stage 1
  extract.py         ✅ stage 2
  segment.py         ✅ stage 3 orchestration
  cli.py             ✅ ingest + segment CLI entry points
  llm/
    __init__.py
    base.py          ✅ LLMAdapter ABC, SectionType enum, SectionSegment/SegmentResult dataclasses
    claude.py        ✅ ClaudeAdapter (Haiku, tool-use structured output, header heuristic)
raw/resumes/         31 real PDF resumes (test corpus)
parsed/              31 JSON output files (SHA-256 prefix as filename)
segmented/           stage 3 output directory (empty until `segment` is run)
pyproject.toml       package + `ingest` + `segment` console scripts
.venv/               Python 3.13 virtualenv
```

### Stage 2 output format (per file in `parsed/`)

```json
{
  "file_id": "<sha256[:12]>",
  "source_uri": "file:///abs/path/to/resume.pdf",
  "file_type": "pdf_text | pdf_scanned | image",
  "extractor": "pdfplumber | google-document-ai",
  "extracted_at": "<ISO 8601 UTC>",
  "pages": [
    {
      "page": 1,
      "text": "...",
      "words": [{"text": "...", "x0": ..., "y0": ..., "x1": ..., "y1": ...}]
    }
  ]
}
```

---

## Pipeline Stages

### Stage 1 — File Classification ✅ Done
**File:** `src/resume_parser/classify.py`

Detects one of three types:
- `pdf_text` — PDF with embedded text (pdfplumber path)
- `pdf_scanned` — PDF with no/little embedded text (OCR path)
- `image` — JPEG/PNG/TIFF (OCR path)

Decision criterion: average chars/page ≥ 100 → text PDF.

---

### Stage 2 — Text & Layout Extraction ✅ Done
**File:** `src/resume_parser/extract.py`

- **Text PDFs:** pdfplumber extracts text + word-level bounding boxes per page.
- **Scanned PDFs / images:** Google Document AI returns text + block-level bounding boxes + per-block confidence scores.
- Output written to `parsed/<file_id>.json`.
- Env vars required for Document AI path: `DOCAI_PROJECT_ID`, `DOCAI_PROCESSOR_ID`, `DOCAI_LOCATION` (default: `us`).

---

### Stage 3 — Section Segmentation ✅ Done
**Files:** `src/resume_parser/segment.py`, `src/resume_parser/llm/base.py`, `src/resume_parser/llm/claude.py`

**What it does:** Assembles full resume text from `parsed/` pages, calls the LLM via a provider adapter, and writes labeled sections to `segmented/`.

**Input:** `parsed/<file_id>.json` (stage 2 output)

**Output:** `segmented/<file_id>.json`

```json
{
  "file_id": "<sha256[:12]>",
  "source_uri": "file:///...",
  "segmented_at": "<ISO 8601 UTC>",
  "model": "claude-haiku-4-5-20251001",
  "prompt_version": 1,
  "sections": [
    {
      "section_type": "contact | summary | objective | experience | education | skills | projects | certifications | awards | publications | volunteer | languages | interests | references | other",
      "raw_header": "exact header text from resume (empty string for contact block)",
      "text": "full section text including header",
      "llm_confidence": 0.95,
      "header_score": 1.0,
      "confidence": 0.95
    }
  ]
}
```

**Confidence design:**
- `llm_confidence` — self-reported by the LLM (0.0–1.0)
- `header_score` — rule-based heuristic: does `raw_header` appear as a standalone line? Is it short (≤6 words)? Title/upper case?
- `confidence = min(llm_confidence, header_score)` — the queryable threshold field

**Key decisions made:**
- LLM adapter interface (`LLMAdapter` ABC in `llm/base.py`) — swap provider by implementing a new concrete class; no other code changes needed.
- Model: `claude-haiku-4-5-20251001` by default; overridable via `LLM_MODEL` env var.
- Structured output via Claude tool use (not raw JSON prompting) — schema-enforced, no parsing needed.
- Full section text stored in `segmented/` (not offsets) — stage 4 is self-contained.
- Idempotent: skips files already in `segmented/` unless `--force` is passed.

**Env vars needed:** `ANTHROPIC_API_KEY` (+ optional `LLM_MODEL`)

---

### Stage 4 — Field Extraction ❌ Not started
**Planned file:** `src/resume_parser/field_extract.py`

**What it does:** For each section, call the LLM with a section-specific JSON schema to extract atomic fields.

**Schema by section:**
- **Experience:** company, title, start\_date, end\_date, location, bullets (each bullet = its own record)
- **Education:** institution, degree, field, start\_date, end\_date
- **Projects:** name, description, technologies\[\], links\[\], bullets\[\]
- **Skills:** flat list of skill strings

**Input:** `segmented/<file_id>.json`

**Output:** `extracted/<file_id>.json` — structured records, one per entity.

**Note:** Bullets are atomic records from the start — concatenating them here would destroy downstream retrieval quality.

---

### Stage 5 — Normalization & Enrichment ❌ Not started
**Planned file:** `src/resume_parser/normalize.py`

**What it does:** Canonicalize extracted values while preserving the raw form.
- Dates → ISO 8601 (`YYYY-MM` or `YYYY-MM-DD`)
- Company names → canonical form ("Google LLC" → "Google")
- Skills → deduplicated canonical names ("ReactJS" / "React.js" → "React")
- Locations → consistent format (city, state/country)

Both raw and canonical forms are stored — raw is kept because canonicalization can be wrong.

**Input:** `extracted/<file_id>.json`

**Output:** normalized records with `{raw: "...", canonical: "..."}` fields where applicable.

---

### Stage 6 — Validation, Provenance & Indexing ❌ Not started
**Planned file:** `src/resume_parser/index.py`

**What it does:**
1. Attach provenance to every record: source URI, page/position, parser version, confidence score, extraction timestamp.
2. Compute embeddings for every bullet and experience description via OpenAI `text-embedding-3-small` (1536-dim).
3. Write all records to PostgreSQL in a single transaction per resume.

**Env vars needed:** `OPENAI_API_KEY`, `DATABASE_URL`

**PostgreSQL schema (planned):**
```
parser_version (id, version_string, created_at)
resume         (id, file_id, source_uri, parser_version_id, ingested_at)
section        (id, resume_id, label, raw_text)
experience     (id, section_id, company_raw, company_canonical, title, start_date, end_date, location)
bullet         (id, experience_id OR project_id, text, embedding vector(1536), confidence)
education      (id, section_id, institution, degree, field, start_date, end_date)
project        (id, section_id, name, description, technologies JSONB, links JSONB)
skill          (id, resume_id, raw, canonical)
```

Low-confidence records must be queryable: `SELECT * FROM bullet WHERE confidence < 0.7`.

---

## Infrastructure Still Needed

| Component | Status | Notes |
|---|---|---|
| PostgreSQL + pgvector | ❌ | Local Docker or managed (Supabase, Neon) |
| Google Document AI credentials | ⚠️ | Needed for scan/image path; text PDFs work without it |
| OpenAI API key | ❌ | For embeddings in stage 6 |
| LLM API key (Claude or GPT) | ⚠️ | `ANTHROPIC_API_KEY` needed for stage 3+; `LLM_MODEL` overrides default Haiku |
| `.env` file | ❌ | `.env.example` exists; copy and fill in keys |

---

## Implementation Order

1. ~~**Stage 3** — section segmentation~~ ✅ Done
2. **Stage 4** — field extraction (section-specific schemas, bullet atomicity)
3. **Stage 5** — normalization (date parser, company/skill canonical maps)
4. **Stage 6** — embeddings + DB write (postgres schema migration, pgvector, provenance)
5. **Infrastructure** — set up Postgres locally, wire `.env`, run full batch end-to-end

Stages 3–4 can be developed and tested against the existing `parsed/` JSON files without any database. Stages 5–6 require database infrastructure.

---

## Running (current)

```bash
source .venv/bin/activate

# Stage 2: extract text from raw resumes
ingest raw/resumes/          # entire directory
ingest raw/resumes/foo.pdf   # single file

# Stage 3: segment extracted text into labeled sections
segment parsed/              # all files in parsed/
segment parsed/abc123.json   # single file
segment parsed/ --force      # re-segment even if output exists
segment parsed/ --segmented-dir segmented/   # custom output dir
```

Or without activating: `.venv/bin/ingest raw/resumes/` / `.venv/bin/segment parsed/`

## Design Constraints (non-negotiable)

- **Provenance on every record** — source URI, parser version, confidence, timestamp
- **Re-parseability** — raw text (stage 2) and structured parse stored separately; re-running stages 3–6 must not require re-OCR'ing
- **URI-addressed files** — `file:///` locally, same interface for future S3 migration
- **Low-confidence records queryable** — no silent data loss; bad parses surface, not get discarded
- **Atomic bullets** — each resume bullet is its own DB row from stage 4 onward
