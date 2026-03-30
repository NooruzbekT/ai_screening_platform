"""Video transcription via local Whisper."""

from __future__ import annotations

import os
import tempfile
from typing import Optional

import httpx

from app.core.config import settings

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(settings.WHISPER_MODEL)
    return _whisper_model


async def transcribe(video_url: str, language: Optional[str] = None) -> str:
    """Download video/audio from URL and return Whisper transcript."""
    audio_data = await _download(video_url)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        model = _get_model()
        kwargs = {}
        if language:
            kwargs["language"] = language
        result = model.transcribe(tmp_path, **kwargs)
        return result["text"].strip()
    finally:
        os.unlink(tmp_path)


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content
