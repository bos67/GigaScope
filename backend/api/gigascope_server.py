"""GigaScope SPA Server — порт 8099.

Чистый прокси-сервер: отдаёт статику Three.js SPA и проксирует
/api/gigascope/* на Ouroboros (порт 8765). Никакой собственной бизнес-логики.
Все данные — гипотезы, инциденты, граф, engine — живут в Ouroboros Gateway.
"""

import json
import os
import pathlib
import sys
import urllib.request
import urllib.error

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route


SPA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "gigascope-spa"
OUROBOROS_API = os.environ.get("OUROBOROS_API_URL", "http://localhost:8765")
SPA_HOST = os.environ.get("GIGASCOPE_SPA_HOST", "127.0.0.1")
SPA_PORT = int(os.environ.get("GIGASCOPE_SPA_PORT", "8099"))


def _proxy_request(method, path, headers=None, body=None):
    """Proxy an HTTP request to Ouroboros and return (status, headers, body)."""
    url = f"{OUROBOROS_API}{path}"
    req_headers = {}
    if headers:
        for h in ("Content-Type", "Accept", "Authorization"):
            if h in headers:
                req_headers[h] = headers[h]
    data = body if body else None
    try:
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except urllib.error.URLError as e:
        return 502, {"Content-Type": "application/json"}, json.dumps(
            {"error": "backend unreachable", "detail": str(e.reason)}
        ).encode()


async def proxy_api(request):
    """Прокси запросов к Ouroboros API."""
    path = request.url.path
    query = request.url.query
    if query:
        path += f"?{query}"

    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body() if method in ("POST", "PUT", "PATCH") else None

    status, resp_headers, content = _proxy_request(method, path, headers, body)
    return Response(
        content=content,
        status_code=status,
        headers=resp_headers,
    )


async def spa_index(request):
    """Serve index.html."""
    index_path = SPA_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>GigaScope SPA</h1><p>Frontend not built yet.</p>",
            status_code=200,
        )
    content = index_path.read_text()
    return HTMLResponse(content)


async def spa_static(request):
    """Serve static files from SPA directory."""
    file_path = SPA_DIR / request.path_params.get("rest", "index.html")
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


# Starlette app — всё через прокси, никакой собственной бизнес-логики
app = Starlette(
    debug=False,
    routes=[
        Route("/api/gigascope/{rest:path}", endpoint=proxy_api,
              methods=["GET", "POST", "PUT", "DELETE", "PATCH"]),
        Route("/{rest:path}", endpoint=spa_static, methods=["GET"]),
        Route("/", endpoint=spa_index, methods=["GET"]),
    ],
)


if __name__ == "__main__":
    # Парсим --host и --port из sys.argv (для совместимости с restart.sh)
    host = SPA_HOST
    port = SPA_PORT
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
        elif arg == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1])

    print(f"🚀 GigaScope SPA proxy starting on {host}:{port}")
    print(f"   Upstream API -> {OUROBOROS_API}")
    print(f"   SPA dir      -> {SPA_DIR}")
    uvicorn.run(app, host=host, port=port, log_level="info")
