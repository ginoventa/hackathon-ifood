"""Agente do Ailo, construído com LangChain (``create_agent``).

A cada mensagem do usuário, o agente do LangChain:

1. envia o histórico ao Gemini com as ferramentas disponíveis;
2. executa as ferramentas que o modelo pedir e devolve os resultados;
3. repete até o modelo responder em texto (ou atingir o limite de passos).

Os cartões da interface vêm como ARTEFATOS das ToolMessages: são dados
produzidos pelas regras do Ailo e pelo iFood, nunca texto livre da IA.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from ..config import config
from ..errors import AppError
from ..sessions import Session
from .chat_model import get_chat_model, to_model_error
from .system_prompt import SYSTEM_PROMPT
from .tools import TurnState, create_agent_tools

# Quantidade máxima de mensagens guardadas no histórico da sessão.
MAX_HISTORY_MESSAGES = 60

MODE_LABELS = {"restaurants": "Restaurantes", "market": "Mercado (preparo em casa)"}


def _trim_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Corta o histórico antigo sem separar uma chamada de ferramenta da sua resposta.

    O corte sempre começa numa mensagem do usuário.
    """
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    start = len(messages) - MAX_HISTORY_MESSAGES
    while start < len(messages) and not isinstance(messages[start], HumanMessage):
        start += 1
    return messages[start:]


def _context_note(session: Session) -> str:
    """Contexto enviado junto da mensagem para o modelo saber o estado da interface."""
    restrictions = ", ".join(item.label for item in session.restrictions) or "nenhuma informada ainda"
    address = (session.address or {}).get("alias") or (session.address or {}).get("formattedAddress") or "endereço não definido"
    return f"[Contexto do app: modo {MODE_LABELS.get(session.mode, session.mode)}; restrições ativas: {restrictions}; entrega em {address}]"


def _message_text(message: BaseMessage | None) -> str:
    """Texto final de uma mensagem do modelo (o conteúdo pode vir em blocos)."""
    if message is None:
        return ""
    # `text` junta os blocos de texto da resposta (o Gemini pode devolver o conteúdo em blocos).
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return str(text)
    return message.content if isinstance(message.content, str) else ""


async def run_agent_turn(session: Session, message: str, *, model: BaseChatModel | None = None) -> dict:
    """Processa uma mensagem do usuário.

    Args:
        session: Sessão da conversa.
        message: Texto do usuário (pode conter identificadores entre colchetes).
        model: Permite injetar um modelo falso nos testes.

    Returns:
        ``{"reply": str, "cards": list[dict]}``.
    """
    turn = TurnState()
    agent = create_agent(
        model=model or get_chat_model(),
        tools=create_agent_tools(session, turn),
        system_prompt=SYSTEM_PROMPT,
    )

    inputs = [*session.history, HumanMessage(f"{_context_note(session)}\n{message}")]
    try:
        result = await agent.ainvoke(
            {"messages": inputs},
            # Cada rodada usa dois passos do grafo (modelo + ferramentas).
            {"recursion_limit": config.gemini.max_tool_rounds * 2 + 1},
        )
    except GraphRecursionError:
        reply = "Precisei de muitas etapas para responder. Pode detalhar um pouco mais o que você quer?"
        session.history = _trim_history([*inputs, AIMessage(reply)])
        return {"reply": reply, "cards": []}
    except AppError:
        raise
    except Exception as error:  # noqa: BLE001 (erros do provedor chegam em vários tipos)
        raise to_model_error(error) from error

    # Sem login no iFood não há como continuar: o usuário precisa conectar a conta.
    if turn.auth_error:
        raise turn.auth_error

    messages: list[BaseMessage] = result["messages"]
    new_messages = messages[len(inputs):]
    cards = [message.artifact for message in new_messages if isinstance(message, ToolMessage) and message.artifact]

    reply = _message_text(messages[-1]).strip() if isinstance(messages[-1], AIMessage) else ""
    if not reply:
        reply = "Confira as informações acima. Como quer seguir?" if cards else "Não consegui gerar uma resposta agora. Pode tentar reformular?"
        messages = [*messages, AIMessage(reply)]

    session.history = _trim_history(messages)
    return {"reply": reply, "cards": cards}
