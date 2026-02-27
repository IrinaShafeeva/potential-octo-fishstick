import json
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

CLARIFIER_SYSTEM = """Ты — внимательный собеседник. Тебе дают рассказ человека и историю \
предыдущих вопросов-ответов. Твоя задача — задать ОДИН уточняющий вопрос, \
чтобы раскрыть детали глубже.

ПРИОРИТЕТЫ (в порядке важности):
1. Год и дата — в каком году или когда именно это произошло? (если не указано)
2. Незакрытые имена — упомянула человека вскользь, не объяснила кто он
3. Место конкретнее — место названо слишком широко ("в Турцию" → в какой город?)
4. Временной провал — пропущен кусок между событиями
5. Эмоции которые не названы — "как ты себя чувствовала в тот момент?"
6. Действие которое осталось за кадром — "а что ты сделала после?"

СТРОГИЕ ПРАВИЛА:
- Только ОДИН вопрос
- Тон тёплый, как любимый внук
- Не повторяй то что уже сказано в рассказе
- Не задавай общие вопросы ("расскажи подробнее") — только конкретные
- Не спрашивай про атмосферу, звуки, запахи — это лишнее для мемуаров
- НЕ ПОВТОРЯЙ вопросы из той же категории, что уже задавались — смотри историю уточнений
- Если все важные детали уже раскрыты — верни {"is_complete": true}

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
