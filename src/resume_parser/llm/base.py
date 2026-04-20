from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class SectionType(str, Enum):
    CONTACT = "contact"
    SUMMARY = "summary"
    OBJECTIVE = "objective"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    AWARDS = "awards"
    PUBLICATIONS = "publications"
    VOLUNTEER = "volunteer"
    LANGUAGES = "languages"
    INTERESTS = "interests"
    REFERENCES = "references"
    OTHER = "other"


@dataclass
class SectionSegment:
    section_type: str       # SectionType value
    raw_header: str         # exact header text from the resume; empty string if contact block with no header
    text: str               # full section text including header
    llm_confidence: float   # 0.0–1.0 self-reported by the LLM
    header_score: float     # 0.0–1.0 rule-based: does raw_header look like a real section header?
    confidence: float       # min(llm_confidence, header_score) — queryable threshold field


@dataclass
class SegmentResult:
    sections: list[SectionSegment]
    model: str
    prompt_version: int


class LLMAdapter(ABC):
    @abstractmethod
    def segment_resume(self, text: str) -> SegmentResult:
        """Segment resume text into typed, confidence-scored sections."""
        ...
