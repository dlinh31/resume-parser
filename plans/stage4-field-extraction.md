# Stage 4 — Field Extraction: Implementation Plan

## Goal

For each segmented resume, make **one LLM call** that extracts all structured fields from all sections simultaneously. Output lands in `data/extracted/<file_id>.json`. Bullets are atomic records from the start — each bullet is its own row in the DB and its own item in the JSON array.

**Input:** `data/segmented/<file_id>.json`  
**Output:** `data/extracted/<file_id>.json`

---

## LLM Call Strategy

One call per resume. All segmented sections are passed together in a single prompt. The LLM returns a single compound JSON object covering all section types. Any section type absent from the resume comes back as `null` or an empty array.

**Why one call:**
- Segmented text per resume is small (bounded by stage 3 output)
- Schema is well-defined enough for Claude tool use to handle compound heterogeneous output
- 31 total calls against our corpus vs. ~155 for one-call-per-section

---

## Output Schema (per `data/extracted/<file_id>.json`)

```json
{
  "file_id": "00fedaa7b995",
  "source_uri": "file:///...",
  "extracted_at": "<ISO 8601 UTC>",
  "model": "claude-haiku-4-5-20251001",
  "prompt_version": 1,
  "contact": {
    "name": "Minh Duong",
    "email": "hongminh4402@gmail.com",
    "phone": "+1-(520) 910-8686",
    "linkedin": "linkedin.com/in/mykeduong",
    "github": "github.com/mykeduong",
    "website": "minhduong.me"
  },
  "experiences": [
    {
      "company": "Credit One Bank",
      "title": "Software Engineer, Infrastructure",
      "location": "Las Vegas, NV",
      "start_date": "Jul. 2024",
      "end_date": null,
      "is_current": true,
      "bullets": [
        "Building an infrastructure automation service using React, Go, and PostgreSQL, reducing timelines from 2 weeks to 2 hours.",
        "Creating an event-driven scheduler with Go, AWS Lambda and EventBridge, automating 100+ infrastructure requests monthly."
      ]
    }
  ],
  "education": [
    {
      "institution": "University of Arizona",
      "degree": "BS",
      "field": "Computer Science",
      "gpa": "4.00/4.00",
      "graduation_date": "May 2024",
      "honors": ["Outstanding Senior in Economics", "Academic Year Highest Academic Distinction"],
      "courses": ["Data Structures and Algorithms", "Operating Systems", "Computer Vision"]
    }
  ],
  "projects": [
    {
      "name": "Verdant - SQL Database Management System",
      "technologies": ["C++", "Abseil", "gRPC", "Protobuf"],
      "links": [],
      "bullets": [
        "Built a DBMS using C++, using gRPC for communications from front-end client to back-end storage engine.",
        "Implemented indices for fast retrieval, including B-Tree and Extendible Hashing, improving the query performance by up to 92%."
      ]
    }
  ],
  "skill_groups": [
    {
      "category": "Programming Languages",
      "items": ["Go", "Java", "C", "C++", "Python", "JavaScript", "TypeScript"]
    },
    {
      "category": "Tools/Frameworks",
      "items": ["Kubernetes", "Docker", "React", "Kafka", "Terraform"]
    }
  ],
  "awards": [
    {
      "name": "Outstanding Senior in Economics",
      "issuer": null,
      "date": null
    }
  ]
}
```

---

## Database Schema

### Entity hierarchy

```
resume
  ├── contact                      (1:1)
  ├── section[]                    (1:many — stage 3 raw, kept for provenance)
  │     ├── experience[]           (1:many)
  │     │     └── experience_bullet[]   (1:many — the vector search atoms)
  │     ├── education[]            (1:many)
  │     ├── project[]              (1:many)
  │     │     └── project_bullet[] (1:many — the vector search atoms)
  │     ├── skill_group[]          (1:many — one row per category label)
  │     │     └── skill[]          (1:many — one row per individual skill)
  │     └── award[]                (1:many)
  └── parser_version               (many:1)
```

### Tables

```sql
parser_version (
  id              serial PK,
  version_string  text UNIQUE,
  created_at      timestamptz
)

resume (
  id                serial PK,
  file_id           text UNIQUE,        -- sha256[:12]
  source_uri        text,
  parser_version_id int FK → parser_version,
  ingested_at       timestamptz,
  extracted_at      timestamptz
)

-- Stage 3 raw output, preserved verbatim as provenance anchor
section (
  id            serial PK,
  resume_id     int FK → resume,
  section_type  text,
  raw_header    text,
  raw_text      text,
  confidence    float
)

contact (
  id         serial PK,
  resume_id  int FK → resume,
  name       text,
  email      text,
  phone      text,
  linkedin   text,
  github     text,
  website    text
)

experience (
  id          serial PK,
  section_id  int FK → section,
  resume_id   int FK → resume,   -- shortcut, avoids join through section
  company     text,
  title       text,
  location    text,
  start_date  text,              -- raw string; normalized to date in stage 5
  end_date    text,              -- null when is_current = true
  is_current  boolean
)

experience_bullet (
  id             serial PK,
  experience_id  int FK → experience,
  text           text,
  embedding      vector(1536),   -- populated in stage 6
  confidence     float
)

education (
  id               serial PK,
  section_id       int FK → section,
  resume_id        int FK → resume,
  institution      text,
  degree           text,         -- 'BS' | 'MS' | 'PhD' | 'BA' | ...
  field            text,         -- 'Computer Science'
  gpa              text,         -- raw: '4.00/4.00'; parsed to float in stage 5
  graduation_date  text,         -- raw: 'May 2024'; normalized in stage 5
  honors           text[],
  courses          text[]
)

project (
  id           serial PK,
  section_id   int FK → section,
  resume_id    int FK → resume,
  name         text,
  technologies text[],
  links        text[]
)

project_bullet (
  id          serial PK,
  project_id  int FK → project,
  text        text,
  embedding   vector(1536),      -- populated in stage 6
  confidence  float
)

skill_group (
  id          serial PK,
  section_id  int FK → section,
  resume_id   int FK → resume,
  category    text               -- 'Programming Languages' | null if unstructured
)

skill (
  id             serial PK,
  skill_group_id int FK → skill_group,
  resume_id      int FK → resume,  -- shortcut for flat skill queries
  raw            text,             -- 'ReactJS' as written on resume
  canonical      text              -- 'React' — populated in stage 5
)

award (
  id          serial PK,
  section_id  int FK → section,
  resume_id   int FK → resume,
  name        text,
  issuer      text,
  date        text
)
```

