# inVision U — API Documentation для фронтенда

**Base URL:** `https://your-railway-app.railway.app/api`  
**Локально:** `http://localhost:8000/api`  
**Swagger UI:** `/api/docs`

Все защищённые эндпоинты требуют заголовок:
```
Authorization: Bearer <access_token>
```

---

## ПРОЦЕСС ЛОГИКА — читай сначала

### Абитуриент (applicant)

```
1. Регистрация → получаешь access_token + user_id
2. Создать заявку → получаешь application id (сохрани его!)
3. Заполнить личные данные (профиль)
4. Загрузить документы (ENT сертификат, IELTS/TOEFL)
5. Ответить на письменные вопросы формы
6. Запросить вопросы для видео (генерирует ИИ на основе письменных ответов)
7. Записать видео-презентацию и загрузить
8. Сабмит → статус меняется, ИИ начинает скоринг в фоне
9. Периодически проверять статус (polling)
10. Если статус = awaiting_interview → пройти Pre-Interview (голосовой чат)
```

### Как узнать application_id после логина
```
GET /me → получить user_id
GET /applications/mine → получить список заявок с id
```

### Статусы заявки (что показывать пользователю)

| Статус | Что показывать |
|---|---|
| `draft` | "Черновик — продолжи заполнение" |
| `submitted` | "Заявка отправлена" |
| `scoring` | "ИИ анализирует заявку..." (показать спиннер) |
| `zone_a` | "Заявка рассматривается" |
| `zone_b` | "Заявка рассматривается" |
| `zone_c` | "Заявка рассматривается" |
| `awaiting_interview` | "Пройдите Pre-Interview" (показать кнопку) |
| `shortlisted` | "Поздравляем! Вы в шорт-листе" |
| `hold` | "Заявка на рассмотрении" |
| `rejected` | "К сожалению, не прошли" |
| `offer` | "Вы приняты! Ожидайте оффер" |

> ⚠️ Никогда не показывай числовой скор абитуриенту — только статус!

### Pre-Interview поток (Zone B)

```
1. POST /interview/{app_id}/start
   → получаешь {interview_id, question, audio_url, question_number, total_questions}
   → воспроизвести audio_url (mp3)
   → показать текст вопроса

2. Пользователь говорит → Web Speech API → текст

3. POST /interview/{interview_id}/message  body: {text: "ответ пользователя"}
   → получаешь {next_question, audio_url, is_complete, question_number}
   → если is_complete=false → воспроизвести аудио, показать вопрос, повторить шаг 2
   → если is_complete=true → показать {new_zone} ("A" или "C")

Всего 4 вопроса. interview_id ≠ app_id — это разные UUID!
```

---

## AUTH

### POST /auth/register
Регистрация нового пользователя.

**Body:**
```json
{
  "email": "student@example.com",
  "password": "password123",
  "full_name": "Айгерим Досова",
  "role": "applicant"
}
```
> `role`: `"applicant"` или `"reviewer"` (по умолчанию `applicant`)  
> `password`: минимум 8 символов

**Response 201:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "role": "applicant",
  "user_id": "uuid"
}
```

---

### POST /auth/login
Вход.

**Body:**
```json
{
  "email": "student@example.com",
  "password": "password123"
}
```

**Response 200:** — то же что register

---

## USER

### GET /me 🔒
Профиль текущего залогиненного пользователя.

**Response 200:**
```json
{
  "id": "uuid",
  "email": "student@example.com",
  "full_name": "Айгерим Досова",
  "role": "applicant",
  "created_at": "2026-04-05T10:00:00+05:00"
}
```

---

## APPLICATIONS — сторона абитуриента

### GET /applications/mine 🔒
Список своих заявок. Вызывай сразу после логина чтобы получить application_id.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "status": "draft",
    "program": "foundation",
    "created_at": "...",
    "updated_at": "..."
  }
]
```
> Обычно у абитуриента одна заявка. Берёшь `[0].id` и сохраняешь.

---

### POST /applications 🔒
Создать новую заявку. Вызывать один раз при первом входе если список mine пустой.

**Body:**
```json
{
  "program": "foundation",
  "country": "KZ",
  "city": "Алматы"
}
```
> `program`: `"foundation"` или `"bachelor"`  
> `country`: ISO 2 буквы (`"KZ"`, `"KG"`, `"RU"` и т.д.)

