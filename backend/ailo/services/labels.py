"""Consulta externa de rótulos de produtos industrializados.

Quando a resposta do iFood inclui um código de barras (EAN), ele pode ser
usado para consultar os alergênicos do rótulo. Fora da demonstração, este serviço busca o rótulo na Open Food Facts
(https://world.openfoodfacts.org), base aberta e colaborativa, e devolve:

- alergênicos declarados ("contém"): ``allergens``;
- avisos de possível contaminação ("pode conter"): ``traces``;
- selos ("sem glúten", "vegano", "halal"...): ``labels``;
- lista de ingredientes: ``ingredients``.

Por ser colaborativa, a informação é tratada como evidência, nunca como
certificação: a interface sempre lembra de conferir a embalagem.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from ..config import config

import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://world.openfoodfacts.org/api/v2/product/{ean}.json"
FIELDS = "product_name,allergens_tags,traces_tags,labels_tags,ingredients_text_pt,ingredients_text"
TIMEOUT_SECONDS = 8
# A Open Food Facts pede um User-Agent que identifique o app.
USER_AGENT = "Ailo/2.0 (hackathon SEMCOMP x iFood)"

# Rótulos mudam pouco: o cache evita repetir a mesma consulta.
CACHE_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[float, dict | None]] = {}

EAN_PATTERN = re.compile(r"^\d{8,14}$")


def _parse(ean: str, payload: dict) -> dict:
    product = payload.get("product") or {}
    return {
        "found": True,
        "ean": ean,
        "productName": product.get("product_name") or "",
        "allergens": product.get("allergens_tags") or [],
        "traces": product.get("traces_tags") or [],
        "labels": product.get("labels_tags") or [],
        "ingredients": product.get("ingredients_text_pt") or product.get("ingredients_text") or "",
        "url": f"https://world.openfoodfacts.org/product/{ean}",
    }


async def fetch_label(ean: str | None) -> dict | None:
    """Busca o rótulo pelo código de barras.

    Returns:
        O rótulo (``found=True``), ``{"found": False}`` se o produto não está
        na base, ou ``None`` se não há EAN válido ou a consulta falhou.
    """
    if not ean or not EAN_PATTERN.match(str(ean)):
        return None

    if config.demo_mode:
        labels = json.loads((Path(__file__).resolve().parents[1] / "data/demo_labels.json").read_text(encoding="utf-8"))
        return deepcopy(labels.get(str(ean), {"found": False, "ean": str(ean), "demo": True}))

    cached = _cache.get(ean)
    if cached and cached[0] > time.time():
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(API_URL.format(ean=ean), params={"fields": FIELDS})
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Não foi possível consultar o rótulo %s: %s", ean, error)
        return None  # Falha temporária: não guarda no cache.

    label = _parse(ean, payload) if payload.get("status") == 1 else {"found": False, "ean": ean}
    _cache[ean] = (time.time() + CACHE_TTL_SECONDS, label)
    return label
