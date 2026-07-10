import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GeneratedResumeModel(Base):
    __tablename__ = "generated_resumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resume_name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_job_title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    target_company: Mapped[str] = mapped_column(String(200), nullable=True, index=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    job_analysis_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    profile_match_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resume_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_resumes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
