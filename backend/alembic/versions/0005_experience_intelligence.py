"""add experience intelligence to resume intelligence packages

Revision ID: 0005_experience_intelligence
Revises: 0004_rip
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_experience_intelligence"
down_revision: str | Sequence[str] | None = "0004_rip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_intelligence_packages",
        sa.Column("experience_intelligence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_intelligence_packages", "experience_intelligence_json")
