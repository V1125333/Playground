import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ResumeStatus(str, enum.Enum):
    draft = "draft"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    target_role: Mapped[str] = mapped_column(String(160))
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    job_description: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSONB)
    ats_score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ResumeStatus] = mapped_column(Enum(ResumeStatus, name="resume_status"), default=ResumeStatus.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="resumes")
    suggestions = relationship("ResumeSuggestion", back_populates="resume", cascade="all, delete-orphan")


class ResumeSuggestion(Base):
    __tablename__ = "resume_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    resume = relationship("Resume", back_populates="suggestions")
