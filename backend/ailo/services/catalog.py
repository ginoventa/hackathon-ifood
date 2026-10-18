"""Consultas ao catálogo do iFood (busca, detalhes e cardápio completo),
já adaptadas ao formato usado pelo agente e pela interface."""

from __future__ import annotations

import time
from typing import Any

from ..errors import AppError
from ..ifood.client import get_ifood_client
from ..sessions import Session, remember_declared_tags
from .account import user_location

# Páginas de cardápio consultadas para avaliar contato cruzado (25 itens cada).
MENU_PAGES = 3
MENU_PAGE_SIZE = 25

# Cache de cardápios: evita refazer a mesma varredura em poucos minutos.
MENU_CACHE_TTL_SECONDS = 10 * 60
_menu_cache: dict[str, tuple[float, list[dict]]] = {}
_tagged_cache: dict[str, tuple[float, set[str]]] = {}


def summarize_item_result(result: dict) -> dict[str, Any]:
    """Resume um resultado de busca do tipo ITEM."""
    merchant = result.get("merchant") or {}
    delivery = merchant.get("deliveryMethod") or {}
    unit_price = result.get("unitPrice")
    return {
        "itemId": result.get("itemId"),
        "itemName": result.get("itemName"),
        "itemEan": result.get("itemEan") or None,
        "imageUrl": result.get("itemImageUrl"),
        "unitPrice": unit_price,
        "promotionalUnitPrice": result.get("promotionalUnitPrice", unit_price),
        "merchantId": merchant.get("merchantId"),
        "merchantName": merchant.get("merchantName"),
        "merchantRating": merchant.get("reviewRating"),
        "distanceKm": merchant.get("straightLineDistanceKm"),
        "isOpen": merchant.get("isOpen", True),
        "deliveryFee": delivery.get("promotionalFee", delivery.get("fee")),
        "deliveryMinutes": delivery.get("estimatedMinutes"),
        "minimumOrderAmount": merchant.get("minimumOrderAmount"),
    }


def summarize_merchant_result(result: dict) -> dict[str, Any]:
    """Resume um resultado de busca do tipo MERCHANT."""
    delivery = result.get("deliveryMethod") or {}
    return {
        "merchantId": result.get("merchantId"),
        "merchantName": result.get("merchantName"),
        "logoUrl": result.get("merchantLogoUrl"),
        "rating": result.get("reviewRating"),
        "distanceKm": result.get("straightLineDistanceKm"),
        "isOpen": result.get("isOpen", True),
        "deliveryFee": delivery.get("promotionalFee", delivery.get("fee")),
        "deliveryMinutes": delivery.get("estimatedMinutes"),
        "minimumOrderAmount": result.get("minimumOrderAmount"),
    }


async def search_offers(
    session: Session,
    *,
    query: str,
    merchant_type: str | None = None,
    result_kind: str = "ITEM",
    refinements: dict | None = None,
    page_size: int = 8,
) -> dict[str, Any]:
    """Busca ofertas por texto no iFood.

    Se a busca usou filtros ``itemRestrictions``, os itens retornados ficam
    marcados na sessão com essas etiquetas do iFood (evidência para a análise).
    """
    refinements = refinements or {}
    args: dict[str, Any] = {
        "query": query,
        "resultKind": result_kind,
        "refinements": refinements,
        "pageSize": page_size,
        "userLocation": user_location(session),
    }
    if merchant_type:
        args["merchantType"] = merchant_type
    response = await get_ifood_client().call_tool("searchOffers", args)

    results = response.get("results") or []
    if result_kind == "ITEM":
        remember_declared_tags(session, [item.get("itemId") for item in results], refinements.get("itemRestrictions"))
        return {"kind": "ITEM", "items": [summarize_item_result(item) for item in results], "hasMore": bool(response.get("hasMore"))}
    return {"kind": "MERCHANT", "merchants": [summarize_merchant_result(item) for item in results], "hasMore": bool(response.get("hasMore"))}


async def browse_items(session: Session, *, merchant_type: str, refinements: dict, page_size: int = 8) -> list[dict]:
    """Navega pelos itens perto do usuário sem termo de busca (ex.: tudo com GLUTEN_FREE).

    Os itens retornados ficam marcados na sessão com as etiquetas do filtro.
    """
    response = await get_ifood_client().call_tool("browseOffers", {
        "merchantType": merchant_type,
        "resultKind": "ITEM",
        "pageSize": page_size,
        "refinements": refinements,
        "userLocation": user_location(session),
    })
    results = response.get("results") or []
    remember_declared_tags(session, [item.get("itemId") for item in results], refinements.get("itemRestrictions"))
    return [summarize_item_result(item) for item in results]


async def get_item_details(session: Session, merchant_id: str, item_id: str) -> dict:
    """Detalhes completos de um item (descrição e adicionais)."""
    return await get_ifood_client().call_tool(
        "getItem", {"merchantId": merchant_id, "itemId": item_id, "userLocation": user_location(session)},
    )


async def get_tagged_item_ids(session: Session, merchant_id: str, tag: str, merchant_type: str = "RESTAURANT") -> set[str]:
    """Ids dos itens da loja que o iFood classifica com a etiqueta (ex.: GLUTEN_FREE).

    Falhas não interrompem a análise: sem a lista, nenhum item é tratado como etiquetado.
    """
    key = f"{merchant_id}:{tag}"
    cached = _tagged_cache.get(key)
    if cached and cached[0] > time.time():
        return cached[1]

    ids: set[str] = set()
    next_page_token = None
    try:
        for _ in range(MENU_PAGES):
            args: dict[str, Any] = {
                "merchantType": merchant_type,
                "resultKind": "ITEM",
                "pageSize": MENU_PAGE_SIZE,
                "refinements": {"merchantId": merchant_id, "itemRestrictions": [tag]},
                "userLocation": user_location(session),
            }
            if next_page_token:
                args["nextPageToken"] = next_page_token
            response = await get_ifood_client().call_tool("browseOffers", args)
            ids.update(item.get("itemId") for item in response.get("results") or [])
            next_page_token = response.get("nextPageToken")
            if not response.get("hasMore") or not next_page_token:
                break
    except AppError:
        return ids

    _tagged_cache[key] = (time.time() + MENU_CACHE_TTL_SECONDS, ids)
    return ids


async def get_menu_items(session: Session, merchant_id: str, merchant_type: str = "RESTAURANT") -> list[dict]:
    """Lê o cardápio do estabelecimento (até MENU_PAGES páginas) para avaliar contato cruzado."""
    cached = _menu_cache.get(merchant_id)
    if cached and cached[0] > time.time():
        return cached[1]

    items: list[dict] = []
    next_page_token = None
    for _ in range(MENU_PAGES):
        args: dict[str, Any] = {
            "merchantType": merchant_type,
            "resultKind": "ITEM",
            "pageSize": MENU_PAGE_SIZE,
            "refinements": {"merchantId": merchant_id},
            "userLocation": user_location(session),
        }
        if next_page_token:
            args["nextPageToken"] = next_page_token
        response = await get_ifood_client().call_tool("browseOffers", args)
        items.extend({"itemId": item.get("itemId"), "itemName": item.get("itemName")} for item in response.get("results") or [])
        next_page_token = response.get("nextPageToken")
        if not response.get("hasMore") or not next_page_token:
            break

    _menu_cache[merchant_id] = (time.time() + MENU_CACHE_TTL_SECONDS, items)
    return items
