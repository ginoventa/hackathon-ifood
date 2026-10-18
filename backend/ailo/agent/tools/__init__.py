"""Registro das ferramentas do agente, no formato do LangChain.

``create_agent_tools`` converte as definições em ferramentas LangChain
(``StructuredTool``) com ``response_format="content_and_artifact"``: a saída
volta para a LLM como conteúdo e o cartão viaja como artefato da ToolMessage
até a interface.

Note que ``submitOrder`` NÃO está aqui de propósito: a LLM nunca envia pedidos.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_core.tools import StructuredTool

from ...errors import AppError, IfoodAuthError
from ...sessions import Session
from .base import ToolDefinition
from .cart import BUILD_CART, BUILD_GROCERY_CART
from .catalog import MERCHANT_MENU, SEARCH_OPTIONS
from .market import GROCERY_PLAN, REGISTER_RECIPE
from .restrictions import ANALYZE_PRODUCT, CLARIFICATION_MESSAGE, ESTABLISHMENT_ANSWER, REGISTER_RESTRICTIONS

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS: list[ToolDefinition] = [
    REGISTER_RESTRICTIONS,
    SEARCH_OPTIONS,
    MERCHANT_MENU,
    ANALYZE_PRODUCT,
    CLARIFICATION_MESSAGE,
    ESTABLISHMENT_ANSWER,
    REGISTER_RECIPE,
    GROCERY_PLAN,
    BUILD_CART,
    BUILD_GROCERY_CART,
]

TOOL_NAMES = [definition.name for definition in TOOL_DEFINITIONS]


@dataclass
class TurnState:
    """Estado de um turno: guarda um erro de login para interromper a resposta."""

    auth_error: IfoodAuthError | None = None


def _make_tool(definition: ToolDefinition, session: Session, turn: TurnState) -> StructuredTool:
    async def run(**kwargs):
        try:
            output, card = await definition.execute(session, kwargs)
        except AppError as error:
            logger.warning("Ferramenta %s falhou: %s", definition.name, error.message)
            if isinstance(error, IfoodAuthError):
                # Login é algo que só o usuário resolve: o turno será interrompido.
                turn.auth_error = error
            # A LLM recebe o erro como resultado e pode se corrigir ou explicar.
            return json.dumps({"erro": error.message}, ensure_ascii=False), None
        except Exception:  # noqa: BLE001 (nenhuma falha de ferramenta deve derrubar a conversa)
            logger.exception("Erro inesperado na ferramenta %s", definition.name)
            return json.dumps({"erro": "Falha inesperada ao executar a ferramenta."}, ensure_ascii=False), None
        return json.dumps(output, ensure_ascii=False), card

    return StructuredTool.from_function(
        coroutine=run,
        name=definition.name,
        description=definition.description,
        args_schema=definition.schema,
        response_format="content_and_artifact",
    )


def create_agent_tools(session: Session, turn: TurnState) -> list[StructuredTool]:
    """Cria as ferramentas LangChain ligadas a uma sessão de conversa."""
    return [_make_tool(definition, session, turn) for definition in TOOL_DEFINITIONS]
