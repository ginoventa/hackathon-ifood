"""Ponto de entrada do backend do Ailo (FastAPI).

Um único servidor entrega a interface (pasta ``frontend/``) e a API (``/api/*``).
Execute na raiz do repositório com ``npm run dev`` (ou ``uv run python -m ailo.main``
dentro de ``backend/``).
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from .api.routes import router
from .config import config, config_problems
from .errors import AppError
from .ifood import oauth

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("ailo")

app = FastAPI(title="Ailo", description="Agente do iFood para pessoas com restrições alimentares.")
app.include_router(router)

# Arquivos da pasta frontend/ que não fazem parte da interface publicada.
BLOCKED_FILES = {"server.mjs", "build.mjs", "package.json"}
ALLOWED_EXTENSIONS = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".ico", ".json"}


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
    """Erros da aplicação viram JSON padronizado para a interface."""
    return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": error.message}})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


if oauth.handles_callback_in_app():
    # Quando a Redirect URL do agente aponta para este servidor, o retorno do login cai aqui.
    @app.get(oauth.callback_path(), response_class=HTMLResponse)
    async def oauth_callback(request: Request) -> HTMLResponse:
        success, message = await asyncio.to_thread(oauth.finish_login, dict(request.query_params))
        return HTMLResponse(oauth.callback_page(success, message), status_code=200 if success else 400)


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    """Entrega os arquivos da interface, bloqueando acesso fora da pasta."""
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": {"code": "ROTA_INEXISTENTE", "message": "Rota não encontrada."}})

    relative = path or "index.html"
    root = config.frontend_dir.resolve()
    file_path = (root / relative).resolve()
    parts = Path(relative).parts
    is_allowed = (
        file_path.is_relative_to(root)
        and file_path.suffix in ALLOWED_EXTENSIONS
        and relative not in BLOCKED_FILES
        and not any(part.startswith(".") or part in {"node_modules", "dist"} for part in parts)
        and file_path.is_file()
    )
    if not is_allowed:
        return PlainTextResponse("Página não encontrada", status_code=404)

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type, headers={"Cache-Control": "no-cache"})


def run() -> None:
    """Inicia o servidor web."""
    for problem in config_problems():
        logger.warning("Atenção: %s", problem)
    logger.info("Ailo disponível em http://localhost:%d", config.port)
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="warning")


if __name__ == "__main__":
    run()
