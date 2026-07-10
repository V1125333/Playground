import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QuestionCategory(str, enum.Enum):
    behavioral = "behavioral"
    technical = "technical"
    design = "design"


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[QuestionCategory] = mapped_column(Enum(QuestionCategory, name="question_category"))
    text: Mapped[str] = mapped_column(Text)


class InterviewProgress(Base):
    __tablename__ = "interview_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"), primary_key=True)
    practiced: Mapped[bool] = mapped_column(Boolean, default=False)
    practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
