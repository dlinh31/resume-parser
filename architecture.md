# Resume Parser — System Architecture

## Purpose of this document

This document is a reference architecture for the ingestion, parsing, storage, and indexing portion of the resume tailoring project. It is the companion to `resume-parser-design.md` — that document describes *what* the system does and *why*; this document describes *how it is built*. It is intended to be attached to another conversation as context for producing a drawable architecture diagram.

Scope matches the design doc: file ingestion, parsing pipeline, storage schema, and indexing. Pattern extraction, generation, and the user-facing application are out of scope.

---

## Summary of decisions

Each of these is expanded in its own section below. Collected here so the shape of the system is visible at a glance.

- **Orchestration:** plain Python scripts, run as batch jobs. No workflow engine.
- **Raw file storage:** local filesystem for now, addressed via URI so the schema is ready for S3/R2/GCS later. PDFs are never stored in Postgres as bytes.
- **Text extraction — PDFs:** layout-aware Python extractor (e.g. `pdfplumber` or `pymupdf`) preserving positional metadata.
- **Text extraction — images and scanned PDFs:** cloud OCR (AWS Textract or Google Document AI), not Tesseract. Chosen for layout handling on multi-column resumes.
- **Section segmentation and field extraction:** LLM with structured output (Claude or GPT, provider left open). High-level decision only; specific model can change without schema impact.
- **Embeddings:** OpenAI `text-embedding-3-small` as the default. 1536-dimensional vectors stored in pgvector. Model choice is swappable.
- **Database:** PostgreSQL with JSONB columns for variable fields and the pgvector extension for embeddings. One database, three jobs.
- **Provenance:** every parsed record carries source pointer, parser version, confidence score, and extraction timestamp — not just OCR'd records.
- **Processing mode:** batch. No streaming ingestion.
- **Human-in-the-loop review:** deferred. Not part of the current architecture.

---

## System components

The system is a hybrid of a data-flow pipeline and a small set of stateful components. The pipeline runs through six processing stages; the stateful components are the raw file store, the Postgres database, and the external services called by the pipeline.

### Stateful components

1. **Raw file store** — holds the original PDFs and images. Local filesystem initially. Files are immutable once written. Each file is addressed by a URI (`file:///...` now, `s3://...` later).
2. **PostgreSQL database** — single source of truth for structured data, variable fields, and vector embeddings. Uses JSONB columns and the pgvector extension.
3. **Parser version registry** — a table inside Postgres recording every version of the parser that has ever run against the corpus. Every extracted record foreign-keys to a row here, so re-parses are traceable.

### External services called by the pipeline

4. **Cloud OCR service** — AWS Textract or Google Document AI. Called only for image inputs and for PDFs detected as scans (no embedded text).
5. **LLM provider** — Claude or GPT. Called in the segmentation and extraction stages. Structured output / JSON mode required.
6. **Embedding model provider** — OpenAI `text-embedding-3-small` by default. Called in the final indexing stage to embed bullets and experience descriptions.

### Processing components (the pipeline)

The six stages below are Python functions or modules, run sequentially inside a batch script. They read from and write to the stateful components above.

---

## Data flow

The pipeline is a linear funnel. A file enters at stage 1 and produces records in Postgres by stage 6. Each stage reads the output of the previous one and writes its own output before the next stage begins. Failures are isolated to a single stage and a single file — one bad resume does not halt the batch.

### Stage 1 — File classification and preprocessing

**Input:** a file URI from the raw file store.

**Processing:**
- Detect file type (PDF vs image).
- For PDFs, detect whether the PDF has embedded text or is a scan. This is the key branching decision — text-embedded PDFs go through the direct extraction path; scans and images go through OCR.
- For images, run basic preprocessing (deskew, denoise) to improve OCR accuracy.

**Output:** the file URI plus a classification record indicating which extraction path to take.

