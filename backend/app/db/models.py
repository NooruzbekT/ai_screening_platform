import uuid
import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum,
    Float, ForeignKey, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class UserRole(str, enum.Enum):
    applicant = "applicant"
    reviewer = "reviewer"


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    scoring = "scoring"
    zone_a = "zone_a"
    zone_b = "zone_b"
    zone_c = "zone_c"
    awaiting_interview = "awaiting_interview"
    shortlisted = "shortlisted"
    hold = "hold"
    rejected = "rejected"
    offer = "offer"


class AnswerSource(str, enum.Enum):
    form = "form"
    video = "video"
    interview = "interview"


class ScoreLayer(str, enum.Enum):
    rule = "rule"
    nlp_written = "nlp_written"
    nlp_video = "nlp_video"
    interview = "interview"


class DecisionType(str, enum.Enum):
    shortlist = "shortlist"
    hold = "hold"
    reject = "reject"


class ProgramType(str, enum.Enum):
    foundation = "foundation"
    bachelor = "bachelor"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    applications = relationship("Application", back_populates="user")
    decisions = relationship("Decision", back_populates="reviewer")


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    program = Column(SAEnum(ProgramType), nullable=False)
    country = Column(String(2), nullable=False, default="KZ")
    city = Column(String, nullable=True)
    status = Column(SAEnum(ApplicationStatus), nullable=False, default=ApplicationStatus.draft)
    regional_coeff = Column(Float, nullable=True)
    # Документы (ENT, GPA, языковые тесты) хранятся в JSONB
    documents = Column(JSONB, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="applications")
    answers = relationship("Answer", back_populates="application", cascade="all, delete-orphan")
    scores = relationship("Score", back_populates="application", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="application")
    interview_logs = relationship("InterviewLog", back_populates="application", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    source = Column(SAEnum(AnswerSource), nullable=False)
    question_id = Column(String(10), nullable=False)
    text = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)

    application = relationship("Application", back_populates="answers")


class Score(Base):
    __tablename__ = "scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    layer = Column(SAEnum(ScoreLayer), nullable=False)
    scores = Column(JSONB, nullable=True)
    explanations = Column(JSONB, nullable=True)
    attribution = Column(JSONB, nullable=True)
    ai_probability = Column(Float, nullable=True)
    ai_detector_detail = Column(JSONB, nullable=True)
    consistency_score = Column(Float, nullable=True)
    zone = Column(String(1), nullable=True)
    final_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="scores")


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    decision = Column(SAEnum(DecisionType), nullable=False)
    agreed_with_ai = Column(Boolean, nullable=True)
    override_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="decisions")
    reviewer = relationship("User", back_populates="decisions")


class InterviewLog(Base):
    __tablename__ = "interview_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    messages = Column(JSONB, nullable=False, default=list)
    final_score = Column(Float, nullable=True)
    new_zone = Column(String(1), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    application = relationship("Application", back_populates="interview_logs")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String, nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
