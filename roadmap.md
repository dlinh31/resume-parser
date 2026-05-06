# Resume Parser — Roadmap

## Project Goal

A batch pipeline that ingests resume files (PDF, image), parses and structures them, and stores results in PostgreSQL for downstream resume-tailoring use. Scope: ingestion only — no generation, no user-facing app.

---

## Current State (as of 2026-05-06)

**Stages 1–6 are fully implemented and verified.** All 31 test resumes parse successfully end-to-end. Normalized records are indexed into a local PostgreSQL database with pgvector embeddings on every bullet.

### What exists

```
src/resume_parser/
  __init__.py
  classify.py        ✅ stage 1
  extract.py         ✅ stage 2
  segment.py         ✅ stage 3 orchestration
  field_extract.py   ✅ stage 4 field extraction
  normalize.py       ✅ stage 5 normalization
  index.py           ✅ stage 6 DB indexer
  cli.py             ✅ ingest + segment + extract + normalize + index CLI entry points
  data/
    skills_map.json  ✅ raw → canonical skill aliases (manually maintained)
  llm/
    __init__.py
    base.py          ✅ LLMAdapter ABC, SectionType enum, SectionSegment/SegmentResult dataclasses
    claude.py        ✅ ClaudeAdapter (Haiku, tool-use structured output, header heuristic)
data/raw/resumes/         31 real PDF resumes (test corpus)
data/parsed/              31 JSON output files (SHA-256 prefix as filename)
data/segmented/           stage 3 output (31 JSON files)
data/extracted/           stage 4 output (31 JSON files)
data/normalized/          stage 5 output (31 JSON files)
pyproject.toml       package + `ingest` + `segment` + `extract` + `normalize` + `index` console scripts
.venv/               Python 3.13 virtualenv
```

### Stage 2 output format (per file in `data/parsed/`)

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
- Output written to `data/parsed/<file_id>.json`.
- Env vars required for Document AI path: `DOCAI_PROJECT_ID`, `DOCAI_PROCESSOR_ID`, `DOCAI_LOCATION` (default: `us`).

---

### Stage 3 — Section Segmentation ✅ Done
**Files:** `src/resume_parser/segment.py`, `src/resume_parser/llm/base.py`, `src/resume_parser/llm/claude.py`

**What it does:** Assembles full resume text from `data/parsed/` pages, calls the LLM via a provider adapter, and writes labeled sections to `data/segmented/`.

**Input:** `data/parsed/<file_id>.json` (stage 2 output)

**Output:** `data/segmented/<file_id>.json`

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
- Full section text stored in `data/segmented/` (not offsets) — stage 4 is self-contained.
- Idempotent: skips files already in `data/segmented/` unless `--force` is passed.

**Env vars needed:** `ANTHROPIC_API_KEY` (+ optional `LLM_MODEL`)

---

### Stage 4 — Field Extraction ✅ Done
**Files:** `src/resume_parser/field_extract.py`, `src/resume_parser/llm/base.py`, `src/resume_parser/llm/claude.py`

**What it does:** One LLM call per resume extracts all structured fields simultaneously. Sections are passed as labeled blocks; Claude returns a compound JSON object via tool use.

**Input:** `data/segmented/<file_id>.json`

**Output:** `data/extracted/<file_id>.json`

```json
{
  "file_id": "...",
  "source_uri": "file:///...",
  "extracted_at": "<ISO 8601 UTC>",
  "model": "claude-haiku-4-5-20251001",
  "prompt_version": 1,
  "contact": {"name", "email", "phone", "linkedin", "github", "website"},
  "experiences": [{"company", "title", "location", "start_date", "end_date", "is_current", "bullets": ["..."]}],
  "education": [{"institution", "degree", "field", "gpa", "graduation_date", "honors": [], "courses": []}],
  "projects": [{"name", "technologies": [], "links": [], "bullets": ["..."]}],
  "skill_groups": [{"category", "items": []}],
  "awards": [{"name", "issuer", "date"}],
  "other_sections": [{"section_type", "raw_header", "text"}]
}
```

**Key decisions made:**
- One LLM call per resume (31 calls total for corpus, not ~155)
- Education: one row per degree — BS + BA from same institution → two education rows
- Unhandled section types (certifications, volunteer, interests, references, etc.) → `other_sections` array, preserved verbatim
- Dates copied as raw strings; normalization deferred to Stage 5
- Bullets are flat strings, not objects
- Structured output via Claude tool use (`extract_resume_fields` tool)

**Env vars needed:** `ANTHROPIC_API_KEY` (+ optional `LLM_MODEL`)

---

### Stage 5 — Normalization & Enrichment ✅ Done
**Files:** `src/resume_parser/normalize.py`, `src/resume_parser/data/skills_map.json`

**What it does:** Canonicalize extracted values while preserving the raw form.
- Dates → ISO 8601 `YYYY-MM` added as `_iso` suffixed fields alongside raw strings
- Company names → legal suffix stripped (`_canonical` field added)
- Skills → flat deduplicated `skills: [{raw, canonical, category}]` list; slash compounds split into two items; year annotations ("C++ (6 years)") stripped; subcategory parentheticals ("SQL (PostgreSQL, MySQL)") → parent only
- Locations → `(Remote)` / `, Remote` stripped into `is_remote: bool`; spelled-out US states abbreviated

