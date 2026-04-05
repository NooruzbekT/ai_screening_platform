# inVision U — Technical & API Reference

**Base URL (prod):** `https://invisionu-screening.up.railway.app/api`  
**Base URL (local):** `http://localhost:8000/api`  
**Swagger UI:** `/api/docs`

Все защищённые эндпоинты `🔒` требуют заголовок:
```
Authorization: Bearer <access_token>
```

---

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
│   │   └── llm_explainer.py     # Claude/Groq: объяснения + TTS + интервью
│   └── data/
│       ├── regional_coeffs.json
│       ├── leadership_keywords_ru.json
│       └── leadership_keywords_kz.json
├── download_models.py           # Авто-загрузка .pkl из HuggingFace при старте
├── models_trained/              # roberta_en.pkl / rubert_ru.pkl / mbert_kz.pkl
└── audio_cache/                 # TTS mp3 (edge-tts, временные)
```

---

## Переменные окружения

| Переменная | Обязательна | Описание |
|-----------|-------------|---------|
| `GROQ_API_KEY` | Да | console.groq.com |
| `ANTHROPIC_API_KEY` | Да | console.anthropic.com |
| `DATABASE_URL` | Да | `postgresql://user:pass@host:5432/db` |
| `JWT_SECRET` | Да | Минимум 32 символа |
| `JURY_EMAIL` | Да | Email аккаунта комиссии |
| `JURY_PASSWORD` | Да | Пароль аккаунта комиссии |
| `CLOUDINARY_CLOUD_NAME` | Да | Cloudinary dashboard |
| `CLOUDINARY_API_KEY` | Да | Cloudinary dashboard |
| `CLOUDINARY_API_SECRET` | Да | Cloudinary dashboard |
| `HF_TOKEN` | Нет | HuggingFace token для .pkl моделей |
| `HF_REPO_ID` | Нет | `Nooruzbek/invisionu-models` |
| `GROQ_MODEL` | Нет | `llama-3.3-70b-versatile` |
| `ZONE_A_THRESHOLD` | Нет | `8.0` |
| `ZONE_B_THRESHOLD` | Нет | `6.0` |
| `AI_DETECTOR_THRESHOLD` | Нет | `0.60` |
| `CONSISTENCY_THRESHOLD` | Нет | `0.60` |
| `NLP_WEIGHT` | Нет | `0.70` |
| `STRUCT_WEIGHT` | Нет | `0.30` |
| `WHISPER_MODEL` | Нет | `medium` |

---

## Scoring Pipeline

### Порядок выполнения (`scorer.py`)

```
1. check_gate(app)
   → KZ: ENT >= 80
   → KG/UZ/TJ/TM: GPA + языковой тест
   → fail → статус rejected, zone C

2. struct_score(app) → float 0–10
   = ENT_norm*0.5 + lang_norm*0.3 + completeness*0.2

3. nlp_model.score(written_text) → scores{7 качеств}, attribution
   → определяет язык (langdetect)
   → .pkl модель если есть, иначе MiniLM fallback

4. ai_detector.analyze(written_text)
   → perplexity (GPT-2)
   → burstiness (std/mean длин предложений)
   → specificity (NER count / tokens, spaCy)
   → composite = среднее трёх нормализованных

5. transcriber.transcribe(video_url) → transcript (Whisper)

6. nlp_model.score(transcript) → nlp_video scores

7. consistency.compute(written_scores, video_scores)
   → cosine similarity векторов 7 качеств

8. final_score = (nlp_combined * 0.70 + struct * 0.30) * regional_coeff
   nlp_combined = written*0.6 + video*0.4 (если есть видео)

9. zone:
   A: final >= 8.0 AND consistency >= 0.60 AND ai < 0.20
   C: final < 6.0 OR ai > 0.60
   B: всё остальное → awaiting_interview

10. llm_explainer.explain({scores, ai_detector, zone, ...})
    → Claude Sonnet генерирует объяснения на русском

11. Сохранить Score записи, обновить статус заявки
```

### Post-Interview Pipeline

```
После 4-го ответа кандидата:
1. nlp_model.score(все ответы интервью)
2. ai_detector.analyze(interview_text)
3. consistency.compute(written_scores, interview_nlp)
4. blended_final = old_final*0.70 + interview_nlp_val*10*0.30
5. zone_a = blended_final >= 8.0 AND consistency >= 0.60 AND ai < 0.20
6. Обновить статус: zone_a или zone_c
```

