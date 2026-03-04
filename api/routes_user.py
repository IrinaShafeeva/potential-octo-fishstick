"""User routes: GET /me, PATCH /me."""
from aiohttp import web

from api.auth import require_auth
from bot.db.engine import async_session
from bot.db.repository import Repository
from bot.db.models import User
from sqlalchemy import update


@require_auth
async def get_me(request: web.Request) -> web.Response:
    """GET /api/v1/me - profile, memories_count, is_premium, chapters."""
    user = request["user"]
    async with async_session() as session:
        repo = Repository(session)
        chapters = await repo.get_chapters(user.id)
        is_premium = await repo.is_premium_by_user_id(user.id)
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

    return web.json_response({
        "user_id": user.id,
        "first_name": user.first_name,
        "memories_count": user.memories_count,
        "is_premium": is_premium,
        "premium_until": user.premium_until.isoformat() if user.premium_until else None,
        "chapters": chapters_data,
    })


@require_auth
async def patch_me(request: web.Request) -> web.Response:
    """PATCH /api/v1/me - update first_name."""
    user = request["user"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    first_name = (data.get("first_name") or "").strip()
    if not first_name:
        return web.json_response({"error": "first_name_required"}, status=400)

    async with async_session() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(first_name=first_name)
        )
        await session.commit()

    return web.json_response({"ok": True, "first_name": first_name})
