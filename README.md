# inVision U — AI Screening Platform

> **Decentrathon 5.0 · Track: AI inDrive**

## Проблема

inVision U получает **965 заявок** на **35 мест**. Ручной скрининг — 15 минут на каждую заявку. Итого: **241 час непрерывной работы** приёмной комиссии.

С открытием бакалавриата поток вырастет в три-пять раз. Ручной скрининг не масштабируется. Разные проверяющие ставят разные баллы за одни и те же ответы. ChatGPT уже помог нескольким кандидатам написать эссе — и никто этого не заметил. А самый сильный абитуриент из маленького аула проигрывает по формальным критериям отличнику из Алматы.

Система несправедлива — и она этого не замечает.

---

## Решение

Автоматизированная AI-платформа скрининга в три слоя:

```
Заявка
  │
  ▼  Слой 1: Rule Engine (детерминированный)
     ENT ≥ 80 / IELTS ≥ 6.0 / GPA (иностранцы)
     Региональный коэффициент 0.95–1.15 (настраивается комиссией)
  │
  ▼  Слой 2: NLP + AI-детектор
     7 качеств лидерства (Penn University метод)
     Три модели: RoBERTa-EN / RuBERT-RU / mBERT-KZ
     AI-детектор: perplexity + burstiness + NER specificity
     Consistency Score: письмо ↔ видео ↔ интервью
  │
  ▼  Слой 3: LLM (Claude Sonnet 4.6 + Groq Llama-3.3-70b)
     Только объясняет числа — не выставляет баллы
  │
  ▼
  Зона A → рекомендован к зачислению
  Зона B → AI Pre-Interview (голосовой чат, 4 вопроса)
  Зона C → отклонён с объяснением для комиссии
```

**Результат: 25 часов вместо 241. −90%. Стоимость AI за весь сезон — ~$15.**

---

## Быстрый старт для жюри

Всё задеплоено и готово к демонстрации:

| Сервис | URL |
|--------|-----|
| Фронтенд | https://invision-u-seven.vercel.app |
| Backend API | https://invisionu-screening.up.railway.app |
| Swagger UI | https://invisionu-screening.up.railway.app/api/docs |

### Вход для проверяющей стороны (комиссия)

```
Email:    jury@invisionu.kz
Пароль:   jury@invisionu.kz
```

Этот аккаунт имеет роль `reviewer` — открывает доступ к дашборду, карточкам кандидатов, истории решений и настройкам системы.

### Загрузить демо-кандидатов

Три синтетических кандидата для демонстрации системы:

```bash
# Получить токен
TOKEN=$(curl -s -X POST https://invisionu-screening.up.railway.app/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"jury@invisionu.kz","password":"jury@invisionu.kz"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Залить 3 демо-кандидата
curl -s -X POST https://invisionu-screening.up.railway.app/api/seed \
  -H "Authorization: Bearer $TOKEN"
```

Или через Swagger UI: `POST /api/seed` с токеном.

---

## Три демо-кандидата

| Кандидат | Профиль | Скор | Зона |
|----------|---------|------|------|
| **Айгерим Досова**, Шымкент | ENT 91 · IELTS 6.5 · живые истории · regional×1.12 | ~9.2 | A — рекомендована |
| **Максат Кенжеев**, Кызылорда | ENT 84 · IELTS 6.0 · кризисный лидер (паводок, 200 семей) · regional×1.12 | ~8.8 | B → Pre-Interview |
| **Дана Нурланова**, Алматы | ENT 95 · IELTS 7.0 · текст написан ChatGPT · ai_prob=0.87 | ~5.9 | C — отклонена |

---

## Что видит комиссия в карточке кандидата

- **Зона и итоговый скор** — рассчитаны тремя слоями, не одним числом
- **Объяснение от Claude** — почему именно эта зона, цитируя конкретные числа на русском
- **Скоры 7 качеств** — leadership, motivation, perseverance и др. (0–10) с радар-графиком
- **AI-детектор** — perplexity, burstiness, NER specificity — три числа, полная объяснимость
- **Attribution** — ключевые слова из текста, которые повлияли на скор
- **Письменные ответы** — полный текст для ручной проверки
- **Видео** — ссылка на Cloudinary + транскрипт (Whisper)
- **Диалог Pre-Interview** — полная стенограмма Q&A с аудио каждого вопроса
- **История решений** — кто и когда принял решение, согласился ли с AI

---

## Ключевые принципы (§6 хакатона)

- **Объяснимость**: комиссия видит каждое число — не чёрный ящик
- **Human-in-the-loop**: reviewer всегда может override решение AI с указанием причины
- **Без дискриминации**: пол, этнос, СЭС не собираются и не используются
- **Региональная справедливость**: явный коэффициент, настраивается через интерфейс
- **LLM не судья**: Claude/Groq только форматируют объяснения, зоны определяют числа

---

## Стек

| Компонент | Технология | Стоимость |
|-----------|-----------|-----------|
| Backend | FastAPI + PostgreSQL (Railway) | $5/мес |
| Фронтенд | Next.js (Vercel) | $0 |
| NLP скоринг | RuBERT / RoBERTa / mBERT + sklearn | $0 (локально) |
| AI-детектор | GPT-2 perplexity + spaCy NER | $0 (локально) |
| LLM объяснения | Claude Sonnet 4.6 | ~$0.01/заявка |
| Голосовое интервью | Groq llama-3.3-70b + Edge TTS | $0 (free tier) |
| Транскрипция видео | OpenAI Whisper medium (локально) | $0 |
| Хранение файлов | Cloudinary | $0 (free tier) |

**Итого за скрининговый сезон (965 заявок): ~$15.**

---

## Локальный запуск

```bash
git clone https://github.com/NooruzbekT/ai_screening_platform
cd ai_screening_platform
cp .env.example .env
```

Заполнить `.env`:

```env
GROQ_API_KEY=gsk_...
ANTHROPIC_API_KEY=sk-ant-...
HF_TOKEN=hf_...
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
JURY_EMAIL=jury@invisionu.kz
JURY_PASSWORD=jury@invisionu.kz
JWT_SECRET=min-32-chars-secret
DATABASE_URL=postgresql://user:pass@db:5432/invisionu
```

```bash
docker-compose up --build
```

Первый запуск: 5–10 минут (загрузка NLP моделей из HuggingFace).

| Сервис | URL |
|--------|-----|
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/api/docs |

Аккаунт комиссии (`JURY_EMAIL`) создаётся автоматически при первом старте.
