"""AI-authorship detector.

Three explainable metrics (shown to the commission):
  perplexity  — via GPT-2 (local). Low value → likely AI.
  burstiness  — std(sent_lengths) / mean(sent_lengths). Low → AI.
  specificity — NER_count / total_tokens via spaCy. Low → AI.
  composite   — average of three normalised [0, 1] AI-scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import nltk
import numpy as np

# ---------------------------------------------------------------------------
# Lazy-loaded heavy deps
# ---------------------------------------------------------------------------
_gpt2_model = None
_gpt2_tokenizer = None
_spacy_nlp = None


def _get_gpt2():
    global _gpt2_model, _gpt2_tokenizer
    if _gpt2_model is None:
        import torch
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast

        _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")
        _gpt2_model = GPT2LMHeadModel.from_pretrained("gpt2")
        _gpt2_model.eval()
    return _gpt2_tokenizer, _gpt2_model


def _get_spacy():
    global _spacy_nlp
    if _spacy_nlp is None:
        import spacy

        try:
            _spacy_nlp = spacy.load("ru_core_news_sm")
        except OSError:
            # Fallback: blank model without NER
            import spacy
            _spacy_nlp = spacy.blank("ru")
    return _spacy_nlp


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

@dataclass
class AIDetectorResult:
    perplexity: float
    burstiness: float
    specificity: float
    composite: float  # 0 = human, 1 = AI


def analyze(text: str) -> AIDetectorResult:
    perplexity = _compute_perplexity(text)
    burstiness = _compute_burstiness(text)
    specificity = _compute_specificity(text)

    composite = _composite(perplexity, burstiness, specificity)

    return AIDetectorResult(
        perplexity=round(perplexity, 2),
        burstiness=round(burstiness, 4),
        specificity=round(specificity, 4),
        composite=round(composite, 4),
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _compute_perplexity(text: str) -> float:
    """GPT-2 perplexity. Typical human text: 50–300. AI text: 10–50."""
    try:
        import torch
        tokenizer, model = _get_gpt2()
        inputs = tokenizer(
            text[:2048],  # cap to avoid OOM
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        input_ids = inputs["input_ids"]
        if input_ids.shape[1] < 2:
            return 200.0
        with torch.no_grad():
            loss = model(input_ids, labels=input_ids).loss
        return float(math.exp(loss.item()))
    except Exception:
        return 200.0  # fallback → human-like


def _compute_burstiness(text: str) -> float:
    """Ratio std/mean of sentence lengths (in tokens).
    Human text: > 0.3. AI text: < 0.2.
    """
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)

    try:
        sentences = nltk.sent_tokenize(text)
        if len(sentences) < 2:
            return 0.5  # neutral
        lengths = [len(s.split()) for s in sentences]
        mean = np.mean(lengths)
        std = np.std(lengths)
        return float(std / mean) if mean > 0 else 0.0
    except Exception:
        return 0.5


def _compute_specificity(text: str) -> float:
    """NER entities per token. Human text: > 0.02. AI text: < 0.01."""
    try:
        nlp = _get_spacy()
        doc = nlp(text[:5000])
        total_tokens = len([t for t in doc if not t.is_space])
        if total_tokens == 0:
            return 0.0
        ner_count = len(doc.ents)
        return ner_count / total_tokens
    except Exception:
        return 0.02  # neutral


# ---------------------------------------------------------------------------
# Composite normalisation
# ---------------------------------------------------------------------------

def _composite(perplexity: float, burstiness: float, specificity: float) -> float:
    """Each metric → [0, 1] where 1 = AI. Average."""
    # Perplexity: sigmoid centred at 50, scale=30
    # perplexity=10 → ~0.93 (AI); perplexity=200 → ~0.02 (human)
    p_ai = 1.0 / (1.0 + math.exp((perplexity - 50) / 30))

    # Burstiness: 0.3 = human threshold; below → AI
    # burstiness=0.05 → 0.83; burstiness=0.5 → 0.07
    b_ai = 1.0 / (1.0 + math.exp((burstiness - 0.15) / 0.08))

    # Specificity: 0.02 = threshold; below → AI
    s_ai = 1.0 / (1.0 + math.exp((specificity - 0.015) / 0.008))

    return (p_ai + b_ai + s_ai) / 3.0