**Response 201:**
```json
{
  "id": "uuid",
  "status": "draft",
  "program": "foundation",
  "created_at": "...",
  "updated_at": "..."
}
```

---

### PUT /applications/{id}/profile 🔒
Заполнить личные данные. Все поля опциональные — отправляй только то что изменилось.

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

**Response 200:** `ApplicationStatusResponse`

---

### PUT /applications/{id}/documents 🔒
Числовые данные документов (без файла). Все поля опциональные.

**Body:**
```json
{
  "ent_score": 91,
  "ielts_score": 6.5,
  "toefl_score": null,
  "duolingo_score": null,
  "gpa": 4.8,
  "graduation_year": 2026,
  "school_name": "НИШ №5"
}
```

**Response 200:** `ApplicationStatusResponse`

---

### POST /applications/{id}/documents/upload 🔒
Загрузить файл документа (сертификат). `multipart/form-data`.

**Query params:**
| Параметр | Обязателен | Значения |
|---|---|---|
| `doc_type` | ✅ | `ent_cert` / `language_cert` / `recommendation` |
| `cert_type` | только для language_cert | `IELTS` / `TOEFL` / `Duolingo` |
| `score` | нет | числовой скор (ENT 0-140, IELTS 0-9, TOEFL 0-120) |

**Form field:** `file` — PDF, JPEG или PNG, до 10 МБ

**Примеры:**
```
POST /applications/{id}/documents/upload?doc_type=ent_cert&score=91
POST /applications/{id}/documents/upload?doc_type=language_cert&cert_type=IELTS&score=6.5
POST /applications/{id}/documents/upload?doc_type=recommendation
```

**Response 200:**
```json
{
  "doc_url": "https://res.cloudinary.com/dypyjcadg/image/upload/...",
  "doc_type": "ent_cert",
  "cert_type": null,
  "score": 91.0
}
```

---

### GET /questions
Получить список вопросов формы. Публичный эндпоинт, токен не нужен.

**Query params:**
- `program=foundation` или `program=bachelor` (опционально, фильтр)

**Response 200:**
```json
[
  {
    "id": "uuid",
    "program": "foundation",
    "order": 1,
    "text": "Опишите ситуацию, когда вы взяли на себя ответственность за решение сложной проблемы.",
    "created_at": "..."
  }
]
```
> Сортируй по `order` при отображении.

---

### PUT /applications/{id}/answers 🔒
Сохранить письменные ответы на вопросы формы.

**Body:**
```json
{
  "answers": [
    {"question_id": "V2", "text": "Во время хакатона я организовал команду..."},
    {"question_id": "V4", "text": "Я был лидером волонтёрского движения..."}
  ]
}
```
> `question_id` берётся из `GET /questions`  
> Можно вызывать многократно — данные перезаписываются  
> Можно отправлять частично (только изменённые вопросы)

**Response 200:** `ApplicationStatusResponse`

---

### GET /applications/{id}/video-questions 🔒
Получить персонализированные вопросы для видео-презентации.

> ⚠️ Вызывать ТОЛЬКО после того как заполнены письменные ответы!  
> ИИ (Claude) анализирует письменные ответы и генерирует вопросы под слабые места.

**Response 200:**
```json
{
  "questions": [
    "Расскажите о конкретном моменте, когда ваша команда столкнулась с разногласием. Как вы его разрешили?",
    "Что вас лично мотивирует к лидерству? Приведите конкретный пример из жизни."
  ]
}
```

---

### POST /applications/{id}/video/upload 🔒
Загрузить видео-презентацию на Cloudinary. `multipart/form-data`.

**Query params:**
- `question_id` ✅ — id вопроса (например `"V1"`)

**Form field:** `file` — MP4, WebM, MOV, AVI, до 200 МБ

**Response 200:**
```json
{
  "video_url": "https://res.cloudinary.com/dypyjcadg/video/upload/...",
  "question_id": "V1"
}
```

---

### PUT /applications/{id}/video 🔒
Альтернатива upload — если видео уже где-то захостено, просто передай URL.

