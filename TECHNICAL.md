# inVision U — Technical Reference

## Архитектура

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, startup (DB + models warmup)
│   ├── core/config.py           # Settings (pydantic-settings, .env)
│   ├── api/
│   │   ├── routes.py            # Все эндпоинты
│   │   └── schemas.py           # Pydantic request/response модели
│   ├── db/
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── models.py            # ORM модели
│   │   └── migrations/          # Alembic
│   ├── models/
│   │   ├── scorer.py            # Оркестратор: запускает все слои по порядку
│   │   ├── rule_engine.py       # Слой 1: gate check + struct score
│   │   ├── nlp_model.py         # Слой 2: NLP scoring (7 качеств)
│   │   ├── ai_detector.py       # AI-детектор: perplexity/burstiness/NER
│   │   ├── consistency.py       # Cosine similarity письмо vs видео
│   │   ├── transcriber.py       # Whisper транскрипция видео
│   │   └── llm_explainer.py     # Groq: объяснения + TTS + интервью
│   └── data/
│       ├── regional_coeffs.json
│       ├── leadership_keywords_ru.json
│       └── leadership_keywords_kz.json
├── download_models.py           # Авто-загрузка .pkl из HuggingFace при старте
├── models_trained/              # roberta_en.pkl / rubert_ru.pkl / mbert_kz.pkl
└── audio_cache/                 # TTS mp3 (edge-tts)
```

---

## Переменные окружения

| Переменная | Обязательна | Описание |
|-----------|-------------|---------|
| `GROQ_API_KEY` | Да | console.groq.com |
| `DATABASE_URL` | Да | `postgresql://user:pass@host:5432/db` |
| `JWT_SECRET` | Да | Минимум 32 символа |
| `HF_TOKEN` | Нет | HuggingFace token для загрузки .pkl моделей |
| `HF_REPO_ID` | Нет | `Nooruzbek/invisionu-models` |
| `GROQ_MODEL` | Нет | `llama-3.3-70b-versatile` |
| `ZONE_A_THRESHOLD` | Нет | `8.0` |
| `ZONE_B_THRESHOLD` | Нет | `6.0` |
| `AI_DETECTOR_THRESHOLD` | Нет | `0.60` |
| `CONSISTENCY_THRESHOLD` | Нет | `0.60` |
| `NLP_WEIGHT` | Нет | `0.70` |
| `STRUCT_WEIGHT` | Нет | `0.30` |
| `WHISPER_MODEL` | Нет | `medium` |
| `JWT_EXPIRE_HOURS` | Нет | `24` |

---

## Scoring Pipeline

### Порядок выполнения (`scorer.py`)

```
1. check_gate(app_input)
   → KZ: ENT >= 80
   → KG/UZ/TJ/TM: GPA + языковой тест
   → fail → статус rejected, zone C

2. struct_score(app_input) → float 0–10
   = ENT_norm*0.5 + lang_norm*0.3 + completeness*0.2

3. nlp_model.score(written_text) → scores{7 качеств}, attribution
   → определяет язык (langdetect)
   → .pkl модель если есть, иначе MiniLM fallback

4. ai_detector.analyze(written_text)
   → perplexity (GPT-2)
   → burstiness (std/mean длин предложений)
   → specificity (NER count / tokens, spaCy)
   → composite = среднее трёх нормализованных

5. transcriber.transcribe(video_url) → transcript

6. nlp_model.score(transcript) → nlp_video scores

7. consistency.compute(written_scores, video_scores)
   → cosine similarity векторов 7 качеств

8. final_score = (nlp_combined * NLP_WEIGHT + struct * STRUCT_WEIGHT) * regional_coeff
   nlp_combined = written*0.6 + video*0.4 (если есть видео)

9. zone:
   A: final >= 8.0 AND consistency >= 0.60 AND ai < 0.20
   C: final < 6.0 OR ai > 0.60
   B: всё остальное

10. llm_explainer.explain({scores, ai_detector, zone, final_score, ...})
    → Groq генерирует zone_explanation + объяснения по каждому качеству

11. Сохранить Score записи: nlp_written / nlp_video / rule
12. Обновить статус заявки
```

