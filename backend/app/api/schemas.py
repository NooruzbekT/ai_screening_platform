from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRoleEnum(str, enum.Enum):
    applicant = "applicant"
    reviewer = "reviewer"


class ApplicationStatusEnum(str, enum.Enum):
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


class ProgramEnum(str, enum.Enum):
    foundation = "foundation"
    bachelor = "bachelor"


class DecisionEnum(str, enum.Enum):
    shortlist = "shortlist"
    hold = "hold"
    reject = "reject"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2)
    role: UserRoleEnum = UserRoleEnum.applicant


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRoleEnum
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRoleEnum
    user_id: UUID


# ---------------------------------------------------------------------------
# Application — applicant side
# ---------------------------------------------------------------------------

class ApplicationCreate(BaseModel):
    program: ProgramEnum
    country: str = Field(default="KZ", min_length=2, max_length=2)
    city: Optional[str] = None


class DocumentsUpdate(BaseModel):
    ent_score: Optional[int] = Field(default=None, ge=0, le=140)
    ielts_score: Optional[float] = Field(default=None, ge=0.0, le=9.0)
    toefl_score: Optional[int] = Field(default=None, ge=0, le=120)
    duolingo_score: Optional[int] = Field(default=None, ge=0, le=160)
    gpa: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    graduation_year: Optional[int] = None
    school_name: Optional[str] = None


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2)
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    city: Optional[str] = None
    school_name: Optional[str] = None
    ent_score: Optional[int] = Field(default=None, ge=0, le=140)
    graduation_year: Optional[int] = None
    gpa: Optional[float] = Field(default=None, ge=0.0, le=10.0)


class LanguageCertType(str, enum.Enum):
    ielts = "IELTS"
    toefl = "TOEFL"
    duolingo = "Duolingo"


class DocType(str, enum.Enum):
    ent_cert = "ent_cert"
    language_cert = "language_cert"
    recommendation = "recommendation"


class DocumentUploadResponse(BaseModel):
    doc_url: str
    doc_type: DocType
    cert_type: Optional[LanguageCertType] = None
    score: Optional[float] = None


class VideoUploadResponse(BaseModel):
    video_url: str
    question_id: str


# kept for backwards compat
class LanguageCertUploadResponse(DocumentUploadResponse):
    pass


class AnswerItem(BaseModel):
    question_id: str
    text: Optional[str] = None


class AnswersUpdate(BaseModel):
    answers: List[AnswerItem]


class VideoUpdate(BaseModel):
    question_id: str
    video_url: str


class ApplicationStatusResponse(BaseModel):
    id: UUID
    status: ApplicationStatusEnum
    program: ProgramEnum
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Application — reviewer side
# ---------------------------------------------------------------------------

class AIDetectorDetail(BaseModel):
    perplexity: float
    burstiness: float
    specificity: float
    composite: float


class ScoreDetail(BaseModel):
    layer: str
    scores: Optional[Dict[str, float]] = None
    explanations: Optional[Dict[str, str]] = None
    attribution: Optional[Dict[str, List[str]]] = None
    ai_probability: Optional[float] = None
    ai_detector_detail: Optional[AIDetectorDetail] = None
    consistency_score: Optional[float] = None
    zone: Optional[str] = None
    final_score: Optional[float] = None

    model_config = {"from_attributes": True}


class AnswerDetail(BaseModel):
    question_id: str
    source: str
    text: Optional[str] = None
    video_url: Optional[str] = None
    transcript: Optional[str] = None

    model_config = {"from_attributes": True}


class InterviewMessageDetail(BaseModel):
    role: str    # "assistant" | "user"
    content: str
    audio_url: Optional[str] = None


class InterviewLogDetail(BaseModel):
    interview_id: UUID
    messages: List[InterviewMessageDetail]
    final_score: Optional[float] = None
    new_zone: Optional[str] = None
    completed_at: Optional[datetime] = None


class ApplicationDetail(BaseModel):
    id: UUID
    status: ApplicationStatusEnum
    program: ProgramEnum
    country: str
    city: Optional[str]
    regional_coeff: Optional[float]
    full_name: str
    documents: Optional[Dict[str, Any]] = None
    answers: List[AnswerDetail] = []
    scores: List[ScoreDetail] = []
    interview_log: Optional[InterviewLogDetail] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Interview
# ---------------------------------------------------------------------------

class InterviewStartResponse(BaseModel):
    interview_id: UUID
    question: str
    audio_url: Optional[str] = None
    question_number: int = 1
    total_questions: int = 4


class InterviewMessageRequest(BaseModel):
    text: str = Field(min_length=1)


class InterviewMessageResponse(BaseModel):
    next_question: Optional[str] = None
    audio_url: Optional[str] = None
    is_complete: bool = False
    question_number: Optional[int] = None
    new_zone: Optional[str] = None  # "A" or "C" when is_complete=True


# ---------------------------------------------------------------------------
# Dashboard & Stats
# ---------------------------------------------------------------------------

class ApplicationSummary(BaseModel):
    id: UUID
    full_name: str
    program: ProgramEnum
    city: Optional[str]
    status: ApplicationStatusEnum
    final_score: Optional[float]
    zone: Optional[str]
    ai_probability: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    total: int
    total_filtered: int
    zone_a: int
    zone_b: int
    zone_c: int
    pending_review: int
    by_program: Dict[str, int]
    applications: List[ApplicationSummary]
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

class QuestionCreate(BaseModel):
    program: ProgramEnum
    order: int = 0
    text: str = Field(min_length=10)


class QuestionUpdate(BaseModel):
    order: Optional[int] = None
    text: Optional[str] = Field(default=None, min_length=10)


class QuestionResponse(BaseModel):
    id: UUID
    program: ProgramEnum
    order: int
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoQuestionsResponse(BaseModel):
    questions: List[str]


class StatsResponse(BaseModel):
    total_applications: int
    by_status: Dict[str, int]
    by_zone: Dict[str, int]
    avg_final_score: float
    ai_flagged: int


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

class DecisionCreate(BaseModel):
    decision: DecisionEnum
    agreed_with_ai: Optional[bool] = None
    override_reason: Optional[str] = None
    notes: Optional[str] = None


class DecisionResponse(BaseModel):
    id: UUID
    decision: DecisionEnum
    agreed_with_ai: Optional[bool]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionHistoryItem(BaseModel):
    id: UUID
    decision: DecisionEnum
    agreed_with_ai: Optional[bool]
    override_reason: Optional[str]
    notes: Optional[str]
    reviewer_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StatusPatch(BaseModel):
    status: ApplicationStatusEnum


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class SettingsResponse(BaseModel):
    zone_a_threshold: float
    zone_b_threshold: float
    ai_detector_threshold: float
    consistency_threshold: float
    nlp_weight: float
    struct_weight: float
    regional_coeffs: Dict[str, Any]


class SettingsUpdate(BaseModel):
    zone_a_threshold: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    zone_b_threshold: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    ai_detector_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    consistency_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    nlp_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    struct_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    regional_coeffs: Optional[Dict[str, float]] = None
