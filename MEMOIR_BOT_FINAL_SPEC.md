# MEMOIR BOOK BOT — FINAL SPEC v2 (VOICE + INTERVIEW + MONETIZATION)

Language: Russian
Platform: Telegram (aiogram 3+)
Input: Voice-first
DB: PostgreSQL (asyncpg)
STT: OpenAI Whisper API
LLM: GPT-4o-mini (cleaning, classification), GPT-4o (literary editing)
Core: Memoir editor + book organizer + gentle interviewer

---

## 1) WHY QUESTIONS MODE

Most users struggle to start speaking. The bot must offer:
- A guided interview flow (gentle prompts)
- Topic packs (childhood, family, work, etc.)
- Adaptive follow-ups based on what was already said
- Minimal cognitive load (1 question at a time)

Key principle: the user can always ignore questions and just speak freely.

---

## 2) PRODUCT UX (BUTTONS)

### Main reply keyboard:
- 🎙 Записать воспоминание
- 🧠 Вспомнить вместе
- 📖 Моя книга
- 🧩 Структура глав
- ⭐ Подписка

### Inline buttons after memory preview:
- ✅ Сохранить в книгу
- ✏️ Исправить текст
- 🧩 Разбить на истории
- 🧷 В другую главу
- 🎙 Перезаписать

---

## 3) INTERVIEW QUESTIONS — IMPLEMENTATION

### 3.1 Two modes
A) **On-demand prompts**: user taps "Вспомнить вместе"
B) **Soft nudges**: if user silent for N days, suggest 1 question (V2)

### 3.2 Question packs (content library)
Question library grouped into packs (13 packs, 60-80 questions total):

- Детство (childhood)
- Родители и дом (parents_home)
- Школа и друзья (school)
- Молодость (youth)
- Работа и профессия (work)
- Любовь и брак (love)
- Дети и семья (children_family)
- Переезды и города (places)
- Трудные времена (hardships)
- Радости и достижения (achievements)
- Быт и традиции (traditions)
- Любимые вещи и места (favorites)
- Поздние годы (later_years)

Each question metadata:
```json
{
  "id": "childhood_001",
  "pack": "childhood",
  "text": "Каким был дом, где вы жили в детстве? Что вы хорошо помните?",
  "difficulty": "easy",
  "emotional_intensity": "low",
  "tags": ["home", "childhood"],
  "followups": [
    "Кто жил вместе с вами?",
    "Какая была обстановка: тепло, шумно, тихо?"
  ]
}
```

### 3.3 Question Router (selection logic)

1. Load user coverage map (topics already told)
2. Filter out already-asked questions
3. Prefer pack with least coverage OR user-selected pack
4. Choose next question by:
   - Easy difficulty first (then medium)
   - Low emotional intensity first
   - Avoid same tag twice in a row

### 3.4 Follow-up questions (template-based, not AI-generated for MVP)

Each question has 1-3 pre-written follow-ups.
After user answers → offer 1 follow-up from template.
Rule: max 1 follow-up per memory.

### 3.5 Question action buttons

Every question includes:
- 🎙 Ответить голосом
- 📝 Написать текстом
- 🔄 Другой вопрос
- ⏸ Не сейчас

### 3.6 Safety / comfort

For seniors: avoid intense topics early.
Start with: childhood, home, traditions, favorites.
If user skips emotional questions → move to neutral packs.

---

## 4) CONTEXT MODULES (implemented as repository methods, not separate framework)

### Author Context
- Language, preferred tone
- Known people glossary (extracted from memories)
- Known places glossary
- Already asked question IDs
- Topic coverage statistics

### Book Context
- Chapter list and order
- Chapter rules (by years / life stages / themes)
- Memory counts per chapter

### Life Timeline Context
- Extracted timeline anchors (years/decades)
- Life periods mapping

### Raw Truth Archive (MANDATORY — never overwrite)
- raw_transcript
- cleaned_transcript
- edited_memoir_text

### Senior UX Context
- Short messages preferred
- Voice-first
- 1 question at a time max

---

## 5) AI SKILLS

### MVP (Phase 1-3):
1. **Voice Processing (STT)** — Whisper API → raw transcript + confidence
2. **Oral Speech Cleaning** — GPT-4o-mini → remove fillers, make readable
3. **Memoir Literary Editor** — GPT-4o → memoir style, no clichés, no invented facts
4. **Timeline Extraction** — GPT-4o-mini → year/range/relative/unknown + confidence
5. **Chapter Classification** — GPT-4o-mini → chapter_suggestion + confidence
6. **Question Router** — deterministic algorithm (no AI needed)

### V2:
7. Memory Segmentation (split long voice into scenes)
8. Duplicate Detection (embeddings-based)
9. AI-generated follow-up questions
10. Gentle Clarification (AI asks about unclear timeline/people/places)

---

## 6) AI OUTPUT CONTRACTS (STRICT JSON)

### 6.1 Memory processing output
```json
{
  "raw_transcript": "",
  "cleaned_transcript": "",
  "edited_memoir_text": "",
  "title": "",
  "time_hint": {
    "type": "year|range|relative|unknown",
    "value": "",
    "confidence": 0.0
  },
  "chapter_suggestion": "",
  "tags": [],
  "people": [],
  "places": [],
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": ""
}
```

