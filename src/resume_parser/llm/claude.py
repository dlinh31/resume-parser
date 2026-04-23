import os
import re

import anthropic

from .base import (
    AwardFields,
    ContactFields,
    EducationFields,
    ExperienceFields,
    ExtractionResult,
    LLMAdapter,
    OtherSectionFields,
    ProjectFields,
    SectionSegment,
    SectionType,
    SegmentResult,
    SkillGroup,
)

_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

_SECTION_TYPES = [t.value for t in SectionType]

# Tool schema forces structured JSON output without prompt-level parsing.
_SEGMENT_TOOL = {
    "name": "output_segments",
    "description": "Output the segmented sections of the resume in document order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_type": {"type": "string", "enum": _SECTION_TYPES},
                        "raw_header": {
                            "type": "string",
                            "description": "Exact header text as it appears in the resume. Empty string if no explicit header (e.g. contact block at top).",
                        },
                        "text": {
                            "type": "string",
                            "description": "Body text only, excluding the header line. Do not repeat the header.",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "How confident you are in this section boundary and type.",
                        },
                    },
                    "required": ["section_type", "raw_header", "text", "confidence"],
                },
            }
        },
        "required": ["sections"],
    },
}

_SYSTEM = """\
You are a resume parser. Segment the given resume text into typed sections.

Rules:
- The opening block (name, contact info) is section_type "contact" even without an explicit header; use raw_header ""
- Use "other" for sections that don't match any known type
- Every word in the resume must belong to exactly one section — no gaps, no overlaps
- Return sections in document order
- confidence: your estimate of how correct this boundary and label are (0.0 = guessing, 1.0 = certain)\
"""


def _header_score(raw_header: str, full_text: str) -> float:
    """
    Rule-based heuristic: how much does raw_header look like a real section header?

    A genuine section header typically:
    - Appears as its own line (or near the start of a line) in the text
    - Is short (1–5 words)
    - Matches common section-name patterns (all-caps, title-case, etc.)

    Returns 1.0 for contact blocks with no header (always trusted).
    """
    if not raw_header:
        return 1.0

    word_count = len(raw_header.split())
    if word_count > 6:
        return 0.5  # suspiciously long for a header

    # Check if raw_header appears as a standalone line in the text
    escaped = re.escape(raw_header.strip())
    standalone = bool(re.search(rf"(?:^|\n)\s*{escaped}\s*(?:\n|$)", full_text))
    if not standalone:
        return 0.6  # header text not found as a clean line boundary

    # Bonus for common formatting patterns
    is_upper = raw_header.isupper()
    is_title = raw_header.istitle()
    if is_upper or is_title:
        return 1.0

    return 0.85  # found as standalone line but mixed case


_KNOWN_SECTION_TYPES = {"contact", "experience", "education", "skills", "projects", "awards"}

_EXTRACT_TOOL = {
    "name": "extract_resume_fields",
    "description": "Extract structured fields from all sections of a resume.",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact": {
                "type": ["object", "null"],
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "email": {"type": ["string", "null"]},
                    "phone": {"type": ["string", "null"]},
                    "linkedin": {"type": ["string", "null"]},
                    "github": {"type": ["string", "null"]},
                    "website": {"type": ["string", "null"]},
                },
            },
            "experiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "location": {"type": ["string", "null"]},
                        "start_date": {"type": ["string", "null"]},
                        "end_date": {"type": ["string", "null"]},
                        "is_current": {"type": "boolean"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["company", "title", "is_current", "bullets"],
                },
            },
            "education": {
                "type": "array",
                "description": "One entry per degree. If the candidate earned a BS and BA from the same institution, return two separate entries sharing the same institution.",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution": {"type": "string"},
                        "degree": {"type": ["string", "null"]},
                        "field": {"type": ["string", "null"]},
                        "gpa": {"type": ["string", "null"]},
                        "graduation_date": {"type": ["string", "null"]},
                        "honors": {"type": "array", "items": {"type": "string"}},
                        "courses": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["institution", "honors", "courses"],
                },
            },
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "technologies": {"type": "array", "items": {"type": "string"}},
                        "links": {"type": "array", "items": {"type": "string"}},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "technologies", "links", "bullets"],
                },
            },
            "skill_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": ["string", "null"],
                            "description": "Category label (e.g. 'Programming Languages'). Null if the resume lists skills without categories.",
                        },
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["category", "items"],
                },
            },
            "awards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "issuer": {"type": ["string", "null"]},
                        "date": {"type": ["string", "null"]},
                    },
                    "required": ["name"],
                },
            },
            "other_sections": {
                "type": "array",
                "description": "Any section not covered above: volunteer, interests, references, languages, certifications, publications, etc.",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_type": {"type": "string"},
                        "raw_header": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["section_type", "raw_header", "text"],
                },
            },
        },
        "required": ["experiences", "education", "projects", "skill_groups", "awards", "other_sections"],
    },
}

