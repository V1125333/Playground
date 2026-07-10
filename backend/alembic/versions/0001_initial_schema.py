"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    resume_status = postgresql.ENUM("draft", "applied", "interview", "offer", "rejected", name="resume_status")
    question_category = postgresql.ENUM("behavioral", "technical", "design", name="question_category")
    resume_status.create(op.get_bind(), checkfirst=True)
    question_category.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "interview_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=160), nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM("behavioral", "technical", "design", name="question_category", create_type=False),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_interview_questions_role"), "interview_questions", ["role"], unique=False)

    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("target_role", sa.String(length=160), nullable=False),
        sa.Column("company", sa.String(length=160), nullable=True),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ats_score", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("draft", "applied", "interview", "offer", "rejected", name="resume_status", create_type=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resumes_user_id"), "resumes", ["user_id"], unique=False)

    op.create_table(
        "interview_progress",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practiced", sa.Boolean(), nullable=False),
        sa.Column("practiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["interview_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "question_id"),
    )

    op.create_table(
        "resume_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resume_suggestions_resume_id"), "resume_suggestions", ["resume_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_resume_suggestions_resume_id"), table_name="resume_suggestions")
    op.drop_table("resume_suggestions")
    op.drop_table("interview_progress")
    op.drop_index(op.f("ix_resumes_user_id"), table_name="resumes")
    op.drop_table("resumes")
    op.drop_index(op.f("ix_interview_questions_role"), table_name="interview_questions")
    op.drop_table("interview_questions")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    postgresql.ENUM(name="question_category").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="resume_status").drop(op.get_bind(), checkfirst=True)