**Body:**
```json
{
  "question_id": "V1",
  "video_url": "https://example.com/video.mp4"
}
```

**Response 200:** `ApplicationStatusResponse`

---

### POST /applications/{id}/submit 🔒
Отправить заявку на скоринг. После этого редактирование невозможно.

> Статус меняется: `draft` → `submitted` → `scoring` (автоматически)  
> Скоринг идёт в фоне (~30-60 сек). После него статус = `zone_a/b/c` или `awaiting_interview`.

**Response 200:** `ApplicationStatusResponse`

---

### GET /applications/{id}/status 🔒
Текущий статус заявки. Используй для polling после сабмита.

**Response 200:**
```json
{
  "id": "uuid",
  "status": "scoring",
  "program": "foundation",
  "created_at": "...",
  "updated_at": "..."
}
```
> Polling каждые 3-5 секунд пока `status == "scoring"`

---

### DELETE /applications/{id} 🔒
Удалить заявку. Только если статус `draft`.

**Response 204:** пустой ответ

---

## PRE-INTERVIEW (только для zone = awaiting_interview)

### POST /interview/{app_id}/start 🔒
Начать Pre-Interview. Передаёшь `app_id` (не interview_id!).

**Response 200:**
```json
{
  "interview_id": "uuid",
  "question": "Расскажите подробнее о вашем опыте лидерства...",
  "audio_url": "https://res.cloudinary.com/dypyjcadg/video/upload/invisionu/interview_audio/xxx.mp3",
  "question_number": 1,
  "total_questions": 4
}
```
> Сохрани `interview_id` — он нужен для следующего шага  
> Воспроизведи `audio_url` (TTS голос)  
> Покажи текст вопроса

---

### POST /interview/{interview_id}/message 🔒
Отправить ответ кандидата и получить следующий вопрос.

**Body:**
```json
{
  "text": "Да, в 2024 году я организовал хакатон для 200 участников..."
}
```
> `text` — то что сказал кандидат, переведённое из речи через Web Speech API на фронте

**Response 200 (продолжение):**
```json
{
  "next_question": "Как вы справились с конфликтом в команде?",
  "audio_url": "https://res.cloudinary.com/.../xxx.mp3",
  "is_complete": false,
  "question_number": 2
}
```

**Response 200 (конец интервью):**
```json
{
  "is_complete": true,
  "new_zone": "A"
}
```
> `new_zone`: `"A"` (прошёл) или `"C"` (не прошёл)  
> Покажи соответствующий экран

---

## REVIEWER — только с role=reviewer

### GET /dashboard 🔒
Список всех заявок с фильтрами.

**Query params:**
| Параметр | Тип | Пример |
|---|---|---|
| `zone` | string | `A`, `B`, `C` |
| `status` | string | `shortlisted`, `hold`, `rejected` |
| `program` | string | `foundation`, `bachelor` |
| `page` | int | `1` |
| `page_size` | int | `50` (макс 200) |

**Response 200:**
```json
{
  "total": 34,
  "total_filtered": 12,
  "zone_a": 8,
  "zone_b": 7,
  "zone_c": 12,
  "pending_review": 15,
  "by_program": {"foundation": 18, "bachelor": 16},
  "page": 1,
  "page_size": 50,
  "applications": [
    {
      "id": "uuid",
      "full_name": "Максат Кенжеев",
      "program": "bachelor",
      "city": "Кызылорда",
      "status": "zone_a",
      "final_score": 8.8,
      "zone": "A",
      "ai_probability": 0.03,
      "created_at": "..."
    }
  ]
}
```

---

### GET /applications/{id}/detail 🔒
Полная информация по кандидату.

