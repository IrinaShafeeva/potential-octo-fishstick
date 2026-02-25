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


async def edit_memoir(
    cleaned_transcript: str,
    known_people: list[str] | None = None,
    known_places: list[str] | None = None,
) -> dict:
    """Literary editing: transform cleaned transcript into memoir text.

    Returns dict with keys: edited_memoir_text, title, tags, people, places,
    needs_clarification, clarification_question.
    """
    people_str = ", ".join(known_people) if known_people else "нет данных"
    places_str = ", ".join(known_places) if known_places else "нет данных"

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
        "Ты — литературный редактор мемуаров.\n"
        "Тебе дан готовый текст воспоминания и уточняющий ответ автора.\n"
        "Встрой ответ органично в основной текст — так, чтобы получился единый связный рассказ "
        "от первого лица. Сохрани стиль и голос автора. "
        "Верни ТОЛЬКО итоговый текст, без пояснений.\n\n"
        f"ТЕКСТ ВОСПОМИНАНИЯ:\n{memoir_text}\n\n"
        f"УТОЧНЕНИЕ АВТОРА:\n{clarification_answer}"
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
