import json
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

SEGMENTATION_PROMPT = """Тебе дан длинный текст воспоминания, в котором автор рассказывает несколько
отдельных историй или эпизодов подряд.

Раздели текст на отдельные сцены/эпизоды. Каждый эпизод — это самостоятельная история
с единым временем, местом и действием.

Верни JSON-массив:
[
  {"title": "краткий заголовок", "text": "текст эпизода"},
  ...
]

Если текст содержит только один эпизод — верни массив с одним элементом.
Верни ТОЛЬКО валидный JSON."""


async def segment_text(long_text: str) -> list[dict]:
    """Split a long transcript into separate scenes/episodes."""
    if len(long_text) < 500:
        return [{"title": "", "text": long_text}]

    try:
        response = await client.chat.completions.create(
            model=settings.fast_model,
            messages=[
                {"role": "system", "content": SEGMENTATION_PROMPT},
                {"role": "user", "content": long_text},
            ],
            temperature=0.3,
            max_tokens=4000,
        )
        text = response.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        segments = json.loads(text)
        if isinstance(segments, list) and segments:
            return segments
        return [{"title": "", "text": long_text}]
    except Exception as e:
        logger.error("Segmentation error: %s", e)
        return [{"title": "", "text": long_text}]
