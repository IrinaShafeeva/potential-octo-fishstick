"""Subscription routes: GET /subscription, POST /subscription/promo."""
from aiohttp import web

from api.auth import require_auth
from bot.config import settings
from bot.db.engine import async_session
from bot.db.repository import Repository


@require_auth
async def get_subscription(request: web.Request) -> web.Response:
    """GET /api/v1/subscription - status, limits."""
    user = request["user"]
    async with async_session() as session:
        repo = Repository(session)
        is_premium = await repo.is_premium_by_user_id(user.id)

    return web.json_response({
        "is_premium": is_premium,
        "premium_until": user.premium_until.isoformat() if user.premium_until else None,
        "memories_count": user.memories_count,
        "free_memories_limit": settings.free_memories_limit,
        "free_chapters_limit": settings.free_chapters_limit,
        "free_questions_limit": settings.free_questions_limit,
    })


@require_auth
async def post_promo(request: web.Request) -> web.Response:
    """POST /api/v1/subscription/promo - redeem promo code."""
    user = request["user"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    code = (data.get("code") or "").strip()
    if not code:
        return web.json_response({"error": "code_required"}, status=400)

    async with async_session() as session:
        repo = Repository(session)
        result = await repo.redeem_promo_code(user.id, code)

    if not result["ok"]:
        return web.json_response({"error": result["msg"]}, status=400)
    return web.json_response({
        "ok": True,
        "message": result["msg"],
        "days": result["days"],
    })