### 6.2 Next question output
```json
{
  "question_id": "",
  "pack": "",
  "text": "",
  "difficulty": "easy|medium",
  "emotional_intensity": "low|medium",
  "tags": [],
  "suggested_followups": []
}
```

---

## 7) DATABASE (PostgreSQL + SQLAlchemy async)

### users
- id, telegram_id, username, first_name, created_at
- is_premium (bool), premium_until (datetime nullable)
- memories_count (int, for free tier limit)

### chapters
- id, user_id, title, period_hint, order_index, created_at

### memories
- id, user_id, chapter_id (nullable)
- audio_file_id
- raw_transcript, cleaned_transcript, edited_memoir_text
- title
- time_hint_type, time_hint_value, time_confidence
- tags (json), people (json), places (json)
- created_at, approved (bool)
- source_question_id (nullable)

### questions (pre-loaded from JSON)
- id, pack, text, difficulty, emotional_intensity
- tags (json), followups (json)

### question_log
- id, user_id, question_id
- asked_at, status (asked/answered/skipped)
- answered_memory_id (nullable)

### topic_coverage
- user_id, tag, count, last_used_at

---

## 8) MONETIZATION

### Free tier (проба):
- 5 голосовых воспоминаний
- 1 глава
- 3 вопроса из интервьюера
- Без экспорта

### "Моя книга" — 3 990 ₽ / 3 месяца:
- Безлимит голосовых
- Все главы
- Полный интервьюер
- Экспорт в PDF
- Прогресс книги

### "Семейная история" — 6 990 ₽ / 3 месяца (V2):
- До 3 авторов
- Общая или раздельные книги

### Upsells:
- Печатная книга: 2990-4990 ₽
- Продление: 2990 ₽ / 3 мес
- Подарочный сертификат

### Free tier limits (constants):
- FREE_MEMORIES_LIMIT = 5
- FREE_CHAPTERS_LIMIT = 1
- FREE_QUESTIONS_LIMIT = 3

---

## 9) PROJECT STRUCTURE

```
memoir_bot/
├── .env.example
├── .gitignore
├── requirements.txt
├── bot/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── loader.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py
│   │   ├── voice.py
│   │   ├── questions.py
│   │   ├── book.py
│   │   ├── structure.py
│   │   └── subscription.py
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── main_menu.py
│   │   ├── inline_memory.py
│   │   └── inline_question.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── stt.py
│   │   ├── ai_editor.py
│   │   ├── question_router.py
│   │   ├── classifier.py
│   │   ├── timeline.py
│   │   ├── segmentation.py
│   │   ├── book_builder.py
│   │   └── export.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── models.py
│   │   └── repository.py
│   ├── data/
│   │   └── questions.json
│   └── prompts/
│       ├── __init__.py
│       ├── cleaner.py
│       ├── editor.py
│       ├── classifier.py
│       └── timeline.py
```

---

## 10) TELEGRAM HANDLERS

- **start.py** — /start, onboarding, main menu
- **voice.py** — voice intake → STT → clean → edit → preview → approve
- **questions.py** — "Вспомнить вместе", pack selection, question flow, skip/answer
- **book.py** — chapter list, chapter view, memory list, progress
- **structure.py** — create/edit/reorder chapters, move memories
- **subscription.py** — pricing display, payment handling, premium check

---

## 11) ONBOARDING FLOW

Bot message after /start:

> Здравствуйте! Я помогу вам сохранить воспоминания и собрать их в книгу.
>
> Как это работает: вы рассказываете — голосом или текстом — а я записываю,
> редактирую и раскладываю по главам.
>
> Например, расскажите: каким был двор, где вы играли в детстве?
> А я покажу, как это будет выглядеть в книге.

Buttons:
- 🎙 Начать говорить
- 🧠 Помочь вопросами
- 🧩 Сначала настрою главы

If "Помочь вопросами" → offer 3 starting packs:
- Детство
- Семья
- Работа
Then ask first question from selected pack.

---

## 12) SYSTEM PROMPT — MEMOIR EDITOR

```
You are an AI memoir editor for Russian-speaking seniors.
Rules:
1. Preserve meaning 100%. Never invent facts.
2. Keep first-person narration.
3. Remove speech fillers (ну, вот, значит, как бы).
4. Fix grammar but keep the author's voice and word choices.
5. Avoid clichés and poetic language.
6. Structure into paragraphs for readability.
7. If timeline/people/place is unclear — set unknown, do not guess.
8. Return ONLY valid JSON.
```

---

## 13) PROGRESS TRACKING

Show user their book progress:
- Total memories count
- Chapters filled / total
- Estimated book pages (1 memory ≈ 0.5-1 page)
- "Ваша книга: 12 воспоминаний, 4 главы, ~8 страниц"
- Visual progress bar (emoji-based): ▓▓▓▓░░░░░░ 40%

---

## 14) ERROR HANDLING

- STT confidence < 0.3 → "Не удалось разобрать запись. Попробуйте записать ещё раз в тихом месте."
- Voice too short (< 3 sec) → "Запись слишком короткая. Расскажите подробнее!"
- Voice too long (> 10 min) → split into segments (V2), for MVP: process first 10 min
- API timeout → retry once, then "Сервер задумался. Попробуйте через минуту."
- Empty transcript → "Не удалось распознать речь. Убедитесь, что микрофон работает."

---

END OF SPEC
