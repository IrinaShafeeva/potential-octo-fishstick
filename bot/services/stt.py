import io
import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> dict:
    """Transcribe voice using OpenAI Whisper API.

    Returns {"text": str, "confidence": float}.
    Confidence is estimated from the response (Whisper doesn't return it directly,
    so we use a heuristic based on text length vs audio size).
    """
    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        response = await client.audio.transcriptions.create(
            model=settings.whisper_model,
            file=audio_file,
            language="ru",
            response_format="text",
        )

        text = response.strip()
        if not text:
            return {"text": "", "confidence": 0.0}

        confidence = min(1.0, len(text) / max(len(audio_bytes) * 0.001, 1))
        confidence = max(0.3, min(confidence, 0.95))

        return {"text": text, "confidence": confidence}

    except Exception as e:
        logger.error("STT error: %s", e)
        return {"text": "", "confidence": 0.0}
