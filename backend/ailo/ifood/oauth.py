"""Login OAuth 2.1 (Authorization Code + PKCE) do agente cadastrado no MCP Portal.

Segue o guia "Autenticação > Implementação" do iFood
(https://mcp-developer.ifood.com.br/pt-BR/docs/guides/authentication/implementacao):

1. ``start_login()`` gera o PKCE e o ``state`` e devolve a URL de ``/authorize``.
2. O usuário entra com a conta (de teste) no id.ifood; o OTP da conta de teste
   aparece no MCP Portal.
3. O iFood redireciona para a Redirect URL cadastrada no agente, com ``code`` e
   ``state``. O backend valida o ``state`` e troca o código por tokens enviando
   ``client_id`` + ``client_secret`` + ``code_verifier``.
4. Os tokens ficam em ``.data/ifood-tokens.json`` e são renovados (com rotação)
   antes de expirar.
5. Ao desconectar, os tokens são revogados em ``/revoke``.

O ``client_secret`` fica apenas no backend (variável de ambiente).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from ..config import config
from ..errors import AppError, IfoodAuthError
from ..storage import read_json, remove_json, write_json

logger = logging.getLogger(__name__)

TOKENS_FILE = "ifood-tokens.json"

# A documentação recomenda renovar com 5 minutos de folga.
EXPIRY_MARGIN_SECONDS = 5 * 60

# Tempo máximo esperando o usuário concluir o login no navegador.
LOGIN_TIMEOUT_SECONDS = 10 * 60

HTTP_TIMEOUT_SECONDS = 20

# Evita duas renovações simultâneas (os tokens são rotacionados a cada renovação).
_refresh_lock = threading.Lock()


@dataclass
class PendingLogin:
    """Login em andamento: dados do PKCE aguardando o retorno do iFood."""

    state: str
    code_verifier: str
    created_at: float
    server: HTTPServer | None = None


_pending: PendingLogin | None = None


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _require_credentials() -> None:
    if not config.ifood.client_id or not config.ifood.client_secret:
        raise AppError(
            "Configure IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET no .env com as credenciais do seu agente "
            "(MCP Portal > Meus agentes > Credenciais de acesso).",
            status=503,
            code="IFOOD_CREDENCIAIS_AUSENTES",
        )


def _client_credentials() -> dict[str, str]:
    return {"client_id": config.ifood.client_id, "client_secret": config.ifood.client_secret}


def _request_tokens(params: dict[str, str]) -> dict:
    """Chama o endpoint de token (troca de código ou renovação) e salva o resultado."""
    response = httpx.post(
        config.ifood.token_url,
        data={**_client_credentials(), **params},
        headers={"Accept": "application/json"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code != 200 or "access_token" not in body:
        reason = body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"
        logger.warning("Falha no endpoint de token do iFood: %s", reason)
        if body.get("error") == "invalid_client":
            raise AppError("O iFood recusou as credenciais do agente. Confira IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET.", status=401, code="IFOOD_CREDENCIAIS_INVALIDAS")
        if body.get("error") == "invalid_scope":
            raise AppError("O iFood recusou os escopos pedidos. Use em IFOOD_SCOPES só os escopos liberados para o agente.", status=401, code="IFOOD_ESCOPO_INVALIDO")
        raise IfoodAuthError(f"O iFood recusou o login ({reason}). Conecte a conta novamente.")

    previous = read_json(TOKENS_FILE, {}) or {}
    tokens = {
        "accessToken": body["access_token"],
        # Os tokens são rotacionados: guardamos sempre o refresh_token mais recente.
        "refreshToken": body.get("refresh_token") or previous.get("refreshToken"),
        "expiresAt": time.time() + int(body.get("expires_in") or 3600),
        "scope": body.get("scope") or previous.get("scope"),
        "obtainedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_json(TOKENS_FILE, tokens)
    return tokens


def _redirect_parts() -> tuple[int, str]:
    """Porta e caminho da Redirect URL cadastrada no agente."""
    parsed = urlparse(config.ifood.redirect_uri)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return port, parsed.path or "/"


def handles_callback_in_app() -> bool:
    """O retorno do login cai no próprio servidor do Ailo (mesma porta)?"""
    port, _ = _redirect_parts()
    return port == config.port


def callback_path() -> str:
    return _redirect_parts()[1]


def finish_login(query: dict[str, str]) -> tuple[bool, str]:
    """Processa o retorno do iFood (``code`` e ``state``).

    Returns:
        ``(sucesso, mensagem)`` para mostrar ao usuário no navegador.
    """
    global _pending
    pending = _pending
    if pending is None or query.get("state") != pending.state:
        # Validação obrigatória contra CSRF.
        return False, "A resposta do iFood não corresponde a este login. Tente novamente pelo Ailo."
    if query.get("error"):
        _close_pending()
        return False, query.get("error_description") or "O iFood não autorizou o acesso."

    try:
        _request_tokens({
            "grant_type": "authorization_code",
            "code": query.get("code", ""),
            "redirect_uri": config.ifood.redirect_uri,
            "code_verifier": pending.code_verifier,
        })
    except AppError as error:
        return False, error.message
    finally:
        _close_pending()

    logger.info("Login no iFood concluído.")
    return True, "Conta do iFood conectada! Você já pode voltar ao Ailo."


def callback_page(success: bool, message: str) -> str:
    """Página HTML simples mostrada no navegador ao fim do login."""
    title = "Conta do iFood conectada!" if success else "Não foi possível concluir o login"
    refresh = f'<meta http-equiv="refresh" content="3;url={config.app_url}">' if success else ""
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>{refresh}</head>'
        '<body style="font-family:Arial,sans-serif;display:grid;place-items:center;height:100vh;margin:0;background:#f5f5f5">'
        '<main style="background:#fff;border-radius:24px;padding:32px;max-width:420px;text-align:center">'
        f'<h1 style="font-size:22px">{title}</h1><p style="color:#666">{message}</p>'
        f'<a href="{config.app_url}" style="color:#f92371">Voltar ao Ailo</a></main></body></html>'
    )


class _CallbackHandler(BaseHTTPRequestHandler):
    """Servidor temporário para quando a Redirect URL usa outra porta (ex.: 8080)."""

    def do_GET(self) -> None:  # noqa: N802 (nome exigido pela biblioteca padrão)
        parsed = urlparse(self.path)
        if parsed.path != callback_path():
            self.send_response(404)
            self.end_headers()
            return
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        success, message = finish_login(query)
        body = callback_page(success, message).encode("utf-8")
        self.send_response(200 if success else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        """Silencia o log padrão (a URL contém o código de autorização)."""


def _close_pending() -> None:
    global _pending
    pending, _pending = _pending, None
    if pending and pending.server:
        # shutdown() bloqueia até o laço parar; roda numa thread para não travar o handler.
        threading.Thread(target=pending.server.shutdown, daemon=True).start()


def start_login() -> str:
    """Inicia o login e devolve a URL de autorização para abrir no navegador."""
    global _pending
    _require_credentials()
    _close_pending()

    code_verifier = _base64url(secrets.token_bytes(32))
    code_challenge = _base64url(hashlib.sha256(code_verifier.encode("ascii")).digest())
    state = _base64url(secrets.token_bytes(16))
    pending = PendingLogin(state=state, code_verifier=code_verifier, created_at=time.time())

    # Se a Redirect URL não aponta para o servidor do Ailo, abrimos um servidor temporário nela.
    if not handles_callback_in_app():
        port, _ = _redirect_parts()
        try:
            server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        except OSError as error:
            raise AppError(
                f"A porta {port} da Redirect URL está em uso. Feche o outro programa (ex.: outro login do MCP) e tente de novo.",
                status=409,
                code="PORTA_EM_USO",
            ) from error
        threading.Thread(target=server.serve_forever, daemon=True).start()
        # Encerra o servidor se o usuário não concluir o login a tempo.
        # daemon=True: o temporizador não impede o processo de terminar.
        timeout = threading.Timer(LOGIN_TIMEOUT_SECONDS, lambda: _pending is pending and _close_pending())
        timeout.daemon = True
        timeout.start()
        pending.server = server

    _pending = pending
    params = {
        "response_type": "code",
        "client_id": config.ifood.client_id,
        "redirect_uri": config.ifood.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if config.ifood.scopes:
        params["scope"] = config.ifood.scopes
    return f"{config.ifood.authorize_url}?{urlencode(params)}"


def get_access_token() -> str:
    """Retorna um access token válido, renovando-o se necessário.

    Raises:
        IfoodAuthError: se o usuário não estiver conectado.
    """
    tokens = read_json(TOKENS_FILE)
    if not tokens or not tokens.get("accessToken"):
        raise IfoodAuthError()
    if time.time() < tokens.get("expiresAt", 0) - EXPIRY_MARGIN_SECONDS:
        return tokens["accessToken"]
    return force_refresh()


def force_refresh() -> str:
    """Renova os tokens com o refresh_token (usado também quando o MCP responde 401)."""
    _require_credentials()
    with _refresh_lock:
        tokens = read_json(TOKENS_FILE)
        if not tokens or not tokens.get("refreshToken"):
            raise IfoodAuthError("Sua sessão do iFood expirou. Conecte a conta novamente.")
        # Outra requisição pode ter renovado enquanto esperávamos o lock.
        if time.time() < tokens.get("expiresAt", 0) - EXPIRY_MARGIN_SECONDS:
            return tokens["accessToken"]
        renewed = _request_tokens({"grant_type": "refresh_token", "refresh_token": tokens["refreshToken"]})
        return renewed["accessToken"]


def has_stored_login() -> bool:
    tokens = read_json(TOKENS_FILE)
    return bool(tokens and tokens.get("accessToken"))


def logout() -> None:
    """Revoga os tokens no iFood (quando possível) e apaga a cópia local."""
    _close_pending()
    tokens = read_json(TOKENS_FILE) or {}
    token = tokens.get("refreshToken") or tokens.get("accessToken")
    if token and config.ifood.client_id and config.ifood.client_secret:
        try:
            httpx.post(config.ifood.revoke_url, data={"token": token, **_client_credentials()}, timeout=HTTP_TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            logger.warning("Não foi possível revogar o token no iFood: %s", error)
    remove_json(TOKENS_FILE)