**Input:** `data/extracted/<file_id>.json`

**Output:** `data/normalized/<file_id>.json` — structurally identical to extracted with canonical fields added

**Key decisions made:**
- Seasonal dates: Spring → 05, Summer → 08, Fall/Autumn → 12
- "Expected May 2026" → `graduation_date_iso: "2026-05"`, `is_expected: true`
- "Present" → `end_date_iso: null` (`is_current` is already the authoritative signal)
- No new dependencies — all date parsing done with stdlib `datetime.strptime`
- `skills_map.json` is bundled data, manually maintained, covers ~30 observed corpus aliases

**Env vars needed:** none

---

### Stage 6 — Validation, Provenance & Indexing ✅ Done
**File:** `src/resume_parser/index.py`

**What it does:**
1. Attaches provenance to every resume record: source URI, normalizer version, normalized timestamp.
2. Computes embeddings for every bullet via OpenAI `text-embedding-3-small` (1536-dim).
3. Writes all records to PostgreSQL in a single transaction per resume; idempotent (skips or force-replaces).

**Env vars needed:** `OPENAI_API_KEY`, `DATABASE_URL`

**PostgreSQL schema (migration: `migrations/001_initial.sql`):**
```
resume        (id, file_id, source_uri, normalizer_version, normalized_at, contact_*)
experience    (id, resume_id, company_raw, company_canonical, title, location_*, is_remote, start/end_date_*, is_current, position)
education     (id, resume_id, institution, degree, field, gpa, graduation_date_*, is_expected, honors JSONB, courses JSONB, position)
project       (id, resume_id, name, technologies JSONB, links JSONB, position)
bullet        (id, experience_id OR project_id [exclusive], text, embedding vector(1536), position)
skill         (id, canonical UNIQUE)
resume_skill  (id, resume_id, skill_id, raw, category)
other_section (id, resume_id, section_type, raw_header, raw_text, position)
```

---

## Infrastructure Still Needed

| Component | Status | Notes |
|---|---|---|
| PostgreSQL + pgvector | ✅ | Postgres.app 16.2 running locally; schema migrated |
| Google Document AI credentials | ⚠️ | Needed for scan/image path; text PDFs work without it |
| OpenAI API key | ✅ | Set in `.env`; used for bullet embeddings in stage 6 |
| LLM API key (Claude or GPT) | ✅ | `ANTHROPIC_API_KEY` set in `.env`; `LLM_MODEL` overrides default Haiku |
| `.env` file | ✅ | Contains `ANTHROPIC_API_KEY`, `DATABASE_URL`, `OPENAI_API_KEY` |

---

## Implementation Order

1. ~~**Stage 3** — section segmentation~~ ✅ Done
2. ~~**Stage 4** — field extraction (section-specific schemas, bullet atomicity)~~ ✅ Done
3. ~~**Stage 5** — normalization (date parser, company/skill canonical maps)~~ ✅ Done
4. ~~**Stage 6** — embeddings + DB write (postgres schema migration, pgvector, provenance)~~ ✅ Done
5. ~~**Infrastructure** — set up Postgres locally, wire `.env`, run full batch end-to-end~~ ✅ Done

---

## Running (current)

```bash
source .venv/bin/activate

# Stage 2: extract text from raw resumes
ingest data/raw/resumes/          # entire directory
ingest data/raw/resumes/foo.pdf   # single file

# Stage 3: segment extracted text into labeled sections
segment data/parsed/              # all files in data/parsed/
segment data/parsed/abc123.json   # single file
segment data/parsed/ --force      # re-segment even if output exists
segment data/parsed/ --segmented-dir data/segmented/   # custom output dir

# Stage 4: extract structured fields from segmented sections
extract data/segmented/              # all files in data/segmented/
extract data/segmented/abc123.json   # single file
extract data/segmented/ --force      # re-extract even if output exists
extract data/segmented/ --extracted-dir data/extracted/   # custom output dir

# Stage 5: normalize dates, companies, skills, locations
normalize data/extracted/              # all files in data/extracted/
normalize data/extracted/abc123.json   # single file
normalize data/extracted/ --force      # re-normalize even if output exists
normalize data/extracted/ --normalized-dir data/normalized/   # custom output dir

# Stage 6: embed bullets and write to PostgreSQL
index data/normalized/              # all files in data/normalized/
index data/normalized/abc123.json   # single file
index data/normalized/ --force      # re-index even if resume already exists
```

Or without activating: `.venv/bin/ingest data/raw/resumes/` / `.venv/bin/segment data/parsed/`

## Design Constraints (non-negotiable)

- **Provenance on every record** — source URI, parser version, confidence, timestamp
- **Re-parseability** — raw text (stage 2) and structured parse stored separately; re-running stages 3–6 must not require re-OCR'ing
- **URI-addressed files** — `file:///` locally, same interface for future S3 migration
- **Low-confidence records queryable** — no silent data loss; bad parses surface, not get discarded
- **Atomic bullets** — each resume bullet is its own DB row from stage 4 onward
