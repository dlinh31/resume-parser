# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Stages 1 and 2 of the pipeline are **implemented and working**. All 31 test resumes parse successfully via pdfplumber. Stages 3–6 are not yet implemented.

## Purpose

A batch pipeline that ingests resume files (PDF, image), parses and structures them, and stores results in PostgreSQL for downstream resume-tailoring use. Scope is ingestion only — no generation or user-facing app.

## Stack

- **Language:** Python 3.10+
- **PDF extraction:** `pdfplumber` (text PDFs), Google Document AI (scanned PDFs and images)
- **OCR:** Google Document AI (not Tesseract)
- **LLM:** Claude or GPT behind an adapter interface (structured output / JSON mode) — not yet wired
- **Embeddings:** OpenAI `text-embedding-3-small` (1536-dim) — not yet wired
- **Database:** PostgreSQL with `pgvector` and JSONB columns — not yet wired
- **Orchestration:** Plain Python scripts as batch jobs (no workflow engine)

## Project Structure

```
src/
  resume_parser/
    __init__.py
    classify.py   # stage 1: detect pdf_text / pdf_scanned / image
    extract.py    # stage 2: extract text + layout, write to data/parsed/
    cli.py        # `ingest` CLI entry point
data/raw/
  resumes/        # original resume files (31 PDFs)
data/parsed/           # stage 2 JSON output, one file per resume (keyed by SHA-256 prefix)
pyproject.toml
```

## Running

```bash
source .venv/bin/activate
ingest data/raw/resumes/          # entire directory
ingest data/raw/resumes/foo.pdf   # single file
ingest data/raw/resumes/*.pdf     # glob
```

Or without activating: `.venv/bin/ingest data/raw/resumes/`

## Pipeline Stages

1. **File Classification** (`classify.py`) — detects `pdf_text`, `pdf_scanned`, or `image` ✅
2. **Text & Layout Extraction** (`extract.py`) — pdfplumber for text PDFs, Document AI for scanned/images; persists JSON to `data/parsed/` ✅
3. **Section Segmentation** — LLM call with structured output to identify resume sections
4. **Field Extraction** — LLM call to extract atomic fields per section; bullets stored separately
5. **Normalization & Enrichment** — canonicalize dates, companies, skills, locations
6. **Validation, Provenance & Indexing** — provenance metadata, embeddings, write to DB

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
