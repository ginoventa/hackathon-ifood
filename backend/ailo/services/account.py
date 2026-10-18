"""Dados da conta do iFood: usuário e endereço de entrega.

O endereço é obrigatório para buscar ofertas (as ferramentas de descoberta
precisam da localização) e para montar carrinhos.
"""

from __future__ import annotations

from typing import Any

from ..errors import ValidationError
from ..ifood.client import get_ifood_client
from ..sessions import Session


def _to_address(raw: dict) -> dict[str, Any]:
    """Converte um endereço do MCP no formato usado pelo Ailo."""
    return {
        "addressId": raw.get("addressId"),
        "formattedAddress": raw.get("formattedAddress"),
        "alias": raw.get("alias"),
        "coordinates": raw.get("coordinates"),
        "isLastUsedAddress": bool(raw.get("isLastUsedAddress")),
        "isMostUsedAddress30d": bool(raw.get("isMostUsedAddress30d")),
    }


async def list_addresses() -> list[dict[str, Any]]:
    """Endereços salvos na conta do iFood."""
    response = await get_ifood_client().call_tool("listAddresses", {})
    return [_to_address(item) for item in response.get("results") or []]


def _pick_default_address(addresses: list[dict]) -> dict | None:
    """Escolhe o endereço mais provável, como orienta o próprio MCP:
    último usado, depois o mais usado nos últimos 30 dias, depois o primeiro."""
    for key in ("isLastUsedAddress", "isMostUsedAddress30d"):
        for address in addresses:
            if address[key]:
                return address
    return addresses[0] if addresses else None


async def ensure_account_context(session: Session) -> None:
    """Garante que a sessão conheça o usuário e o endereço (consulta o iFood só na primeira vez)."""
    if session.user is None:
        response = await get_ifood_client().call_tool("getUser", {})
        data = response.get("data") or {}
        session.user = {"fullName": data.get("fullName") or ""}
    if session.address is None:
        session.address = _pick_default_address(await list_addresses())


async def select_address(session: Session, address_id: str) -> dict:
    """Troca o endereço de entrega por outro endereço salvo."""
    address = next((item for item in await list_addresses() if item["addressId"] == address_id), None)
    if address is None:
        raise ValidationError("Endereço não encontrado na sua conta do iFood.")
    session.address = address
    return address


def user_location(session: Session) -> dict[str, float]:
    """Localização usada nas buscas."""
    coordinates = (session.address or {}).get("coordinates")
    if not coordinates:
        raise ValidationError("Cadastre um endereço de entrega no iFood para que eu possa buscar opções perto de você.")
    return {"latitude": coordinates["latitude"], "longitude": coordinates["longitude"]}


def first_name(session: Session) -> str:
    """Primeiro nome do usuário, para personalizar mensagens."""
    full_name = (session.user or {}).get("fullName") or ""
    return full_name.split(" ")[0] if full_name else ""
