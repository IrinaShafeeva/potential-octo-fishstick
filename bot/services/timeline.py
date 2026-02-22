import json
import logging

from openai import AsyncOpenAI

from bot.config import settings
from bot.prompts.timeline import TIMELINE_SYSTEM, TIMELINE_USER

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


async def extract_timeline(memoir_text: str) -> dict:
    """Extract time hints from memoir text.

    Returns {"type": "year|range|relative|unknown", "value": str, "confidence": float}.
    """
    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": TIMELINE_SYSTEM},
                {"role": "user", "content": TIMELINE_USER.format(memoir_text=memoir_text)},
            ],
            temperature=0.2,
            max_tokens=200,
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        logger.error("Timeline extraction error: %s", e)
        return {"type": "unknown", "value": "", "confidence": 0.0}
