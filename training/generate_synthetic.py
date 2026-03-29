"""
Генерация синтетических данных RU + KZ с нуля через Claude Haiku 4.5
~$0.39 за 560 текстов (280 RU + 280 KZ)

"""

import json, os, re, time, random
from pathlib import Path
from tqdm import tqdm
import anthropic

MODEL = "claude-haiku-4-5"
DELAY = 0.3

CITIES_RU = [
    "Шымкент", "Кызылорда", "Тараз", "Актобе", "Семей",
    "Павлодар", "Туркестан", "Петропавловск", "Уральск",
    "Костанай", "Атырау", "Актау", "Усть-Каменогорск",
    "аул Шиели Кызылординской области",
    "посёлок Сарыагаш ЮКО",
    "Жанаозен Мангистауской области",
    "Балхаш Карагандинской области",
    "районный центр Арысь ЮКО",
]

CITIES_KZ = [
    "Шымкент", "Қызылорда", "Тараз", "Ақтөбе", "Семей",
    "Павлодар", "Түркістан", "Петропавл", "Орал",
    "Қостанай", "Атырау", "Ақтау", "Өскемен",
    "Қызылорда облысының Шиелі ауылы",
    "Жаңаөзен қаласы",
    "Балқаш қаласы",
    "Оңтүстік Қазақстан облысының Сарыағаш ауылы",
]

NAMES_RU = [
    "Айгерим", "Нурлан", "Диана", "Дамир", "Акмарал",
    "Берик", "Айдана", "Ержан", "Молдир", "Асхат",
    "Жанара", "Назгуль", "Бекзат", "Сауле", "Руслан",
    "Гульмира", "Адиль", "Карина", "Арман", "Зарина",
]

NAMES_KZ = [
    "Айгерім", "Нұрлан", "Диана", "Дәмір", "Ақмарал",
    "Бекзат", "Айдана", "Ержан", "Молдір", "Асхат",
    "Жанара", "Назгүл", "Берік", "Сәуле", "Руслан",
    "Гүлмира", "Әділ", "Карина", "Арман", "Зарина",
]

PROGRAMS = [
    "Creative Engineering",
    "IT Product Design",
    "Sociology: Leadership and Innovation",
    "Public Policy and Development",
    "Digital Media and Marketing",
]

# ─── вопросы и признаки для каждого качества ──────────────────────────────

QUALITIES_RU = {
    "leadership": {
        "q": "Что для тебя значит лидерство? Приведи реальный пример из своей жизни.",
        "high":   "Конкретная роль с реальным влиянием на других. Измеримый результат (число людей, конкретный исход). Лидерство через вдохновение. Фразы: «по моей инициативе», «я предложила и команда достигла».",
        "medium": "Есть конкретный пример, но роль скромная. Результат ограничен. Хорошее намерение, недостаточная глубина.",
        "low":    "Абстрактные рассуждения без примеров. Шаблонные фразы. Нет личного опыта.",
    },
    "motivation": {
        "q": "Почему ты хочешь учиться в inVision U? Как это связано с твоими долгосрочными целями?",
        "high":   "Чёткая связь личной истории → программы → цели. Привязка к конкретному региону. Желание вернуться и изменить свой город.",
        "medium": "Мотивация есть но общая. Нет глубокой связи с личной историей.",
        "low":    "Шаблонные фразы. «Уникальная возможность». Нет личной истории.",
    },
    "perseverance": {
        "q": "Какой главный вызов ты преодолел в своей жизни? Что тебе помогло?",
        "high":   "Конкретная трудность с деталями. Несколько попыток, не сдался. Чему конкретно научился. Рост через провал.",
        "medium": "Вызов есть но незначительный. Преодоление описано поверхностно.",
        "low":    "Нет реального вызова. «Я всегда справлялся». Абстрактно.",
    },
    "teamwork": {
        "q": "Опиши ситуацию где ты работал в команде над трудной задачей. Какова была твоя роль?",
        "high":   "Конкретные роли участников. Был реальный конфликт который решили вместе. Результат команды больше суммы частей.",
        "medium": "Командная работа есть но поверхностно. Роль кандидата неясна.",
        "low":    "Нет конкретного примера. «Я люблю работать в команде». Абстрактно.",
    },
    "goal_pursuit": {
        "q": "Опиши конкретную большую цель которую ты поставил и к которой идёшь. Как ты к ней движешься?",
        "high":   "Конкретная цель с дедлайном. Пошаговый план. Препятствия и как преодолел. Измеримый результат.",
        "medium": "Цель есть но план нечёткий.",
        "low":    "Нет конкретной цели. «Хочу добиться успеха». Абстрактно.",
    },
    "intrinsic_motivation": {
        "q": "Что ты делаешь когда никто не смотрит и не оценивает? Чем занимаешься для себя?",
        "high":   "Конкретная деятельность ради процесса, не результата. Нет упоминания наград. Глубокое личное увлечение давно и без внешнего стимула.",
        "medium": "Увлечение есть но мотивация смешанная.",
        "low":    "Всё делается ради оценки или признания. Нет внутренней мотивации.",
    },
    "prosocial_purpose": {
        "q": "Какую проблему в твоём городе или регионе ты хотел бы решить первой? Почему именно её?",
        "high":   "Конкретная локальная проблема с деталями. Понимание системных причин. Конкретный план. Ориентация на других, не на себя.",
        "medium": "Проблема упомянута без деталей и плана.",
        "low":    "Глобальные абстрактные проблемы. Нет локального контекста.",
    },
}

