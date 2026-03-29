import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from langdetect import LangDetectException, detect
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings

DATA_DIR = Path(__file__).parent.parent / "data"

QUALITY_WEIGHTS: Dict[str, float] = {
    "leadership":           0.20,
    "motivation":           0.22,
    "perseverance":         0.16,
    "teamwork":             0.12,
    "goal_pursuit":         0.10,
    "intrinsic_motivation": 0.10,
    "prosocial_purpose":    0.10,
}

QUESTION_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "V2":      {"perseverance": 1.5},
    "V4":      {"leadership":   1.5},
    "V5":      {"teamwork":     1.5},
    "V4_bach": {"goal_pursuit": 1.3},
    "P5":      {"intrinsic_motivation": 1.3},
}

QUALITIES: List[str] = list(QUALITY_WEIGHTS.keys())


def _load_keywords() -> Dict[str, Dict[str, List[str]]]:
    result: Dict[str, Dict[str, List[str]]] = {}
    for lang, fname in [("ru", "leadership_keywords_ru.json"), ("kz", "leadership_keywords_kz.json")]:
        path = DATA_DIR / fname
        if path.exists():
            with open(path, encoding="utf-8") as f:
                result[lang] = json.load(f)
    return result


class NLPModel:
    def __init__(self) -> None:
        self._fallback: Optional[SentenceTransformer] = None
        self._pkl_models: Dict[str, object] = {}
        self._keywords: Dict[str, Dict[str, List[str]]] = _load_keywords()
        self._kw_embeddings: Dict[str, Dict[str, np.ndarray]] = {}
        self._ready = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def score(
        self,
        text: str,
        question_ids: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
        """Return (quality_scores 0–10, attribution keywords)."""
        self._ensure_ready()
        lang = self._detect_lang(text)

        if lang in self._pkl_models:
            raw_scores, attribution = self._score_pkl(text, lang)
        else:
            raw_scores, attribution = self._score_fallback(text, lang)

        raw_scores = self._apply_multipliers(raw_scores, question_ids or [])
        scores = {k: round(min(v * 10, 10.0), 2) for k, v in raw_scores.items()}
        return scores, attribution

    def compute_nlp_score(self, quality_scores: Dict[str, float]) -> float:
        return round(sum(quality_scores.get(q, 0.0) * QUALITY_WEIGHTS[q] for q in QUALITIES), 4)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _ensure_ready(self) -> None:
        if self._ready:
            return
        self._fallback = SentenceTransformer(settings.NLP_FALLBACK_MODEL)
        self._precompute_kw_embeddings()
        self._load_pkl_models()
        self._ready = True

    def _load_pkl_models(self) -> None:
        for lang, path_str in [
            ("en", settings.NLP_MODEL_EN),
            ("ru", settings.NLP_MODEL_RU),
            ("kz", settings.NLP_MODEL_KZ),
        ]:
            path = Path(path_str)
            if path.exists():
                with open(path, "rb") as f:
                    self._pkl_models[lang] = pickle.load(f)

    def _precompute_kw_embeddings(self) -> None:
        assert self._fallback is not None
        for lang, kw_dict in self._keywords.items():
            self._kw_embeddings[lang] = {}
            for quality, words in kw_dict.items():
                if words:
                    self._kw_embeddings[lang][quality] = self._fallback.encode(
                        words, convert_to_numpy=True, show_progress_bar=False
                    )

    # ------------------------------------------------------------------
    # Scoring backends
    # ------------------------------------------------------------------

    def _score_fallback(
        self, text: str, lang: str
    ) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
        assert self._fallback is not None
        text_emb = self._fallback.encode([text], convert_to_numpy=True)

        kw_lang = lang if lang in self._kw_embeddings else "ru"
        kw_embs = self._kw_embeddings.get(kw_lang, {})
        kw_words = self._keywords.get(kw_lang, {})

        raw_scores: Dict[str, float] = {}
        attribution: Dict[str, List[str]] = {}

        for quality in QUALITIES:
            embs = kw_embs.get(quality)
            if embs is not None and len(embs) > 0:
                sims = cosine_similarity(text_emb, embs)[0]
                raw_scores[quality] = float(np.mean(sims))
                top_idx = np.argsort(sims)[-3:][::-1]
                words = kw_words.get(quality, [])
                attribution[quality] = [words[i] for i in top_idx if i < len(words)]
            else:
                raw_scores[quality] = 0.5
                attribution[quality] = []

        return raw_scores, attribution

    def _score_pkl(
        self, text: str, lang: str
    ) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
        assert self._fallback is not None
        clf_data = self._pkl_models[lang]
        model = clf_data["model"]
        vectorizer = clf_data.get("vectorizer")

        features = vectorizer.transform([text]) if vectorizer else \
            self._fallback.encode([text], convert_to_numpy=True)

        proba = model.predict_proba(features)[0]
        raw_scores = {q: float(proba[i]) if i < len(proba) else 0.5
                      for i, q in enumerate(QUALITIES)}

        kw_lang = lang if lang in self._keywords else "ru"
        attribution = self._keyword_attribution(text, kw_lang)
        return raw_scores, attribution

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_lang(self, text: str) -> str:
        try:
            lang = detect(text)
            return {"ru": "ru", "kk": "kz", "en": "en"}.get(lang, "fallback")
        except LangDetectException:
            return "fallback"

    def _apply_multipliers(
        self, scores: Dict[str, float], question_ids: List[str]
    ) -> Dict[str, float]:
        result = dict(scores)
        for qid in question_ids:
            for quality, mult in QUESTION_MULTIPLIERS.get(qid, {}).items():
                if quality in result:
                    result[quality] = min(result[quality] * mult, 1.0)
        return result

    def _keyword_attribution(self, text: str, lang: str) -> Dict[str, List[str]]:
        text_lower = text.lower()
        return {
            quality: [kw for kw in words if kw.lower() in text_lower][:3]
            for quality, words in self._keywords.get(lang, {}).items()
        }


nlp_model = NLPModel()
