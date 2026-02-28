import json
import logging

from openai import AsyncOpenAI

from bot.config import settings
from bot.prompts.cleaner import CLEANER_SYSTEM, CLEANER_USER
from bot.prompts.editor import EDITOR_SYSTEM, EDITOR_USER, FANTASY_EDITOR_SYSTEM, FANTASY_EDITOR_USER
from bot.services.character_extractor import format_characters_for_editor

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
    known_characters: list | None = None,
    known_places: list | None = None,
    style_notes: str | None = None,
    clarification_qa: list[dict] | None = None,
    author_gender: str | None = None,
) -> dict:
    """Literary editing: transform cleaned transcript into memoir text.

    Returns dict with keys: edited_memoir_text, title, tags, people, places.
    known_characters: list of Character ORM objects or dicts with name/relationship/description.
    known_places: list[str] or list[tuple[str, int]].
    clarification_qa: list of {"role": "question"|"answer", "text": "..."} from clarifier loop.
    """
    qa_str = ""
    if clarification_qa:
        lines = []
        for item in clarification_qa:
            prefix = "В:" if item["role"] == "question" else "О:"
            lines.append(f"{prefix} {item['text']}")
        qa_str = "\nУточняющие вопросы и ответы автора:\n" + "\n".join(lines) + "\n"

    if author_gender == "female":
        gender_hint = "\nАВТОР — ЖЕНЩИНА. Во всех глаголах и кратких прилагательных от первого лица используй женский род (была, переехала, жила и т.д.)."
    elif author_gender == "male":
        gender_hint = "\nАВТОР — МУЖЧИНА. Во всех глаголах и кратких прилагательных от первого лица используй мужской род (был, переехал, жил и т.д.)."
    else:
        gender_hint = "\nОПРЕДЕЛИ пол автора по форме глаголов в его тексте (переехала/переехал, была/был и т.д.) и используй соответствующий грамматический род."

    try:
        response = await client.chat.completions.create(
            model=settings.editor_model,
            messages=[
                {"role": "system", "content": EDITOR_SYSTEM + gender_hint},
                {
                    "role": "user",
                    "content": EDITOR_USER.format(
                        cleaned_transcript=cleaned_transcript,
                        clarification_qa=qa_str,
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
        return {"edited_memoir_text": cleaned_transcript, "title": "Без названия", "tags": [], "people": [], "places": []}
    except Exception as e:
        logger.error("Editor error: %s", e)
        return {"edited_memoir_text": cleaned_transcript, "title": "Без названия", "tags": [], "people": [], "places": []}


async def fantasy_edit_memoir(
    cleaned_transcript: str,
    clarification_qa: list[dict] | None = None,
    thread_summary: str | None = None,
    author_gender: str | None = None,
) -> str:
    """Creative editing: enrich the memoir with sensory details and atmosphere.

    Returns the fantasy memoir text (plain string), or empty string on error.
    clarification_qa: list of {role: question|answer, text} from clarifier loop.
    thread_summary: existing chapter context (used for tonal consistency).
    """
    qa_str = ""
    if clarification_qa:
        lines = []
        for item in clarification_qa:
            prefix = "В:" if item["role"] == "question" else "О:"
            lines.append(f"{prefix} {item['text']}")
        qa_str = "\nУточняющие ответы автора:\n" + "\n".join(lines) + "\n"

    thread_context = ""
    if thread_summary:
        thread_context = f"\nКонтекст главы (для тона и атмосферы):\n{thread_summary}\n"

    if author_gender == "female":
        fantasy_gender_hint = "\nАВТОР — ЖЕНЩИНА. Во всех глаголах и кратких прилагательных от первого лица используй женский род."
    elif author_gender == "male":
        fantasy_gender_hint = "\nАВТОР — МУЖЧИНА. Во всех глаголах и кратких прилагательных от первого лица используй мужской род."
    else:
        fantasy_gender_hint = "\nОПРЕДЕЛИ пол автора по форме глаголов в тексте и используй соответствующий грамматический род."

    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": FANTASY_EDITOR_SYSTEM + fantasy_gender_hint},
                {
                    "role": "user",
                    "content": FANTASY_EDITOR_USER.format(
                        cleaned_transcript=cleaned_transcript,
                        clarification_qa=qa_str,
                        thread_context=thread_context,
                    ),
                },
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Fantasy editor error: %s", e)
        return ""


async def apply_corrections(original_text: str, user_instruction: str) -> str:
    """Apply user's free-form corrections to a transcript.

    The user describes errors in any format (voice or text), e.g.:
    - "не Пангорица, а Подгорица"
    - "замени бабушка Маша на бабушка Мария"
    - "там было не 1985, а 1983 год"
    The AI finds the mentioned errors and fixes them without touching anything else.
    """
    system_prompt = (
        "Ты помощник, исправляющий ошибки в распознанном тексте.\n"
        "Пользователь описывает ошибки в свободной форме — иногда голосом, "
        "иногда текстом, в любом формате.\n\n"
        "ПРАВИЛА:\n"
        "- Примени ТОЛЬКО те исправления, о которых просит пользователь.\n"
        "- НЕ меняй стиль, порядок слов, формулировки или пунктуацию.\n"
        "- НЕ добавляй и не удаляй информацию.\n"
        "- Если пользователь упоминает слово и его замену — найди максимально "
        "похожее слово в тексте и замени.\n"
        "- Если не можешь найти упомянутое слово — верни текст без изменений.\n"
        "- Верни ТОЛЬКО исправленный текст, без комментариев и пояснений."
    )
    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Исходный текст:\n{original_text}\n\n"
                        f"Исправления от пользователя:\n{user_instruction}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Apply corrections error: %s", e)
        return original_text


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
