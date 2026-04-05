"""LLM explanations (Groq) and TTS audio generation (edge-tts)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Dict, Optional

from groq import Groq

from app.core.config import settings

_groq_client: Optional[Groq] = None
_anthropic_client = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


def _get_claude():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def _claude(prompt: str, model: str, max_tokens: int = 800) -> str:
    client = _get_claude()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _groq(prompt: str, max_tokens: int = 600, temperature: float = 0.3) -> str:
    client = _get_groq()
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Explanations for reviewer dashboard
# ---------------------------------------------------------------------------

def explain(payload: dict) -> Dict[str, str]:
    """Generate Russian explanations via Claude Sonnet (falls back to Groq)."""
    prompt = _build_explain_prompt(payload)
    try:
        if settings.ANTHROPIC_API_KEY:
            raw = _claude(prompt, settings.CLAUDE_MODEL_HEAVY, max_tokens=800)
        else:
            raw = _groq(prompt, max_tokens=600)
    except Exception:
        raw = _groq(prompt, max_tokens=600)
    return _parse_explain_response(raw, payload)


def _build_explain_prompt(p: dict) -> str:
    scores_str = json.dumps(p.get("scores", {}), ensure_ascii=False, indent=2)
    ai = p.get("ai_detector", {})
    zone = p.get("zone", "?")
    final_score = p.get("final_score", 0.0)
    struct_score = p.get("struct_score", 0.0)
    consistency = p.get("consistency_score")
    reject_reason = p.get("reject_reason", "")

    if reject_reason:
        zone_hint = (
            f"Автоотклонение. Причина: {reject_reason}. "
            f"Объясни это в zone_explanation одним предложением."
        )
    else:
        cons_str = f"{consistency:.2f}" if consistency is not None else "—"
        zone_hint = (
            f"Итоговый скор: {final_score:.2f}/10 "
            f"(NLP×0.7 + структурный {struct_score:.2f}×0.3 × регион.коэф.). "
            f"Согласованность письмо/видео: {cons_str}. "
            f"AI-вероятность: {ai.get('composite', '—')}. "
            f"Зона: {zone}. "
            f"В zone_explanation объясни КОНКРЕТНО почему именно эта зона — "
            f"цитируй числа, порог, что перевесило."
        )

    return f"""Ты аналитик приёмной комиссии inVision U (Казахстан).
Тебе даны числовые скоры NLP-анализа заявки кандидата.
Объясни каждый скор одним-двумя предложениями на русском — кратко и конкретно.
Не выставляй новые числа. Используй только данные ниже.

Скоры качеств (0–10):
{scores_str}

AI-детектор: перплексия={ai.get('perplexity')}, burstiness={ai.get('burstiness')}, specificity={ai.get('specificity')}, composite={ai.get('composite')}
Регион: {p.get('city', '—')}, коэффициент={p.get('regional_coeff', 1.0)}

{zone_hint}

Ответь строго в формате JSON:
{{
  "zone_explanation": "2-3 предложения: почему именно эта зона, конкретные числа",
  "summary": "общий вывод об уровне кандидата",
  "leadership": "объяснение",
  "motivation": "объяснение",
  "perseverance": "объяснение",
  "teamwork": "объяснение",
  "goal_pursuit": "объяснение",
  "intrinsic_motivation": "объяснение",
  "prosocial_purpose": "объяснение",
  "ai_comment": "комментарий по AI-детектору"
}}"""


def _parse_explain_response(raw: str, payload: dict) -> Dict[str, str]:
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"summary": raw}


# ---------------------------------------------------------------------------
# Interview question generation
# ---------------------------------------------------------------------------

def generate_interview_questions(
    application_data: dict,
    contradictions: list,
    n_questions: int = 4,
    language: str = "ru",
) -> list[str]:
    """Generate personalised Pre-Interview questions from contradictions."""
    prompt = _build_interview_prompt(application_data, contradictions, n_questions, language)
    client = _get_client()
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400,
    )
    raw = resp.choices[0].message.content.strip()
    return _parse_questions(raw, n_questions)


def _build_interview_prompt(data: dict, contradictions: list, n: int, lang: str) -> str:
    lang_note = "Задавай вопросы на русском языке." if lang != "kk" else "Задавай вопросы на казахском языке."
    contra_str = "\n".join(
        f"- {c['quality']}: письменно={c['written']:.1f}, видео={c['video']:.1f}"
        for c in contradictions
    )
    return f"""Ты проводишь уточняющее Pre-Interview для приёмной комиссии inVision U.
{lang_note}
Задай ровно {n} вопроса по конкретным местам заявки.
Каждый вопрос — отдельная строка, начинается с цифры и точки.

