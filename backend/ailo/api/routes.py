"""Rotas da API (/api/*). Mantêm o mesmo contrato usado pela interface.

Todas as rotas recebem o cabeçalho ``X-Session-Id``, gerado por aba no navegador.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Header

from ..agent.agent import run_agent_turn
from ..agent.tools.base import summarize_restrictions
from ..config import config, config_problems
from ..errors import ValidationError
from ..ifood import oauth
from ..ifood.client import get_ifood_client
from ..profiles import delete_profile, read_profile, read_profile_restrictions, save_profile
from ..restrictions.catalog import list_restriction_options, resolve_restriction
from ..services.account import ensure_account_context, list_addresses, select_address
from ..services.cart import get_checkout_options, submit_order, track_order
from ..sessions import Session, get_session, reset_conversation

router = APIRouter(prefix="/api")

# Tamanho máximo de uma mensagem do usuário (igual ao limite da interface).
MAX_MESSAGE_LENGTH = 2000

VALID_MODES = ("restaurants", "market")

SessionHeader = Header(default=None, alias="X-Session-Id")


def _session_payload(session: Session) -> dict[str, Any]:
    """Estado da sessão enviado à interface."""
    return {
        "sessionId": session.id,
        "mode": session.mode,
        "user": session.user,
        "address": session.address,
        "restrictions": summarize_restrictions(session.restrictions),
        "restrictionInputs": session.restriction_inputs,
    }


# ------------------------------------------------------------------ Status e login


@router.get("/status")
async def status() -> dict[str, Any]:
    return {
        "ifoodConnected": await get_ifood_client().is_authenticated(),
        "llmConfigured": bool(config.gemini.api_key),
        "credentialsConfigured": bool(config.ifood.client_id and config.ifood.client_secret),
        "submitEnabled": config.ifood.allow_submit_order,
        "problems": config_problems(),
    }


@router.post("/auth/ifood/login")
async def login() -> dict[str, str]:
    """Inicia o login OAuth e devolve a URL de autorização do iFood."""
    return {"authorizationUrl": await asyncio.to_thread(oauth.start_login)}


@router.post("/auth/ifood/logout")
async def logout() -> dict[str, bool]:
    await get_ifood_client().disconnect()
    await asyncio.to_thread(oauth.logout)
    return {"ok": True}


# ------------------------------------------------------------------------ Sessão


@router.get("/session")
async def load_session(session_id: str | None = SessionHeader) -> dict[str, Any]:
    """Carrega a conta do iFood, o endereço e as restrições do perfil salvo (se autorizado)."""
    session = get_session(session_id)
    if not session.restrictions:
        session.restrictions = read_profile_restrictions()
        session.restriction_inputs = read_profile()["restrictions"]
    await ensure_account_context(session)
    return _session_payload(session)


@router.get("/addresses")
async def addresses() -> dict[str, Any]:
    return {"addresses": await list_addresses()}


@router.post("/session/address")
async def change_address(body: dict = Body(...), session_id: str | None = SessionHeader) -> dict[str, Any]:
    session = get_session(session_id)
    await select_address(session, str(body.get("addressId") or ""))
    return _session_payload(session)


@router.post("/session/mode")
async def change_mode(body: dict = Body(...), session_id: str | None = SessionHeader) -> dict[str, str]:
    if body.get("mode") not in VALID_MODES:
        raise ValidationError("Modo inválido.")
    session = get_session(session_id)
    session.mode = body["mode"]
    return {"mode": session.mode}


@router.post("/session/reset")
async def reset(session_id: str | None = SessionHeader) -> dict[str, Any]:
    return _session_payload(reset_conversation(get_session(session_id).id))


# ------------------------------------------------------------------------ Conversa


@router.post("/chat")
async def chat(body: dict = Body(...), session_id: str | None = SessionHeader) -> dict[str, Any]:
    message = str(body.get("message") or "").strip()
    if not message:
        raise ValidationError("Escreva uma mensagem.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValidationError(f"A mensagem pode ter até {MAX_MESSAGE_LENGTH} caracteres.")

    session = get_session(session_id)
    if session.busy:
        # Duas mensagens simultâneas embaralhariam o histórico.
        raise ValidationError("Ainda estou respondendo sua mensagem anterior.")
    if body.get("mode") in VALID_MODES:
        session.mode = body["mode"]

    session.busy = True
    try:
        await ensure_account_context(session)
        result = await run_agent_turn(session, message)
        return {**result, "restrictions": summarize_restrictions(session.restrictions)}
    finally:
        session.busy = False


# ------------------------------------------------------------------- Perfil alimentar


@router.get("/restrictions/catalog")
async def restriction_catalog() -> dict[str, Any]:
    return {"restrictions": list_restriction_options()}


@router.get("/profile")
async def get_profile() -> dict[str, Any]:
    profile = read_profile()
    resolved = [item for item in map(resolve_restriction, profile["restrictions"]) if item]
    return {**profile, "resolved": summarize_restrictions(resolved)}


@router.put("/profile")
async def put_profile(body: dict = Body(...), session_id: str | None = SessionHeader) -> dict[str, Any]:
    """Salva o perfil (exige consentimento) e aplica as restrições à conversa atual."""
    profile = save_profile(body.get("restrictions"), body.get("consent"))
    session = get_session(session_id)
    session.restrictions = [item for item in map(resolve_restriction, profile["restrictions"]) if item]
    session.restriction_inputs = profile["restrictions"]
    session.analyses.clear()
    return {**profile, "resolved": summarize_restrictions(session.restrictions)}


@router.delete("/profile")
async def remove_profile() -> dict[str, bool]:
    delete_profile()
    return {"ok": True}


# ------------------------------------------------------------- Revisão e pedido


@router.get("/carts/{cart_id}/checkout")
async def checkout(cart_id: str, session_id: str | None = SessionHeader) -> dict[str, Any]:
    return await get_checkout_options(get_session(session_id), cart_id)


@router.post("/orders")
async def create_order(body: dict = Body(...), session_id: str | None = SessionHeader) -> dict[str, Any]:
    """Única forma de enviar um pedido: o usuário revisou tudo e clicou em "Confirmar pedido"."""
    order = await submit_order(get_session(session_id), {
        "cartId": body.get("cartId"),
        "deliveryMethodId": body.get("deliveryMethodId"),
        "timeSlotId": body.get("timeSlotId"),
        "paymentMethodId": body.get("paymentMethodId"),
        "cardTokenId": body.get("cardTokenId"),
        "document": body.get("document"),
        "userConfirmed": body.get("userConfirmed") is True,
        "alertsAcknowledged": body.get("alertsAcknowledged") is True,
    })
    return {"order": order}


@router.get("/orders/{order_id}/track")
async def track(order_id: str, session_id: str | None = SessionHeader) -> dict[str, Any]:
    return await track_order(get_session(session_id), order_id)
