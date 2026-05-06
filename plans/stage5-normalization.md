# Stage 5 — Normalization & Enrichment: Implementation Plan

## Goal

Transform `data/extracted/<file_id>.json` (Stage 4 output) into `data/normalized/<file_id>.json` by adding canonical forms alongside every raw value. No raw data is discarded.

---

## Corpus Research (31 resumes analyzed)

### Date format diversity observed

| Pattern | Examples |
|---|---|
| `MMM. YYYY` | "Jul. 2024", "Mar. 2022", "Feb. 2024" |
| `MMM YYYY` | "Jan 2025", "Aug 2024", "Sep 2022" |
| `MMMM YYYY` | "July 2024", "August 2023", "March 2025" |
| `MMMM. YYYY` | "March. 2025" (malformed — strip period) |
| `MM/YYYY` | "01/2025", "06/2024", "09/2023" |
| Seasonal | "Spring 2027", "Fall 2025" |
| Expected | "Expected May 2026", "Expected Dec. 2025" |
| Relative | "Present" (end_date only) |
| Year only | "2022", "2023", "2024" (awards) |
| Compound | "2022 & 2023", "Summer 2024/Fall 2025" (awards) |

All standard formats parse with stdlib `datetime.strptime` after stripping trailing periods — **no new dependency needed**.

### Skill normalization needs observed

| Category | Examples |
|---|---|
| Case variants | "TypeScript" / "Typescript", "PyTorch" / "Pytorch", "Scikit-learn" / "SciKit" / "Scikit-Learn" |
| Alias variants | "React" / "React.js", "Node.js" / "NodeJS", "Amazon Web Services" / "AWS" |
| Year annotations | "C++ (6 years)", "Python (3 years)", "Pandas (3 years)" |
| Subcategory parents | "SQL (PostgreSQL, MySQL)", "AWS (EC2, S3, RDS, Lambda)" |
| Slash compounds | "C/C++", "UNIX/Linux", "React/Next.js", "JavaScript/TypeScript" |
| API variants | "REST", "REST API", "RESTful", "RESTful API", "RESTful APIs" |
| Spring variants | "Spring Boot" / "Springboot" / "SpringBoot" |

### Location variants observed

- `"City, ST"` — standard: "Tucson, AZ", "Las Vegas, NV"
- `"City, ST (Remote)"` — "Chicago, IL (Remote)", "Villanova, PA (Remote)"
- `"City, ST, Remote"` — "Cary, NC, Remote"
- `"Remote"` — standalone, no city
- `"City, Country"` — "Hanoi, Vietnam", "Ho Chi Minh City, Vietnam"
- `"City, Country (Remote)"` — "Hanoi, Vietnam (Remote)"
- `"City, State"` — "Chicago, Illinois" (spelled out state)

---

## Output Schema: `data/normalized/<file_id>.json`

Structurally identical to the extracted file with these additions:

```json
{
  "file_id": "...",
  "source_uri": "...",
  "normalized_at": "<ISO 8601 UTC>",
  "normalizer_version": 1,

  "contact": { ...unchanged from extracted... },

  "experiences": [
    {
      "company": "University of Arizona Information Technology Services",
      "company_canonical": "University of Arizona Information Technology Services",
      "title": "Mobile Developer",
      "location": "Tucson, AZ",
      "location_canonical": "Tucson, AZ",
      "is_remote": false,
      "start_date": "Oct. 2022",
      "start_date_iso": "2022-10",
      "end_date": "Feb. 2024",
      "end_date_iso": "2024-02",
      "is_current": false,
      "bullets": ["..."]
    }
  ],

  "education": [
    {
      "institution": "...",
      "degree": "...",
      "field": "...",
      "gpa": "...",
      "graduation_date": "Expected May 2026",
      "graduation_date_iso": "2026-05",
      "is_expected": true,
      "honors": [...],
      "courses": [...]
    }
  ],

  "projects": [...unchanged from extracted...],

  "skill_groups": [...unchanged from extracted...],

  "skills": [
    { "raw": "ReactJS", "canonical": "React", "category": "Frameworks & Libraries" },
    { "raw": "PyTorch (3 years)", "canonical": "PyTorch", "category": "Libraries" },
    { "raw": "AWS (EC2, S3, RDS)", "canonical": "AWS", "category": "Cloud" }
  ],

  "awards": [
    {
      "name": "...",
      "issuer": "...",
      "date": "Dec. 2024",
      "date_iso": "2024-12"
    }
  ],

  "other_sections": [...unchanged from extracted...]
}
```

