from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    Integer, LargeBinary, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Resume(Base):
    __tablename__ = "resume"

    id = Column(Integer, primary_key=True)
    file_id = Column(Text, nullable=False, unique=True)
    source_uri = Column(Text, nullable=False)
    normalizer_version = Column(Integer, nullable=False, default=1)
    normalized_at = Column(DateTime(timezone=True), nullable=False)
    contact_name = Column(Text)
    contact_email = Column(Text)
    contact_phone = Column(Text)
    contact_linkedin = Column(Text)
    contact_github = Column(Text)
    contact_website = Column(Text)
    pdf_bytes = Column(LargeBinary)

    experiences = relationship(
        "Experience", back_populates="resume",
        cascade="all, delete-orphan", order_by="Experience.position",
    )
    education = relationship(
        "Education", back_populates="resume",
        cascade="all, delete-orphan", order_by="Education.position",
    )
    projects = relationship(
        "Project", back_populates="resume",
        cascade="all, delete-orphan", order_by="Project.position",
    )
    skills = relationship(
        "ResumeSkill", back_populates="resume", cascade="all, delete-orphan",
    )
    other_sections = relationship(
        "OtherSection", back_populates="resume",
        cascade="all, delete-orphan", order_by="OtherSection.position",
    )


class Experience(Base):
    __tablename__ = "experience"

    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resume.id", ondelete="CASCADE"), nullable=False)
    company_raw = Column(Text, nullable=False)
    company_canonical = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    location_raw = Column(Text)
    location_canonical = Column(Text)
    is_remote = Column(Boolean, nullable=False, default=False)
    start_date_raw = Column(Text)
    start_date_iso = Column(Text)
    end_date_raw = Column(Text)
    end_date_iso = Column(Text)
    is_current = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False)

    resume = relationship("Resume", back_populates="experiences")
    bullets = relationship(
        "Bullet", back_populates="experience",
        cascade="all, delete-orphan", order_by="Bullet.position",
        primaryjoin="Bullet.experience_id == Experience.id",
    )


class Education(Base):
    __tablename__ = "education"

    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resume.id", ondelete="CASCADE"), nullable=False)
    institution = Column(Text, nullable=False)
    degree = Column(Text)
    field = Column(Text)
    gpa = Column(Text)
    graduation_date_raw = Column(Text)
    graduation_date_iso = Column(Text)
    is_expected = Column(Boolean, nullable=False, default=False)
    honors = Column(JSONB)
    courses = Column(JSONB)
    position = Column(Integer, nullable=False)

    resume = relationship("Resume", back_populates="education")


class Project(Base):
    __tablename__ = "project"

    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resume.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    technologies = Column(JSONB)
    links = Column(JSONB)
    position = Column(Integer, nullable=False)

    resume = relationship("Resume", back_populates="projects")
    bullets = relationship(
        "Bullet", back_populates="project",
        cascade="all, delete-orphan", order_by="Bullet.position",
        primaryjoin="Bullet.project_id == Project.id",
    )


class Bullet(Base):
    __tablename__ = "bullet"
    __table_args__ = (
        CheckConstraint(
            "(experience_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1",
            name="bullet_one_parent",
        ),
    )

    id = Column(Integer, primary_key=True)
    experience_id = Column(Integer, ForeignKey("experience.id", ondelete="CASCADE"))
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"))
    text = Column(Text, nullable=False)
    embedding = Column(Vector(1536))
    position = Column(Integer, nullable=False)

    experience = relationship(
        "Experience", back_populates="bullets",
        foreign_keys=[experience_id],
    )
    project = relationship(
        "Project", back_populates="bullets",
        foreign_keys=[project_id],
    )


class Skill(Base):
    __tablename__ = "skill"

    id = Column(Integer, primary_key=True)
    canonical = Column(Text, nullable=False, unique=True)


class ResumeSkill(Base):
    __tablename__ = "resume_skill"
    __table_args__ = (UniqueConstraint("resume_id", "skill_id"),)

    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resume.id", ondelete="CASCADE"), nullable=False)
    skill_id = Column(Integer, ForeignKey("skill.id"), nullable=False)
    raw = Column(Text, nullable=False)
    category = Column(Text)

    resume = relationship("Resume", back_populates="skills")
    skill = relationship("Skill")

    @property
    def canonical(self) -> str:
        return self.skill.canonical


class OtherSection(Base):
    __tablename__ = "other_section"

    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resume.id", ondelete="CASCADE"), nullable=False)
    section_type = Column(Text, nullable=False)
    raw_header = Column(Text)
    raw_text = Column(Text, nullable=False)
    position = Column(Integer, nullable=False)

    resume = relationship("Resume", back_populates="other_sections")
