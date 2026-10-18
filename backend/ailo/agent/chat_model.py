"""Modelo de linguagem do agente: Gemini via LangChain (``langchain-google-genai``).

Trocar de provedor (OpenAI, Anthropic…) exige mudar só este arquivo: o resto
do agente usa a interface padrão de chat models do LangChain.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from ..config import config
from ..errors import AppError

# Tentativas automáticas em falhas temporárias do Gemini.
MAX_RETRIES = 2

_model: BaseChatModel | None = None


def get_chat_model() -> BaseChatModel:
    """Retorna o modelo de chat (criado sob demanda, para o servidor subir mesmo sem chave)."""
    global _model
    if not config.gemini.api_key:
        raise AppError("A chave do Gemini não está configurada. Defina GEMINI_API_KEY no arquivo .env.", status=503, code="LLM_NAO_CONFIGURADA")
    if _model is None:
        _model = ChatGoogleGenerativeAI(
            model=config.gemini.model,
            google_api_key=config.gemini.api_key,
            temperature=0.3,
            max_retries=MAX_RETRIES,
        )
    return _model


def to_model_error(error: Exception) -> AppError:
    """Traduz erros do Gemini em mensagens úteis para o usuário."""
    text = str(error)
    lowered = text.lower()
    if "429" in text or "quota" in lowered or "rate limit" in lowered or "resource_exhausted" in lowered:
        return AppError("O limite de uso do Gemini foi atingido. Aguarde um pouco e tente de novo.", status=429, code="LLM_LIMITE")
    if "api key" in lowered or "api_key" in lowered or "permission" in lowered or "401" in text or "403" in text:
        return AppError("A chave do Gemini é inválida. Confira GEMINI_API_KEY no .env.", status=503, code="LLM_CHAVE_INVALIDA")
    if "404" in text and "model" in lowered:
        return AppError(f'O modelo "{config.gemini.model}" não foi encontrado. Ajuste GEMINI_MODEL no .env.', status=503, code="LLM_MODELO_INVALIDO")
    return AppError("Não consegui falar com o Gemini agora. Tente novamente.", status=502, code="LLM_ERRO")