**Rationale:** OCR'ing a text-embedded PDF throws away clean text and introduces noise. This stage exists entirely to prevent that silent quality loss.

### Stage 2 — Text and layout extraction

**Input:** file URI plus classification from stage 1.

**Processing — text-PDF path:** use a layout-aware extractor (`pdfplumber`, `pymupdf`) that preserves positional metadata. The output is not a plain string; it is text plus coordinates so that multi-column layouts, sidebars, and icons can be handled correctly downstream.

**Processing — OCR path:** send the file to AWS Textract or Google Document AI. These services return text with positional and structural metadata, and they handle multi-column layouts natively — which Tesseract does not. OCR confidence scores are captured per-token and carried forward.

**Output:** a raw-text artifact with positional metadata, stored in Postgres alongside a pointer to the source file.

**Rationale for cloud OCR over Tesseract:** Tesseract runs around 85–95% character accuracy on resume scans because resumes have non-standard layouts, sidebars, and design elements. Cloud services are layout-aware and significantly better on exactly these cases. Since only a minority of inputs are images, the per-page cost (~$1.50/1000 pages) is negligible in aggregate and buys meaningful quality on the hard cases.

### Stage 3 — Section segmentation

**Input:** the extracted text with layout metadata.

**Processing:** send the text to an LLM with a structured output schema that asks it to segment the resume into sections (Experience, Education, Projects, Skills, Summary, etc.). The LLM returns a list of sections with their boundaries.

**Output:** the same text, now partitioned into labeled sections.

**Rationale for LLM over rules or a classifier:** section headers vary widely across resumes ("Work Experience," "Professional History," "Career") and some resumes omit headers entirely. Rule-based segmentation requires constant maintenance; a dedicated classifier requires training data. An LLM with structured output handles the long tail today without either investment.

### Stage 4 — Field extraction within sections

**Input:** labeled sections from stage 3.

**Processing:** for each section, call the LLM with a section-specific schema. The schema enforces the hierarchy laid out in the design doc:
- **Experience:** company, title, dates, location, and bullets — each bullet as its own atomic record.
- **Education:** institution, degree, field, dates.
- **Projects:** name, description, technologies, links, bullets.
- **Skills:** flat list.

**Output:** structured records for each entity in each section, ready for normalization.

**Rationale:** bullets are the smallest meaningful unit of analysis in this corpus. Concatenating them at this stage would discard information that all downstream layers (pattern extraction, similarity search, analytics) need. The schema enforces atomicity at the earliest point possible.

### Stage 5 — Normalization and enrichment

**Input:** structured records from stage 4.

**Processing:** canonicalize values while preserving the raw form:
- Dates to ISO format.
- Company names mapped to canonical entries ("Google LLC" → "Google").
- Skills mapped to canonical skills ("ReactJS" / "React.js" / "React" → one entry).
- Locations to a consistent format.

Both the raw extracted value and the canonical form are stored. The raw is kept because canonicalization can be wrong, and the raw text may carry signal the canonical form discards.

**Output:** normalized records, still atomic, with both raw and canonical values.

### Stage 6 — Validation, provenance, and indexing

**Input:** normalized records.

**Processing:**
- Attach provenance to every record: source file URI, page/position where available, parser version, confidence score, extraction timestamp.
- Compute embeddings for every bullet and every experience description using OpenAI `text-embedding-3-small`. Store the 1536-dimensional vectors in pgvector columns alongside the structured records.
- Write everything to Postgres in a single transaction per resume.

**Output:** a fully parsed resume, queryable by structured fields, JSONB fields, and vector similarity.

**Rationale for confidence on every record, not just OCR:** the biggest source of error in the pipeline is not OCR, it is LLM-based segmentation and extraction. Sections get misclassified, bullets get truncated, dates get simplified, company names occasionally get hallucinated. A universal confidence field — sourced from OCR scores on the image path and from LLM self-consistency or returned scores on the text path — is what makes the corpus re-parseable later. Confidence tied only to OCR would leave most of the corpus with no re-parse signal.