### Формулы

```python
struct  = ENT_norm*0.5 + lang_norm*0.3 + completeness*0.2      # 0–10
nlp     = sum(score[q] * weight[q] for q in 7_qualities)        # 0–10
final   = (nlp*0.70 + struct*0.30) * regional_coeff             # 0–10

# Веса качеств
leadership=0.20, motivation=0.22, perseverance=0.16,
teamwork=0.12, goal_pursuit=0.10,
intrinsic_motivation=0.10, prosocial_purpose=0.10

# AI-детектор composite
p_ai = sigmoid((50 - perplexity) / 30)
b_ai = sigmoid((0.15 - burstiness) / 0.08)
s_ai = sigmoid((0.015 - specificity) / 0.008)
composite = (p_ai + b_ai + s_ai) / 3
```

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

| Язык | Модель | Fallback |
|------|--------|---------|
| RU | `DeepPavlov/rubert-base-cased` | |
| KZ | `bert-base-multilingual-cased` (mBERT) | |
| EN | `roberta-base` | |
| Fallback | `paraphrase-multilingual-MiniLM-L12-v2` | если .pkl не загружены |

Модели скачиваются из HuggingFace Hub при старте (`download_models.py`).  
Обучение: `training/train_models.ipynb`, Google Colab T4 GPU.

---

## Docker

```bash
docker-compose up --build   # первый запуск ~10 мин
docker-compose up           # повторный ~1 мин
```

---

## Процесс логика для фронтенда

### Абитуриент — порядок шагов

```
1.  POST /auth/register         → access_token
2.  GET  /applications/mine     → найти существующую заявку
    POST /applications          → или создать новую (если mine пустой)
3.  PUT  /applications/{id}/profile   → имя, город, школа, ENT скор
4.  POST /applications/{id}/documents/upload?doc_type=ent_cert
    POST /applications/{id}/documents/upload?doc_type=language_cert&cert_type=IELTS
5.  GET  /questions?program=foundation  → получить вопросы формы
    PUT  /applications/{id}/answers     → сохранить письменные ответы
6.  GET  /applications/{id}/video-questions  → ИИ генерирует вопросы для видео
7.  POST /applications/{id}/video/upload     → загрузить видео на Cloudinary
8.  POST /applications/{id}/submit           → отправить на скоринг
9.  GET  /applications/{id}/status  → polling каждые 3–5 сек пока status="scoring"
10. Если status="awaiting_interview":
    POST /interview/{app_id}/start          → получить первый вопрос + audio_url
    POST /interview/{interview_id}/message  → отправить ответ, получить следующий
    Повторять пока is_complete=true
```

### Статусы — что показывать пользователю

| Статус | UI |
|--------|----|
| `draft` | Черновик — продолжи заполнение |
| `submitted` | Заявка отправлена |
| `scoring` | ИИ анализирует заявку… (спиннер) |
| `zone_a` / `zone_b` / `zone_c` | Заявка рассматривается |
| `awaiting_interview` | Пройдите Pre-Interview (кнопка) |
| `shortlisted` | Поздравляем! Вы в шорт-листе |
| `hold` | Заявка на рассмотрении |
| `rejected` | К сожалению, не прошли |
| `offer` | Вы приняты! Ожидайте оффер |

> Никогда не показывай числовой скор абитуриенту — только статус.

### Pre-Interview поток

```
POST /interview/{app_id}/start
  ← { interview_id, question, audio_url, question_number:1, total_questions:4 }

Воспроизвести audio_url → показать текст вопроса
Пользователь говорит → Web Speech API → текст

POST /interview/{interview_id}/message  { text: "ответ" }
  ← { next_question, audio_url, is_complete:false, question_number:2 }

Повторять до is_complete:true
  ← { is_complete:true, new_zone:"A" }   // "A" или "C"
```

### Быстрый старт (JavaScript)

```javascript
const api = 'https://invisionu-screening.up.railway.app/api'

// 1. Вход
const { access_token } = await fetch(`${api}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password })
}).then(r => r.json())

const h = { 'Authorization': `Bearer ${access_token}`, 'Content-Type': 'application/json' }

// 2. Найти или создать заявку
const apps = await fetch(`${api}/applications/mine`, { headers: h }).then(r => r.json())
let appId = apps[0]?.id
if (!appId) {
  const app = await fetch(`${api}/applications`, {
    method: 'POST', headers: h,
    body: JSON.stringify({ program: 'foundation', country: 'KZ' })
  }).then(r => r.json())
  appId = app.id
}