`skill_groups` is preserved verbatim (human-readable). `skills` is a new top-level flat list, deduplicated across all skill_groups, for Stage 6's DB row-per-skill write.

---

## Files to Create

| File | Purpose |
|---|---|
| `src/resume_parser/normalize.py` | Stage 5 orchestration |
| `src/resume_parser/data/skills_map.yaml` | Raw → canonical skill aliases, bundled with package |
| `src/resume_parser/data/__init__.py` | Makes `data/` a package for `importlib.resources` |

**Modified files:**
- `cli.py` — add `normalize_main()`
- `pyproject.toml` — add `normalize` console script

---

## Implementation

### normalize.py

```python
def normalize(
    extracted_path: Path,
    normalized_dir: Path,
    *,
    force: bool = False,
) -> dict:
    # load extracted JSON
    # apply normalization to each entity type
    # write data/normalized/<file_id>.json
    # return {"file_id": ..., "status": "ok"|"skipped"}
```

Internal helpers (all pure functions, no I/O):

- `_parse_date_iso(raw: str | None) -> str | None` — returns `"YYYY-MM"` or `None`
- `_is_expected_date(raw: str) -> bool` — true if "Expected" prefix present
- `_normalize_company(raw: str) -> str` — strip legal suffixes, normalize whitespace
- `_normalize_location(raw: str | None) -> tuple[str | None, bool]` — returns `(canonical, is_remote)`
- `_normalize_skills(skill_groups: list, skills_map: dict) -> list[dict]` — flat deduped `[{raw, canonical, category}]`
- `_load_skills_map() -> dict` — loads `data/skills_map.yaml` once at import time

### Date parsing algorithm (`_parse_date_iso`)

All corpus formats handle cleanly with stdlib:
1. Strip whitespace
2. Strip "Expected" prefix (case-insensitive), set `is_expected = True`
3. Strip trailing periods from month names: `"Jul."` → `"Jul"`
4. Try formats in order: `MM/YYYY`, `%b %Y`, `%B %Y`, `YYYY`
5. If none match → return `None` (logged as unparseable)

No `python-dateutil` needed.

### Company normalization (`_normalize_company`)

Strip trailing legal entity suffixes with regex:
```
\b(LLC|Inc|Corp|Ltd|L\.P\.|Co|LLP|PLC|GmbH)\.?\s*$
```
Title-case normalize only if currently all-caps. Preserve original casing otherwise.

### Location normalization (`_normalize_location`)

1. Check for remote indicators: `(Remote)`, `, Remote`, standalone `"Remote"`
2. Strip remote indicator → `is_remote = True`
3. Normalize state abbreviation if spelled out ("Illinois" → "IL") using a US states dict
4. Return `(cleaned_location_or_None, is_remote)`

### Skills normalization (`_normalize_skills`)

1. Load `skills_map.yaml` — dict of `raw_form: canonical_form`
2. For each item in each skill_group:
   a. Strip year annotations: `"C++ (6 years)"` → `"C++"`
   b. Strip subcategory parentheticals: `"SQL (PostgreSQL, MySQL)"` → `"SQL"`  
      (Decision 3 — see below)
   c. Look up in skills_map → `canonical`. If not found, `canonical = item` (identity)
   d. Emit `{raw: original_item, canonical: canonical, category: group.category}`
3. Deduplicate by `canonical` — keep first occurrence (preserves category)

### skills_map.yaml (seed entries)

Located at `src/resume_parser/data/skills_map.yaml`. Manually maintained. Loaded via `importlib.resources`.

Structure:
```yaml
# key: raw form as it appears in extracted JSON
# value: canonical form

# Case variants
Typescript: TypeScript
Pytorch: PyTorch
Tensorflow: TensorFlow
Scikit-learn: scikit-learn
Scikit-Learn: scikit-learn
SciKit: scikit-learn

# Node/React ecosystem
React.js: React
NodeJS: Node.js
Node.js/Express.js: Node.js  # slash compound → primary only
Angular.js: Angular

# AWS
Amazon Web Services: AWS
"Amazon Web Services (AWS)": AWS

# Spring
Springboot: Spring Boot
SpringBoot: Spring Boot

# REST
REST API: REST
RESTful: REST
RESTful API: REST
RESTful APIs: REST
```

