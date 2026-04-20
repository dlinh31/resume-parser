import os
import re

import anthropic

from .base import LLMAdapter, SectionSegment, SectionType, SegmentResult

PROMPT_VERSION = 1
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


class ClaudeAdapter(LLMAdapter):
    def __init__(self, model: str = _MODEL) -> None:
        self._client = anthropic.Anthropic()
        self._model = model

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

        return SegmentResult(sections=sections, model=self._model, prompt_version=PROMPT_VERSION)
