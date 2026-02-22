import json
import logging

from openai import AsyncOpenAI

from bot.config import settings
from bot.prompts.classifier import CLASSIFIER_SYSTEM, CLASSIFIER_USER

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


async def classify_chapter(
    memoir_text: str,
    time_hint: dict,
    chapters: list[dict],
) -> dict:
    """Suggest which chapter a memory belongs to.

    Returns {"chapter_suggestion": str, "confidence": float, "reasoning": str}.
    """
    time_str = f"{time_hint.get('type', 'unknown')}: {time_hint.get('value', '')}"
    chapters_str = "\n".join(
        f"- {ch['title']} ({ch.get('period_hint', '')})" for ch in chapters
    ) or "Глав пока нет"

    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM},
                {
                    "role": "user",
                    "content": CLASSIFIER_USER.format(
                        memoir_text=memoir_text,
                        time_hint=time_str,
                        chapters_list=chapters_str,
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        logger.error("Classification error: %s", e)
        return {"chapter_suggestion": "", "confidence": 0.0, "reasoning": ""}