**Response 200:**
```json
{
  "id": "uuid",
  "status": "zone_a",
  "program": "bachelor",
  "country": "KZ",
  "city": "Кызылорда",
  "regional_coeff": 1.12,
  "full_name": "Максат Кенжеев",
  "documents": {
    "ent_score": 84,
    "ielts_score": 6.0,
    "gpa": 4.5,
    "school_name": "НИШ Кызылорда",
    "ent_cert_url": "https://res.cloudinary.com/...",
    "language_cert_url": "https://res.cloudinary.com/...",
    "language_cert_type": "IELTS"
  },
  "answers": [
    {
      "question_id": "V2",
      "source": "form",
      "text": "Письменный ответ кандидата...",
      "video_url": null,
      "transcript": null
    },
    {
      "question_id": "V1",
      "source": "video",
      "text": null,
      "video_url": "https://res.cloudinary.com/.../video.mp4",
      "transcript": "Транскрипт видео через Whisper..."
    }
  ],
  "scores": [
    {
      "layer": "nlp_written",
      "scores": {
        "leadership": 8.7,
        "motivation": 8.5,
        "perseverance": 9.2,
        "teamwork": 9.0,
        "goal_pursuit": 8.8,
        "intrinsic_motivation": 8.3,
        "prosocial_purpose": 9.1
      },
      "explanations": {
        "summary": "Кандидат демонстрирует высокий уровень лидерских качеств...",
        "leadership": "Конкретные примеры организации команды..."
      },
      "ai_probability": 0.03,
      "ai_detector_detail": {
        "perplexity": 45.2,
        "burstiness": 4.1,
        "specificity": 0.12,
        "composite": 0.03
      },
      "consistency_score": 0.87,
      "zone": "A",
      "final_score": 8.8
    }
  ],
  "interview_log": {
    "interview_id": "uuid",
    "messages": [
      {
        "role": "assistant",
        "content": "Расскажите о конкретном случае...",
        "audio_url": "https://res.cloudinary.com/.../audio.mp3"
      },
      {
        "role": "user",
        "content": "Да, в 2024 году я организовал..."
      }
    ],
    "final_score": 9.1,
    "new_zone": "A",
    "completed_at": "2026-04-05T15:30:00+05:00"
  },
  "created_at": "..."
}
```

> **scores.layer** может быть: `rule`, `nlp_written`, `nlp_video`, `interview`  
> **ai_probability**: 0-1, выше 0.6 = подозрительно  
> **consistency_score**: 0-1, ниже 0.6 = письмо и видео сильно расходятся  

---