### Post-Interview Pipeline

```
После 4-го ответа кандидата:

1. nlp_model.score(все ответы интервью) → interview_nlp
2. ai_detector.analyze(interview_text) → ai_interview
3. consistency.compute(written_scores, interview_nlp) → new_cons
4. blended_final = old_final * 0.70 + interview_nlp_val * 10 * 0.30
5. zone_a = blended_final >= 8.0 AND new_cons >= 0.60 AND ai_interview < 0.20
6. Сохранить ScoreLayer.interview
7. Обновить статус: zone_a или zone_c
```

---

## Формулы

```python
# Структурный скор
struct = ENT_norm*0.5 + lang_norm*0.3 + completeness*0.2   # → 0–10

# NLP скор
nlp = sum(score[q] * weight[q] for q in 7_qualities)       # → 0–10

# Веса качеств
leadership=0.20, motivation=0.22, perseverance=0.16,
teamwork=0.12, goal_pursuit=0.10,
intrinsic_motivation=0.10, prosocial_purpose=0.10

# Итоговый скор
final = (nlp*0.70 + struct*0.30) * regional_coeff          # → 0–10

# AI-детектор composite
p_ai = sigmoid((50 - perplexity) / 30)   # perplexity < 50 → AI
b_ai = sigmoid((0.15 - burstiness) / 0.08)
s_ai = sigmoid((0.015 - specificity) / 0.008)
composite = (p_ai + b_ai + s_ai) / 3
```

---

## API Reference

Базовый URL: `https://invisionu-screening.up.railway.app`

Авторизация: `Authorization: Bearer <JWT token>`

---

### Auth

#### `POST /api/auth/register`
Регистрация пользователя.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "min8chars",
  "full_name": "Иван Иванов",
  "role": "applicant"
}
```
`role`: `"applicant"` | `"reviewer"`

**Response `201`:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "role": "applicant",
  "user_id": "uuid"
}
```

---

#### `POST /api/auth/login`
**Body:**
```json
{ "email": "user@example.com", "password": "pass" }
```
**Response `200`:** аналогично register.

---

### Applications (Applicant)

#### `POST /api/applications`
Создать заявку. Требует auth (любая роль).

**Body:**
```json
{
  "program": "foundation",
  "country": "KZ",
  "city": "Алматы"
}
```
`program`: `"foundation"` | `"bachelor"`

**Response `201`:**
```json
{
  "id": "uuid",
  "status": "draft",
  "program": "foundation",
  "created_at": "2025-04-04T...",
  "updated_at": "2025-04-04T..."
}
```

---

#### `PUT /api/applications/{id}/documents`
Загрузить документы.

**Body:**
```json
{
  "ent_score": 91,
  "ielts_score": 6.5,
  "toefl_score": null,
  "duolingo_score": null,
  "gpa": null,
  "graduation_year": 2024,
  "school_name": "Школа №12"
}
```
**Response `200`:** `ApplicationStatusResponse`

---

#### `PUT /api/applications/{id}/answers`
Сохранить письменные ответы.

**Body:**
```json
{
  "answers": [
    { "question_id": "V2", "text": "В 2023 году..." },
    { "question_id": "V4", "text": "Я основала кружок..." }
  ]
}
```
**Response `200`:** `ApplicationStatusResponse`

---

#### `PUT /api/applications/{id}/video`
Загрузить ссылку на видео-презентацию.

**Body:**
```json
{ "question_id": "V1_video", "video_url": "https://..." }
```
**Response `200`:** `ApplicationStatusResponse`

---

#### `POST /api/applications/{id}/submit`
Отправить заявку на скоринг. Запускает pipeline в фоне.

**Response `200`:**
```json
{ "id": "uuid", "status": "submitted", ... }
```
После завершения скоринга статус станет `zone_a` / `zone_b` / `zone_c` / `awaiting_interview` / `rejected`.