Расхождения письмо vs видео:
{contra_str}

Данные кандидата: {json.dumps(data, ensure_ascii=False)}

Вопросы:"""


def _parse_questions(raw: str, n: int) -> list[str]:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    questions = []
    for line in lines:
        for sep in [". ", ") ", "- "]:
            if line[:3].replace(sep, "").isdigit():
                line = line[line.find(sep) + len(sep):]
                break
        if line:
            questions.append(line)
    return questions[:n]


def generate_next_question(
    messages: list[dict],
    system_context: str,
) -> tuple[str, bool]:
    """Continue interview. Returns (next_question, is_complete).

    messages — only role=assistant/user entries (system_context is passed separately).
    """
    answered = sum(1 for m in messages if m.get("role") == "user")
    # Inject current progress so LLM always knows where it is
    progress_note = (
        f"\n[Внутренний счётчик: кандидат уже ответил на {answered} из "
        f"отведённых вопросов. Следующий вопрос — #{answered + 1}.]"
    )
    client = _get_groq()
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "system", "content": system_context + progress_note}] + messages,
        temperature=0.6,
        max_tokens=200,
    )
    content = resp.choices[0].message.content.strip()
    is_complete = "INTERVIEW_COMPLETE" in content
    if is_complete:
        return "", True
    return content, False


# ---------------------------------------------------------------------------
# Video question generation
# ---------------------------------------------------------------------------

def generate_video_questions(
    answers: list[dict],
    nlp_scores: dict,
    program: str,
    n_questions: int = 2,
) -> list[str]:
    """Generate personalized video questions based on written answers + NLP scores."""
    weak = sorted(nlp_scores.items(), key=lambda x: x[1])[:3]
    weak_str = ", ".join(f"{q} ({s:.1f}/10)" for q, s in weak)
    answers_str = "\n".join(
        f"- Q{a['question_id']}: {(a.get('text') or '')[:250]}"
        for a in answers if a.get("text")
    )
    prompt = f"""Ты помощник приёмной комиссии inVision U (Казахстан).
Программа кандидата: {program}.

Письменные ответы:
{answers_str}

Слабые стороны по NLP-анализу: {weak_str}

Сгенерируй ровно {n_questions} вопроса для видеопрезентации.
Каждый вопрос даёт кандидату шанс раскрыть слабые стороны через конкретную историю.
Не повторяй письменные вопросы дословно.
Язык: русский. Формат: каждый вопрос с новой строки, начинается с цифры и точки.

Вопросы:"""
    try:
        if settings.ANTHROPIC_API_KEY:
            raw = _claude(prompt, settings.CLAUDE_MODEL_FAST, max_tokens=300)
        else:
            raw = _groq(prompt, max_tokens=300, temperature=0.7)
    except Exception:
        raw = _groq(prompt, max_tokens=300, temperature=0.7)
    return _parse_questions(raw, n_questions)


_QUALITY_RU = {
    "leadership":           "лидерство",
    "motivation":           "мотивация",
    "perseverance":         "настойчивость / стрессоустойчивость",
    "teamwork":             "командная работа",
    "goal_pursuit":         "целеустремлённость",
    "intrinsic_motivation": "внутренняя мотивация",
    "prosocial_purpose":    "просоциальная направленность",
}


def build_interview_system_context(
    app_data: dict,
    contradictions: list,
    max_questions: int = 4,
) -> str:
    """Build system prompt for dynamic Pre-Interview with follow-up logic."""
    answers = app_data.get("answers", [])
    answers_str = "\n".join(
        f'[{a["question_id"]}]: "{(a.get("text") or "").strip()[:300]}"'
        for a in answers if a.get("text")
    )

    has_video = any(c.get("video", 0) > 0 for c in contradictions)

    # Build numbered topic list with context from actual answers
    topics_lines = []
    for i, c in enumerate(contradictions[:max_questions], 1):
        quality_ru = _QUALITY_RU.get(c["quality"], c["quality"])
        if has_video:
            gap = c["written"] - c["video"]
            direction = "письменно выше чем в видео" if gap > 0 else "видео выше чем письменно"
            hint = f"расхождение {abs(gap):.1f} пунктов ({direction})"
        else:
            hint = f"письменный скор {c['written']:.1f}/10 — требует проверки"
        topics_lines.append(f"Тема {i}. {quality_ru.upper()} — {hint}")

    if not topics_lines:
        topics_lines = [
            "Тема 1. МОТИВАЦИЯ — уточни конкретную причину выбора программы",
            "Тема 2. ЛИДЕРСТВО — попроси конкретный пример инициативы",
        ]

    topics_str = "\n".join(topics_lines)

    return f"""Ты — интервьюер приёмной комиссии inVision U (Казахстан).
