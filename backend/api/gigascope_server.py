"""GigaScope SPA Server — порт 8099.

Сервит Three.js SPA и проксирует /api/gigascope/* на Ouroboros (порт 8080).
"""

import json
import os
import pathlib
import sys
from urllib.parse import urlencode

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles


# Конфигурация
SPA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "gigascope-spa"
OUROBOROS_API = os.environ.get("OUROBOROS_API_URL", "http://localhost:8765")
SPA_PORT = int(os.environ.get("GIGASCOPE_SPA_PORT", "8099"))


async def proxy_api(request):
    """Прокси запросов к Ouroboros API."""
    path = request.url.path
    query = urlencode(dict(request.query_params)) if request.query_params else ""

    target_url = f"{OUROBOROS_API}{path}"
    if query:
        target_url += f"?{query}"

    method = request.method
    headers = dict(request.headers)
    # Remove host header to avoid confusion
    headers.pop("host", None)

    body = await request.body() if method in ("POST", "PUT", "PATCH") else None

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(
                method,
                target_url,
                headers=headers,
                content=body,
                timeout=30.0,
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
        except httpx.RequestError as e:
            return JSONResponse(
                {"error": f"Proxy error: {e}"},
                status_code=502,
            )


async def spa_index(request):
    """Serve index.html for SPA routes."""
    index_path = SPA_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>GigaScope SPA</h1><p>Frontend not built yet. "
            "Place your Three.js app in frontend/gigascope-spa/</p>",
            status_code=200,
        )
    content = index_path.read_text()
    return HTMLResponse(content)


async def spa_static(request):
    """Serve static files from SPA directory."""
    file_path = SPA_DIR / request.path_params.get("rest", "index.html")

    # Security: prevent directory traversal
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(SPA_DIR.resolve())):
            return Response("Forbidden", status_code=403)
    except (ValueError, OSError):
        return Response("Forbidden", status_code=403)

    if not file_path.exists() or not file_path.is_file():
        return await spa_index(request)

    content = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    media_types = {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".woff2": "font/woff2",
    }
    return Response(content, media_type=media_types.get(suffix, "application/octet-stream"))


# Starlette app
app = Starlette(
    debug=False,
    routes=[
        # API proxy
        Route("/api/gigascope/{rest:path}", endpoint=proxy_api, methods=["GET", "POST", "PUT", "DELETE", "PATCH"]),
        # SPA static files
        Route("/{rest:path}", endpoint=spa_static, methods=["GET"]),
        Route("/", endpoint=spa_index, methods=["GET"]),
    ],
)


if __name__ == "__main__":
    print(f"🚀 GigaScope SPA server starting on port {SPA_PORT}")
    print(f"   API proxy -> {OUROBOROS_API}")
    print(f"   SPA dir   -> {SPA_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=SPA_PORT, log_level="info")
