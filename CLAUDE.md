# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

All 6 pipeline stages are implemented and working. All 31 test resumes parse and index successfully. A FastAPI server (`server.py`) wraps the full pipeline as an async job API.

## Purpose

A batch pipeline that ingests resume files (PDF, image), parses and structures them, and stores results in PostgreSQL for downstream resume-tailoring use. Exposes an HTTP API for single-file upload and async processing.

## Stack

- **Language:** Python 3.10+
- **PDF extraction:** `pdfplumber` (text PDFs), Google Document AI (scanned PDFs and images)
- **OCR:** Google Document AI (not Tesseract)
- **LLM:** Claude via `ClaudeAdapter` (`claude-haiku-4-5-20251001` by default, overridable with `LLM_MODEL`)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536-dim)
- **Database:** PostgreSQL with `pgvector`; raw PDF bytes stored as `BYTEA` on the `resume` table
- **API:** FastAPI with async job pattern (`POST /resumes`, `GET /jobs/{job_id}`, `GET /resumes/{file_id}`)
- **Orchestration:** Plain Python scripts as batch jobs (CLI) or via HTTP API

## Project Structure

```
src/resume_parser/
  classify.py      # stage 1: detect pdf_text / pdf_scanned / image
  extract.py       # stage 2: extract text + layout, write to output_dir
  segment.py       # stage 3: LLM section segmentation
  field_extract.py # stage 4: LLM field extraction
  normalize.py     # stage 5: date/company/skill canonicalization
  index.py         # stage 6: embed bullets, write to PostgreSQL
  pipeline.py      # orchestrates stages 1–6 for a single file
  jobs.py          # in-memory job store (threading.Lock-based)
  server.py        # FastAPI app
  cli.py           # CLI entry points
  llm/
    base.py        # LLMAdapter ABC + dataclasses
    claude.py      # ClaudeAdapter implementation
migrations/
  001_initial.sql  # full schema
  002_add_pdf_bytes.sql
data/raw/resumes/  # original resume files
```

## Running

```bash
source .venv/bin/activate

# CLI batch mode
ingest data/raw/resumes/          # entire directory
ingest data/raw/resumes/foo.pdf   # single file

# API server
serve                             # starts on http://0.0.0.0:8000
```

Or without activating: `.venv/bin/serve`

## Pipeline Stages

1. **File Classification** (`classify.py`) — detects `pdf_text`, `pdf_scanned`, or `image` ✅
2. **Text & Layout Extraction** (`extract.py`) — pdfplumber for text PDFs, Document AI for scanned/images ✅
3. **Section Segmentation** (`segment.py`) — LLM call to identify resume sections ✅
4. **Field Extraction** (`field_extract.py`) — LLM call to extract atomic fields; bullets stored separately ✅
5. **Normalization & Enrichment** (`normalize.py`) — canonicalize dates, companies, skills, locations ✅
6. **Indexing** (`index.py`) — OpenAI embeddings for bullets, write all records to PostgreSQL ✅

Each stage's output is persisted so any stage can be re-run independently.

## Key Design Constraints

- **Provenance on every record:** source URI, parser version, confidence score, extraction timestamp
- **Re-parseability:** raw text (stage 2) and structured parse stored separately; parser version registry tracks which records need re-parsing
- **File addressing:** `file:///` URIs locally, same interface for future S3 migration
- **Low-confidence records** must be queryable for selective re-parsing (no silent data loss)

## Storage Layout

```
data/raw/          # original uploaded files (URI-addressed)
data/parsed/       # stage 2 raw text output per file (SHA-256 prefix as filename)
```

PostgreSQL schema (planned): resume → section → field/bullet with JSONB for variable fields.
