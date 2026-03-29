import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "regional_coeffs.json", encoding="utf-8") as _f:
    _REGIONAL = json.load(_f)

_FOREIGN_COUNTRIES: set = set(_REGIONAL.get("foreign_countries", {}).keys())


@dataclass
class ApplicationInput:
    country: str
    city: Optional[str]
    ent_score: Optional[int]
    gpa: Optional[float]
    ielts_score: Optional[float]
    toefl_score: Optional[int]
    duolingo_score: Optional[int]
    answers_count: int
    total_questions: int


def check_gate(app: ApplicationInput) -> Tuple[bool, str]:
    if app.country == "KZ":
        if app.ent_score is None:
            return False, "Для казахстанских абитуриентов обязателен результат ЕНТ"
        if app.ent_score < 80:
            return False, f"Результат ЕНТ ({app.ent_score}) ниже минимального порога 80 баллов"
    elif app.country in _FOREIGN_COUNTRIES:
        if app.gpa is None:
            return False, "Для иностранных абитуриентов обязателен GPA"
        if not _has_valid_language_test(app):
            return False, "Требуется языковой тест: IELTS ≥6.0, TOEFL ≥60 или Duolingo ≥105"
    else:
        return False, f"Страна {app.country} не поддерживается"

    return True, "Gate passed"


def struct_score(app: ApplicationInput) -> float:
    if app.country == "KZ":
        ent_norm = min((app.ent_score - 80) / (140 - 80), 1.0) if app.ent_score else 0.0
    elif app.country in _FOREIGN_COUNTRIES:
        ent_norm = min(app.gpa / 10.0, 1.0) if app.gpa else 0.0
    else:
        ent_norm = 0.0

    lang_norm = _lang_score_normalized(app)
    completeness = app.answers_count / app.total_questions if app.total_questions > 0 else 0.0

    raw = ent_norm * 0.5 + lang_norm * 0.3 + completeness * 0.2
    return round(raw * 10, 2)  # 0–10 scale


def get_regional_coeff(city: Optional[str], country: str) -> float:
    if country != "KZ":
        return _REGIONAL["foreign_countries"].get(country, 1.0)
    if city:
        coeff = _REGIONAL["cities"].get(city)
        if coeff is not None:
            return coeff
    return _REGIONAL["default"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_valid_language_test(app: ApplicationInput) -> bool:
    if app.ielts_score is not None and app.ielts_score >= 6.0:
        return True
    if app.toefl_score is not None and app.toefl_score >= 60:
        return True
    if app.duolingo_score is not None and app.duolingo_score >= 105:
        return True
    return False


def _lang_score_normalized(app: ApplicationInput) -> float:
    if app.ielts_score is not None and app.ielts_score >= 6.0:
        return min((app.ielts_score - 6.0) / (9.0 - 6.0), 1.0)
    if app.toefl_score is not None and app.toefl_score >= 60:
        return min((app.toefl_score - 60) / (120 - 60), 1.0)
    if app.duolingo_score is not None and app.duolingo_score >= 105:
        return min((app.duolingo_score - 105) / (160 - 105), 1.0)
    return 0.0