---

#### `GET /api/applications/{id}/status`
Статус своей заявки (applicant видит только enum, не числа).

**Response `200`:**
```json
{ "id": "uuid", "status": "zone_a", "program": "foundation", ... }
```

---

#### `GET /api/applications/{id}/video-questions`
Получить персонализированные вопросы для видео-презентации (генерирует Groq на основе письменных ответов).

**Response `200`:**
```json
{ "questions": ["Расскажи про случай...", "Опиши момент когда..."] }
```

---

### Pre-Interview (Zone B, Applicant)

#### `POST /api/interview/{app_id}/start`
Начать Pre-Interview. Доступно только при `status=awaiting_interview`.
Если сессия уже существует — возвращает текущий вопрос (без дубликата).

**Response `200`:**
```json
{
  "interview_id": "uuid",
  "question": "Ты упомянул штаб из 47 волонтёров — как именно ты их распределял?",
  "audio_url": "/audio/abc123.mp3",
  "question_number": 1,
  "total_questions": 4
}
```

---

#### `POST /api/interview/{interview_id}/message`
Отправить ответ. Фронт транскрибирует голос через Web Speech API.

**Body:**
```json
{ "text": "Я разбил их на 5 групп по районам..." }
```

**Response `200` (не последний вопрос):**
```json
{
  "next_question": "47 человек за 72 часа — в какой момент ты понял что не справляешься?",
  "audio_url": "/audio/def456.mp3",
  "is_complete": false,
  "question_number": 2
}
```

**Response `200` (последний вопрос):**
```json
{
  "is_complete": true,
  "new_zone": "A"
}
```
`new_zone`: `"A"` | `"C"` — результат после NLP-анализа интервью.

---

### Questions (Reviewer CRUD)

#### `GET /api/questions?program=foundation`
Список вопросов (публичный, без auth).

**Response `200`:**
```json
[
  { "id": "uuid", "program": "foundation", "order": 1, "text": "Опишите...", "created_at": "..." }
]
```

---

#### `POST /api/questions` *(reviewer)*
**Body:**
```json
{ "program": "foundation", "order": 1, "text": "Расскажи о случае..." }
```
**Response `201`:** `QuestionResponse`

---

#### `PUT /api/questions/{id}` *(reviewer)*
**Body:**
```json
{ "order": 2, "text": "Обновлённый текст вопроса" }
```

---

#### `DELETE /api/questions/{id}` *(reviewer)*
**Response `204`**

---

### Dashboard & Detail (Reviewer)

#### `GET /api/dashboard`
Список заявок с фильтрацией и пагинацией.

**Query params:**
| Параметр | Тип | Описание |
|---------|-----|---------|
| `zone` | `A`\|`B`\|`C` | Фильтр по зоне |
| `status` | string | Фильтр по статусу (`zone_a`, `shortlisted`, ...) |
| `program` | `foundation`\|`bachelor` | Фильтр по программе |
| `page` | int (≥1) | Страница, default=1 |
| `page_size` | int (1–200) | Размер страницы, default=50 |

**Response `200`:**
```json
{
  "total": 965,
  "total_filtered": 142,
  "zone_a": 312,
  "zone_b": 421,
  "zone_c": 232,
  "pending_review": 733,
  "by_program": { "foundation": 480, "bachelor": 485 },
  "page": 1,
  "page_size": 50,
  "applications": [
    {
      "id": "uuid",
      "full_name": "Айгерим Досова",
      "program": "foundation",
      "city": "Шымкент",
      "status": "zone_a",
      "final_score": 9.21,
      "zone": "A",
      "ai_probability": 0.04,
      "created_at": "..."
    }
  ]
}
```

---

#### `GET /api/applications/{id}/detail` *(reviewer)*
Полная карточка заявки.

