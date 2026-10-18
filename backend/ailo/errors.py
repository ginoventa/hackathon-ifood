"""Erros da aplicação com status HTTP e mensagem amigável em português.

As rotas convertem estes erros em respostas JSON padronizadas:
``{"error": {"code": ..., "message": ...}}``.
"""

from __future__ import annotations


class AppError(Exception):
    """Erro com mensagem exibível ao usuário."""

    def __init__(self, message: str, *, status: int = 500, code: str = "ERRO_INTERNO") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class IfoodAuthError(AppError):
    """O usuário ainda não conectou a conta do iFood (ou o token expirou)."""

    def __init__(self, message: str = "Conecte sua conta do iFood para continuar.") -> None:
        super().__init__(message, status=401, code="IFOOD_LOGIN_NECESSARIO")


class IfoodToolError(AppError):
    """Uma ferramenta do MCP do iFood respondeu com erro."""

    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(f"O iFood recusou a operação {tool_name}: {message}", status=502, code="IFOOD_ERRO_FERRAMENTA")
        self.tool_name = tool_name


class ValidationError(AppError):
    """Entrada inválida enviada pelo frontend ou pela LLM."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status=400, code="DADOS_INVALIDOS")
