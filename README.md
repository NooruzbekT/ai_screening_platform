# inVision U — AI Screening Platform

> **Decentrathon 5.0 · Track: AI inDrive**

## Проблема

inVision U получает **965 заявок** на **35 мест**. Ручной скрининг каждой заявки — 15 минут. Итого: **241 час непрерывной работы** приёмной комиссии до начала учебного года.

Вся работа сводится к трём повторяющимся действиям: проверить ENT, прочитать эссе, посмотреть видео. Это именно то, что делает AI.

## Решение

Автоматизированная система скрининга на трёх слоях:

```
Заявка
  │
  ▼  Слой 1: Rule Engine
     ENT ≥ 80 / IELTS ≥ 6.0 / GPA (иностранцы)
     Региональный коэффициент 0.95–1.15 (настраивается комиссией)
  │
  ▼  Слой 2: NLP + AI-детектор
     7 качеств лидерства (Penn University метод)
     Три модели: RoBERTa-EN / RuBERT-RU / mBERT-KZ
     AI-детектор: perplexity + burstiness + NER specificity
     Consistency Score: письмо ↔ видео ↔ интервью
  │
  ▼  Слой 3: LLM (Claude Sonnet + Groq Llama-3.3-70b)
     Только объясняет числа — не выставляет баллы
  │
  ▼
  Зона A → рекомендован к зачислению
  Зона B → AI Pre-Interview (голосовой чат, 4 вопроса)
  Зона C → отклонён с объяснением для комиссии
```

**Результат: 25 часов вместо 241. −90%.**

---

## Быстрый старт для жюри

Всё задеплоено:

| Сервис | URL |
|--------|-----|
| Фронтенд | https://invision-u-seven.vercel.app |
| Backend API | https://invisionu-screening.up.railway.app |
| Swagger UI | https://invisionu-screening.up.railway.app/api/docs |

Аккаунт комиссии создаётся автоматически при старте — логин из переменных окружения `JURY_EMAIL` / `JURY_PASSWORD`.

**Загрузить синтетических кандидатов:**
```bash
# 1. Получить токен
TOKEN=$(curl -s -X POST https://invisionu-screening.up.railway.app/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<JURY_EMAIL>","password":"<JURY_PASSWORD>"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Залить 3 демо-кандидата
curl -s -X POST https://invisionu-screening.up.railway.app/api/seed \
  -H "Authorization: Bearer $TOKEN"
```

---

## Три демо-кандидата

| Кандидат | Профиль | Скор | Зона |
|----------|---------|------|------|
| **Айгерим Досова**, Шымкент | ENT 91 · IELTS 6.5 · живые истории (пожар, 3D-кружок) · regional×1.0 | 9.21 | A |
| **Максат Кенжеев**, Кызылорда | ENT 84 · IELTS 6.0 · кризисный лидер (паводок, 200 семей) · regional×1.12 | 8.83 | B → Pre-Interview |
| **Дана Нурланова**, Алматы | ENT 95 · IELTS 7.0 · текст написан ChatGPT · ai_prob=0.87 | 5.9 | C |

---

## Что видит комиссия в карточке кандидата

- **zone_explanation** — Claude Sonnet объясняет почему именно эта зона, цитируя конкретные числа
- **Скоры 7 качеств** — leadership, motivation, perseverance и др. (0–10)
- **AI-детектор** — perplexity, burstiness, NER specificity с порогами
- **Attribution** — ключевые слова из текста, повлиявшие на скор
- **Письменные ответы** — полный текст для ручной проверки
- **Видео** — ссылка + транскрипт (Whisper)
- **Диалог Pre-Interview** — полная стенограмма Q&A с голосового чата

---

## Ключевые принципы (§6 хакатона)

- **Объяснимость**: комиссия видит каждое число — не чёрный ящик
- **Human-in-the-loop**: reviewer всегда может override решение AI
- **Без дискриминации**: пол, этнос, СЭС не собираются и не используются
- **Региональная справедливость**: явный коэффициент, настраивается через API
- **LLM не судья**: Claude/Groq только форматируют объяснения, зоны определяют числа

---

## Стек

| Компонент | Технология | Стоимость |
|-----------|-----------|-----------|
| Backend | FastAPI + PostgreSQL | $0 |
| NLP scoring | RuBERT / RoBERTa / mBERT + sklearn | $0 (локально) |
| AI-детектор | GPT-2 perplexity + spaCy NER | $0 (локально) |
| LLM объяснения | Claude Sonnet 4.6 (Anthropic API) | ~$0.01/заявка |
| Голосовое интервью | Groq llama-3.3-70b + Edge TTS | $0 (free tier) |
| Транскрипция видео | OpenAI Whisper medium (локально) | $0 |
| Деплой | Railway Hobby + Vercel | $5/мес |

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
GROQ_API_KEY=gsk_...          # console.groq.com (бесплатно)
ANTHROPIC_API_KEY=sk-ant-...  # console.anthropic.com
HF_TOKEN=hf_...               # huggingface.co/settings/tokens
JURY_EMAIL=jury@yourdomain.kz
JURY_PASSWORD=strongpassword
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