### Why two bullet tables

`experience_bullet` and `project_bullet` are separate rather than a single `bullet` table with nullable FKs because:
- A constraint (`experience_id XOR project_id`) can't be expressed cleanly in SQL
- Queries are simpler: `WHERE experience_id = X` vs. filtering on a discriminator column
- Both tables are structurally identical — no duplication of logic, just two tables

### What each table serves downstream

| Table | Vector search | Structured filter | Tailoring context |
|---|---|---|---|
| `experience_bullet` | primary | — | primary |
| `project_bullet` | primary | — | primary |
| `skill` | — | primary (canonical) | primary (which to surface) |
| `experience` | — | title, dates, company | context for rewriting bullets |
| `education` | — | degree, field, gpa, date | as-is |
| `project` | — | technologies[] | name + tech emphasis |

---

## Implementation Steps

### Step 1 — LLM tool schema (`llm/base.py`)

Extend `llm/base.py` with:
- `ExtractionResult` dataclass that mirrors the output schema above
- Section-specific dataclasses: `ContactFields`, `ExperienceFields`, `EducationFields`, `ProjectFields`, `SkillGroup`, `AwardFields`
- `extract()` abstract method on `LLMAdapter`

### Step 2 — Claude adapter (`llm/claude.py`)

Implement `ClaudeAdapter.extract(segmented: SegmentResult) -> ExtractionResult`:
- Build prompt from all sections in the segmented file
- Define tool schema matching the output JSON structure
- Call Claude with `tool_choice={"type": "tool", "name": "extract_resume_fields"}`
- Parse and return typed `ExtractionResult`

**Prompt construction:** Pass each section's `section_type` + `text` as labeled blocks. The LLM already has clean section boundaries from stage 3 — no need to re-detect headers.

**Model:** `claude-haiku-4-5-20251001` (same as stage 3). Overridable via `LLM_MODEL` env var.

### Step 3 — Orchestration (`field_extract.py`)

Mirror `segment.py` structure:
- `extract(parsed_dir, segmented_dir, extracted_dir, force=False)` function
- Idempotent: skip files already in `data/extracted/` unless `--force`
- Reads from `data/segmented/<file_id>.json`, writes to `data/extracted/<file_id>.json`

### Step 4 — CLI (`cli.py`)

Add `extract_main()` alongside existing `ingest_main()` and `segment_main()`:
```
extract data/segmented/              # all files
extract data/segmented/abc123.json   # single file
extract data/segmented/ --force      # re-extract even if output exists
extract data/segmented/ --extracted-dir data/extracted/   # custom output dir
```

Wire up in `pyproject.toml` as `extract` console script.

### Step 5 — Smoke test

Run against one segmented file, inspect output JSON manually:
- All section types present
- Bullets are flat string arrays (not nested objects)
- Skill groups have category labels where the resume provided them
- `is_current: true` when end_date is absent/present

---

## Key Constraints

- **Bullets are strings, not objects** — no sub-structure extracted from bullet text at this stage. Technology mentions inside bullets are NOT re-extracted here (they're already in `project.technologies` and `skill.items`). Bullet text is stored verbatim.
- **Dates are raw strings** — LLM copies the date as written ("Jul. 2024", "May 2024"). Stage 5 normalizes to ISO 8601.
- **Skills: category is optional** — if the resume has a flat skills list with no category headers, `category` is `null`. The skill_group row still exists to anchor the section_id FK.
- **No confidence per bullet** — bullet confidence defaults to the parent section's `confidence` from stage 3. Individual bullet confidence scoring is a stage 5/6 concern.
- **One experience entry per role** — if a candidate held two titles at the same company, they appear as two separate `experience` rows. The LLM should split them even if the resume groups them under one company header.

---



## File layout after implementation

```
src/resume_parser/
  field_extract.py       -- stage 4 orchestration (new)
  llm/
    base.py              -- add ExtractionResult + extract() ABC method
    claude.py            -- implement extract() on ClaudeAdapter
data/extracted/               -- stage 4 output directory (new)
plans/
  stage4-field-extraction.md   -- this file
```
