"""Main scoring pipeline (Scorer.score_application)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Answer, AnswerSource, Application, ApplicationStatus, Score, ScoreLayer
from app.models import ai_detector, consistency
from app.models import llm_explainer
from app.models import transcriber as transcriber_mod
from app.models.nlp_model import QUALITY_WEIGHTS, QUALITIES, nlp_model
from app.models.rule_engine import ApplicationInput, check_gate, get_regional_coeff, struct_score

log = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    application_id: UUID
    zone: str
    final_score: float
    struct: float
    nlp_written: Dict[str, float]
    nlp_video: Dict[str, float]
    consistency_score: float
    ai_probability: float
    ai_detector_detail: dict
    attribution_written: Dict[str, List[str]]
    attribution_video: Dict[str, List[str]]
    explanations: dict
    rejected: bool = False
    reject_reason: str = ""


async def score_application(application_id: UUID, db: Session) -> ScoreResult:
    # 1. Load application
    app: Application = db.get(Application, application_id)
    if app is None:
        raise ValueError(f"Application {application_id} not found")

    app.status = ApplicationStatus.scoring
    db.commit()

    documents = app.documents or {}
    answers: List[Answer] = app.answers

    written_answers = [a for a in answers if a.source == AnswerSource.form and a.text]
    video_answers = [a for a in answers if a.source == AnswerSource.video]

    question_ids_written = [a.question_id for a in written_answers]
    written_text = "\n\n".join(a.text for a in written_answers if a.text)

    # 2. Gate check
    app_input = _build_app_input(app, documents, answers)
    passed, reason = check_gate(app_input)
    if not passed:
        _save_rejection(app, reason, db)
        return ScoreResult(
            application_id=application_id,
            zone="C", final_score=0.0,
            struct=0.0, nlp_written={}, nlp_video={},
            consistency_score=0.0, ai_probability=0.0,
            ai_detector_detail={}, attribution_written={},
            attribution_video={}, explanations={"summary": reason},
            rejected=True, reject_reason=reason,
        )

    # 3. Structural score
    s_score = struct_score(app_input)

    # 4. NLP written
    nlp_written_scores, attr_written = nlp_model.score(written_text, question_ids_written)
    nlp_written_val = nlp_model.compute_nlp_score(nlp_written_scores)

    # 5. AI detector
    ai_result = ai_detector.analyze(written_text)
    _save_score(
        app, ScoreLayer.nlp_written,
        scores=nlp_written_scores,
        attribution=attr_written,
        ai_probability=ai_result.composite,
        ai_detector_detail={
            "perplexity": ai_result.perplexity,
            "burstiness": ai_result.burstiness,
            "specificity": ai_result.specificity,
            "composite": ai_result.composite,
        },
        db=db,
    )

    # 6 & 7. Transcription + NLP video
    nlp_video_scores: Dict[str, float] = {}
    attr_video: Dict[str, List[str]] = {}
    nlp_video_val = 0.0

    video_answer = video_answers[0] if video_answers else None
    transcript = ""
    if video_answer:
        if video_answer.transcript:
            transcript = video_answer.transcript
        elif video_answer.video_url:
            try:
                transcript = await transcriber_mod.transcribe(video_answer.video_url)
                video_answer.transcript = transcript
                db.commit()
            except Exception as exc:
                log.warning("Transcription failed: %s", exc)

        if transcript:
            video_qids = [video_answer.question_id] if video_answer.question_id else []
            nlp_video_scores, attr_video = nlp_model.score(transcript, video_qids)
            nlp_video_val = nlp_model.compute_nlp_score(nlp_video_scores)
            _save_score(app, ScoreLayer.nlp_video, scores=nlp_video_scores, attribution=attr_video, db=db)

    # 8. Consistency
    if nlp_video_scores:
        cons_score = consistency.compute(nlp_written_scores, nlp_video_scores)
    else:
        cons_score = 1.0  # no video → neutral

    # 9. Final score + zone
    nlp_combined = (
        nlp_written_val * (0.6 if nlp_video_scores else 1.0) +
        nlp_video_val * (0.4 if nlp_video_scores else 0.0)
    )
    regional_coeff = get_regional_coeff(app.city, app.country)
    app.regional_coeff = regional_coeff

    final = (nlp_combined * settings.NLP_WEIGHT + s_score * settings.STRUCT_WEIGHT) * regional_coeff
    final = round(min(final, 10.0), 4)

    zone = _compute_zone(final, cons_score, ai_result.composite)

    # 10. LLM explanations
    explanations: dict = {}
    try:
        explanations = llm_explainer.explain({
            "scores": nlp_written_scores,
            "attribution": attr_written,
            "ai_detector": {
                "perplexity": ai_result.perplexity,
                "burstiness": ai_result.burstiness,
                "specificity": ai_result.specificity,
                "composite": ai_result.composite,
            },
            "regional_coeff": regional_coeff,
            "city": app.city,
            "zone": zone,
            "final_score": final,
            "struct_score": s_score,
            "consistency_score": cons_score,
        })
    except Exception as exc:
        log.warning("LLM explainer failed: %s", exc)

    # 11. Save final score record
    _save_score(
        app, ScoreLayer.rule,
        scores={"struct_score": s_score},
        consistency_score=cons_score,
        zone=zone,
        final_score=final,
        explanations=explanations,
        ai_probability=ai_result.composite,
        ai_detector_detail={
            "perplexity": ai_result.perplexity,
            "burstiness": ai_result.burstiness,
            "specificity": ai_result.specificity,
            "composite": ai_result.composite,
        },
        db=db,
    )

    # 12. Update application status
    if zone == "A":
        app.status = ApplicationStatus.zone_a
    elif zone == "B":
        app.status = ApplicationStatus.awaiting_interview
    else:
        app.status = ApplicationStatus.zone_c

    db.commit()

    return ScoreResult(
        application_id=application_id,
        zone=zone,
        final_score=final,
        struct=s_score,
        nlp_written=nlp_written_scores,
        nlp_video=nlp_video_scores,
        consistency_score=cons_score,
        ai_probability=ai_result.composite,
        ai_detector_detail={
            "perplexity": ai_result.perplexity,
            "burstiness": ai_result.burstiness,
            "specificity": ai_result.specificity,
            "composite": ai_result.composite,
        },
        attribution_written=attr_written,
        attribution_video=attr_video,
        explanations=explanations,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app_input(app: Application, documents: dict, answers: List[Answer]) -> ApplicationInput:
    total_q = len([a for a in answers if a.source == AnswerSource.form])
    filled_q = len([a for a in answers if a.source == AnswerSource.form and a.text])
    return ApplicationInput(
        country=app.country,
        city=app.city,
        ent_score=documents.get("ent_score"),
        gpa=documents.get("gpa"),
        ielts_score=documents.get("ielts_score"),
        toefl_score=documents.get("toefl_score"),
        duolingo_score=documents.get("duolingo_score"),
        answers_count=filled_q,
        total_questions=max(total_q, 1),
    )


def _compute_zone(final: float, cons: float, ai_prob: float) -> str:
    if (final >= settings.ZONE_A_THRESHOLD
            and cons >= settings.CONSISTENCY_THRESHOLD
            and ai_prob < 0.20):
        return "A"
    if (final < settings.ZONE_B_THRESHOLD
            or ai_prob > settings.AI_DETECTOR_THRESHOLD):
        return "C"
    return "B"


def _save_score(app: Application, layer: ScoreLayer, db: Session, **kwargs) -> Score:
    score = Score(application_id=app.id, layer=layer, **kwargs)
    db.add(score)
    db.flush()
    return score


def _save_rejection(app: Application, reason: str, db: Session) -> None:
    app.status = ApplicationStatus.rejected
    explanations = {"summary": reason, "zone_explanation": reason}
    try:
        explanations = llm_explainer.explain({
            "scores": {},
            "ai_detector": {},
            "zone": "C",
            "final_score": 0.0,
            "struct_score": 0.0,
            "reject_reason": reason,
        })
        explanations["summary"] = reason
    except Exception:
        pass
    _save_score(
        app, ScoreLayer.rule,
        scores={}, zone="C", final_score=0.0,
        explanations=explanations,
        db=db,
    )
    db.commit()
