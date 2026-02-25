"""Maintains a running thread summary for each chapter."""
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


async def refresh_thread_summary(
    chapter_title: str,
    existing_summary: str | None,
    new_memory_text: str,
) -> str | None:
    """Append new memory to the chapter's running digest.

    Returns updated summary (≤150 words), or existing_summary on error.
    """
    if not new_memory_text or len(new_memory_text.split()) < 10:
        return existing_summary

    if existing_summary:
        prompt = (
            f"Ты ведёшь краткое содержание главы мемуаров «{chapter_title}».\n\n"
            f"ТЕКУЩЕЕ КРАТКОЕ СОДЕРЖАНИЕ:\n{existing_summary}\n\n"
            f"НОВОЕ ВОСПОМИНАНИЕ, ДОБАВЛЕННОЕ В ГЛАВУ:\n{new_memory_text}\n\n"
            "Обнови краткое содержание: добавь ключевые факты из нового воспоминания. "
            "Сохрани всё важное из старого содержания. "
            "Не более 150 слов. "
            "Верни ТОЛЬКО обновлённый текст, без заголовков и пояснений."
        )
    else:
        prompt = (
            f"Напиши краткое содержание первого воспоминания из главы мемуаров «{chapter_title}».\n\n"
            f"ТЕКСТ ВОСПОМИНАНИЯ:\n{new_memory_text}\n\n"
            "Укажи кратко: кто, что, когда, где — ключевые факты и эмоциональный тон. "
            "Не более 100 слов. "
            "Верни ТОЛЬКО краткое содержание, без заголовков и пояснений."
        )

    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Thread summary update error: %s", e)
        return existing_summary
