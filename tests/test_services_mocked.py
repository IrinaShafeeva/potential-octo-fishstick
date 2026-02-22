"""Tests for AI services with mocked OpenAI calls."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from bot.services.stt import transcribe_voice
from bot.services.ai_editor import clean_transcript, edit_memoir
from bot.services.timeline import extract_timeline
from bot.services.classifier import classify_chapter


def _mock_chat_response(content: str):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = content
    return mock_resp


def _mock_transcription(text: str):
    return text


@pytest.mark.asyncio
class TestSTT:
    @patch("bot.services.stt.client")
    async def test_transcribe_returns_text(self, mock_client):
        mock_client.audio.transcriptions.create = AsyncMock(return_value="Тестовый текст")
        result = await transcribe_voice(b"\x00" * 5000, "test.ogg")
        assert result["text"] == "Тестовый текст"
        assert result["confidence"] > 0

    @patch("bot.services.stt.client")
    async def test_transcribe_empty_returns_zero_confidence(self, mock_client):
        mock_client.audio.transcriptions.create = AsyncMock(return_value="")
        result = await transcribe_voice(b"\x00" * 100)
        assert result["text"] == ""
        assert result["confidence"] == 0.0

    @patch("bot.services.stt.client")
    async def test_transcribe_handles_error(self, mock_client):
        mock_client.audio.transcriptions.create = AsyncMock(side_effect=Exception("API error"))
        result = await transcribe_voice(b"\x00" * 100)
        assert result["text"] == ""
        assert result["confidence"] == 0.0


@pytest.mark.asyncio
class TestCleaner:
    @patch("bot.services.ai_editor.client")
    async def test_clean_returns_text(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_chat_response("Чистый текст без паразитов")
        )
        result = await clean_transcript("Ну вот значит чистый текст без паразитов")
        assert result == "Чистый текст без паразитов"

    @patch("bot.services.ai_editor.client")
    async def test_clean_fallback_on_error(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("fail"))
        result = await clean_transcript("оригинал")
        assert result == "оригинал"


@pytest.mark.asyncio
class TestEditor:
    @patch("bot.services.ai_editor.client")
    async def test_edit_returns_json(self, mock_client):
        json_response = '''{
            "edited_memoir_text": "Литературный текст",
            "title": "Мой двор",
            "tags": ["childhood"],
            "people": ["мама"],
            "places": ["Москва"],
            "needs_clarification": false,
            "clarification_question": ""
        }'''
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_chat_response(json_response)
        )
        result = await edit_memoir("Очищенный текст")
        assert result["edited_memoir_text"] == "Литературный текст"
        assert result["title"] == "Мой двор"
        assert "childhood" in result["tags"]

    @patch("bot.services.ai_editor.client")
    async def test_edit_handles_bad_json(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_chat_response("not json at all")
        )
        result = await edit_memoir("текст")
        assert result["edited_memoir_text"] == "текст"
        assert result["title"] == "Без названия"

    @patch("bot.services.ai_editor.client")
    async def test_edit_handles_error(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("fail"))
        result = await edit_memoir("текст")
        assert result["edited_memoir_text"] == "текст"


@pytest.mark.asyncio
class TestTimeline:
    @patch("bot.services.timeline.client")
    async def test_extract_year(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_chat_response('{"type":"year","value":"1965","confidence":0.9}')
        )
        result = await extract_timeline("В 1965 году мы переехали")
        assert result["type"] == "year"
        assert result["value"] == "1965"

    @patch("bot.services.timeline.client")
    async def test_extract_unknown(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_chat_response('{"type":"unknown","value":"","confidence":0.1}')
        )
        result = await extract_timeline("Однажды мы гуляли")
        assert result["type"] == "unknown"

    @patch("bot.services.timeline.client")
    async def test_extract_handles_error(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("fail"))
        result = await extract_timeline("текст")
        assert result["type"] == "unknown"


@pytest.mark.asyncio
class TestClassifier:
    @patch("bot.services.classifier.client")
    async def test_classify_existing_chapter(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_chat_response(
                '{"chapter_suggestion":"Детство","confidence":0.85,"reasoning":"о детстве"}'
            )
        )
        result = await classify_chapter(
            "Мы играли во дворе",
            {"type": "relative", "value": "детство"},
            [{"title": "Детство", "period_hint": "1950-1960"}],
        )
        assert result["chapter_suggestion"] == "Детство"
        assert result["confidence"] > 0.5

    @patch("bot.services.classifier.client")
    async def test_classify_handles_error(self, mock_client):
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("fail"))
        result = await classify_chapter("текст", {}, [])
        assert result["confidence"] == 0.0
