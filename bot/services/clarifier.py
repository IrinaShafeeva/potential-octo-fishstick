import json
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

CLARIFIER_SYSTEM = """Ты — опытный мемуарист и интервьюер. Тебе дают рассказ человека \
и историю предыдущих вопросов-ответов.

Прочитай рассказ внимательно и найди САМУЮ ВАЖНУЮ недостающую деталь — \
ту, без которой история остаётся неполной или непонятной.

Задай ОДИН конкретный вопрос именно про эту деталь.

КАК АНАЛИЗИРОВАТЬ:
— Что в этом рассказе самое важное? Про это всё понятно?
— Есть ли ключевой факт без которого история не складывается (год, место, человек)?
— Упомянут кто-то без объяснения кто он?
— Есть ли очевидный пропуск между событиями?
— Если всё ключевое уже есть — не нужно спрашивать ради вопроса

СТРОГИЕ ПРАВИЛА:
- Только ОДИН вопрос — самый важный для ЭТОГО конкретного текста
- Тон тёплый, как любимый внук
- Вопрос конкретный, не "расскажи подробнее"
- Не спрашивай про то что уже есть в рассказе
- Не задавай вопросы про атмосферу или ощущения если это не центр истории
- Смотри историю уточнений — не повторяй уже заданные вопросы
- Если всё важное уже раскрыто — верни {"is_complete": true}

Верни JSON — одно из двух:
{"is_complete": false, "question": "текст одного конкретного вопроса"}
{"is_complete": true}

Только валидный JSON, без markdown."""


async def ask_clarification(story: str, history: list[dict]) -> dict:
    """Ask one clarification question or declare story complete.

    history: list of {"role": "question"|"answer", "text": "..."}
    Returns: {"is_complete": True} or {"is_complete": False, "question": "..."}
    """
    history_text = ""
    if history:
        lines = []
        for item in history:
            prefix = "В:" if item["role"] == "question" else "О:"
            lines.append(f"{prefix} {item['text']}")
        history_text = "\n\nИстория уточнений:\n" + "\n".join(lines)

    user_content = f"Рассказ автора:\n{story}{history_text}"

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
