"""Configuração central do backend, lida das variáveis de ambiente.

O arquivo ``.env`` na raiz do repositório é carregado automaticamente.
Veja ``.env.example`` para a lista completa de variáveis.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

# Variáveis já definidas no ambiente têm prioridade sobre o .env.
load_dotenv(REPO_ROOT / ".env", override=False)


def _env(name: str, default: str = "") -> str:
    """Lê uma variável de ambiente sem espaços acidentais."""
    value = os.environ.get(name, "")
    return value.strip() if value.strip() else default


def _env_flag(name: str, default: bool) -> bool:
    """Converte "true"/"false" (e variações) em booleano."""
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "sim", "yes"}


@dataclass(frozen=True)
class LlmConfig:
    # "chatgpt": usa a assinatura do ChatGPT via OAuth (integração experimental do LangChain).
    # "gemini": usa a API do Gemini com GEMINI_API_KEY.
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "chatgpt").lower())
    # Modelos aceitos pelo backend do Codex numa conta Plus (out/2026): gpt-5.6-terra,
    # gpt-5.6-luna, gpt-5.6-sol, gpt-6-luna, gpt-6-sol. Nomes como "gpt-5.5" são recusados.
    chatgpt_model: str = field(default_factory=lambda: _env("CHATGPT_MODEL", "gpt-5.6-terra"))
    # Máximo de rodadas de ferramenta por mensagem, para evitar laços infinitos.
    max_tool_rounds: int = field(default_factory=lambda: int(_env("AGENT_MAX_TOOL_ROUNDS", "10")))


@dataclass(frozen=True)
class GeminiConfig:
    # Aceita API_KEY por compatibilidade com o .env original do projeto.
    api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY", _env("API_KEY")))
    model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-flash-latest"))


@dataclass(frozen=True)
class IfoodConfig:
    mcp_url: str = field(default_factory=lambda: _env("IFOOD_MCP_URL", "https://consumer-mcp.ifood.com.br/marketplace"))
    # Credenciais do agente cadastrado no MCP Portal (mcp-developer.ifood.com.br).
    client_id: str = field(default_factory=lambda: _env("IFOOD_CLIENT_ID"))
    client_secret: str = field(default_factory=lambda: _env("IFOOD_CLIENT_SECRET"))
    # Deve ser EXATAMENTE a Redirect URL (Callback URL) cadastrada no agente.
    redirect_uri: str = field(default_factory=lambda: _env("IFOOD_REDIRECT_URI", "http://localhost:8080/callback"))
    # Escopos técnicos liberados para o agente (separados por espaço). Vazio = padrão do iFood.
    scopes: str = field(default_factory=lambda: _env("IFOOD_SCOPES"))
    # Endpoints de autenticação (documentação: Autenticação > Implementação).
    authorize_url: str = field(default_factory=lambda: _env("IFOOD_AUTHORIZE_URL", "https://id.ifood.com.br/authorize"))
    token_url: str = field(default_factory=lambda: _env("IFOOD_TOKEN_URL", "https://id.ifood.com.br/token"))
    revoke_url: str = field(default_factory=lambda: _env("IFOOD_REVOKE_URL", "https://id.ifood.com.br/revoke"))
    # Envio do pedido (submitOrder). Sempre exige confirmação explícita na interface.
    allow_submit_order: bool = field(default_factory=lambda: _env_flag("ALLOW_SUBMIT_ORDER", True))


@dataclass(frozen=True)
class Config:
    port: int = field(default_factory=lambda: int(_env("PORT", "5173")))
    frontend_dir: Path = REPO_ROOT / "frontend"
    # Dados locais: tokens do iFood e perfil alimentar (fora do git).
    data_dir: Path = field(default_factory=lambda: (BACKEND_ROOT / _env("DATA_DIR", ".data")).resolve())
    llm: LlmConfig = field(default_factory=LlmConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    ifood: IfoodConfig = field(default_factory=IfoodConfig)

    @property
    def chatgpt_token_path(self) -> Path:
        """Onde o login do ChatGPT é salvo (fora do git, junto dos demais dados locais)."""
        return self.data_dir / "chatgpt-auth.json"

    @property
    def app_url(self) -> str:
        """URL da interface, usada para voltar ao app após o login do iFood."""
        return _env("APP_URL", f"http://localhost:{self.port}")


config = Config()


def config_problems() -> list[str]:
    """Lista problemas de configuração que impedem o app de funcionar."""
    problems = []
    if config.llm.provider == "gemini" and not config.gemini.api_key:
        problems.append("Defina GEMINI_API_KEY no arquivo .env (crie uma chave em https://aistudio.google.com/apikey).")
    elif config.llm.provider == "chatgpt" and not config.chatgpt_token_path.exists():
        problems.append("Entre na sua conta do ChatGPT: rode `npm run login-chatgpt` na raiz do projeto.")
    elif config.llm.provider not in ("gemini", "chatgpt"):
        problems.append('LLM_PROVIDER deve ser "chatgpt" ou "gemini".')
    if not config.ifood.client_id or not config.ifood.client_secret:
        problems.append(
            "Defina IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET no .env com as credenciais do agente "
            "cadastrado no MCP Portal (mcp-developer.ifood.com.br)."
        )
    return problems
