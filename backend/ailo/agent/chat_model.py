"""Modelo de linguagem do agente, escolhido por ``LLM_PROVIDER``.

- ``chatgpt`` (padrão): usa a assinatura do ChatGPT via OAuth, com a integração
  ``_ChatOpenAICodex`` do ``langchain-openai``. Ela é EXPERIMENTAL e NÃO OFICIAL:
  acessa o backend do Codex (chatgpt.com/backend-api/codex), respeita os limites
  do plano e pode mudar sem aviso. O login é feito com ``npm run login-chatgpt``.
- ``gemini``: usa a API do Gemini com ``GEMINI_API_KEY`` (``langchain-google-genai``).

Trocar de provedor exige mudar só este arquivo: o resto do agente usa a
interface padrão de chat models do LangChain.
"""

from __future__ import annotations

import warnings

from langchain_core.language_models import BaseChatModel

from ..config import config
from ..errors import AppError

# Tentativas automáticas em falhas temporárias do provedor.
MAX_RETRIES = 2

_model: BaseChatModel | None = None


def _chatgpt_model() -> BaseChatModel:
    """ChatGPT via OAuth da assinatura (integração experimental do LangChain)."""
    # Importação tardia: o módulo só é carregado quando este provedor é usado.
    from langchain_openai.chat_models.codex import _ChatOpenAICodex
    from langchain_openai.chatgpt_oauth import _FileChatGPTOAuthTokenProvider

    if not config.chatgpt_token_path.exists():
        raise AppError(
            "Entre na sua conta do ChatGPT: rode `npm run login-chatgpt` na raiz do projeto e reinicie o servidor.",
            status=503,
            code="LLM_LOGIN_NECESSARIO",
        )

    with warnings.catch_warnings():
        # O aviso "experimental e não oficial" já está documentado no README e neste módulo.
        warnings.simplefilter("ignore", UserWarning)
        return _ChatOpenAICodex(
            model=config.llm.chatgpt_model,
            # O token fica em backend/.data/ e é renovado automaticamente.
            token_provider=_FileChatGPTOAuthTokenProvider(path=config.chatgpt_token_path),
            max_retries=MAX_RETRIES,
        )


def _gemini_model() -> BaseChatModel:
    """Gemini via API key."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not config.gemini.api_key:
        raise AppError("A chave do Gemini não está configurada. Defina GEMINI_API_KEY no arquivo .env.", status=503, code="LLM_NAO_CONFIGURADA")
    return ChatGoogleGenerativeAI(
        model=config.gemini.model,
        google_api_key=config.gemini.api_key,
        temperature=0.3,
        max_retries=MAX_RETRIES,
    )


def get_chat_model() -> BaseChatModel:
    """Retorna o modelo de chat (criado sob demanda, para o servidor subir mesmo sem login)."""
    global _model
    if _model is None:
        if config.llm.provider == "chatgpt":
            _model = _chatgpt_model()
        elif config.llm.provider == "gemini":
            _model = _gemini_model()
        else:
            raise AppError('LLM_PROVIDER deve ser "chatgpt" ou "gemini".', status=503, code="LLM_PROVEDOR_INVALIDO")
    return _model


def is_model_configured() -> bool:
    """Indica se o provedor escolhido tem login/chave disponível."""
    if config.llm.provider == "chatgpt":
        return config.chatgpt_token_path.exists()
    return bool(config.gemini.api_key)


def to_model_error(error: Exception) -> AppError:
    """Traduz erros do provedor em mensagens úteis para o usuário."""
    text = str(error)
    lowered = text.lower()
    provider = "ChatGPT" if config.llm.provider == "chatgpt" else "Gemini"

    if "refresh" in lowered and ("oauth" in lowered or "token" in lowered):
        return AppError("O login do ChatGPT expirou. Rode `npm run login-chatgpt` de novo.", status=503, code="LLM_LOGIN_NECESSARIO")
    if "429" in text or "quota" in lowered or "rate limit" in lowered or "usage limit" in lowered or "resource_exhausted" in lowered:
        return AppError(f"O limite de uso do {provider} foi atingido. Aguarde um pouco e tente de novo.", status=429, code="LLM_LIMITE")
    if "api key" in lowered or "api_key" in lowered or "401" in text or "403" in text or "unauthorized" in lowered:
        hint = "rode `npm run login-chatgpt` de novo" if provider == "ChatGPT" else "confira GEMINI_API_KEY no .env"
        return AppError(f"O {provider} recusou a autenticação: {hint}.", status=503, code="LLM_AUTENTICACAO")
    if ("404" in text or "not found" in lowered or "not supported" in lowered) and "model" in lowered:
        if provider == "ChatGPT":
            message = (
                f'O modelo "{config.llm.chatgpt_model}" não é aceito na sua conta do ChatGPT. '
                "Ajuste CHATGPT_MODEL no .env (ex.: gpt-5.6-terra)."
            )
        else:
            message = "O modelo configurado não está disponível. Ajuste GEMINI_MODEL no .env."
        return AppError(message, status=503, code="LLM_MODELO_INVALIDO")
    return AppError(f"Não consegui falar com o {provider} agora. Tente novamente.", status=502, code="LLM_ERRO")