---

## Technology choices and justification

### Orchestration: plain Python scripts

For a curated corpus in the low thousands, processed in batch, and re-parsed occasionally as the pipeline improves, a Python script with clear stage boundaries is right-sized. A workflow engine (Prefect, Dagster, Airflow) adds operational overhead that would not pay for itself at this scale. The design leaves room to graduate later: each stage is a pure function, so moving to an orchestrator is a wrapper change, not a rewrite.

### Raw file storage: local filesystem, URI-addressed

Three options were considered:
- **Local filesystem** — chosen for development simplicity.
- **Object storage (S3, R2, GCS)** — the long-term correct answer; low cost, durable, separates binary blobs from the query database.
- **Postgres `bytea`** — rejected. Storing PDF bytes inside the database bloats it, complicates backups, and Postgres is not built for serving binary blobs.

The decision that matters: the schema stores a URI string, not the bytes and not a path. Starting with `file:///path/to/pdf` and moving later to `s3://bucket/key` is a single-character change at the storage layer and zero schema migration.

### Text extraction for PDFs: layout-aware Python extractor

`pdfplumber` and `pymupdf` both preserve positional metadata, which is required for handling multi-column resumes, sidebars, and design-heavy layouts. A naive string extraction (e.g. `PyPDF2.extract_text`) interleaves columns and loses the spatial information needed by stage 3.

### OCR for images and scanned PDFs: cloud service (Textract or Document AI)

Tesseract runs ~95–99% character accuracy on clean, simple documents but closer to 85–95% on resumes because of their layout complexity. More importantly, Tesseract is not layout-aware — it returns text in reading-order guesses that fail on multi-column designs. Textract and Document AI are layout-aware by design, handle forms and tables, and cost around $1.50 per 1000 pages. Since images are the minority input in this corpus, the aggregate cost is small and the quality difference is largest on exactly the cases OCR is used for.

### Segmentation and extraction: LLM with structured output

Resumes have high variance in structure. Rule-based approaches require ongoing maintenance; a trained classifier requires a labeled dataset that does not exist yet. An LLM with a JSON schema and strict output validation handles the long tail today. The specific provider (Claude, GPT) is interchangeable — they are called behind a thin adapter, so switching is a config change.

### Embeddings: OpenAI `text-embedding-3-small`

An embedding model converts text to a dense vector (1536 numbers in this case). Semantically similar text produces vectors that are close in this space, which is what enables "find bullets similar to this one" without keyword matching.

`text-embedding-3-small` is the sensible default:
- **Cheap:** ~$0.02 per million tokens.
- **Good quality:** strong on retrieval benchmarks for its price.
- **Dimensions:** 1536, fits comfortably in pgvector.

Alternatives considered:
- `text-embedding-3-large` (3072-dim, ~6x cost) — modest quality gain, overkill at this scale.
- Voyage `voyage-3` — competitive quality, similar pricing. Worth revisiting if retrieval quality becomes a bottleneck.

Model choice does not affect the schema beyond the dimension count of the vector column, so swapping later is cheap.

### Database: PostgreSQL with JSONB and pgvector

One database doing three jobs:

- **Relational core** handles the resume hierarchy (resume → experiences → bullets, resume → education entries) with foreign keys and joins. This is what relational databases are built for, and it makes cross-corpus analytical SQL straightforward.
- **JSONB columns** hold the variable fields that do not fit cleanly into fixed columns — direct-report counts on some experiences, GitHub links on some projects, security clearances on some roles. JSONB is indexable in Postgres, so flexibility does not cost query performance.
- **pgvector** stores bullet and experience embeddings in the same database as the structured data. Semantic similarity lives in the same SQL dialect and the same transaction as everything else.

