"""add skills intelligence to resume intelligence packages

Revision ID: 0006_skills_intelligence
Revises: 0005_experience_intelligence
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_skills_intelligence"
down_revision: str | Sequence[str] | None = "0005_experience_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_intelligence_packages",
        sa.Column("skills_intelligence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_intelligence_packages", "skills_intelligence_json")
