"""Sessões de conversa em memória.

Cada aba do navegador gera um ``sessionId`` e o envia em toda requisição
(cabeçalho ``X-Session-Id``). A sessão guarda o histórico com a LLM e o
CONTEXTO ESTRUTURADO da conversa (restrições, análises, receita, carrinhos),
que permite trocar do fluxo de restaurante para o de mercado sem o usuário
repetir informações (seção 3 da proposta).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage

from .restrictions.catalog import Restriction

# Sessões sem uso por mais tempo que isto são descartadas.
SESSION_TTL_SECONDS = 6 * 60 * 60

# Formato aceito para identificadores vindos do navegador.
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]{8,64}$")


@dataclass
class Session:
    id: str
    updated_at: float = field(default_factory=time.time)
    mode: str = "restaurants"
    # Histórico de mensagens do LangChain (HumanMessage, AIMessage, ToolMessage).
    history: list[BaseMessage] = field(default_factory=list)
    restrictions: list[Restriction] = field(default_factory=list)
    # Restrições como informadas (para salvar no perfil).
    restriction_inputs: list[dict[str, Any]] = field(default_factory=list)
    address: dict[str, Any] | None = None
    user: dict[str, Any] | None = None
    # Etiquetas itemRestrictions do iFood por item (vindas de buscas filtradas).
    declared_tags: dict[str, list[str]] = field(default_factory=dict)
    # Produtos descartados ao solicitar outra opção (loja, item).
    excluded_items: set[tuple[str, str]] = field(default_factory=set)
    # Últimas análises por item.
    analyses: dict[str, dict] = field(default_factory=dict)
    # Respostas dos estabelecimentos informadas pelo usuário.
    confirmations: list[dict] = field(default_factory=list)
    recipe: dict | None = None
    market_plan: dict | None = None
    # Carrinhos criados nesta sessão: cartId → {merchantId, itemIds}.
    carts: dict[str, dict] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)
    # Evita duas mensagens simultâneas na mesma sessão.
    busy: bool = False


_sessions: dict[str, Session] = {}


def _cleanup() -> None:
    limit = time.time() - SESSION_TTL_SECONDS
    for session_id in [key for key, session in _sessions.items() if session.updated_at < limit]:
        del _sessions[session_id]


def get_session(session_id: str | None) -> Session:
    """Busca a sessão pelo id, criando-a se necessário."""
    _cleanup()
    valid_id = session_id if session_id and SESSION_ID_PATTERN.match(session_id) else str(uuid.uuid4())
    session = _sessions.get(valid_id)
    if session is None:
        session = Session(id=valid_id)
        _sessions[valid_id] = session
    session.updated_at = time.time()
    return session


def reset_conversation(session_id: str) -> Session:
    """Reinicia a conversa mantendo o que é do usuário (endereço e restrições)."""
    previous = _sessions.get(session_id)
    session = Session(id=session_id)
    if previous:
        session.address = previous.address
        session.user = previous.user
        session.restrictions = previous.restrictions
        session.restriction_inputs = previous.restriction_inputs
        session.mode = previous.mode
    _sessions[session_id] = session
    return session


def remember_declared_tags(session: Session, item_ids: list[str], tags: list[str] | None) -> None:
    """Registra as etiquetas do iFood de itens que vieram de uma busca filtrada."""
    if not tags:
        return
    for item_id in item_ids:
        current = dict.fromkeys(session.declared_tags.get(item_id, []))
        current.update(dict.fromkeys(tags))
        session.declared_tags[item_id] = list(current)