Alternatives rejected:
- **Document database (MongoDB)** — resume-shaped JSON is tempting, but cross-corpus analytical queries and joins against canonicalized entities (skills, companies) become painful. Also forces a separate vector store.
- **Pure relational without JSONB** — forces either dropping variable fields or sprawling nullable columns and side tables.
- **Dedicated vector store (Pinecone, Weaviate) as primary** — good as a secondary index once scale demands it, not as a source of truth. pgvector is sufficient for tens of millions of vectors.
- **Graph database (Neo4j)** — overkill for parsing and storage. Possibly interesting later for career-path modeling, but not foundational.

One database also means one backup story, one connection pool, one set of migrations, and transactional consistency across structured and vector data — all of which matter more at this stage than theoretical scaling headroom.

---

## Provenance and re-parseability

The parser will improve over time, and the corpus will be valuable for years. These two facts together mean re-parseability is a first-class requirement, not an afterthought.

Concretely:
- Raw source files are stored permanently and never modified.
- Raw extracted text from stage 2 is stored alongside the structured parse, so stages 3–6 can be re-run without re-extracting.
- Every parsed record references its source file URI and the parser version row that produced it.
- Confidence scores are stored on every record — OCR confidence on the image path, LLM-reported or self-consistency confidence on the text path.
- Low-confidence records can be identified with a single SQL query and re-parsed selectively when the pipeline improves.

The parser version registry is important here: it is the mechanism that lets "everything parsed by version 3 or earlier, where confidence < 0.7" be a trivial query.

---

## Drawing the diagram

The diagram being produced from this doc is a **hybrid view** — it combines a pipeline / data-flow diagram with a component diagram. This is the right view for a system at this stage because it answers both *how processing flows* and *what the pieces are* in a single picture.

The structure of the diagram should be:

- **A horizontal pipeline across the middle** showing the six stages as a funnel, with arrows indicating data flow between them.
- **Stateful components drawn outside the pipeline** — the raw file store on the left (as the entry point), Postgres on the right (as the terminus), with arrows showing which stages read from and write to them.
- **External services drawn above or below the pipeline**, with arrows showing which stages call them. Cloud OCR connects to stage 2 only on the image/scan branch. The LLM provider connects to stages 3 and 4. The embedding provider connects to stage 6.
- **A visible branch at stage 1** showing the split between the text-PDF path and the OCR path, which re-converges at stage 3.
- **Annotations on each stage** naming the output artifact (e.g. stage 2 outputs "raw text + layout metadata", stage 4 outputs "atomic structured records").

Color / grouping conventions that help readability:
- One color for processing stages (the pipeline itself).
- A second color for stateful components (file store, database, version registry).
- A third color for external services (OCR, LLM, embeddings).
- Distinct arrow styles for data flow vs. API calls — data flow between pipeline stages is a solid arrow; calls to external services are a different style (e.g. dashed) to visually separate "this is where data moves" from "this is where a service is invoked".

Things the diagram must show, non-negotiable:
- The branching at stage 1 (text PDF vs scan/image).
- Provenance writing on every stage output, not just at the end.
- Raw text being stored after stage 2, independently of the structured parse.
- The three jobs of Postgres (relational, JSONB, vector) visible as distinct concerns even though it is one database.

Things that are optional but useful:
- A small legend explaining the color and arrow conventions.
- A note on the diagram indicating that stages are Python functions run sequentially in a batch script, so readers do not expect a workflow engine.

---

## Open questions deferred to later

These are acknowledged so the diagram does not try to answer them:

- Human-in-the-loop review for low-confidence parses. Not part of the current architecture; will be added as a separate component when introduced.
- Specific LLM provider for stages 3 and 4. Interchangeable; chosen behind an adapter.
- Migration from local filesystem to object storage. URI-addressed design makes this a config change.
- Graduation from a plain Python script to a workflow engine. Stage boundaries are clean enough that this is a wrapping change, not a rewrite.