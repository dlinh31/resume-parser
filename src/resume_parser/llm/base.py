from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dc_field
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


# ── Stage 4 extraction dataclasses ──────────────────────────────────────────

@dataclass
class ContactFields:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


@dataclass
class ExperienceFields:
    company: str = ""
    title: str = ""
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    bullets: list[str] = dc_field(default_factory=list)


@dataclass
class EducationFields:
    institution: str = ""
    degree: str | None = None
    field: str | None = None
    gpa: str | None = None
    graduation_date: str | None = None
    honors: list[str] = dc_field(default_factory=list)
    courses: list[str] = dc_field(default_factory=list)


@dataclass
class ProjectFields:
    name: str = ""
    technologies: list[str] = dc_field(default_factory=list)
    links: list[str] = dc_field(default_factory=list)
    bullets: list[str] = dc_field(default_factory=list)


@dataclass
class SkillGroup:
    category: str | None = None
    items: list[str] = dc_field(default_factory=list)


@dataclass
class AwardFields:
    name: str = ""
    issuer: str | None = None
    date: str | None = None


@dataclass
class OtherSectionFields:
    section_type: str = ""
    raw_header: str = ""
    text: str = ""


@dataclass
class ExtractionResult:
    contact: ContactFields | None
    experiences: list[ExperienceFields]
    education: list[EducationFields]
    projects: list[ProjectFields]
    skill_groups: list[SkillGroup]
    awards: list[AwardFields]
    other_sections: list[OtherSectionFields]
    model: str


# ── Adapter interface ────────────────────────────────────────────────────────

class LLMAdapter(ABC):
    @abstractmethod
    def segment_resume(self, text: str) -> SegmentResult:
        """Segment resume text into typed, confidence-scored sections."""
        ...

    @abstractmethod
    def extract(self, segmented: SegmentResult) -> ExtractionResult:
        """Extract structured fields from all sections of a segmented resume."""
        ...
