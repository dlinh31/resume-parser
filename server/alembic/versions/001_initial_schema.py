"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "resume",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("file_id", sa.Text, nullable=False, unique=True),
        sa.Column("source_uri", sa.Text, nullable=False),
        sa.Column("normalizer_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contact_name", sa.Text),
        sa.Column("contact_email", sa.Text),
        sa.Column("contact_phone", sa.Text),
        sa.Column("contact_linkedin", sa.Text),
        sa.Column("contact_github", sa.Text),
        sa.Column("contact_website", sa.Text),
        sa.Column("pdf_bytes", sa.LargeBinary),
    )

    op.create_table(
        "experience",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("resume_id", sa.Integer, sa.ForeignKey("resume.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_raw", sa.Text, nullable=False),
        sa.Column("company_canonical", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("location_raw", sa.Text),
        sa.Column("location_canonical", sa.Text),
        sa.Column("is_remote", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("start_date_raw", sa.Text),
        sa.Column("start_date_iso", sa.Text),
        sa.Column("end_date_raw", sa.Text),
        sa.Column("end_date_iso", sa.Text),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("position", sa.Integer, nullable=False),
    )

    op.create_table(
        "education",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("resume_id", sa.Integer, sa.ForeignKey("resume.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution", sa.Text, nullable=False),
        sa.Column("degree", sa.Text),
        sa.Column("field", sa.Text),
        sa.Column("gpa", sa.Text),
        sa.Column("graduation_date_raw", sa.Text),
        sa.Column("graduation_date_iso", sa.Text),
        sa.Column("is_expected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("honors", JSONB),
        sa.Column("courses", JSONB),
        sa.Column("position", sa.Integer, nullable=False),
    )

    op.create_table(
        "project",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("resume_id", sa.Integer, sa.ForeignKey("resume.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("technologies", JSONB),
        sa.Column("links", JSONB),
        sa.Column("position", sa.Integer, nullable=False),
    )

    op.create_table(
        "bullet",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experience_id", sa.Integer, sa.ForeignKey("experience.id", ondelete="CASCADE")),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("project.id", ondelete="CASCADE")),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536)),
        sa.Column("position", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "(experience_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1",
            name="bullet_one_parent",
        ),
    )

    op.create_table(
        "skill",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("canonical", sa.Text, nullable=False, unique=True),
    )

    op.create_table(
        "resume_skill",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("resume_id", sa.Integer, sa.ForeignKey("resume.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skill.id"), nullable=False),
        sa.Column("raw", sa.Text, nullable=False),
        sa.Column("category", sa.Text),
        sa.UniqueConstraint("resume_id", "skill_id"),
    )

    op.create_table(
        "other_section",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("resume_id", sa.Integer, sa.ForeignKey("resume.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_type", sa.Text, nullable=False),
        sa.Column("raw_header", sa.Text),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )

    op.create_index("ix_experience_resume_id", "experience", ["resume_id"])
    op.create_index("ix_education_resume_id", "education", ["resume_id"])
    op.create_index("ix_project_resume_id", "project", ["resume_id"])
    op.create_index("ix_bullet_experience_id", "bullet", ["experience_id"])
    op.create_index("ix_bullet_project_id", "bullet", ["project_id"])
    op.create_index("ix_resume_skill_resume_id", "resume_skill", ["resume_id"])
    op.create_index("ix_resume_skill_skill_id", "resume_skill", ["skill_id"])
    op.create_index("ix_other_section_resume_section", "other_section", ["resume_id", "section_type"])


def downgrade() -> None:
    op.drop_table("other_section")
    op.drop_table("resume_skill")
    op.drop_table("skill")
    op.drop_table("bullet")
    op.drop_table("project")
    op.drop_table("education")
    op.drop_table("experience")
    op.drop_table("resume")
    op.execute("DROP EXTENSION IF EXISTS vector")
