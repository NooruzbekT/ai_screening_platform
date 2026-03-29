"""
Silver labeling — ASAP essays → inVision U quality scores
Claude Haiku 4.5, ~$0.86 за 900 эссе
"""

import json, os, re, time
import pandas as pd
from pathlib import Path
from tqdm import tqdm
import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

ASAP_FILE   = "training_set_rel3.tsv"
OUTPUT_FILE = "en_labeled.json"
GOOD_SETS   = [1, 2, 7, 8]
MIN_WORDS   = 150
MAX_RECORDS = 900
DELAY       = 0.3
MODEL       = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

SYSTEM = """You are a data labeling expert for a university admissions AI system.
Read the student essay and score it on 7 personal qualities.

Scoring: 1-3=absent, 4-6=moderate, 7-9=clear, 10=exceptional

Qualities:
- leadership: initiating action, organizing others, influencing outcomes
- motivation: clear purpose, genuine drive, connection to personal history
- perseverance: overcoming obstacles, resilience, learning from failure
- teamwork: collaborating, considering others, collective success
- goal_pursuit: concrete goals, measurable progress, long-term thinking
- intrinsic_motivation: doing things for internal satisfaction not rewards
- prosocial_purpose: desire to help others, community focus, social impact

Rules:
- Score ONLY on text evidence
- @PERSON1 @LOCATION1 are anonymization placeholders, ignore them
- Personal stories score higher than pure opinion

Return ONLY valid JSON, no markdown, no explanation:
{"leadership":N,"motivation":N,"perseverance":N,"teamwork":N,"goal_pursuit":N,"intrinsic_motivation":N,"prosocial_purpose":N}"""


def clean(text: str) -> str:
    text = re.sub(r'@[A-Z]+\d+', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def label(client: anthropic.Anthropic, essay: str, retries=3) -> dict | None:
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=120, temperature=0.1,
                system=SYSTEM,
                messages=[{"role": "user", "content": f"Essay:\n{essay[:2000]}"}],
            )
            raw = re.sub(r'```json|```', '', msg.content[0].text.strip()).strip()
            scores = json.loads(raw)
            required = {"leadership","motivation","perseverance","teamwork",
                        "goal_pursuit","intrinsic_motivation","prosocial_purpose"}
            if not required.issubset(scores.keys()):
                raise ValueError("Missing keys")
            return {k: int(v) for k, v in scores.items() if k in required}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  Parse error {attempt+1}: {e}")
            time.sleep(1)
        except anthropic.RateLimitError:
            print("  Rate limit, waiting 10s...")
            time.sleep(10)
        except Exception as e:
            print(f"  Error {attempt+1}: {e}")
            time.sleep(2)
    return None


def main():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("Loading ASAP dataset...")
    df = pd.read_csv(ASAP_FILE, sep='\t', encoding='latin-1')
    df = df[df['essay_set'].isin(GOOD_SETS)].copy()
    df['essay_clean'] = df['essay'].apply(clean)
    df['wc'] = df['essay_clean'].str.split().str.len()
    df = df[df['wc'] >= MIN_WORDS].reset_index(drop=True)

    personal = df[df['essay_set'].isin([7, 8])].sample(frac=1, random_state=42)
    opinion  = df[df['essay_set'].isin([1, 2])].sample(frac=1, random_state=42)
    n_p = min(len(personal), int(MAX_RECORDS * 0.6))
    n_o = min(len(opinion), MAX_RECORDS - n_p)
    selected = pd.concat([personal.head(n_p), opinion.head(n_o)]).sample(frac=1, random_state=42).reset_index(drop=True)
    print(f"Selected: {len(selected)} essays ({n_p} personal + {n_o} opinion)")

    results, done_ids = [], set()
    if Path(OUTPUT_FILE).exists():
        with open(OUTPUT_FILE) as f:
            results = json.load(f)
        done_ids = {r['id'] for r in results}
        print(f"Resuming from {len(done_ids)}")

    errors = 0
    for _, row in tqdm(selected.iterrows(), total=len(selected)):
        rid = f"en_asap{int(row['essay_set'])}_{int(row['essay_id'])}"
        if rid in done_ids:
            continue

        scores = label(client, row['essay_clean'])
        if scores is None:
            errors += 1
            continue

        pq = max(scores, key=scores.get)
        pv = scores[pq]
        level = "high" if pv >= 8 else ("medium" if pv >= 5 else "low")

        results.append({
            "id": rid, "text": row['essay_clean'], "lang": "en",
            "source": "kaggle_asap", "essay_set": int(row['essay_set']),
            "word_count": int(row['wc']), "primary_quality": pq,
            "level": level, "scores": scores,
        })

        if len(results) % 50 == 0:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  Checkpoint: {len(results)}")

        time.sleep(DELAY)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    from collections import Counter
    print(f"\nDone: {len(results)} labeled, {errors} errors")
    print(f"Qualities: {dict(Counter(r['primary_quality'] for r in results))}")
    print(f"Levels:    {dict(Counter(r['level'] for r in results))}")
    print(f"Cost est:  ~${len(results) * 0.00095:.2f}")


if __name__ == "__main__":
    main()