### GET /applications/{id}/decisions 🔒
История всех решений по заявке.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "decision": "shortlist",
    "agreed_with_ai": true,
    "override_reason": null,
    "notes": "Сильный кандидат из региона",
    "reviewer_name": "Приёмная комиссия",
    "created_at": "..."
  }
]
```

---

### POST /applications/{id}/decision 🔒
Принять решение по кандидату.

**Body:**
```json
{
  "decision": "shortlist",
  "agreed_with_ai": true,
  "override_reason": null,
  "notes": "Отличный региональный кандидат"
}
```
> `decision`: `"shortlist"` / `"hold"` / `"reject"`  
> `agreed_with_ai`: согласен ли с AI рекомендацией (для статистики)  
> `override_reason`: причина если не согласен с AI

Статус заявки меняется автоматически:
- `shortlist` → статус `shortlisted`
- `hold` → статус `hold`
- `reject` → статус `rejected`

**Response 201:** `DecisionResponse`

---

### PATCH /applications/{id}/status 🔒
Вручную изменить статус (например вернуть из hold на пересмотр).

**Body:**
```json
{
  "status": "zone_b"
}
```
> Любой статус из: `draft`, `submitted`, `scoring`, `zone_a`, `zone_b`, `zone_c`, `awaiting_interview`, `shortlisted`, `hold`, `rejected`, `offer`

**Response 200:** `ApplicationStatusResponse`

---

### POST /applications/{id}/rescore 🔒
Пересчитать скоры заново (если изменились модели или пороги).

**Response 200:** `ApplicationStatusResponse`

---

### GET /stats 🔒
Общая статистика платформы.

**Response 200:**
```json
{
  "total_applications": 34,
  "by_status": {
    "zone_a": 8,
    "zone_b": 7,
    "zone_c": 12,
    "shortlisted": 5,
    "rejected": 2
  },
  "by_zone": {"A": 8, "B": 7, "C": 12},
  "avg_final_score": 7.77,
  "ai_flagged": 3
}
```

---

## QUESTIONS — управление вопросами (reviewer)

### POST /questions 🔒
Создать вопрос формы.

**Body:**
```json
{
  "program": "foundation",
  "order": 1,
  "text": "Опишите ситуацию, когда вы взяли ответственность..."
}
```

**Response 201:** `QuestionResponse`

---

### PUT /questions/{id} 🔒
Редактировать вопрос.

**Body:**
```json
{
  "order": 2,
  "text": "Обновлённый текст вопроса..."
}
```

**Response 200:** `QuestionResponse`

---

### DELETE /questions/{id} 🔒
Удалить вопрос.

**Response 204:** пустой ответ

---

## SETTINGS 🔒

### GET /settings
Текущие пороговые значения системы.

**Response 200:**
```json
{
  "zone_a_threshold": 8.0,
  "zone_b_threshold": 6.0,
  "ai_detector_threshold": 0.6,
  "consistency_threshold": 0.6,
  "nlp_weight": 0.7,
  "struct_weight": 0.3,
  "regional_coeffs": {
    "Алматы": 0.95,
    "Астана": 0.95,
    "Шымкент": 1.0
  }
}
```

---

### PUT /settings 🔒
Обновить пороги. Все поля опциональные.

**Body:**
```json
{
  "zone_a_threshold": 8.0,
  "zone_b_threshold": 6.0,
  "ai_detector_threshold": 0.7,
  "consistency_threshold": 0.6,
  "nlp_weight": 0.7,
  "struct_weight": 0.3
}
```

> ⚠️ Изменения хранятся в памяти — сбрасываются при рестарте сервера.

**Response 200:** `SettingsResponse`

---

## SEED (только для демо)

### POST /seed 🔒
Заполнить БД тремя тестовыми кандидатами.

| Кандидат | Ожидаемый результат |
|---|---|
| Айгерим Досова (Шымкент, Foundation) | Zone A, скор ~9.2 |
| Максат Кенжеев (Кызылорда, Bachelor) | Zone A, скор ~8.8 |
| Дана Нурланова (Алматы, Sociology) | Zone B, ai_probability=0.87 |

**Response 201:**
```json
{
  "seeded": ["Айгерим Досова", "Максат Кенжеев", "Дана Нурланова"]
}
```

---

## ОШИБКИ

| Код | Причина |
|---|---|
| `400` | Неверные данные (валидация) |
| `401` | Нет токена или токен истёк |
| `403` | Нет прав (например applicant пытается в reviewer эндпоинт) |
| `404` | Не найдено |
| `422` | Неверный формат запроса |
| `500` | Ошибка сервера |

**Формат ошибки:**
```json
{
  "detail": "Текст ошибки"
}
```

---

## БЫСТРЫЙ СТАРТ — типичный сценарий для фронта

```javascript
// 1. Регистрация
const {access_token, user_id} = await POST('/auth/register', {...})
localStorage.setItem('token', access_token)

// 2. После логина — найти или создать заявку
const apps = await GET('/applications/mine')
let appId = apps[0]?.id
if (!appId) {
  const app = await POST('/applications', {program: 'foundation', country: 'KZ'})
  appId = app.id
}

// 3. Заполнение формы
await PUT(`/applications/${appId}/profile`, {full_name, city, ent_score, ...})
await PUT(`/applications/${appId}/answers`, {answers: [{question_id, text}, ...]})

// 4. Загрузить ENT сертификат
const formData = new FormData()
formData.append('file', file)
await POST(`/applications/${appId}/documents/upload?doc_type=ent_cert&score=91`, formData)

// 5. Получить вопросы для видео (после заполнения письменных!)
const {questions} = await GET(`/applications/${appId}/video-questions`)

// 6. Загрузить видео
const fd = new FormData()
fd.append('file', videoFile)
await POST(`/applications/${appId}/video/upload?question_id=V1`, fd)

// 7. Сабмит
await POST(`/applications/${appId}/submit`)

// 8. Polling статуса
const poll = setInterval(async () => {
  const {status} = await GET(`/applications/${appId}/status`)
  if (status !== 'scoring') {
    clearInterval(poll)
    updateUI(status)
  }
}, 4000)

// 9. Pre-Interview (если status === 'awaiting_interview')
const {interview_id, question, audio_url} = await POST(`/interview/${appId}/start`)
playAudio(audio_url)

// После каждого ответа пользователя:
const {next_question, audio_url, is_complete, new_zone} = 
  await POST(`/interview/${interview_id}/message`, {text: speechText})
```