_EXTRACT_SYSTEM = """\
You are a resume parser. Extract structured fields from the provided resume sections.

Rules:
- Dates: copy exactly as written (e.g. "Jul. 2024", "May 2024"). Do not normalize.
- Education: one entry per degree. If the candidate has both a BS and BA, return two separate education entries.
- Bullets: copy verbatim as flat strings. Do not sub-structure them.
- Skills: preserve category labels if present; use null category for unstructured skill lists.
- Sections not covered by the main fields (volunteer, interests, certifications, etc.) go in other_sections.\
"""


class ClaudeAdapter(LLMAdapter):
    def __init__(self, model: str = _MODEL) -> None:
        self._client = anthropic.Anthropic()
        self._model = model

    def extract(self, segmented: SegmentResult) -> ExtractionResult:
        blocks = "\n\n".join(
            f"[{s.section_type.upper()}]\n{s.text}" for s in segmented.sections
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=_EXTRACT_SYSTEM,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_resume_fields"},
            messages=[{"role": "user", "content": f"Extract all fields from this resume:\n\n{blocks}"}],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        d = tool_use.input

        contact = None
        if d.get("contact"):
            c = d["contact"]
            contact = ContactFields(
                name=c.get("name"),
                email=c.get("email"),
                phone=c.get("phone"),
                linkedin=c.get("linkedin"),
                github=c.get("github"),
                website=c.get("website"),
            )

        experiences = [
            ExperienceFields(
                company=e["company"],
                title=e["title"],
                location=e.get("location"),
                start_date=e.get("start_date"),
                end_date=e.get("end_date"),
                is_current=e.get("is_current", False),
                bullets=e.get("bullets", []),
            )
            for e in d.get("experiences", [])
        ]

        education = [
            EducationFields(
                institution=e["institution"],
                degree=e.get("degree"),
                field=e.get("field"),
                gpa=e.get("gpa"),
                graduation_date=e.get("graduation_date"),
                honors=e.get("honors", []),
                courses=e.get("courses", []),
            )
            for e in d.get("education", [])
        ]

        projects = [
            ProjectFields(
                name=p["name"],
                technologies=p.get("technologies", []),
                links=p.get("links", []),
                bullets=p.get("bullets", []),
            )
            for p in d.get("projects", [])
        ]

        skill_groups = [
            SkillGroup(category=sg.get("category"), items=sg.get("items", []))
            for sg in d.get("skill_groups", [])
        ]

        awards = [
            AwardFields(name=a["name"], issuer=a.get("issuer"), date=a.get("date"))
            for a in d.get("awards", [])
        ]

        other_sections = [
            OtherSectionFields(
                section_type=o["section_type"],
                raw_header=o["raw_header"],
                text=o["text"],
            )
            for o in d.get("other_sections", [])
        ]

        return ExtractionResult(
            contact=contact,
            experiences=experiences,
            education=education,
            projects=projects,
            skill_groups=skill_groups,
            awards=awards,
            other_sections=other_sections,
            model=self._model,
        )

    def segment_resume(self, text: str) -> SegmentResult:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=_SYSTEM,
            tools=[_SEGMENT_TOOL],
            tool_choice={"type": "tool", "name": "output_segments"},
            messages=[{"role": "user", "content": f"Segment this resume:\n\n{text}"}],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        raw_sections = tool_use.input["sections"]

        sections = []
        for s in raw_sections:
            llm_conf = float(s["confidence"])
            h_score = _header_score(s["raw_header"], text)
            sections.append(
                SectionSegment(
                    section_type=s["section_type"],
                    raw_header=s["raw_header"],
                    text=s["text"],
                    llm_confidence=llm_conf,
                    header_score=h_score,
                    confidence=min(llm_conf, h_score),
                )
            )

        return SegmentResult(sections=sections, model=self._model)
