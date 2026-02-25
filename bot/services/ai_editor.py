import json
import logging

from openai import AsyncOpenAI

from bot.config import settings
from bot.prompts.cleaner import CLEANER_SYSTEM, CLEANER_USER
from bot.prompts.editor import EDITOR_SYSTEM, EDITOR_USER

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


async def clean_transcript(raw_transcript: str) -> str:
    """Remove fillers, fix grammar, keep author's voice."""
    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": CLEANER_SYSTEM},
                {"role": "user", "content": CLEANER_USER.format(raw_transcript=raw_transcript)},
            ],
            temperature=0.3,
            max_tokens=4000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Cleaning error: %s", e)
        return raw_transcript


def _format_context_list(items: list) -> str:
    """Format people/places with counts for the editor prompt.

    Accepts either list[str] or list[tuple[str, int]].
    """
    if not items:
        return "нет данных"
    if isinstance(items[0], (list, tuple)):
        return ", ".join(f"{name} (×{count})" for name, count in items[:20])
    return ", ".join(str(x) for x in items[:20])


async def edit_memoir(
    cleaned_transcript: str,
    known_people: list | None = None,
    known_places: list | None = None,
    style_notes: str | None = None,
) -> dict:
    """Literary editing: transform cleaned transcript into memoir text.

    Returns dict with keys: edited_memoir_text, title, tags, people, places,
    needs_clarification, clarification_question.
    Accepts known_people/known_places as list[str] or list[tuple[str, int]].
    """
    people_str = _format_context_list(known_people) if known_people else "нет данных"
    places_str = _format_context_list(known_places) if known_places else "нет данных"
    style_str = style_notes.strip() if style_notes else "профиль ещё формируется"

    try:
        response = await client.chat.completions.create(
            model=settings.editor_model,
            messages=[
                {"role": "system", "content": EDITOR_SYSTEM},
                {
                    "role": "user",
                    "content": EDITOR_USER.format(
                        cleaned_transcript=cleaned_transcript,
                        known_people=people_str,
                        known_places=places_str,
                        style_notes=style_str,
                    ),
                },
            ],
            temperature=0.5,
            max_tokens=4000,
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Editor returned invalid JSON: %s", text[:200] if 'text' in dir() else "N/A")
        return {
            "edited_memoir_text": cleaned_transcript,
            "title": "Без названия",
            "tags": [],
            "people": [],
            "places": [],
            "needs_clarification": False,
            "clarification_question": "",
        }
    except Exception as e:
        logger.error("Editor error: %s", e)
        return {
            "edited_memoir_text": cleaned_transcript,
            "title": "Без названия",
            "tags": [],
            "people": [],
            "places": [],
            "needs_clarification": False,
            "clarification_question": "",
        }


async def merge_clarification(memoir_text: str, clarification_answer: str) -> str:
    """Weave a clarification answer into an existing memoir text.

    Returns the merged literary text, or original + answer as fallback.
    """
    prompt = (
        "Ты — литературный редактор мемуаров. Твоя задача — дополнить текст воспоминания "
        "новой деталью, которую автор сообщил в уточнении.\n\n"
        "СТРОГИЕ ПРАВИЛА:\n"
        "1. Оригинальный текст воспоминания НЕПРИКОСНОВЕНЕН. Ни одно слово автора не убирается "
        "и не переформулируется — только сохраняется как есть.\n"
        "2. Уточнение встраивается как органичное дополнение — одно-два предложения в нужном месте "
        "или в конце, если оно не привязано к конкретному моменту.\n"
        "3. Сохрани голос автора: его интонацию, характерные слова, ритм речи.\n"
        "4. НЕ пересказывай текст заново. НЕ меняй структуру. НЕ добавляй ничего от себя.\n"
        "5. Верни ТОЛЬКО итоговый текст, без комментариев и пояснений.\n\n"
        f"ОРИГИНАЛЬНЫЙ ТЕКСТ ВОСПОМИНАНИЯ:\n{memoir_text}\n\n"
        f"УТОЧНЕНИЕ АВТОРА (добавить как деталь):\n{clarification_answer}"
    )
    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=4000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Merge clarification error: %s", e)
        return memoir_text + "\n\n" + clarification_answer
