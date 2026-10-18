"""Consulta externa de rótulos de produtos industrializados.

Quando a resposta do iFood inclui um código de barras (EAN), ele pode ser
usado para consultar os alergênicos do rótulo. Sem ele, o produto é procurado pelo
nome (exigindo a mesma marca). Este serviço busca o rótulo na Open Food Facts
(https://world.openfoodfacts.org), base aberta e colaborativa, e devolve:

- alergênicos declarados ("contém"): ``allergens``;
- avisos de possível contaminação ("pode conter"): ``traces``;
- selos ("sem glúten", "vegano", "halal"...): ``labels``;
- lista de ingredientes: ``ingredients``.

Por ser colaborativa, a informação é tratada como evidência, nunca como
certificação: a interface sempre lembra de conferir a embalagem.
"""

from __future__ import annotations

import logging
import re
import time

import httpx

from ..restrictions.text_matching import normalize_text

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

# Busca textual da Open Food Facts (a busca antiga, cgi/search.pl, fica indisponível com frequência).
SEARCH_URL = "https://search.openfoodfacts.org/search"
SEARCH_PAGE_SIZE = 10
_name_cache: dict[str, tuple[float, str | None]] = {}


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


def _name_tokens(name: str) -> set[str]:
    text = normalize_text(name)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|mg|g|ml|l|unidades|un)\b", " ", text)
    return set(re.findall(r"[a-z0-9]+", text)) - {"de", "da", "do", "e", "com"}


async def fetch_label(ean: str | None, product_name: str | None = None) -> dict | None:
    """Busca o rótulo pelo código de barras ou, sem ele, pelo nome do produto.

    Returns:
        O rótulo (``found=True``), ``{"found": False}`` se o produto não está
        na base, ou ``None`` se não há EAN nem nome ou a consulta falhou.
    """
    if not ean or not EAN_PATTERN.match(str(ean)):
        # O iFood raramente informa o EAN: procura o produto pelo nome.
        return await _fetch_label_by_name(product_name) if product_name else None

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


def _best_name_match(product_name: str, hits: list[dict]) -> str | None:
    """EAN do resultado que corresponde ao produto do iFood.

    Todas as palavras do nome encontrado e a marca precisam aparecer no nome do
    anúncio. Entre os aceitos,
    vence o com mais palavras em comum (o mais específico).
    """
    wanted = _name_tokens(product_name)
    best, best_score = None, 0
    for hit in hits:
        tokens = _name_tokens(hit.get("product_name") or "")
        brands = [_name_tokens(brand) for brand in hit.get("brands") or []]
        if not tokens or not tokens <= wanted:
            continue
        # Sem marca igual, o rótulo pode ser de outro fabricante: não serve.
        if not any(brand and brand <= wanted for brand in brands):
            continue
        score = len(tokens)
        if score > best_score and EAN_PATTERN.match(str(hit.get("code") or "")):
            best, best_score = str(hit["code"]), score
    return best


async def _fetch_label_by_name(product_name: str) -> dict | None:
    """Rótulo de um produto sem EAN, localizado pelo nome na Open Food Facts."""
    key = normalize_text(product_name)
    cached = _name_cache.get(key)
    if cached and cached[0] > time.time():
        ean = cached[1]
    else:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(SEARCH_URL, params={
                    "q": product_name, "page_size": SEARCH_PAGE_SIZE, "fields": "code,product_name,brands",
                })
            ean = _best_name_match(product_name, response.json().get("hits") or [])
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Não foi possível buscar o rótulo de %r pelo nome: %s", product_name, error)
            return None
        _name_cache[key] = (time.time() + CACHE_TTL_SECONDS, ean)
    if not ean:
        return {"found": False, "ean": None}

    label = await fetch_label(ean)
    if label and label.get("found"):
        label = {
            **label,
            "matchedBy": "name",
            "sourceNote": "Produto localizado pelo nome (o anúncio do iFood não traz o código de barras); "
            "confira se a embalagem é a mesma. Base colaborativa.",
        }
    return label
