import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResumeIntelligencePackageModel(Base):
    __tablename__ = "resume_intelligence_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    job_description_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_role: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    target_company: Mapped[str] = mapped_column(String(200), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(80), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    job_intelligence_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_requirements_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    profile_match_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary_intelligence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    experience_intelligence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    skills_intelligence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False, default="valid")
    validation_warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