QUALITIES_KZ = {
    "leadership": {
        "q": "Сен үшін көшбасшылық дегеніміз не? Өмірден нақты мысал келтір.",
        "high":   "Басқа адамдарға нақты әсер еткен рөл. Өлшенетін нәтиже. Бұйрықпен емес шабыт беру арқылы жетекшілік. «Менің бастамам бойынша» деген тіркестер.",
        "medium": "Нақты мысал бар, бірақ рөл шағын. Нәтиже шектеулі.",
        "low":    "Нақты мысалсыз абстрактілі ойлар. Жеке тәжірибе жоқ.",
    },
    "motivation": {
        "q": "Неліктен inVision U-да оқығың келеді? Бұл ұзақ мерзімді мақсаттарыңмен қалай байланысты?",
        "high":   "Жеке тарих → бағдарлама → мақсат арасындағы нақты байланыс. Өз аймағына қайтып оны өзгерткісі келеді.",
        "medium": "Мотивация бар бірақ жалпы. Жеке тарихпен байланысы жоқ.",
        "low":    "Шаблонды сөздер. Жеке тарих жоқ.",
    },
    "perseverance": {
        "q": "Өміріңдегі ең үлкен қиындықты қалай жеңдің? Саған не көмектесті?",
        "high":   "Нақты мәліметтермен қиындық. Бірнеше әрекет, бірінші рет берілген жоқ. Не үйренгені нақты.",
        "medium": "Қиындық бар бірақ маңызды емес. Жеңу үстірт.",
        "low":    "Нақты қиындық жоқ. «Мен әрқашан жеңе алдым».",
    },
    "teamwork": {
        "q": "Қиын тапсырмада команда болып жұмыс істеген жағдайды сипатта. Сенің рөлің қандай болды?",
        "high":   "Әр қатысушының нақты рөлі. Бірге шешкен қиындық. Команда нәтижесі бөліктер қосындысынан үлкен.",
        "medium": "Команда жұмысы бар бірақ үстірт. Рөл белгісіз.",
        "low":    "Нақты мысал жоқ. Абстрактілі.",
    },
    "goal_pursuit": {
        "q": "Қойған үлкен мақсатыңды және оған қалай жеткеніңді сипатта.",
        "high":   "Мерзімі бар нақты мақсат. Қадамдық іс-әрекеттер. Кедергілер мен оларды жеңу. Өлшенетін нәтиже.",
        "medium": "Мақсат бар бірақ жоспар түсініксіз.",
        "low":    "Нақты мақсат жоқ. Абстрактілі.",
    },
    "intrinsic_motivation": {
        "q": "Ешкім қарамайтын және бағаламайтын кезде не істейсің? Өзің үшін немен айналысасың?",
        "high":   "Нәтиже үшін емес процесс үшін нақты іс-әрекет. Марапат ескерілмеген. Терең жеке қызығушылық.",
        "medium": "Қызығушылық бар бірақ мотивация аралас.",
        "low":    "Барлығы баға үшін жасалады. Ішкі мотивация жоқ.",
    },
    "prosocial_purpose": {
        "q": "Өз қалаңда немесе аймағыңда алдымен қандай мәселені шешер едің? Неліктен дәл осыны?",
        "high":   "Нақты жергілікті мәселе мәліметтермен. Жүйелік себептерді түсіну. Нақты жоспар. Өзгелерге бағдарлану.",
        "medium": "Мәселе айтылған бірақ жоспарсыз.",
        "low":    "Жаһандық абстрактілі мәселелер. Жергілікті контекст жоқ.",
    },
}


def make_prompt_ru(quality: str, level: str, city: str, name: str, program: str) -> tuple[str, str]:
    qd = QUALITIES_RU[quality]
    system = """Ты генерируешь обучающие данные для NLP-модели.
Пиши реалистичные ответы от лица молодого человека 17–19 лет из Казахстана.
Требования: длина строго 180–280 слов, живой разговорный стиль, конкретные детали (имена людей, места, числа), казахстанский контекст, первое лицо.
Верни ТОЛЬКО текст ответа без заголовков и пояснений."""

    user = f"""Напиши ответ на вопрос от лица {name} из {city}, программа {program}.

Вопрос: «{qd['q']}»

Требуемый уровень качества «{quality}» ({level.upper()}):
{qd[level]}

Используй конкретные детали из жизни в {city}. Строго 180–280 слов."""
    return system, user


