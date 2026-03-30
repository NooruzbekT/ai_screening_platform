"""
Объединяет три файла в финальный dataset.json
Запуск после silver_labeling.py:
    python merge_dataset.py
"""

import json
import random
from pathlib import Path
from collections import Counter


def load(path: str) -> list:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def check_balance(data: list, name: str):
    qualities = Counter(r['primary_quality'] for r in data)
    levels    = Counter(r['level'] for r in data)
    langs     = Counter(r['lang'] for r in data)
    avg_len   = sum(len(r['text'].split()) for r in data) // len(data)
    print(f"\n{name} ({len(data)} записей, avg {avg_len} слов):")
    print(f"  Qualities: {dict(qualities)}")
    print(f"  Levels:    {dict(levels)}")
    print(f"  Langs:     {dict(langs)}")


def main():
    files = {
        "EN (ASAP)": "en_labeled.json",
        "RU":        "ru_part.json",
        "KZ":        "kz_part.json",
    }

    all_data = []
    for name, path in files.items():
        if not Path(path).exists():
            print(f"WARNING: {path} not found, skipping")
            continue
        data = load(path)
        check_balance(data, name)
        all_data.extend(data)

    # перемешиваем
    random.seed(42)
    random.shuffle(all_data)

    # финальная статистика
    check_balance(all_data, "ИТОГО")

    # проверка обязательных полей
    required = {"id","text","lang","source","primary_quality","level","scores"}
    bad = [r for r in all_data if not required.issubset(r.keys())]
    if bad:
        print(f"\nWARNING: {len(bad)} записей с неполными полями!")

    # проверка scores
    quality_keys = {"leadership","motivation","perseverance","teamwork",
                    "goal_pursuit","intrinsic_motivation","prosocial_purpose"}
    bad_scores = [r for r in all_data if not quality_keys.issubset(r['scores'].keys())]
    if bad_scores:
        print(f"WARNING: {len(bad_scores)} записей с неполными scores!")

    # сохранить
    with open("dataset.json", 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Сохранено: dataset.json ({len(all_data)} записей)")
    print("  Отправь dataset.json команде для обучения на Google Colab.")


if __name__ == "__main__":
    main()
