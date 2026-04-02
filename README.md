# inVision U — AI Screening Platform

> **Decentrathon 5.0 · Track: AI inDrive**
> Автоматизированная система скрининга абитуриентов на основе NLP и LLM

---

## 🚀 Быстрый старт — 2 варианта

### Вариант 1: Живое демо (рекомендуется для жюри)

Всё уже задеплоено и готово к работе:

| Компонент | URL |
|-----------|-----|
| **Фронтенд** | https://invision-u-seven.vercel.app |
| **Backend API** | https://invisionu-screening.up.railway.app |
| **Swagger UI** | https://invisionu-screening.up.railway.app/api/docs |

**Аккаунт для жюри (reviewer):**
```
Email:    jury@invisionu.kz
Password: jury2025!
```

---

### Вариант 2: Локальный запуск через Docker

**Требования:** Docker Desktop, 8+ GB RAM, интернет (для загрузки моделей)

```bash
# 1. Клонировать репозиторий
git clone https://github.com/team/invisionu-screening
cd invisionu-screening

# 2. Настроить окружение
cp .env.example .env
```

Открыть `.env` и заполнить два ключа:

```env
GROQ_API_KEY=gsk_...       # получить на console.groq.com (бесплатно)
HF_TOKEN=hf_...            # получить на huggingface.co/settings/tokens
HF_REPO_ID=Nooruzbek/invisionu-models  # уже указан — не менять
```

```bash
# 3. Запустить
docker-compose up --build
```

Первый запуск займёт **5–10 минут** (загрузка моделей из HuggingFace).

| Сервис | URL |
|--------|-----|
| Фронтенд | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/api/docs |

---

## 🎬 Сценарий демо для жюри

### Шаг 1 — Загрузить тестовых кандидатов

В Swagger UI или через curl:

```bash
curl -X POST https://invisionu-screening.up.railway.app/api/seed \
  -H "Authorization: Bearer <токен жюри>"
```

Или прямо в интерфейсе: **Dashboard → кнопка "Загрузить демо-данные"**

Загрузятся три архетипа:

| Кандидат | Профиль | Балл | Зона |
|----------|---------|------|------|
| **Айгерим Досова** | ENT 91, Шымкент, живые истории (экотряд, пожар) | 9.21 | ✅ A |
| **Максат Кенжеев** | ENT 84, Кызылорда, кризисный лидер (паводок) | 8.83 | ⚡ B |
| **Дана Нурланова** | ENT 95, Алматы, текст написан ChatGPT | 5.9 | ❌ C |

### Шаг 2 — Dashboard комиссии

- Ранжированный список заявок по финальному скору
- Фильтры: зона / регион / AI-флаг / программа
- Статистика в шапке: всего / зона A / зона B / зона C

### Шаг 3 — Карточка Айгерим (Зона A)

Показывает работу **региональных коэффициентов**: Шымкент ×1.12 поднял итоговый балл выше алматинского отличника. Вкладка «Attribution» — топ-слова, повлиявшие на каждый скор.

### Шаг 4 — Карточка Даны (Зона C — AI-детектор)

- AI-вероятность: **87%**
- Perplexity: 12.4 (норма живого текста: 35–80)
- Burstiness: 0.07 (норма: 3.0–8.0)
- Specificity NER: 0.4% (норма: ≥8%) — нет имён, дат, мест

### Шаг 5 — Страница Analytics

AUROC по каждому из 7 качеств, Fairness-аудит по регионам, статистика AI-детектора, сравнение с rule-based baseline.

### Шаг 6 — Настройки

Веса качеств, пороги зон, региональные коэффициенты — всё настраивается комиссией в реальном времени.

---

## 🏗 Архитектура системы

```
Заявка кандидата
       │
       ▼
┌─────────────────────────────────┐
│  Слой 1: Rule-based Gate        │
│  ENT ≥ 80 / IELTS ≥ 6.0        │
│  Региональный коэффициент 0.95–1.15 │
└────────────┬────────────────────┘
             │ прошёл
             ▼
┌─────────────────────────────────┐
│  Слой 2: NLP-модели             │
│  • 3 модели: EN/RU/KZ           │
│  • 7 качеств (leadership, ...)  │
│  • AI-детектор (perplexity,     │
│    burstiness, specificity NER) │
│  • Consistency Score            │
│    (письмо ↔ видео)             │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Слой 3: LLM (Groq / Llama)     │
│  Генерирует объяснения          │
│  для комиссии на русском        │
│  НЕ выставляет баллы            │
└────────────┬────────────────────┘
             │
             ▼
     Зона A / B / C
```

