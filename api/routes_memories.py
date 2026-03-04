"""Memory routes: CRUD, audio/text upload, corrections, clarification, save."""
import json
import logging

from aiohttp import web
from sqlalchemy import update

from api.auth import require_auth
from api.pipeline import run_pipeline_from_transcript, run_clarification_answer
from bot.db.engine import async_session
from bot.db.models import Memory
from bot.db.repository import Repository
from bot.services.stt import transcribe_voice
from bot.services.ai_editor import apply_corrections, fantasy_edit_memoir

logger = logging.getLogger(__name__)


def _memory_to_dict(m):
    return {
        "id": m.id,
        "title": m.title,
        "raw_transcript": m.raw_transcript,
        "cleaned_transcript": m.cleaned_transcript,
        "edited_memoir_text": m.edited_memoir_text,
        "fantasy_memoir_text": m.fantasy_memoir_text,
        "chapter_id": m.chapter_id,
        "chapter_suggestion": m.chapter_suggestion,
        "approved": m.approved,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@require_auth
async def post_memories_text(request: web.Request) -> web.Response:
    """POST /api/v1/memories/text - create memory from text."""
    user = request["user"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    text = (data.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "text_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.create_memory(user_id=user.id, raw_transcript=text)

    return web.json_response({
        "memory_id": memory.id,
        "raw_transcript": memory.raw_transcript,
    }, status=201)


@require_auth
async def post_memories_audio(request: web.Request) -> web.Response:
    """POST /api/v1/memories/audio - multipart upload, STT, returns {memory_id, raw_transcript}."""
    user = request["user"]
    reader = await request.multipart()
    audio_data = None
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "audio" or part.name == "file":
            audio_data = await part.read()
            break

    if not audio_data:
        return web.json_response({"error": "audio_required"}, status=400)

    result = await transcribe_voice(audio_data, "voice.ogg")
    raw_transcript = result.get("text", "")

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.create_memory(
            user_id=user.id,
            raw_transcript=raw_transcript,
            audio_file_id="api_upload",
        )

    return web.json_response({
        "memory_id": memory.id,
        "raw_transcript": raw_transcript,
    }, status=201)


@require_auth
async def post_correct_transcript(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/correct-transcript - apply correction instruction."""
    user = request["user"]
    memory_id = int(request.match_info["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    instruction = (data.get("instruction") or "").strip()
    if not instruction:
        return web.json_response({"error": "instruction_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        original = memory.raw_transcript or ""

    corrected = await apply_corrections(original, instruction)

    async with async_session() as session:
        await session.execute(
            update(Memory).where(Memory.id == memory_id).values(raw_transcript=corrected)
        )
        await session.commit()

    return web.json_response({"raw_transcript": corrected})


@require_auth
async def patch_memory_transcript(request: web.Request) -> web.Response:
    """PATCH /api/v1/memories/:id - update raw_transcript (direct edit from app)."""
    user = request["user"]
    memory_id = int(request.match_info["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    raw_transcript = (data.get("raw_transcript") or data.get("text") or "").strip()
    if not raw_transcript:
        return web.json_response({"error": "raw_transcript_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        await session.execute(
            update(Memory).where(Memory.id == memory_id).values(raw_transcript=raw_transcript)
        )
        await session.commit()

    return web.json_response({"raw_transcript": raw_transcript})


@require_auth
async def post_confirm_transcript(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/confirm-transcript - run pipeline."""
    user = request["user"]
    memory_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        raw = memory.raw_transcript or ""

    if not raw.strip():
        return web.json_response({"error": "empty_transcript"}, status=400)

    result = await run_pipeline_from_transcript(user.id, raw, memory_id)
    if result.get("status") == "clarification":
        return web.json_response({"status": "clarification", "question": result["question"]})
    if result.get("status") == "preview":
        return web.json_response(result)
    return web.json_response({"error": "pipeline_failed"}, status=500)


@require_auth
async def get_clarification(request: web.Request) -> web.Response:
    """GET /api/v1/memories/:id/clarification - get current question."""
    user = request["user"]
    memory_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        if memory.clarification_round <= 0:
            return web.json_response({"status": "complete", "question": None})

        thread = json.loads(memory.clarification_thread or "[]")
        last_q = None
        for item in reversed(thread):
            if item.get("role") == "question":
                last_q = item.get("text")
                break

    return web.json_response({"status": "pending", "question": last_q})


@require_auth
async def post_clarification(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/clarification - answer question."""
    user = request["user"]
    memory_id = int(request.match_info["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    answer = (data.get("answer") or data.get("text") or "").strip()
    if not answer:
        return web.json_response({"error": "answer_required"}, status=400)

    result = await run_clarification_answer(user.id, memory_id, answer)
    if result.get("status") == "error":
        return web.json_response({"error": result.get("error", "unknown")}, status=400)
    if result.get("status") == "clarification":
        return web.json_response({"status": "clarification", "question": result["question"]})
    if result.get("status") == "preview":
        return web.json_response(result)
    return web.json_response({"error": "unknown"}, status=500)


@require_auth
async def post_skip_clarification(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/skip-clarification - skip to preview."""
    user = request["user"]
    memory_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        raw = memory.raw_transcript or memory.cleaned_transcript or ""
        if not raw.strip():
            return web.json_response({"error": "empty_transcript"}, status=400)

    result = await run_pipeline_from_transcript(user.id, raw, memory_id)
    if result.get("status") == "clarification":
        return web.json_response({"error": "still_has_question"}, status=400)
    if result.get("status") == "preview":
        return web.json_response(result)
    return web.json_response({"error": "pipeline_failed"}, status=500)


@require_auth
async def get_memory(request: web.Request) -> web.Response:
    """GET /api/v1/memories/:id - full memory."""
    user = request["user"]
    memory_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)

    return web.json_response(_memory_to_dict(memory))


@require_auth
async def post_edit(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/edit - apply corrections to edited text."""
    user = request["user"]
    memory_id = int(request.match_info["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    instruction = (data.get("instruction") or "").strip()
    if not instruction:
        return web.json_response({"error": "instruction_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        original = memory.edited_memoir_text or memory.cleaned_transcript or memory.raw_transcript or ""

    corrected = await apply_corrections(original, instruction)

    async with async_session() as session:
        repo = Repository(session)
        await repo.update_memory_text(memory_id, corrected)
        memory = await repo.get_memory(memory_id)

    return web.json_response({
        "edited_memoir_text": corrected,
        "title": memory.title if memory else None,
        "chapter_suggestion": memory.chapter_suggestion if memory else None,
        "has_fantasy": bool(memory.fantasy_memoir_text) if memory else False,
    })


@require_auth
async def post_save(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/save - approve memory, optionally assign chapter."""
    user = request["user"]
    memory_id = int(request.match_info["id"])
    data = {}
    if request.content_length:
        try:
            data = await request.json()
        except Exception:
            pass
    chapter_id = data.get("chapter_id")

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        if memory.approved:
            return web.json_response({"ok": True, "message": "already_saved"})

        await repo.approve_memory(memory_id, chapter_id)
        await repo.increment_memories_count(user.id)

    return web.json_response({"ok": True, "message": "saved"})


@require_auth
async def post_move(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/move - move to chapter."""
    user = request["user"]
    memory_id = int(request.match_info["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    chapter_id = data.get("chapter_id")
    if chapter_id is None:
        return web.json_response({"error": "chapter_id_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        ch = await repo.get_chapter(int(chapter_id))
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        if not ch or ch.user_id != user.id:
            return web.json_response({"error": "chapter_not_found"}, status=404)
        was_saved = memory.approved
        if was_saved:
            await repo.move_memory(memory_id, ch.id)
        else:
            await repo.approve_memory(memory_id, ch.id)
            await repo.increment_memories_count(user.id)

    return web.json_response({"ok": True})


@require_auth
async def delete_memory(request: web.Request) -> web.Response:
    """DELETE /api/v1/memories/:id."""
    user = request["user"]
    memory_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        await repo.delete_memory(memory_id)

    return web.json_response({"ok": True})


@require_auth
async def post_fantasy(request: web.Request) -> web.Response:
    """POST /api/v1/memories/:id/fantasy - get or regenerate fantasy version."""
    user = request["user"]
    memory_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        memory = await repo.get_memory(memory_id)
        if not memory or memory.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        cleaned = memory.cleaned_transcript or memory.raw_transcript or ""
        fantasy = memory.fantasy_memoir_text

    if not fantasy and cleaned:
        fantasy = await fantasy_edit_memoir(cleaned, None, None, None)
        if fantasy:
            async with async_session() as session:
                await session.execute(
                    update(Memory).where(Memory.id == memory_id).values(fantasy_memoir_text=fantasy)
                )
                await session.commit()

    return web.json_response({"fantasy_memoir_text": fantasy or ""})
