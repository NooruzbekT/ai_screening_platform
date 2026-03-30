"""Consistency between written and video NLP quality scores."""

from __future__ import annotations

from typing import Dict

import numpy as np

from app.models.nlp_model import QUALITIES


def compute(
    written_scores: Dict[str, float],
    video_scores: Dict[str, float],
) -> float:
    """Cosine similarity between two quality-score vectors.

    Returns float in [0, 1]. High → consistent story across written + video.
    """
    w = np.array([written_scores.get(q, 0.0) for q in QUALITIES], dtype=float)
    v = np.array([video_scores.get(q, 0.0) for q in QUALITIES], dtype=float)

    norm_w = np.linalg.norm(w)
    norm_v = np.linalg.norm(v)
    if norm_w == 0 or norm_v == 0:
        return 0.0

    similarity = float(np.dot(w, v) / (norm_w * norm_v))
    return round(max(0.0, min(similarity, 1.0)), 4)


def find_contradictions(
    written_scores: Dict[str, float],
    video_scores: Dict[str, float],
    top_n: int = 2,
) -> list[Dict]:
    """Return top-N qualities where written vs video diverge most."""
    diffs = []
    for q in QUALITIES:
        w = written_scores.get(q, 0.0)
        v = video_scores.get(q, 0.0)
        diffs.append({"quality": q, "written": w, "video": v, "delta": abs(w - v)})

    diffs.sort(key=lambda x: x["delta"], reverse=True)
    return diffs[:top_n]
