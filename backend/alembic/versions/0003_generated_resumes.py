"""generated resumes

Revision ID: 0003_generated_resumes
Revises: 0002_candidate_profiles
Create Date: 2026-07-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_generated_resumes"
down_revision: str | Sequence[str] | None = "0002_candidate_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generated_resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("profile_content_hash", sa.String(length=64), nullable=False),
        sa.Column("resume_name", sa.String(length=200), nullable=False),
        sa.Column("target_job_title", sa.String(length=200), nullable=False),
        sa.Column("target_company", sa.String(length=200), nullable=True),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("job_analysis_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_match_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resume_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("generation_algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_resume_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_resume_id"], ["generated_resumes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generated_resumes_user_id"), "generated_resumes", ["user_id"], unique=False)
    op.create_index(op.f("ix_generated_resumes_profile_id"), "generated_resumes", ["profile_id"], unique=False)
    op.create_index(op.f("ix_generated_resumes_target_company"), "generated_resumes", ["target_company"], unique=False)
    op.create_index(op.f("ix_generated_resumes_target_job_title"), "generated_resumes", ["target_job_title"], unique=False)
    op.create_index(op.f("ix_generated_resumes_parent_resume_id"), "generated_resumes", ["parent_resume_id"], unique=False)
    op.create_index("ix_generated_resumes_updated_at", "generated_resumes", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_generated_resumes_updated_at", table_name="generated_resumes")
    op.drop_index(op.f("ix_generated_resumes_parent_resume_id"), table_name="generated_resumes")
    op.drop_index(op.f("ix_generated_resumes_target_job_title"), table_name="generated_resumes")
    op.drop_index(op.f("ix_generated_resumes_target_company"), table_name="generated_resumes")
    op.drop_index(op.f("ix_generated_resumes_profile_id"), table_name="generated_resumes")
    op.drop_index(op.f("ix_generated_resumes_user_id"), table_name="generated_resumes")
    op.drop_table("generated_resumes")
