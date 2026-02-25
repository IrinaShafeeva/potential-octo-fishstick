"""Extracts named characters from approved memories and builds a character library."""
import json
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

_EXTRACT_PROMPT = """\
Тебе дан текст воспоминания и список персонажей, уже известных из предыдущих воспоминаний автора.

Найди ВСЕХ упомянутых людей (кроме самого автора).

Для каждого человека верни:
- name: каноническое имя или прозвище как автор его называет в этом тексте
- aliases: другие варианты обращения к нему в тексте (пустой список если нет)
- relationship: кем приходится автору ("жена", "мать", "сосед", "друг детства" и т.п.) — если понятно из текста
- description: одно предложение — кто это человек и в каком контексте упомянут

Если человек уже есть в списке известных персонажей — используй его каноническое имя из списка (не изобретай новое).
Если это новый человек — придумай каноническое имя на основе текста.

Верни JSON-массив. Если людей нет — верни [].
Верни ТОЛЬКО валидный JSON, без markdown.

ИЗВЕСТНЫЕ ПЕРСОНАЖИ:
{known_characters}

ТЕКСТ ВОСПОМИНАНИЯ:
{memory_text}"""


async def extract_characters(
    memory_text: str,
    known_characters: list[dict],
) -> list[dict]:
    """Extract characters from a memory text.

    Returns list of dicts: {name, aliases, relationship, description}.
    """
    if not memory_text or len(memory_text.split()) < 10:
        return []

    known_str = (
        "\n".join(
            f"- {c['name']}"
            + (f" ({c['relationship']})" if c.get("relationship") else "")
            + (f": {c['description']}" if c.get("description") else "")
            for c in known_characters[:30]
        )
        or "(пока нет)"
    )

    prompt = _EXTRACT_PROMPT.format(
        known_characters=known_str,
        memory_text=memory_text,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000,
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.error("Character extraction error: %s", e)
        return []


def format_characters_for_editor(characters: list) -> str:
    """Format character library for the editor prompt.

    Accepts list of Character ORM objects or dicts.
    """
    if not characters:
        return "нет данных"

    lines = []
    for c in characters[:20]:
        # Support both ORM objects and dicts
        name = c.name if hasattr(c, "name") else c.get("name", "?")
        relationship = (
            c.relationship if hasattr(c, "relationship") else c.get("relationship")
        )
        description = (
            c.description if hasattr(c, "description") else c.get("description")
        )
        mention_count = (
            c.mention_count if hasattr(c, "mention_count") else c.get("mention_count", 1)
        )
        aliases = c.aliases if hasattr(c, "aliases") else c.get("aliases", [])

        line = f"- {name}"
        if relationship:
            line += f" ({relationship})"
        if mention_count and mention_count > 1:
            line += f" [упом. {mention_count}×]"
        if aliases:
            line += f" — также: {', '.join(aliases[:3])}"
        if description:
            line += f"\n  {description}"
        lines.append(line)

    return "\n".join(lines)
