"""Chapter routes: CRUD, reorder."""
from aiohttp import web

from api.auth import require_auth
from bot.db.engine import async_session
from bot.db.repository import Repository


@require_auth
async def get_chapters(request: web.Request) -> web.Response:
    """GET /api/v1/chapters - list with order_index, memory counts."""
    user = request["user"]
    async with async_session() as session:
        repo = Repository(session)
        chapters = await repo.get_chapters(user.id)
        chapters_data = []
        for ch in chapters:
            mems = await repo.get_memories_by_chapter(ch.id)
            chapters_data.append({
                "id": ch.id,
                "title": ch.title,
                "period_hint": ch.period_hint,
                "order_index": ch.order_index,
                "memories_count": len(mems),
            })
    return web.json_response({"chapters": chapters_data})


@require_auth
async def create_chapter(request: web.Request) -> web.Response:
    """POST /api/v1/chapters - create chapter."""
    user = request["user"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    title = (data.get("title") or "").strip()
    if not title:
        return web.json_response({"error": "title_required"}, status=400)
    period_hint = (data.get("period_hint") or "").strip() or None

    async with async_session() as session:
        repo = Repository(session)
        chapter = await repo.create_chapter(user.id, title, period_hint)
    return web.json_response({
        "id": chapter.id,
        "title": chapter.title,
        "period_hint": chapter.period_hint,
        "order_index": chapter.order_index,
        "memories_count": 0,
    }, status=201)


@require_auth
async def patch_chapter(request: web.Request) -> web.Response:
    """PATCH /api/v1/chapters/:id - rename."""
    user = request["user"]
    chapter_id = int(request.match_info["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    title = (data.get("title") or "").strip()
    if not title:
        return web.json_response({"error": "title_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        chapter = await repo.get_chapter(chapter_id)
        if not chapter or chapter.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        await repo.rename_chapter(chapter_id, title)
    return web.json_response({"ok": True, "title": title})


@require_auth
async def delete_chapter(request: web.Request) -> web.Response:
    """DELETE /api/v1/chapters/:id - safe delete (moves memories to Разное)."""
    user = request["user"]
    chapter_id = int(request.match_info["id"])

    async with async_session() as session:
        repo = Repository(session)
        chapter = await repo.get_chapter(chapter_id)
        if not chapter or chapter.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        await repo.delete_chapter(chapter_id)
    return web.json_response({"ok": True})


@require_auth
async def reorder_chapters(request: web.Request) -> web.Response:
    """POST /api/v1/chapters/reorder - reorder by IDs or swap two chapters."""
    user = request["user"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    chapter_ids = data.get("chapter_ids")
    if chapter_ids is not None:
        if not isinstance(chapter_ids, list):
            return web.json_response({"error": "chapter_ids must be array"}, status=400)
        ids = [int(x) for x in chapter_ids if x is not None]
        if not ids:
            return web.json_response({"error": "chapter_ids required"}, status=400)
        async with async_session() as session:
            repo = Repository(session)
            for ch_id in ids:
                ch = await repo.get_chapter(ch_id)
                if not ch or ch.user_id != user.id:
                    return web.json_response({"error": "not_found"}, status=404)
            await repo.reorder_chapters_by_ids(user.id, ids)
        return web.json_response({"ok": True})

    chapter_id_a = data.get("chapter_id_a")
    chapter_id_b = data.get("chapter_id_b")
    if chapter_id_a is None or chapter_id_b is None:
        return web.json_response({"error": "chapter_id_a and chapter_id_b or chapter_ids required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        ch_a = await repo.get_chapter(int(chapter_id_a))
        ch_b = await repo.get_chapter(int(chapter_id_b))
        if not ch_a or not ch_b or ch_a.user_id != user.id or ch_b.user_id != user.id:
            return web.json_response({"error": "not_found"}, status=404)
        await repo.swap_chapter_order(ch_a.id, ch_b.id)
    return web.json_response({"ok": True})
