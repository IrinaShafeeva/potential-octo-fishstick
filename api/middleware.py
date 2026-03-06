"""CORS and JWT middleware for REST API."""
from aiohttp import web
from aiohttp.web import middleware


@middleware
async def cors_middleware(request: web.Request, handler):
    """Add CORS headers for mobile app."""
    if request.method == "OPTIONS":
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "86400",
            },
        )
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    # Allow embedding in Telegram WebView (fixes 403 Forbidden)
    if request.path.startswith("/miniapp"):
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response
