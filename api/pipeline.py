"""Pipeline logic for API: clean -> clarify -> edit. Reuses bot services."""
import asyncio
import json
import logging

from sqlalchemy import update

from bot.db.engine import async_session
from bot.db.models import Memory
from bot.db.repository import Repository
from bot.services.ai_editor import clean_transcript, edit_memoir, fantasy_edit_memoir
from bot.services.timeline import extract_timeline
from bot.services.classifier import classify_chapter
from bot.services.clarifier import ask_clarification

logger = logging.getLogger(__name__)

MAX_CLARIFICATION_ROUNDS = 3


async def _fetch_user_context(user_id: int) -> dict:
    async with async_session() as session:
        repo = Repository(session)
        known_characters = await repo.get_characters(user_id)
        known_places = await repo.get_places_with_counts(user_id)
        style_notes = await repo.get_style_notes(user_id)
        chapters = await repo.get_chapters(user_id)
        gender = await repo.get_gender(user_id)
    return {
        "known_characters": known_characters,
        "known_places": known_places,
        "style_notes": style_notes,
        "chapters": chapters,
        "gender": gender,
    }


async def _classify_chapter(cleaned: str, chapters: list) -> tuple[str | None, str | None]:
    if not chapters:
        return None, None
    chapters_dicts = [
        {"title": ch.title, "period_hint": ch.period_hint or ""}
        for ch in chapters
    ]
    classification = await classify_chapter(
        cleaned, {"type": "unknown", "value": ""}, chapters_dicts
    )
    suggestion = classification.get("chapter_suggestion")
    thread_summary = None
    if suggestion:
        for ch in chapters:
            if ch.title == suggestion:
                thread_summary = ch.thread_summary
                break
    return suggestion, thread_summary


async def run_pipeline_from_transcript(
    user_id: int,
    raw_transcript: str,
    memory_id: int,
    audio_file_id: str | None = None,
) -> dict:
    """
    Run full pipeline: clean -> classify -> clarify or edit.
    Returns:
      {"status": "clarification", "question": str}
      {"status": "preview", "memory_id": int, "title": str, "preview": str, "chapter_suggestion": str, "has_fantasy": bool}
    """
    cleaned = await clean_transcript(raw_transcript)
    ctx = await _fetch_user_context(user_id)
    chapter_suggestion, thread_summary = await _classify_chapter(cleaned, ctx["chapters"])

    clarifier_chapter_ctx = None
    if chapter_suggestion:
        clarifier_chapter_ctx = [{"title": chapter_suggestion, "summary": thread_summary or ""}]

    clarification = await ask_clarification(
        cleaned, [],
        known_characters=ctx.get("known_characters") or None,
        chapter_summaries=clarifier_chapter_ctx,
    )

    async with async_session() as session:
        await session.execute(
            update(Memory)
            .where(Memory.id == memory_id)
            .values(cleaned_transcript=cleaned, chapter_suggestion=chapter_suggestion)
        )
        await session.commit()

    if not clarification.get("is_complete"):
        question = clarification["question"]
        thread = [{"role": "question", "text": question}]
        async with async_session() as session:
            repo = Repository(session)
            await repo.set_clarification_state(memory_id, thread, 1)
        return {"status": "clarification", "question": question}

    # No clarification — run editor
    return await _run_editor(memory_id, cleaned, [], ctx, chapter_suggestion, thread_summary)


async def run_clarification_answer(
    user_id: int,
    memory_id: int,
    answer_text: str,
) -> dict:
    """
    Process clarification answer. Returns same shape as run_pipeline_from_transcript.
    """
    async with async_session() as session:
        repo = Repository(session)
        pending = await repo.get_memory(memory_id)
    if not pending or pending.user_id != user_id:
        return {"status": "error", "error": "not_found"}
    if pending.clarification_round <= 0:
        return {"status": "error", "error": "no_pending_clarification"}

    thread = json.loads(pending.clarification_thread or "[]")
    thread.append({"role": "answer", "text": answer_text})
    current_round = pending.clarification_round
    cleaned = pending.cleaned_transcript or ""

    ctx = await _fetch_user_context(user_id)
    clarifier_chapter_ctx = None
    if pending.chapter_suggestion:
        summary = ""
        for ch in ctx.get("chapters", []):
            if ch.title == pending.chapter_suggestion:
                summary = ch.thread_summary or ""
                break
        clarifier_chapter_ctx = [{"title": pending.chapter_suggestion, "summary": summary}]

    if current_round < MAX_CLARIFICATION_ROUNDS:
        clarification = await ask_clarification(
            cleaned, thread,
            known_characters=ctx.get("known_characters") or None,
            chapter_summaries=clarifier_chapter_ctx,
        )
        if not clarification.get("is_complete"):
            question = clarification["question"]
            thread.append({"role": "question", "text": question})
            async with async_session() as session:
                repo = Repository(session)
                await repo.set_clarification_state(memory_id, thread, current_round + 1)
            return {"status": "clarification", "question": question}

    return await _run_editor(
        memory_id, cleaned, thread, ctx,
        pending.chapter_suggestion, None,
    )


async def _run_editor(
    memory_id: int,
    cleaned: str,
    qa_thread: list,
    ctx: dict,
    chapter_suggestion: str | None,
    thread_summary: str | None,
) -> dict:
    author_gender = ctx.get("gender")
    edited, fantasy_text = await asyncio.gather(
        edit_memoir(
            cleaned,
            ctx["known_characters"],
            ctx["known_places"],
            ctx["style_notes"],
            qa_thread or None,
            author_gender,
        ),
        fantasy_edit_memoir(cleaned, qa_thread or None, thread_summary, author_gender),
    )

    strict_text = edited.get("edited_memoir_text", cleaned)
    time_hint = await extract_timeline(strict_text)

    async with async_session() as session:
        repo = Repository(session)
        await repo.update_memory_after_edit(
            memory_id=memory_id,
            edited_text=strict_text,
            fantasy_text=fantasy_text or None,
            title=edited.get("title", ""),
            tags=edited.get("tags", []),
            people=edited.get("people", []),
            places=edited.get("places", []),
            time_hint_type=time_hint.get("type"),
            time_hint_value=time_hint.get("value"),
            time_confidence=time_hint.get("confidence"),
            chapter_suggestion=chapter_suggestion,
        )
        await repo.clear_clarification_state(memory_id)

    preview = strict_text[:1500] + ("…" if len(strict_text) > 1500 else "")
    return {
        "status": "preview",
        "memory_id": memory_id,
        "title": edited.get("title", "Воспоминание"),
        "preview": preview,
        "chapter_suggestion": chapter_suggestion,
        "has_fantasy": bool(fantasy_text),
    }