**Response `200`:**
```json
{
  "id": "uuid",
  "full_name": "Максат Кенжеев",
  "status": "zone_a",
  "program": "bachelor",
  "country": "KZ",
  "city": "Кызылорда",
  "regional_coeff": 1.12,
  "documents": { "ent_score": 84, "ielts_score": 6.0 },

  "answers": [
    { "source": "form",      "question_id": "V2", "text": "В апреле 2024..." },
    { "source": "video",     "question_id": "V2_video", "video_url": "https://...", "transcript": "..." },
    { "source": "interview", "question_id": "interview", "text": "Я разбил волонтёров..." }
  ],

  "scores": [
    {
      "layer": "nlp_written",
      "scores": { "leadership": 8.7, "motivation": 8.5, "perseverance": 9.2, ... },
      "attribution": { "leadership": ["координировал", "штаб", "эвакуировать"] },
      "ai_probability": 0.03,
      "ai_detector_detail": { "perplexity": 201.4, "burstiness": 0.52, "specificity": 0.038, "composite": 0.03 }
    },
    {
      "layer": "nlp_video",
      "scores": { ... },
      "consistency_score": 0.72
    },
    {
      "layer": "interview",
      "scores": { ... },
      "ai_probability": 0.05,
      "consistency_score": 0.84,
      "final_score": 8.91,
      "zone": "A"
    },
    {
      "layer": "rule",
      "scores": { "struct_score": 4.2 },
      "zone": "B",
      "final_score": 8.83,
      "explanations": {
        "zone_explanation": "Зона B: итоговый скор 8.83 (порог A=8.0 достигнут), но consistency=0.72 выше порога 0.60. После Pre-Interview blended_final=8.91, новая зона A.",
        "summary": "Сильный кандидат с подтверждённым социальным лидерством.",
        "leadership": "Координировал кризисную операцию 72 часа.",
        "ai_comment": "Perplexity=201 — живой текст, признаков AI нет."
      }
    }
  ],

  "interview_log": {
    "interview_id": "uuid",
    "messages": [
      { "role": "assistant", "content": "47 волонтёров — как ты их распределял?" },
      { "role": "user",      "content": "Разбил на 5 групп по районам..." },
      { "role": "assistant", "content": "В какой момент понял что не справляешься?" },
      { "role": "user",      "content": "На второй день когда закончилась еда..." }
    ],
    "final_score": 8.91,
    "new_zone": "A",
    "completed_at": "2025-04-04T15:30:00Z"
  },

  "created_at": "2025-04-03T10:00:00Z"
}
```

---

#### `POST /api/applications/{id}/decision` *(reviewer)*
Принять решение.

**Body:**
```json
{
  "decision": "shortlist",
  "agreed_with_ai": true,
  "override_reason": null,
  "notes": "Сильный кандидат из региона"
}
```
`decision`: `"shortlist"` | `"hold"` | `"reject"`

**Response `201`:**
```json
{
  "id": "uuid",
  "decision": "shortlist",
  "agreed_with_ai": true,
  "notes": "Сильный кандидат из региона",
  "created_at": "..."
}
```

---

#### `POST /api/applications/{id}/rescore` *(reviewer)*
Пересчитать скоры (удаляет старые, запускает pipeline заново).

**Response `200`:** `ApplicationStatusResponse` со статусом `submitted`.

---

### Stats & Settings (Reviewer)

#### `GET /api/stats`
**Response `200`:**
```json
{
  "total_applications": 965,
  "by_status": { "zone_a": 312, "zone_b": 421, "zone_c": 232 },
  "by_zone": { "A": 312, "B": 421, "C": 232 },
  "avg_final_score": 7.84,
  "ai_flagged": 87
}
```

---

#### `GET /api/settings` *(reviewer)*
Текущие настройки.

