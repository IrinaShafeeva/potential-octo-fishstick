import json
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

CLARIFIER_SYSTEM = """Ты — опытный мемуарист и интервьюер. Тебе дают рассказ человека, \
историю предыдущих вопросов-ответов и контекст (известные персонажи, главы книги).

Прочитай рассказ внимательно и найди САМУЮ ВАЖНУЮ недостающую деталь — \
ту, без которой история остаётся неполной или непонятной.

Задай ОДИН конкретный вопрос именно про эту деталь.

КАК АНАЛИЗИРОВАТЬ:
— Что в этом рассказе самое важное? Про это всё понятно?
— Есть ли ключевой факт без которого история не складывается (год, место, человек)?
— Упомянут кто-то без объяснения кто он? (но если этот человек уже известен из \
контекста персонажей — объяснение не нужно, НЕ спрашивай про него)
— Есть ли очевидный пропуск между событиями?
— Если всё ключевое уже есть — не нужно спрашивать ради вопроса

СТРОГИЕ ПРАВИЛА:
- Только ОДИН вопрос — самый важный для ЭТОГО конкретного текста
- Тон тёплый, как любимый внук
- Вопрос конкретный, не "расскажи подробнее"
- Не спрашивай про то что уже есть в рассказе или в контексте персонажей
- НЕ перефразируй уже заданные вопросы — если в истории уточнений уже спрашивали \
про что-то похожее, задай вопрос про ДРУГОЙ аспект истории
- Не зацикливайся на одной детали — если автор упомянул факт как данность \
(например «прожили месяц»), не спрашивай почему именно столько
- Задавай вопросы которые ОБОГАТЯТ историю: что чувствовал автор, \
как выглядело место, какой характер был у человека, что произошло дальше
- Используй контекст глав чтобы понять ТЕМАТИКУ — задавай вопросы \
которые помогут раскрыть эту тему глубже
- Не задавай вопросы про атмосферу или ощущения если это не центр истории
- Возвращай {"is_complete": true} ТОЛЬКО если история развёрнутая: есть время/год, \
место, люди, что произошло. Одно-два предложения — это никогда не полная история, \
обязательно задай вопрос.

Верни JSON — одно из двух:
{"is_complete": false, "question": "текст одного конкретного вопроса"}
{"is_complete": true}

Только валидный JSON, без markdown."""


async def ask_clarification(
    story: str,
    history: list[dict],
    known_characters: list | None = None,
    chapter_summaries: list[dict] | None = None,
) -> dict:
    """Ask one clarification question or declare story complete.

    history: list of {"role": "question"|"answer", "text": "..."}
    known_characters: list of Character ORM objects (name, relation_to_author, description).
    chapter_summaries: list of {"title": str, "summary": str} for chapter context.
    Returns: {"is_complete": True} or {"is_complete": False, "question": "..."}
    """
    history_text = ""
    if history:
        lines = []
        for item in history:
            if item["role"] == "question":
                prefix = "Вопрос:"
            elif item["role"] == "answer":
                prefix = "Ответ:"
            else:  # skipped
                prefix = "Пропущен (не задавай похожий):"
            lines.append(f"{prefix} {item['text']}")
        history_text = "\n\nИстория уточнений:\n" + "\n".join(lines)

    characters_text = ""
    if known_characters:
        chars = []
        for c in known_characters[:15]:
            name = getattr(c, "name", None) or c.get("name", "") if isinstance(c, dict) else c.name
            rel = getattr(c, "relation_to_author", None) or (c.get("relation_to_author", "") if isinstance(c, dict) else "")
            desc = getattr(c, "description", None) or (c.get("description", "") if isinstance(c, dict) else "")
            parts = [name]
            if rel:
                parts.append(f"({rel})")
            if desc:
                parts.append(f"— {desc}")
            chars.append(" ".join(parts))
        characters_text = "\n\nИзвестные персонажи (уже упоминались ранее):\n" + "\n".join(chars)

    chapters_text = ""
    if chapter_summaries:
        ch_lines = []
        for ch in chapter_summaries:
            title = ch.get("title", "")
            summary = ch.get("summary", "")
            if summary:
                ch_lines.append(f"«{title}»: {summary}")
            else:
                ch_lines.append(f"«{title}»")
        chapters_text = "\n\nГлавы книги автора:\n" + "\n".join(ch_lines)

    user_content = f"Рассказ автора:\n{story}{history_text}{characters_text}{chapters_text}"

    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": CLARIFIER_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        logger.error("Clarifier error: %s", e)
        return {"is_complete": True}  # Fallback: skip clarification on error
