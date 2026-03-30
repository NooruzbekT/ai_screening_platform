"""LLM explanations (Groq) and TTS audio generation (edge-tts)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Dict, Optional

from groq import Groq

from app.core.config import settings

_groq_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
    return _groq_client


# ---------------------------------------------------------------------------
# Explanations for reviewer dashboard
# ---------------------------------------------------------------------------

def explain(payload: dict) -> Dict[str, str]:
    """Send NLP scores to Groq, return dict of Russian text explanations."""
    prompt = _build_explain_prompt(payload)
    client = _get_client()
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=600,
    )
    raw = resp.choices[0].message.content.strip()
    return _parse_explain_response(raw, payload)


def _build_explain_prompt(p: dict) -> str:
    scores_str = json.dumps(p.get("scores", {}), ensure_ascii=False, indent=2)
    ai = p.get("ai_detector", {})
    return f"""Ты аналитик приёмной комиссии inVision U (Казахстан).
Тебе даны числовые скоры NLP-анализа заявки кандидата.
Объясни каждый скор одним-двумя предложениями на русском языке — кратко и конкретно.
Не выставляй новые числа. Используй только данные ниже.

Скоры качеств (0–10):
{scores_str}

AI-детектор: перплексия={ai.get('perplexity')}, burstiness={ai.get('burstiness')}, specificity={ai.get('specificity')}, composite={ai.get('composite')}
Регион: {p.get('city', '—')}, коэффициент={p.get('regional_coeff', 1.0)}
Зона: {p.get('zone', '?')}

Ответь строго в формате JSON:
{{
  "summary": "общий вывод",
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
    language: str = "ru",
) -> tuple[str, bool]:
    """Continue interview. Returns (next_question_or_done, is_complete)."""
    client = _get_client()
    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "system", "content": system_context}] + messages,
        temperature=0.7,
        max_tokens=200,
    )
    content = resp.choices[0].message.content.strip()
    is_complete = "INTERVIEW_COMPLETE" in content
    if is_complete:
        return "", True
    return content, False


# ---------------------------------------------------------------------------
# TTS via edge-tts
# ---------------------------------------------------------------------------

async def text_to_speech(text: str, language: str = "ru") -> Optional[str]:
    """Generate mp3, save to AUDIO_CACHE_DIR, return relative URL path."""
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

        return f"/audio/{filename}"
    except Exception:
        return None
