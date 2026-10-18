"""Cliente do MCP do iFood via LangChain (``langchain-mcp-adapters``).

O ``MultiServerMCPClient`` conecta ao MCP do iFood
(``https://consumer-mcp.ifood.com.br/marketplace``) e transforma cada
ferramenta (searchOffers, getItem, createCart…) numa ferramenta LangChain.
O token OAuth do agente é injetado por um ``httpx.Auth``, que também renova
o token quando o iFood responde 401.

As ferramentas do iFood NÃO são entregues diretamente à LLM: elas são
chamadas pelos serviços do Ailo, que aplicam as regras de restrição antes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Protocol

import httpx
from langchain_core.tools import BaseTool, ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import config
from ..errors import IfoodAuthError, IfoodToolError
from . import oauth

logger = logging.getLogger(__name__)

SERVER_NAME = "ifood"


class IfoodClient(Protocol):
    """Interface usada pelo resto do sistema (permite um cliente falso nos testes)."""

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any: ...

    async def is_authenticated(self) -> bool: ...

    async def disconnect(self) -> None: ...


class IfoodBearerAuth(httpx.Auth):
    """Injeta o token do agente e renova-o uma vez se o MCP responder 401."""

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await asyncio.to_thread(oauth.get_access_token)
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            token = await asyncio.to_thread(oauth.force_refresh)
            request.headers["Authorization"] = f"Bearer {token}"
            yield request


def _parse_tool_message(message: Any) -> Any:
    """Extrai o JSON da resposta de uma ferramenta MCP.

    Prefere o ``structuredContent`` (artefato); senão interpreta o texto.
    """
    artifact = getattr(message, "artifact", None)
    if isinstance(artifact, dict) and artifact.get("structured_content") is not None:
        return artifact["structured_content"]

    content = getattr(message, "content", message)
    if isinstance(content, list):
        content = "\n".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return {"text": content}


def _is_auth_error(error: BaseException) -> bool:
    if isinstance(error, IfoodAuthError):
        return True
    text = str(error)
    return any(marker in text for marker in ("401", "Unauthorized", "unauthorized", "invalid_token"))


def _find_auth_error(error: BaseException) -> IfoodAuthError | None:
    """Procura um IfoodAuthError dentro de grupos de exceção (o SDK MCP usa TaskGroup)."""
    if isinstance(error, IfoodAuthError):
        return error
    for inner in getattr(error, "exceptions", ()):
        found = _find_auth_error(inner)
        if found:
            return found
    cause = error.__cause__ or error.__context__
    return _find_auth_error(cause) if cause else None


class LiveIfoodClient:
    """Cliente real: MCP do iFood via LangChain."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] | None = None
        self._lock = asyncio.Lock()

    async def _load_tools(self) -> dict[str, BaseTool]:
        """Conecta ao MCP e carrega as ferramentas (uma vez)."""
        async with self._lock:
            if self._tools is None:
                client = MultiServerMCPClient(
                    {
                        SERVER_NAME: {
                            "transport": "streamable_http",
                            "url": config.ifood.mcp_url,
                            "auth": IfoodBearerAuth(),
                        }
                    },
                    # Erros do iFood viram exceção, para os serviços tratarem.
                    handle_tool_errors=False,
                )
                tools = await client.get_tools(server_name=SERVER_NAME)
                self._tools = {tool.name: tool for tool in tools}
                logger.info("MCP do iFood conectado: %d ferramentas.", len(self._tools))
            return self._tools

    async def is_authenticated(self) -> bool:
        return oauth.has_stored_login()

    async def disconnect(self) -> None:
        self._tools = None

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Executa uma ferramenta do MCP do iFood e devolve o JSON da resposta."""
        if not oauth.has_stored_login():
            raise IfoodAuthError()

        try:
            tools = await self._load_tools()
        except Exception as error:  # noqa: BLE001 (falhas de rede chegam em vários tipos)
            await self.disconnect()
            auth_error = _find_auth_error(error)
            if auth_error or _is_auth_error(error):
                raise auth_error or IfoodAuthError("Sua sessão do iFood expirou. Conecte a conta novamente.") from error
            logger.warning("Falha ao conectar ao MCP do iFood: %r", error)
            raise IfoodToolError(name, "não foi possível conectar ao iFood agora. Tente novamente em instantes.") from error

        tool = tools.get(name)
        if tool is None:
            raise IfoodToolError(name, "ferramenta não encontrada no MCP do iFood.")

        # Chamada no formato "tool call" para receber a ToolMessage com o artefato estruturado.
        tool_call = {"type": "tool_call", "id": str(uuid.uuid4()), "name": name, "args": args}
        try:
            message = await tool.ainvoke(tool_call)
        except ToolException as error:
            # Erro de negócio do iFood (isError=True), com a mensagem do servidor.
            raise IfoodToolError(name, str(error) or "erro desconhecido") from error
        except Exception as error:  # noqa: BLE001
            auth_error = _find_auth_error(error)
            if auth_error or _is_auth_error(error):
                await self.disconnect()
                raise auth_error or IfoodAuthError("Sua sessão do iFood expirou. Conecte a conta novamente.") from error
            logger.warning("Falha na ferramenta %s do iFood: %r", name, error)
            raise IfoodToolError(name, "não foi possível falar com o iFood agora. Tente novamente.") from error

        return _parse_tool_message(message)


# Instância compartilhada por todo o servidor. Os testes substituem por um cliente falso.
ifood: IfoodClient = LiveIfoodClient()


def set_ifood_client(client: IfoodClient) -> None:
    """Troca o cliente do iFood (usado nos testes)."""
    global ifood
    ifood = client


def get_ifood_client() -> IfoodClient:
    return ifood
