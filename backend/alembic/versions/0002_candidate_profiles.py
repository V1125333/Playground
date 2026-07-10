"""candidate profiles

Revision ID: 0002_candidate_profiles
Revises: 0001_initial_schema
Create Date: 2026-07-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_candidate_profiles"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_name", sa.String(length=160), nullable=False),
        sa.Column("profile_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("completeness_score", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "profile_name", name="uq_candidate_profiles_user_profile_name"),
    )
    op.create_index(op.f("ix_candidate_profiles_user_id"), "candidate_profiles", ["user_id"], unique=False)
    op.create_index(op.f("ix_candidate_profiles_content_hash"), "candidate_profiles", ["content_hash"], unique=False)
    op.create_index("ix_candidate_profiles_updated_at", "candidate_profiles", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_candidate_profiles_updated_at", table_name="candidate_profiles")
    op.drop_index(op.f("ix_candidate_profiles_content_hash"), table_name="candidate_profiles")
    op.drop_index(op.f("ix_candidate_profiles_user_id"), table_name="candidate_profiles")
    op.drop_table("candidate_profiles")