~50–80 entries covers the observed corpus. Extendable without code changes.

---

## Engineering Decisions to Make

### Decision 1 — Seasonal dates: `"Spring 2027"`, `"Fall 2025"`

These appear in graduation_date fields for students.

- **Option A (recommended):** Return `_iso: null`, preserve raw. Honest about ambiguity.  
- **Option B:** Map to approximate month (`Spring` → `"05"`, `Fall` → `"08"`). Enables sorting but is imprecise.

**Question for you:** Is approximate-but-sortable better than null for graduation dates? (Stage 6 may need to sort by graduation year for ranking candidates.)

---

### Decision 2 — Skills with year annotations: `"C++ (6 years)"`

Observed in 3+ resumes. The annotation embeds years-of-experience in the skill string.

- **Option A (recommended):** Strip annotation entirely. `raw: "C++ (6 years)"`, `canonical: "C++"`. Discard years.
- **Option B:** Parse `years_experience` into a separate field: `{raw, canonical, years_experience: 6}`.

**Question for you:** Is years-of-experience per skill worth extracting? It's low-signal (self-reported), but downstream tailoring might find it useful.

---

### Decision 3 — Compound skills with subcategory parentheticals: `"SQL (PostgreSQL, MySQL)"`

Appears frequently: "AWS (EC2, S3, RDS, Lambda)", "SQL (PostgreSQL, MySQL)", "C# (.NET)".

- **Option A (recommended):** Canonical = parent only (`"SQL"`, `"AWS"`, `"C#"`). Parenthetical stripped for canonical, preserved in raw.
- **Option B:** Expand into atomic skills — one row per item inside the parenthetical plus the parent.

**Question for you:** Do you want "PostgreSQL" as a separate queryable skill even when a candidate wrote "SQL (PostgreSQL, MySQL)"? Option B gives richer matching at the cost of invented data (the LLM chose to group them).

---

### Decision 4 — Slash-compound skills: `"C/C++"`, `"UNIX/Linux"`, `"JavaScript/TypeScript"`

- **Option A (recommended):** Treat as a single skill. Handle in `skills_map.yaml` case-by-case (e.g., `"C/C++": "C++"`, `"UNIX/Linux": "Linux"`).
- **Option B:** Split on `/` into separate atomic items for every compound.

**Question for you:** Split or keep compound? Note that `"React/Next.js"` is different from `"JavaScript/TypeScript"` — splitting `"React/Next.js"` loses the relationship, while splitting `"JavaScript/TypeScript"` is accurate. A blanket rule may not be right.

---

### Decision 5 — Company name canonicalization depth

- **Option A (recommended):** Strip legal suffixes only (LLC, Inc., Corp., etc.) with regex. Free, deterministic, safe.
- **Option B:** LLM-assisted: pass company list to Claude, get back canonical names. Handles abbreviations ("UA" → "University of Arizona") but costs tokens and may hallucinate.

**My recommendation:** Option A for now. Option B can be layered in as a separate pass later if needed.

---

### Decision 6 — `"Present"` in end_date

`end_date: "Present"` appears alongside `is_current: true`. Stage 4 already sets `is_current: true` when the job is ongoing.

- **Option A (recommended):** `end_date_iso: null`. `is_current` is already the authoritative signal.  
- **Option B:** `end_date_iso: "<today's ISO date>"`. Makes date arithmetic possible without checking `is_current`.

---

## CLI pattern (matches Stages 3 and 4)

```
normalize data/extracted/                    # all files in data/extracted/
normalize data/extracted/abc123.json         # single file
normalize data/extracted/ --force            # re-normalize even if output exists
normalize data/extracted/ --normalized-dir data/normalized/
```

---

## Stage 5 does NOT need a new dependency

All observed date formats parse cleanly with `datetime.strptime` after minimal preprocessing. `python-dateutil` is not needed.

---

## Verification plan

Run against all 31 extracted resumes. Assert:
- Every `_iso` field is either a valid `"YYYY-MM"` string or `null` — no garbage values
- `skills` list is non-empty for all resumes
- No duplicate `canonical` values in a single resume's `skills` list  
- `is_remote: true` for all known-remote locations (spot-check ~5 resumes)
- `is_expected: true` for all "Expected ..." graduation dates