def make_prompt_kz(quality: str, level: str, city: str, name: str, program: str) -> tuple[str, str]:
    qd = QUALITIES_KZ[quality]
    system = """Сен NLP моделіне арналған оқу деректерін жасайсың.
17–19 жастағы Қазақстандық жас адамның атынан шынайы жауаптар жаз.
Талаптар: қатаң 180–280 сөз, тірі сөйлесу стилі, нақты мәліметтер (есімдер, жер атаулары, сандар), қазақстандық контекст, бірінші жақ.
Тек жауап мәтінін қайтар, тақырып пен түсіндірме жоқ."""

    user = f"""{name} атынан жауап жаз. {city}, {program} бағдарламасы.

Сұрақ: «{qd['q']}»

«{quality}» сапасының деңгейі ({level.upper()}):
{qd[level]}

{city} өміріндегі нақты мәліметтерді қолдан. Қатаң 180–280 сөз."""
    return system, user


def generate_text(client: anthropic.Anthropic, system: str, user: str, retries=3) -> str | None:
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=500, temperature=0.85,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = msg.content[0].text.strip()
            text = re.sub(r'^["\']|["\']$', '', text)
            text = re.sub(r'^(Ответ|Answer|Жауап):\s*', '', text, flags=re.IGNORECASE)
            if len(text.split()) < 100:
                raise ValueError(f"Too short: {len(text.split())} words")
            return text
        except anthropic.RateLimitError:
            print("  Rate limit, waiting 10s...")
            time.sleep(10)
        except Exception as e:
            print(f"  Error {attempt+1}: {e}")
            time.sleep(2)
    return None


def build_scores(primary: str, level: str, all_q: list) -> dict:
    if level == "high":
        ps, other = random.randint(8, 10), (3, 7)
    elif level == "medium":
        ps, other = random.randint(5, 7), (2, 6)
    else:
        ps, other = random.randint(1, 4), (1, 5)
    return {q: (ps if q == primary else random.randint(*other)) for q in all_q}


def generate_lang(client: anthropic.Anthropic, lang: str, output: str, total=280):
    qualities = list((QUALITIES_RU if lang == "ru" else QUALITIES_KZ).keys())
    cities = CITIES_RU if lang == "ru" else CITIES_KZ
    names  = NAMES_RU  if lang == "ru" else NAMES_KZ

    # план: 7 качеств × (20 high + 20 medium + 10 low) = 350, берём 280
    plan = []
    for q in qualities:
        plan += [(q, "high")] * 20 + [(q, "medium")] * 20 + [(q, "low")] * 10
    random.shuffle(plan)
    plan = plan[:total]

    results = []
    if Path(output).exists():
        with open(output, encoding='utf-8') as f:
            results = json.load(f)
        print(f"  Resuming from {len(results)}")

    done = len(results)
    errors = 0

    for i, (quality, level) in enumerate(tqdm(plan[done:], initial=done, total=total, desc=lang.upper())):
        city    = random.choice(cities)
        name    = random.choice(names)
        program = random.choice(PROGRAMS)

        if lang == "ru":
            system, user = make_prompt_ru(quality, level, city, name, program)
        else:
            system, user = make_prompt_kz(quality, level, city, name, program)

        text = generate_text(client, system, user)
        if text is None:
            errors += 1
            continue

        results.append({
            "id":              f"{lang}_{quality}_{level}_{done+i+1:04d}",
            "text":            text,
            "lang":            lang,
            "source":          "synthetic_claude",
            "primary_quality": quality,
            "level":           level,
            "word_count":      len(text.split()),
            "city":            city,
            "program":         program,
            "scores":          build_scores(quality, level, qualities),
        })

        if len(results) % 20 == 0:
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(DELAY)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    from collections import Counter
    print(f"\n{lang.upper()} done: {len(results)} texts, {errors} errors")
    print(f"  Qualities: {dict(Counter(r['primary_quality'] for r in results))}")
    print(f"  Levels:    {dict(Counter(r['level'] for r in results))}")
    avg = sum(r['word_count'] for r in results) // max(len(results), 1)
    print(f"  Avg words: {avg}")


def main():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("=== Generating RU dataset ===")
    generate_lang(client, "ru", "ru_part.json", total=280)

    print("\n=== Generating KZ dataset ===")
    time.sleep(3)
    generate_lang(client, "kz", "kz_part.json", total=280)

    print(f"\n✓ Done. Cost estimate: ~$0.40")
    print("  ru_part.json — 280 записей на русском")
    print("  kz_part.json — 280 записей на казахском")
    print("\nЗапусти merge_dataset.py для объединения с en_labeled.json")


if __name__ == "__main__":
    main()