### Формула итогового балла

```
final_score = (nlp_score × 0.70 + struct_score × 0.30) × regional_coeff

nlp_score   = Σ(quality_i × weight_i)  # 7 качеств с весами
struct_score = f(ENT_norm, IELTS_norm, completeness) → 0–10
regional_coeff: Алматы/Астана=0.95 | малые города=1.10–1.12 | сёла=1.15
```

### Зоны решений

| Зона | Условие | Действие |
|------|---------|----------|
| **A** | score ≥ 8.0 AND consistency ≥ 0.75 AND AI < 20% | Рекомендован на финал |
| **B** | score 6.0–7.9 OR consistency < 0.6 OR AI 20–60% | AI Pre-Interview (15 мин) |
| **C** | score < 6.0 OR AI > 60% | Soft reject → ревью комиссии |

---

## 🧠 NLP-модели

| Язык | Базовая модель | Данные дообучения |
|------|---------------|-------------------|
| EN | roberta-base | Kaggle essays + silver labeling |
| RU | DeepPavlov/rubert-base-cased | Синтез Claude ~280 примеров |
| KZ | bert-base-multilingual-cased | Синтез Claude ~280 примеров |

Обученные `.pkl` файлы хранятся в [HuggingFace Hub](https://huggingface.co/Nooruzbek/invisionu-models) и автоматически скачиваются при старте контейнера.

**Fallback:** если модели недоступны — система использует `paraphrase-multilingual-MiniLM-L12-v2`. Все функции сохраняются, точность немного ниже.

---

## 📊 Метрики качества

| Метрика | Достигнуто | Минимум |
|---------|-----------|---------|
| AUROC (среднее по 7 качествам) | 0.87 | 0.75 |
| F1 macro | 0.81 | 0.70 |
| AI-детектор F1 | 0.84 | 0.75 |
| Улучшение vs baseline | +18% | +10% |

---

## 🔐 Аккаунты для тестирования

| Роль | Email | Пароль |
|------|-------|--------|
| Reviewer (комиссия) | `jury@invisionu.kz` | `jury2025!` |
| Applicant (Айгерим) | `aigerin.dosova@seed.invisionu.kz` | `demo1234` |
| Applicant (Максат) | `maksat.kenzheev@seed.invisionu.kz` | `demo1234` |
| Applicant (Дана) | `dana.nurlanova@seed.invisionu.kz` | `demo1234` |

---

## 🛠 Технический стек

| Слой | Технология |
|------|-----------|
| Frontend | React 18 + Vite 5 + TailwindCSS + shadcn/ui |
| Backend | Python FastAPI 0.110+ |
| БД | PostgreSQL 16 |
| NLP | HuggingFace Transformers + scikit-learn |
| AI-детектор | spaCy + NLTK (perplexity, burstiness, NER) |
| Транскрипция | Whisper medium (open source) |
| LLM | Groq API (llama-3.3-70b) — объяснения |
| Деплой | Docker Compose / Railway + Vercel |

---

## 📁 Структура репозитория

```
invisionu-screening/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # все эндпоинты
│   │   ├── models/scorer.py       # оркестратор 3 слоёв
│   │   ├── models/nlp_model.py    # NLP scoring
│   │   ├── models/ai_detector.py  # детектор AI-текстов
│   │   ├── models/consistency.py  # cosine similarity
│   │   ├── models/transcriber.py  # Whisper
│   │   └── models/llm_explainer.py# Claude / Groq API
│   ├── download_models.py         # авто-загрузка .pkl из HuggingFace
│   └── requirements.txt
├── training/
│   ├── train_models_v3.ipynb      # Google Colab ноутбук
│   ├── dataset_final.json         # итоговый датасет
│   └── silver_labeling.py         # авторазметка EN эссе
├── docker-compose.yml
└── .env.example
```

---

## 📌 Ключевая цифра

> **965 заявок × 15 мин = 241 час ручной работы → 25 часов с нашей системой. −90%. Стоимость AI за сезон: ~$11.**
