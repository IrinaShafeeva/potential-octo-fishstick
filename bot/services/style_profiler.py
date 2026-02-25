"""Builds and updates a cumulative author style profile from approved memories."""
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

_UPDATE_PROMPT = """\
Ты анализируешь стиль автора мемуаров, чтобы помочь редактору сохранить его голос.

Тебе дан:
1. ТЕКУЩИЙ ПРОФИЛЬ стиля автора (может быть пустым для первой записи)
2. НОВЫЙ ТЕКСТ воспоминания — уже отредактированный, подтверждённый автором

Обнови профиль: добавь новые наблюдения, укрепи повторяющиеся паттерны, убери устаревшее.

Фиксируй ТОЛЬКО то, что реально прослеживается в текстах:
— Характерные слова и выражения автора (конкретные примеры в кавычках)
— Ритм и длина предложений (короткие рубленые / длинные с отступлениями / смешанные)
— Как автор начинает воспоминания (с действия / с рефлексии / с места и времени)
— Эмоциональный тон (сдержанный / открытый / ироничный / лирический)
— Что автор НЕ делает (избегает пафоса, не объясняет чувства, не морализирует — если заметно)

Верни ТОЛЬКО обновлённый профиль — короткий связный текст до 400 слов.
Никаких заголовков, никаких списков с маркерами — просто абзацный текст о стиле автора.

ТЕКУЩИЙ ПРОФИЛЬ:
{existing_notes}

НОВЫЙ ТЕКСТ ВОСПОМИНАНИЯ:
{new_memory_text}"""


async def update_style_profile(
    existing_notes: str | None,
    new_memory_text: str,
) -> str:
    """Analyse a new approved memory and return an updated style profile string.

    Returns the updated profile text, or existing_notes unchanged on error.
    """
    if not new_memory_text or len(new_memory_text.split()) < 30:
        # Too short to extract meaningful style signals
        return existing_notes or ""

    prompt = _UPDATE_PROMPT.format(
        existing_notes=existing_notes or "(профиль ещё не сформирован)",
        new_memory_text=new_memory_text,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Style profiler error: %s", e)
        return existing_notes or ""
