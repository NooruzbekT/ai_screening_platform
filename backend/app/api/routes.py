"""All API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.schemas import (
    AIDetectorDetail,
    AnswersUpdate,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationStatusResponse,
    ApplicationSummary,
    DashboardResponse,
    DecisionCreate,
    DecisionResponse,
    DocumentsUpdate,
    InterviewMessageRequest,
    InterviewMessageResponse,
    InterviewStartResponse,
    LoginRequest,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
    RegisterRequest,
    ScoreDetail,
    SettingsUpdate,
    StatsResponse,
    TokenResponse,
    VideoQuestionsResponse,
    VideoUpdate,
)
from app.core.config import settings
from app.db.database import get_db
from app.db.models import (
    Answer,
    AnswerSource,
    Application,
    ApplicationStatus,
    AuditLog,
    Decision,
    InterviewLog,
    Question,
    Score,
    ScoreLayer,
    User,
    UserRole,
)
from app.models import consistency as consistency_mod
from app.models import llm_explainer
from app.models.nlp_model import nlp_model
from app.models.scorer import score_application

_MAX_INTERVIEW_QUESTIONS = 4

router = APIRouter()

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 characters or less")
    return _pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _current_user(
    token: str = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _require_reviewer(user: User = Depends(_current_user)) -> User:
    if user.role != UserRole.reviewer:
        raise HTTPException(status_code=403, detail="Reviewer access required")
    return user


def _audit(db: Session, entity_type: str, entity_id, action: str, actor_id, payload: dict = None):
    db.add(AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        payload=payload or {},
    ))


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email,
        password_hash=_hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = _create_token(str(user.id), user.role.value)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _create_token(str(user.id), user.role.value)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


# ---------------------------------------------------------------------------
# Applications — applicant side
# ---------------------------------------------------------------------------

@router.post("/applications", response_model=ApplicationStatusResponse, status_code=201)
def create_application(
    body: ApplicationCreate,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = Application(
        user_id=user.id,
        program=body.program,
        country=body.country.upper(),
        city=body.city,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    _audit(db, "application", app.id, "created", user.id)
    db.commit()
    return app


@router.put("/applications/{app_id}/documents", response_model=ApplicationStatusResponse)
def update_documents(
    app_id: uuid.UUID,
    body: DocumentsUpdate,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = _get_own_application(app_id, user, db)
    app.documents = body.model_dump(exclude_none=True)
    db.commit()
    db.refresh(app)
    return app


@router.put("/applications/{app_id}/answers", response_model=ApplicationStatusResponse)
def update_answers(
    app_id: uuid.UUID,
    body: AnswersUpdate,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = _get_own_application(app_id, user, db)
    for item in body.answers:
        existing = (
            db.query(Answer)
            .filter(Answer.application_id == app_id, Answer.question_id == item.question_id,
                    Answer.source == AnswerSource.form)
            .first()
        )
        if existing:
            existing.text = item.text
        else:
            db.add(Answer(
                application_id=app_id,
                source=AnswerSource.form,
                question_id=item.question_id,
                text=item.text,
            ))
    db.commit()
    db.refresh(app)
    return app


@router.put("/applications/{app_id}/video", response_model=ApplicationStatusResponse)
def update_video(
    app_id: uuid.UUID,
    body: VideoUpdate,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = _get_own_application(app_id, user, db)
    existing = (
        db.query(Answer)
        .filter(Answer.application_id == app_id, Answer.question_id == body.question_id,
                Answer.source == AnswerSource.video)
        .first()
    )
    if existing:
        existing.video_url = body.video_url
        existing.transcript = None
    else:
        db.add(Answer(
            application_id=app_id,
            source=AnswerSource.video,
            question_id=body.question_id,
            video_url=body.video_url,
        ))
    db.commit()
    db.refresh(app)
    return app


@router.post("/applications/{app_id}/submit", response_model=ApplicationStatusResponse)
async def submit_application(
    app_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = _get_own_application(app_id, user, db)
    if app.status not in (ApplicationStatus.draft,):
        raise HTTPException(status_code=400, detail=f"Cannot submit from status '{app.status}'")

    app.status = ApplicationStatus.submitted
    db.commit()
    _audit(db, "application", app.id, "submitted", user.id)
    db.commit()

    background_tasks.add_task(_run_scoring, app_id)
    db.refresh(app)
    return app


@router.get("/applications/{app_id}/status", response_model=ApplicationStatusResponse)
def get_status(
    app_id: uuid.UUID,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    return _get_own_application(app_id, user, db)


# ---------------------------------------------------------------------------
# Questions (reviewer manages, applicant reads)
# ---------------------------------------------------------------------------

@router.get("/questions", response_model=List[QuestionResponse])
def get_questions(
    program: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Question)
    if program:
        q = q.filter(Question.program == program)
    return q.order_by(Question.program, Question.order).all()


@router.post("/questions", response_model=QuestionResponse, status_code=201)
def create_question(
    body: QuestionCreate,
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    question = Question(
        program=body.program,
        order=body.order,
        text=body.text,
        created_by=reviewer.id,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.put("/questions/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: uuid.UUID,
    body: QuestionUpdate,
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if body.order is not None:
        question.order = body.order
    if body.text is not None:
        question.text = body.text
    db.commit()
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(
    question_id: uuid.UUID,
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()


@router.get("/applications/{app_id}/video-questions", response_model=VideoQuestionsResponse)
async def get_video_questions(
    app_id: uuid.UUID,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = _get_own_application(app_id, user, db)
    written = [a for a in app.answers if a.source == AnswerSource.form and a.text]
    if not written:
        raise HTTPException(status_code=400, detail="No written answers found")

    written_text = "\n\n".join(a.text for a in written)
    nlp_scores, _ = nlp_model.score(written_text, [a.question_id for a in written])

    answers_data = [{"question_id": a.question_id, "text": a.text} for a in written]
    questions = llm_explainer.generate_video_questions(
        answers=answers_data,
        nlp_scores=nlp_scores,
        program=app.program.value,
    )
    return VideoQuestionsResponse(questions=questions)


# ---------------------------------------------------------------------------
# Interview (Zone B)
# ---------------------------------------------------------------------------

@router.post("/interview/{app_id}/start", response_model=InterviewStartResponse)
async def start_interview(
    app_id: uuid.UUID,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    app = db.get(Application, app_id)
    if app is None or str(app.user_id) != str(user.id):
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status != ApplicationStatus.awaiting_interview:
        raise HTTPException(status_code=400, detail="Application is not in awaiting_interview status")

    written_score = _get_layer_score(app, ScoreLayer.nlp_written)
    video_score = _get_layer_score(app, ScoreLayer.nlp_video)
    w_scores = (written_score.scores or {}) if written_score else {}
    v_scores = (video_score.scores or {}) if video_score else {}
    contradictions = consistency_mod.find_contradictions(w_scores, v_scores)

    app_data = {
        "full_name": app.user.full_name,
        "program": app.program.value,
        "city": app.city,
        "answers": [
            {"question_id": a.question_id, "text": a.text}
            for a in app.answers if a.source == AnswerSource.form and a.text
        ],
    }

    system_context = llm_explainer.build_interview_system_context(
        app_data, contradictions, _MAX_INTERVIEW_QUESTIONS
    )
    first_q, _ = llm_explainer.generate_next_question([], system_context)
    if not first_q:
        first_q = "Расскажите о конкретном случае, который повлиял на ваш выбор этой программы."

    log_entry = InterviewLog(
        application_id=app_id,
        messages=[
            {"role": "system_context", "content": system_context},
            {"role": "assistant", "content": first_q},
        ],
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    audio_url = await llm_explainer.text_to_speech(first_q)
    return InterviewStartResponse(
        interview_id=log_entry.id,
        question=first_q,
        audio_url=audio_url,
        question_number=1,
        total_questions=_MAX_INTERVIEW_QUESTIONS,
    )


@router.post("/interview/{interview_id}/message", response_model=InterviewMessageResponse)
async def interview_message(
    interview_id: uuid.UUID,
    body: InterviewMessageRequest,
    user: User = Depends(_current_user),
    db: Session = Depends(get_db),
):
    log_entry: InterviewLog = db.get(InterviewLog, interview_id)
    if log_entry is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    messages: list = list(log_entry.messages or [])

    system_context = next(
        (m["content"] for m in messages if m.get("role") == "system_context"), ""
    )
    user_answers = [m for m in messages if m.get("role") == "user"]
    answer_count = len(user_answers) + 1

    messages.append({"role": "user", "content": body.text})

    if answer_count >= _MAX_INTERVIEW_QUESTIONS:
        log_entry.messages = messages
        log_entry.completed_at = datetime.now(timezone.utc)

        interview_text = " ".join(
            m["content"] for m in messages if m.get("role") == "user"
        )
        interview_scores, _ = nlp_model.score(interview_text)

        app: Application = log_entry.application
        written_score = _get_layer_score(app, ScoreLayer.nlp_written)
        w_scores = (written_score.scores or {}) if written_score else {}

        new_cons = consistency_mod.compute(w_scores, interview_scores)
        final_score_rec = _get_layer_score(app, ScoreLayer.rule)
        old_final = (final_score_rec.final_score or 0.0) if final_score_rec else 0.0

        new_zone = "A" if (
            old_final >= settings.ZONE_A_THRESHOLD
            and new_cons >= settings.CONSISTENCY_THRESHOLD
        ) else "C"
        log_entry.new_zone = new_zone
        log_entry.final_score = old_final
        app.status = ApplicationStatus.zone_a if new_zone == "A" else ApplicationStatus.zone_c

        db.add(Answer(
            application_id=app.id,
            source=AnswerSource.interview,
            question_id="interview",
            text=interview_text,
        ))
        db.commit()
        return InterviewMessageResponse(is_complete=True)

    # Build conversation for Groq (skip system_context storage entry)
    groq_msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("assistant", "user")
    ]
    next_q, is_complete = llm_explainer.generate_next_question(groq_msgs, system_context)

    if is_complete or not next_q:
        return InterviewMessageResponse(is_complete=True)

    messages.append({"role": "assistant", "content": next_q})
    log_entry.messages = messages
    db.commit()

    audio_url = await llm_explainer.text_to_speech(next_q)
    return InterviewMessageResponse(
        next_question=next_q,
        audio_url=audio_url,
        is_complete=False,
        question_number=answer_count + 1,
    )


# ---------------------------------------------------------------------------
# Dashboard (reviewer)
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    apps = db.query(Application).all()
    summaries = [_to_summary(a, db) for a in apps]

    by_program: dict = {}
    for a in apps:
        key = a.program.value
        by_program[key] = by_program.get(key, 0) + 1

    return DashboardResponse(
        total=len(apps),
        zone_a=sum(1 for a in apps if a.status == ApplicationStatus.zone_a),
        zone_b=sum(1 for a in apps if a.status in (
            ApplicationStatus.zone_b, ApplicationStatus.awaiting_interview)),
        zone_c=sum(1 for a in apps if a.status == ApplicationStatus.zone_c),
        pending_review=sum(1 for a in apps if a.status in (
            ApplicationStatus.zone_a, ApplicationStatus.zone_b,
            ApplicationStatus.awaiting_interview)),
        by_program=by_program,
        applications=summaries,
    )


@router.get("/applications/{app_id}/detail", response_model=ApplicationDetail)
def application_detail(
    app_id: uuid.UUID,
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Not found")

    scores = [
        ScoreDetail(
            layer=s.layer.value,
            scores=s.scores,
            explanations=s.explanations,
            attribution=s.attribution,
            ai_probability=s.ai_probability,
            ai_detector_detail=AIDetectorDetail(**s.ai_detector_detail)
            if s.ai_detector_detail and all(
                k in s.ai_detector_detail
                for k in ("perplexity", "burstiness", "specificity", "composite")
            ) else None,
            consistency_score=s.consistency_score,
            zone=s.zone,
            final_score=s.final_score,
        )
        for s in app.scores
    ]

    return ApplicationDetail(
        id=app.id,
        status=app.status,
        program=app.program,
        country=app.country,
        city=app.city,
        regional_coeff=app.regional_coeff,
        full_name=app.user.full_name,
        documents=app.documents,
        scores=scores,
        created_at=app.created_at,
    )


@router.post("/applications/{app_id}/decision", response_model=DecisionResponse, status_code=201)
def make_decision(
    app_id: uuid.UUID,
    body: DecisionCreate,
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Not found")

    decision = Decision(
        application_id=app_id,
        reviewer_id=reviewer.id,
        decision=body.decision,
        agreed_with_ai=body.agreed_with_ai,
        override_reason=body.override_reason,
        notes=body.notes,
    )
    db.add(decision)

    status_map = {
        "shortlist": ApplicationStatus.shortlisted,
        "hold": ApplicationStatus.hold,
        "reject": ApplicationStatus.rejected,
    }
    app.status = status_map[body.decision.value]

    _audit(db, "application", app_id, f"decision:{body.decision.value}", reviewer.id,
           {"agreed_with_ai": body.agreed_with_ai, "override_reason": body.override_reason})
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/stats", response_model=StatsResponse)
def stats(
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    apps = db.query(Application).all()
    by_status: dict = {}
    for a in apps:
        key = a.status.value
        by_status[key] = by_status.get(key, 0) + 1

    final_scores = [
        s.final_score for a in apps
        for s in a.scores if s.final_score is not None and s.layer == ScoreLayer.rule
    ]
    ai_flagged = sum(
        1 for a in apps
        for s in a.scores
        if s.ai_probability is not None and s.ai_probability > settings.AI_DETECTOR_THRESHOLD
    )

    zone_counts: dict = {}
    for a in apps:
        for s in a.scores:
            if s.zone:
                zone_counts[s.zone] = zone_counts.get(s.zone, 0) + 1

    return StatsResponse(
        total_applications=len(apps),
        by_status=by_status,
        by_zone=zone_counts,
        avg_final_score=round(sum(final_scores) / len(final_scores), 2) if final_scores else 0.0,
        ai_flagged=ai_flagged,
    )


@router.put("/settings")
def update_settings(
    body: SettingsUpdate,
    reviewer: User = Depends(_require_reviewer),
):
    # Runtime-only override; persisted via env in production
    if body.zone_a_threshold is not None:
        settings.ZONE_A_THRESHOLD = body.zone_a_threshold
    if body.zone_b_threshold is not None:
        settings.ZONE_B_THRESHOLD = body.zone_b_threshold
    if body.ai_detector_threshold is not None:
        settings.AI_DETECTOR_THRESHOLD = body.ai_detector_threshold
    if body.consistency_threshold is not None:
        settings.CONSISTENCY_THRESHOLD = body.consistency_threshold
    if body.nlp_weight is not None:
        settings.NLP_WEIGHT = body.nlp_weight
    if body.struct_weight is not None:
        settings.STRUCT_WEIGHT = body.struct_weight
    return {"ok": True}


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

@router.post("/seed", status_code=201)
def seed(
    reviewer: User = Depends(_require_reviewer),
    db: Session = Depends(get_db),
):
    """Insert three synthetic archetypes for demo/testing."""
    reviewer_user = db.query(User).filter(User.role == UserRole.reviewer).first()

    created = []
    for archetype in _SEED_ARCHETYPES:
        # Create applicant user
        email = archetype["email"]
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            applicant = existing_user
        else:
            applicant = User(
                email=email,
                password_hash=_hash_password("demo1234"),
                full_name=archetype["full_name"],
                role=UserRole.applicant,
            )
            db.add(applicant)
            db.flush()

        app = Application(
            user_id=applicant.id,
            program=archetype["program"],
            country="KZ",
            city=archetype["city"],
            status=archetype["status"],
            regional_coeff=archetype["regional_coeff"],
            documents=archetype["documents"],
        )
        db.add(app)
        db.flush()

        for ans in archetype["answers"]:
            db.add(Answer(
                application_id=app.id,
                source=AnswerSource.form,
                question_id=ans["question_id"],
                text=ans["text"],
            ))

        score = Score(
            application_id=app.id,
            layer=ScoreLayer.rule,
            scores=archetype["scores"],
            explanations=archetype["explanations"],
            attribution=archetype["attribution"],
            ai_probability=archetype["ai_probability"],
            ai_detector_detail=archetype["ai_detector_detail"],
            consistency_score=archetype["consistency_score"],
            zone=archetype["zone"],
            final_score=archetype["final_score"],
        )
        db.add(score)
        created.append(archetype["full_name"])

    db.commit()
    return {"seeded": created}


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_SEED_ARCHETYPES = [
    # A — «Скрытый талант»
    {
        "email": "aigerin.dosova@seed.invisionu.kz",
        "full_name": "Айгерим Досова",
        "program": "foundation",
        "city": "Шымкент",
        "status": ApplicationStatus.zone_a,
        "regional_coeff": 1.12,
        "documents": {"ent_score": 91, "ielts_score": 6.5},
        "answers": [
            {"question_id": "V2", "text": (
                "В 2023 году в нашей школе случился пожар в лаборатории. Я была дежурной "
                "и первой заметила дым. Не растерявшись, объявила эвакуацию, позвонила в МЧС "
                "и организовала перекличку 34 учеников. Никто не пострадал. После этого случая "
                "стала руководителем отряда ЧС."
            )},
            {"question_id": "V4", "text": (
                "Я основала школьный кружок 3D-печати в 2022 году — с нуля, без бюджета. "
                "Нашла спонсора через email-кампанию, получила принтер. Обучила 12 учеников, "
                "двое из них выиграли республиканский конкурс."
            )},
        ],
        "scores": {
            "leadership": 9.4, "motivation": 8.9, "perseverance": 9.1,
            "teamwork": 8.7, "goal_pursuit": 8.5, "intrinsic_motivation": 9.0,
            "prosocial_purpose": 8.8,
        },
        "explanations": {
            "summary": "Высокий потенциал лидера с реальным кризисным опытом.",
            "leadership": "Проявила лидерство в критической ситуации — эвакуация 34 человек.",
            "motivation": "Основала кружок с нуля — высокая внутренняя мотивация.",
        },
        "attribution": {"leadership": ["организовала", "основала", "руководитель"]},
        "ai_probability": 0.04,
        "ai_detector_detail": {"perplexity": 187.3, "burstiness": 0.48, "specificity": 0.041, "composite": 0.04},
        "consistency_score": 0.91,
        "zone": "A",
        "final_score": 9.21,
    },
    # B — «Кризисный лидер»
    {
        "email": "maksat.kenzheev@seed.invisionu.kz",
        "full_name": "Максат Кенжеев",
        "program": "bachelor",
        "city": "Кызылорда",
        "status": ApplicationStatus.awaiting_interview,
        "regional_coeff": 1.12,
        "documents": {"ent_score": 84, "ielts_score": 6.0},
        "answers": [
            {"question_id": "V2", "text": (
                "В апреле 2024 года паводок затопил три квартала нашего района. Я координировал "
                "волонтёрский штаб: распределял 47 добровольцев, договорился с 3 магазинами о еде, "
                "помог эвакуировать 200 семей за 72 часа. Областной акимат выдал благодарственное письмо."
            )},
            {"question_id": "V4_bach", "text": (
                "Моя цель — стать специалистом по публичной политике и создать программу "
                "подготовки к ЧС для малых городов Казахстана. Уже написал черновик концепции "
                "на 12 страниц, обсудил с замакима."
            )},
        ],
        "scores": {
            "leadership": 8.7, "motivation": 8.5, "perseverance": 9.2,
            "teamwork": 9.0, "goal_pursuit": 8.8, "intrinsic_motivation": 8.3,
            "prosocial_purpose": 9.1,
        },
        "explanations": {
            "summary": "Сильный кандидат с подтверждённым социальным лидерством.",
            "perseverance": "Координировал кризисную операцию 72 часа — высокая стрессоустойчивость.",
            "prosocial_purpose": "Явная ориентация на общественное благо.",
        },
        "attribution": {"leadership": ["координировал", "штаб", "эвакуировать"]},
        "ai_probability": 0.03,
        "ai_detector_detail": {"perplexity": 201.4, "burstiness": 0.52, "specificity": 0.038, "composite": 0.03},
        "consistency_score": 0.72,
        "zone": "B",
        "final_score": 8.83,
    },
    # C — «ChatGPT-заявка»
    {
        "email": "dana.nurlanova@seed.invisionu.kz",
        "full_name": "Дана Нурланова",
        "program": "bachelor",
        "city": "Алматы",
        "status": ApplicationStatus.zone_c,
        "regional_coeff": 0.95,
        "documents": {"ent_score": 95, "ielts_score": 7.0},
        "answers": [
            {"question_id": "V2", "text": (
                "В процессе академической деятельности мне неоднократно приходилось преодолевать "
                "значительные трудности, связанные с комплексными образовательными задачами. "
                "Данный опыт способствовал формированию устойчивых компетенций в области "
                "стратегического мышления и адаптивного реагирования на вызовы."
            )},
            {"question_id": "V4_bach", "text": (
                "Моей долгосрочной целью является интеграция передовых методологических подходов "
                "в социологическую практику с целью достижения максимального позитивного воздействия "
                "на общество посредством применения доказательной базы исследований."
            )},
        ],
        "scores": {
            "leadership": 5.2, "motivation": 6.1, "perseverance": 5.8,
            "teamwork": 5.5, "goal_pursuit": 6.3, "intrinsic_motivation": 5.9,
            "prosocial_purpose": 6.0,
        },
        "explanations": {
            "summary": "Высокая вероятность AI-генерации. Нет конкретных историй.",
            "leadership": "Отсутствуют конкретные примеры лидерства.",
            "ai_comment": "Perplexity=12.4, burstiness=0.07 — характерно для GPT.",
        },
        "attribution": {"leadership": []},
        "ai_probability": 0.87,
        "ai_detector_detail": {"perplexity": 12.4, "burstiness": 0.07, "specificity": 0.004, "composite": 0.87},
        "consistency_score": 0.45,
        "zone": "C",
        "final_score": 7.08,
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_own_application(app_id: uuid.UUID, user: User, db: Session) -> Application:
    app = db.get(Application, app_id)
    if app is None or str(app.user_id) != str(user.id):
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _get_layer_score(app: Application, layer: ScoreLayer) -> Optional[Score]:
    for s in app.scores:
        if s.layer == layer:
            return s
    return None


def _to_summary(app: Application, db: Session) -> ApplicationSummary:
    rule_score = _get_layer_score(app, ScoreLayer.rule)
    return ApplicationSummary(
        id=app.id,
        full_name=app.user.full_name,
        program=app.program,
        city=app.city,
        status=app.status,
        final_score=rule_score.final_score if rule_score else None,
        zone=rule_score.zone if rule_score else None,
        ai_probability=rule_score.ai_probability if rule_score else None,
        created_at=app.created_at,
    )


async def _run_scoring(app_id: uuid.UUID) -> None:
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        await score_application(app_id, db)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Scoring failed for %s: %s", app_id, exc)
    finally:
        db.close()