// 3. Загрузить файл
const fd = new FormData()
fd.append('file', file)
await fetch(`${api}/applications/${appId}/documents/upload?doc_type=ent_cert&score=91`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${access_token}` },
  body: fd
})

// 4. Сабмит + polling
await fetch(`${api}/applications/${appId}/submit`, { method: 'POST', headers: h })

const poll = setInterval(async () => {
  const { status } = await fetch(`${api}/applications/${appId}/status`, { headers: h }).then(r => r.json())
  if (status !== 'scoring') { clearInterval(poll); handleStatus(status) }
}, 4000)

// 5. Pre-Interview
const { interview_id, question, audio_url } =
  await fetch(`${api}/interview/${appId}/start`, { method: 'POST', headers: h }).then(r => r.json())
new Audio(audio_url).play()

// После каждого ответа
const res = await fetch(`${api}/interview/${interview_id}/message`, {
  method: 'POST', headers: h,
  body: JSON.stringify({ text: speechText })
}).then(r => r.json())
if (res.is_complete) showResult(res.new_zone)
```

---

## API Reference

### AUTH

#### `POST /auth/register`
**Body:**
```json
{
  "email": "user@example.com",
  "password": "min8chars",
  "full_name": "Айгерим Досова",
  "role": "applicant"
}
```
`role`: `"applicant"` | `"reviewer"`

**Response `201`:**
```json
{ "access_token": "eyJ...", "token_type": "bearer", "role": "applicant", "user_id": "uuid" }
```

---

#### `POST /auth/login`
**Body:** `{ "email": "...", "password": "..." }`  
**Response `200`:** аналогично register.

---

### USER

#### `GET /me` 🔒
Профиль текущего пользователя.

**Response `200`:**
```json
{ "id": "uuid", "email": "...", "full_name": "...", "role": "applicant", "created_at": "..." }
```

---

### APPLICATIONS — Абитуриент

#### `GET /applications/mine` 🔒
Список своих заявок. Вызывай после логина чтобы получить `application_id`.

**Response `200`:** `[ { "id": "uuid", "status": "draft", "program": "foundation", ... } ]`

---

#### `POST /applications` 🔒
Создать заявку.

**Body:** `{ "program": "foundation", "country": "KZ", "city": "Алматы" }`  
`program`: `"foundation"` | `"bachelor"`

**Response `201`:** `{ "id": "uuid", "status": "draft", ... }`

---

#### `PUT /applications/{id}/profile` 🔒
Личные данные. Все поля опциональные.

**Body:**
```json
{
  "full_name": "Айгерим Досова",
  "country": "KZ",
  "city": "Шымкент",
  "school_name": "НИШ №5",
  "ent_score": 91,
  "graduation_year": 2026,
  "gpa": 4.8
}
```

---

#### `PUT /applications/{id}/documents` 🔒
Числовые данные без файла. Все поля опциональные.

**Body:**
```json
{ "ent_score": 91, "ielts_score": 6.5, "toefl_score": null, "gpa": 4.8, "school_name": "НИШ" }
```

---

#### `POST /applications/{id}/documents/upload` 🔒
Загрузить файл документа. `multipart/form-data`. Файл уходит в Cloudinary.

**Query params:**
| Параметр | Обязателен | Значения |
|---|---|---|
| `doc_type` | ✅ | `ent_cert` / `language_cert` / `recommendation` |
| `cert_type` | только для language_cert | `IELTS` / `TOEFL` / `Duolingo` |
| `score` | нет | числовой скор |

**Form field:** `file` — PDF / JPEG / PNG, до 10 МБ

**Response `200`:**
```json
{ "doc_url": "https://res.cloudinary.com/...", "doc_type": "ent_cert", "cert_type": null, "score": 91.0 }
```

---

#### `GET /questions`
Вопросы формы. Публичный, токен не нужен.

**Query:** `?program=foundation`

**Response `200`:**
```json
[ { "id": "uuid", "program": "foundation", "order": 1, "text": "Опишите ситуацию...", "created_at": "..." } ]
```
> Сортируй по `order`.

---

#### `PUT /applications/{id}/answers` 🔒
Письменные ответы. Можно вызывать частично и многократно.

**Body:**
```json
{ "answers": [ { "question_id": "V2", "text": "В 2024 году я организовал..." } ] }
```

---

#### `GET /applications/{id}/video-questions` 🔒
Персонализированные вопросы для видео. Вызывать после заполнения письменных ответов.  
Claude анализирует письменные ответы и генерирует вопросы под слабые места.

**Response `200`:**
```json
{ "questions": ["Расскажите о моменте когда ваша команда...", "Что вас мотивирует..."] }
```

---

#### `POST /applications/{id}/video/upload` 🔒
Загрузить видео. `multipart/form-data`. Уходит в Cloudinary.

**Query:** `?question_id=V1`  
**Form field:** `file` — MP4 / WebM / MOV / AVI, до 200 МБ

**Response `200`:**
```json
{ "video_url": "https://res.cloudinary.com/...", "question_id": "V1" }
```

---

#### `PUT /applications/{id}/video` 🔒
Альтернатива upload — если видео уже захостено.

**Body:** `{ "question_id": "V1", "video_url": "https://..." }`

---

#### `POST /applications/{id}/submit` 🔒
Отправить на скоринг. После этого редактирование невозможно.  
Скоринг идёт в фоне (~30–60 сек).

---

#### `GET /applications/{id}/status` 🔒
Текущий статус. Используй для polling после submit.

**Response `200`:** `{ "id": "uuid", "status": "scoring", "program": "foundation", ... }`

---

#### `DELETE /applications/{id}` 🔒
Удалить заявку. Только если `status = draft`.

**Response `204`**

---

### PRE-INTERVIEW

#### `POST /interview/{app_id}/start` 🔒
Начать Pre-Interview. Передаёшь `app_id` (не interview_id!).

**Response `200`:**
```json
{
  "interview_id": "uuid",
  "question": "Расскажите подробнее о вашем опыте...",
  "audio_url": "https://res.cloudinary.com/.../audio.mp3",
  "question_number": 1,
  "total_questions": 4
}
```
> Сохрани `interview_id`. Воспроизведи `audio_url`.

---

#### `POST /interview/{interview_id}/message` 🔒
Ответ кандидата → следующий вопрос.

**Body:** `{ "text": "Да, в 2024 году я организовал..." }`

**Response (продолжение):**
```json
{ "next_question": "...", "audio_url": "...", "is_complete": false, "question_number": 2 }
```

**Response (конец):**
```json
{ "is_complete": true, "new_zone": "A" }
```
`new_zone`: `"A"` или `"C"`

---

### REVIEWER 🔒

#### `GET /dashboard`
Список заявок с фильтрами и пагинацией.

**Query params:** `zone=A|B|C`, `status=shortlisted|...`, `program=foundation|bachelor`, `page=1`, `page_size=50`

**Response `200`:**
```json
{
  "total": 965, "total_filtered": 142,
  "zone_a": 312, "zone_b": 421, "zone_c": 232, "pending_review": 733,
  "by_program": { "foundation": 480, "bachelor": 485 },
  "page": 1, "page_size": 50,
  "applications": [
    { "id": "uuid", "full_name": "Максат Кенжеев", "program": "bachelor",
      "city": "Кызылорда", "status": "zone_a", "final_score": 8.83,
      "zone": "A", "ai_probability": 0.03, "created_at": "..." }
  ]
}
```

---

#### `GET /applications/{id}/detail`
Полная карточка кандидата.

**Response `200`:**
```json
{
  "id": "uuid", "full_name": "Максат Кенжеев", "status": "zone_a",
  "program": "bachelor", "country": "KZ", "city": "Кызылорда",
  "regional_coeff": 1.12,
  "documents": {
    "ent_score": 84, "ielts_score": 6.0, "school_name": "НИШ",
    "ent_cert_url": "https://res.cloudinary.com/...",
    "language_cert_url": "https://res.cloudinary.com/...",
    "language_cert_type": "IELTS"
  },
  "answers": [
    { "source": "form",      "question_id": "V2", "text": "В апреле 2024..." },
    { "source": "video",     "question_id": "V1", "video_url": "https://...", "transcript": "..." },
    { "source": "interview", "question_id": "interview", "text": "Разбил на 5 групп..." }
  ],
  "scores": [
    {
      "layer": "nlp_written",
      "scores": { "leadership": 8.7, "motivation": 8.5, "perseverance": 9.2,
                  "teamwork": 9.0, "goal_pursuit": 8.8,
                  "intrinsic_motivation": 8.3, "prosocial_purpose": 9.1 },
      "attribution": { "leadership": ["координировал", "штаб", "эвакуировать"] },
      "ai_probability": 0.03,
      "ai_detector_detail": { "perplexity": 201.4, "burstiness": 0.52, "specificity": 0.038, "composite": 0.03 },
      "explanations": {
        "summary": "Сильный кандидат с подтверждённым социальным лидерством.",
        "leadership": "Координировал кризисную операцию 72 часа.",
        "ai_comment": "Perplexity=201 — живой текст, признаков AI нет."
      }
    },
    {
      "layer": "nlp_video",
      "scores": { "leadership": 8.4, "motivation": 8.1, ... },
      "consistency_score": 0.72
    },
    {
      "layer": "rule",
      "final_score": 8.83,
      "zone": "A"
    }
  ],
  "interview_log": {
    "interview_id": "uuid",
    "messages": [
      { "role": "assistant", "content": "47 волонтёров — как ты их распределял?", "audio_url": "https://..." },
      { "role": "user",      "content": "Разбил на 5 групп по районам..." },
      { "role": "assistant", "content": "В какой момент понял что не справляешься?", "audio_url": "https://..." },
      { "role": "user",      "content": "На второй день когда закончилась еда..." }
    ],
    "final_score": 8.91, "new_zone": "A", "completed_at": "..."
  },
  "created_at": "..."
}
```

---

#### `GET /applications/{id}/decisions`
История всех решений по заявке.

**Response `200`:**
```json
[
  { "id": "uuid", "decision": "shortlist", "agreed_with_ai": true,
    "override_reason": null, "notes": "Сильный региональный кандидат",
    "reviewer_name": "Приёмная комиссия", "created_at": "..." }
]
```

---

#### `POST /applications/{id}/decision`
Принять решение.

**Body:**
```json
{ "decision": "shortlist", "agreed_with_ai": true, "override_reason": null, "notes": "..." }
```
`decision`: `"shortlist"` | `"hold"` | `"reject"`

Статус заявки меняется автоматически: shortlist→`shortlisted`, hold→`hold`, reject→`rejected`.

**Response `201`:** `DecisionResponse`

---

#### `PATCH /applications/{id}/status`
Вручную поменять статус (например вернуть из hold).

**Body:** `{ "status": "zone_b" }`

**Response `200`:** `ApplicationStatusResponse`

---

#### `POST /applications/{id}/rescore`
Пересчитать скоры заново.

**Response `200`:** статус → `submitted`, pipeline запускается в фоне.

---

#### `GET /stats`
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

### QUESTIONS

#### `GET /questions`
Публичный. `?program=foundation`

**Response `200`:** `[ { "id", "program", "order", "text", "created_at" } ]`

#### `POST /questions` 🔒 *(reviewer)*
**Body:** `{ "program": "foundation", "order": 1, "text": "Опишите ситуацию..." }`  
**Response `201`:** `QuestionResponse`

#### `PUT /questions/{id}` 🔒 *(reviewer)*
**Body:** `{ "order": 2, "text": "Обновлённый текст..." }`

#### `DELETE /questions/{id}` 🔒 *(reviewer)*
**Response `204`**

---

### SETTINGS 🔒

#### `GET /settings`
**Response `200`:**
```json
{
  "zone_a_threshold": 8.0, "zone_b_threshold": 6.0,
  "ai_detector_threshold": 0.60, "consistency_threshold": 0.60,
  "nlp_weight": 0.70, "struct_weight": 0.30,
  "regional_coeffs": { "Алматы": 0.95, "Астана": 0.95, "default": 1.0 }
}
```

#### `PUT /settings`
Все поля опциональные. Изменения в памяти — сбрасываются при рестарте.

**Body:**
```json
{ "zone_a_threshold": 8.5, "ai_detector_threshold": 0.70 }
```

---

### SEED & SYSTEM

#### `POST /seed` 🔒 *(reviewer)*
Загрузить трёх демо-кандидатов.

**Response `201`:** `{ "seeded": ["Айгерим Досова", "Максат Кенжеев", "Дана Нурланова"] }`

#### `GET /health`
`{ "status": "ok" }`

---

## Коды ошибок

| Код | Причина |
|-----|---------|
| `400` | Неверные данные / невалидный файл |
| `401` | Нет токена или истёк |
| `403` | Нет прав (applicant → reviewer эндпоинт) |
| `404` | Не найдено |
| `422` | Неверный формат запроса |
| `500` | Ошибка сервера |

**Формат:** `{ "detail": "Текст ошибки" }`
