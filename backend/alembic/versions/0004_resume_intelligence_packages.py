"""resume intelligence packages

Revision ID: 0004_rip
Revises: 0003_generated_resumes
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_rip"
down_revision: str | Sequence[str] | None = "0003_generated_resumes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_intelligence_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("profile_content_hash", sa.String(length=64), nullable=False),
        sa.Column("job_description_hash", sa.String(length=64), nullable=False),
        sa.Column("target_role", sa.String(length=200), nullable=False),
        sa.Column("target_company", sa.String(length=200), nullable=True),
        sa.Column("level", sa.String(length=80), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("job_intelligence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_requirements_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_match_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_intelligence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_status", sa.String(length=40), nullable=False),
        sa.Column("validation_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resume_intelligence_packages_user_id"), "resume_intelligence_packages", ["user_id"], unique=False)
    op.create_index(op.f("ix_resume_intelligence_packages_profile_id"), "resume_intelligence_packages", ["profile_id"], unique=False)
    op.create_index(op.f("ix_resume_intelligence_packages_job_description_hash"), "resume_intelligence_packages", ["job_description_hash"], unique=False)
    op.create_index(op.f("ix_resume_intelligence_packages_target_role"), "resume_intelligence_packages", ["target_role"], unique=False)
    op.create_index(op.f("ix_resume_intelligence_packages_target_company"), "resume_intelligence_packages", ["target_company"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_resume_intelligence_packages_target_company"), table_name="resume_intelligence_packages")
    op.drop_index(op.f("ix_resume_intelligence_packages_target_role"), table_name="resume_intelligence_packages")
    op.drop_index(op.f("ix_resume_intelligence_packages_job_description_hash"), table_name="resume_intelligence_packages")
    op.drop_index(op.f("ix_resume_intelligence_packages_profile_id"), table_name="resume_intelligence_packages")
    op.drop_index(op.f("ix_resume_intelligence_packages_user_id"), table_name="resume_intelligence_packages")
    op.drop_table("resume_intelligence_packages")