Проводишь уточняющее Pre-Interview. Всего вопросов: {max_questions}.

КАНДИДАТ: {app_data.get('full_name')}, программа: {app_data.get('program')}, город: {app_data.get('city')}

ПИСЬМЕННЫЕ ОТВЕТЫ КАНДИДАТА:
{answers_str}

ТЕМЫ ДЛЯ ПРОВЕРКИ (в порядке приоритета):
{topics_str}

════════════════════════════════════
АЛГОРИТМ — следуй строго:

Вопрос 1: задай по Теме 1, сошлись на конкретную деталь из письменного ответа.

После каждого ответа кандидата прими решение:

  ЕСЛИ ответ КОНКРЕТНЫЙ — содержит хотя бы одно из:
    • имя человека / организации
    • число / дату / срок
    • описание своего действия (я сделал / я решил / я организовал)
  → задай ОДИН уточняющий вопрос по этому же ответу: "Что конкретно ты сделал дальше?" /
    "Как ты убедил X?" / "Чем это закончилось?" — копай в детали той же истории.

  ЕСЛИ ответ ОБЩИЙ — только абстракции, нет конкретики, нет действий:
  → переходи к следующей Теме из списка. Не возвращайся к этой теме.

Дополнительные правила:
- Один вопрос за раз. Никогда не задавай два вопроса в одном сообщении.
- Не объясняй своё решение и не хвали ответы кандидата. Сразу следующий вопрос.
- Не повторяй то, о чём кандидат уже рассказал подробно.
- Язык — тот же, что использует кандидат (RU / KZ / EN).

ЗАВЕРШЕНИЕ: как только кандидат ответил на {max_questions}-й вопрос,
верни ТОЛЬКО эту строку без каких-либо добавлений: INTERVIEW_COMPLETE
════════════════════════════════════"""


# ---------------------------------------------------------------------------
# TTS via edge-tts
# ---------------------------------------------------------------------------

async def text_to_speech(text: str, language: str = "ru") -> Optional[str]:
    """Generate mp3, upload to Cloudinary (if configured) or local cache, return URL."""
    try:
        import edge_tts

        voice_map = {
            "ru": settings.TTS_VOICE_RU,
            "kk": settings.TTS_VOICE_KZ,
            "en": settings.TTS_VOICE_EN,
        }
        voice = voice_map.get(language, settings.TTS_VOICE_RU)
        filename = f"{uuid.uuid4().hex}.mp3"
        output_path = os.path.join(settings.AUDIO_CACHE_DIR, filename)

        os.makedirs(settings.AUDIO_CACHE_DIR, exist_ok=True)
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

        if settings.CLOUDINARY_CLOUD_NAME:
            import cloudinary
            import cloudinary.uploader
            cloudinary.config(
                cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                api_key=settings.CLOUDINARY_API_KEY,
                api_secret=settings.CLOUDINARY_API_SECRET,
            )
            with open(output_path, "rb") as f:
                result = cloudinary.uploader.upload(
                    f.read(),
                    public_id=filename.replace(".mp3", ""),
                    folder="invisionu/interview_audio",
                    resource_type="auto",
                    overwrite=False,
                )
            try:
                os.remove(output_path)
            except OSError:
                pass
            return result["secure_url"]

        return f"/audio/{filename}"
    except Exception:
        return None