**Response `200`:**
```json
{
  "zone_a_threshold": 8.0,
  "zone_b_threshold": 6.0,
  "ai_detector_threshold": 0.60,
  "consistency_threshold": 0.60,
  "nlp_weight": 0.70,
  "struct_weight": 0.30,
  "regional_coeffs": {
    "cities": { "Алматы": 0.95, "Астана": 0.95, "Шымкент": 1.0, ... },
    "tiers":  { "capital": 0.95, "rural": 1.15, ... },
    "foreign_countries": { "KG": 1.0, "UZ": 1.0 },
    "default": 1.0
  }
}
```

---

#### `PUT /api/settings` *(reviewer)*
Обновить настройки (runtime, не персистируются при рестарте).

**Body** (все поля опциональны):
```json
{
  "zone_a_threshold": 8.5,
  "consistency_threshold": 0.65,
  "regional_coeffs": {
    "Алматы": 0.90,
    "default": 1.05
  }
}
```
`regional_coeffs` — словарь город:коэффициент. Ключ `"default"` обновляет дефолт для неизвестных городов.

**Response `200`:** полный `SettingsResponse` с актуальными значениями.

---

#### `POST /api/seed` *(reviewer)*
Вставить три синтетических кандидата для демо.

**Response `201`:**
```json
{ "seeded": ["Айгерим Досова", "Максат Кенжеев", "Дана Нурланова"] }
```

---

### System

#### `GET /api/health`
```json
{ "status": "ok" }
```

---

## Статусы заявки

| Статус | Описание |
|--------|---------|
| `draft` | Создана, не отправлена |
| `submitted` | Отправлена, ожидает скоринга |
| `scoring` | Pipeline запущен |
| `zone_a` | Зона A — рекомендован |
| `zone_b` | Зона B (промежуточная) |
| `zone_c` | Зона C — отклонён |
| `awaiting_interview` | Ожидает Pre-Interview |
| `shortlisted` | Reviewer принял решение: shortlist |
| `hold` | Reviewer: на удержании |
| `rejected` | Reviewer: отклонён |
| `offer` | Оффер выдан |

---

## База данных

```sql
users(id, email, password_hash, role, full_name, created_at)

applications(id, user_id, program, country, city, status,
             regional_coeff, documents JSONB, created_at, updated_at)

answers(id, application_id, source, question_id, text, video_url, transcript)
  source: form | video | interview

scores(id, application_id, layer, scores JSONB, explanations JSONB,
       attribution JSONB, ai_probability, ai_detector_detail JSONB,
       consistency_score, zone, final_score, created_at)
  layer: rule | nlp_written | nlp_video | interview

decisions(id, application_id, reviewer_id, decision,
          agreed_with_ai, override_reason, notes, created_at)

interview_logs(id, application_id, messages JSONB,
               final_score, new_zone, completed_at)

questions(id, program, order, text, created_by, created_at, updated_at)

audit_log(id, entity_type, entity_id, action, actor_id, payload JSONB, created_at)
```

---

## Модели NLP

| Язык | Модель | Описание |
|------|--------|---------|
| RU | `DeepPavlov/rubert-base-cased` | Дообучен на синтетических эссе |
| KZ | `bert-base-multilingual-cased` | Google mBERT, мультиязычный |
| EN | `roberta-base` | Дообучен на Kaggle essays |
| Fallback | `paraphrase-multilingual-MiniLM-L12-v2` | Если .pkl не загружены |

Модели хранятся в `models_trained/` (gitignore) и автоматически скачиваются из HuggingFace Hub при старте (`download_models.py`).

### Обучение (Google Colab)

```bash
# Ноутбук: training/train_models.ipynb
# Runtime: T4 GPU (бесплатный tier)
# Время: 20–40 мин на модель
# Результат: roberta_en.pkl / rubert_ru.pkl / mbert_kz.pkl
# Загрузить в: huggingface.co → Settings → New Model Repository
```

---

## Docker

```yaml
# docker-compose.yml
services:
  backend:   # FastAPI на порту 8000
  db:        # PostgreSQL 16
```

```bash
docker-compose up --build   # первый запуск ~10 мин
docker-compose up           # повторный запуск ~1 мин
```

Переменные окружения читаются из `.env` в корне проекта.
