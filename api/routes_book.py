"""Book routes: GET /book, GET /book/pdf, GET /book/progress."""
from aiohttp import web

from api.auth import require_auth
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.services.book_builder import compile_book
from bot.services.export import export_book_pdf


@require_auth
async def get_book(request: web.Request) -> web.Response:
    """GET /api/v1/book - chapters + memories tree."""
    user = request["user"]
    async with async_session() as session:
        repo = Repository(session)
        chapters = await repo.get_chapters(user.id)
        book_data = []
        for ch in chapters:
            mems = await repo.get_memories_by_chapter(ch.id)
            book_data.append({
                "id": ch.id,
                "title": ch.title,
                "period_hint": ch.period_hint,
                "order_index": ch.order_index,
                "memories": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "text": m.edited_memoir_text or m.cleaned_transcript or m.raw_transcript or "",
                    }
                    for m in mems
                ],
            })
    return web.json_response({"chapters": book_data})


@require_auth
async def get_book_pdf(request: web.Request) -> web.Response:
    """GET /api/v1/book/pdf - download PDF binary."""
    user = request["user"]
    async with async_session() as session:
        repo = Repository(session)
        chapters = await repo.get_chapters(user.id)
        chapters_data = []
        for ch in chapters:
            mems = await repo.get_memories_by_chapter(ch.id)
            chapters_data.append({
                "title": ch.title,
                "period_hint": ch.period_hint,
                "memories": [
                    {"title": m.title, "text": m.edited_memoir_text or m.cleaned_transcript or m.raw_transcript or ""}
                    for m in mems
                ],
            })
        author_name = user.first_name or "Автор"
        pdf_bytes = await export_book_pdf(chapters_data, author_name=author_name, user_id=user.id)

    if not pdf_bytes:
        return web.json_response({"error": "pdf_generation_failed"}, status=500)

    return web.Response(
        body=pdf_bytes,
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="memoir_book.pdf"',
        },
    )


@require_auth
async def get_book_progress(request: web.Request) -> web.Response:
    """GET /api/v1/book/progress - stats."""
    user = request["user"]
    async with async_session() as session:
        repo = Repository(session)
        progress = await repo.get_book_progress(user.id)
    return web.json_response(progress)
