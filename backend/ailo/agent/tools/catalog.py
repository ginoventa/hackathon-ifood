"""Ferramentas de busca no catálogo do iFood (seção 1.2 da proposta).

Regras de recomendação (determinísticas, antes da LLM):

1. Se a restrição tem etiqueta no iFood (ex.: GLUTEN_FREE), as opções
   mostradas são SEMPRE as etiquetadas. Para elas, nomes de prato como
   "pizza" ou "massa" não contam como conflito.
2. Sem itens etiquetados, a busca vai "por fora": cada candidato tem a
   descrição (e o rótulo, se for industrializado) analisada, e só os que não
   conflitam aparecem.
3. Nada compatível com o pedido? Mostra outros pratos que atendem às
   restrições (pela etiqueta do iFood) ou avisa que não encontrou. Itens com
   conflito NUNCA são recomendados.
"""

from __future__ import annotations

import asyncio

from ...config import config
from ...errors import AppError
from ...restrictions.analyzer import Verdict, analyze_product
from ...restrictions.catalog import to_ifood_item_restrictions
from ...services.catalog import browse_items, get_item_details, search_offers
from ...services.labels import fetch_label
from ..system_prompt import (
    BUSCAR_OPCOES_PROMPT,
    VER_CARDAPIO_DA_LOJA_PROMPT,
)
from .base import ToolDefinition

# Ordem de exibição entre itens compatíveis.
DISPLAY_RANK = {
    Verdict.NO_DECLARED_CONFLICT: 0,
    Verdict.INSUFFICIENT: 1,
    Verdict.RISK: 2,
}

# Quantos itens sem etiqueta têm a descrição conferida em cada busca.
DEEP_CHECK_LIMIT = 6
MAX_OPTIONS = 3

# Nomes amigáveis das etiquetas do iFood.
TAG_LABELS = {"GLUTEN_FREE": "Sem glúten", "LAC_FREE": "Sem lactose", "VEGAN": "Vegano", "VEGETARIAN": "Vegetariano"}


def _has_all_tags(session, item: dict, tags: list[str]) -> bool:
    declared = session.declared_tags.get(item["itemId"], [])
    return bool(tags) and all(tag in declared for tag in tags)


def _name_verdict(session, item: dict) -> str:
    """Pré-análise pelo nome. Com a etiqueta do iFood, só a substância em si
    ("trigo") conta; sem ela, nomes de prato ("pizza", "massa") também contam."""
    analysis = analyze_product(
        {"itemId": item["itemId"], "itemName": item["itemName"], "merchantName": item["merchantName"]},
        session.restrictions,
        menu_items=[],
        declared_tags=session.declared_tags.get(item["itemId"], []),
    )
    return analysis["verdict"]


async def _description_verdict(session, item: dict) -> str | None:
    """Análise com a descrição completa (e o rótulo, se houver código de barras)."""
    try:
        details = await get_item_details(session, item["merchantId"], item["itemId"])
    except AppError:
        return None
    label = await fetch_label(details.get("itemEan") or item.get("itemEan"), details.get("itemName") or item.get("itemName"))
    analysis = analyze_product(
        details, session.restrictions, declared_tags=session.declared_tags.get(item["itemId"], []), label=label,
    )
    return analysis["verdict"]


async def _compatible_items(session, items: list[dict], tags: list[str]) -> list[dict]:
    """Filtra e ordena os resultados: só ficam itens sem conflito com as restrições."""
    visible = [item for item in items if (item["merchantId"], item["itemId"]) not in session.excluded_items]
    if not session.restrictions:
        return [{**item, "quickVerdict": None, "ifoodTag": False} for item in visible[:MAX_OPTIONS]]

    tagged, untagged = [], []
    for item in visible:
        verdict = _name_verdict(session, item)
        if verdict == Verdict.CONFLICT:
            continue
        entry = {**item, "quickVerdict": verdict, "ifoodTag": _has_all_tags(session, item, tags)}
        (tagged if entry["ifoodTag"] else untagged).append(entry)

    # Regra 1: havendo itens com a etiqueta do iFood, só eles são recomendados.
    if tagged:
        return sorted(tagged, key=lambda item: DISPLAY_RANK.get(item["quickVerdict"], 1))[:MAX_OPTIONS]

    # Regra 2: sem etiqueta, confere a descrição (e o rótulo) de cada candidato.
    candidates = untagged[:DEEP_CHECK_LIMIT]
    verdicts = await asyncio.gather(*[_description_verdict(session, item) for item in candidates])
    checked = []
    for item, verdict in zip(candidates, verdicts):
        if verdict == Verdict.CONFLICT:
            continue
        checked.append({**item, "quickVerdict": verdict or item["quickVerdict"], "descriptionChecked": verdict is not None})
    return sorted(checked, key=lambda item: DISPLAY_RANK.get(item["quickVerdict"], 1))[:MAX_OPTIONS]


def _items_output(items: list[dict]) -> list[dict]:
    """Resumo dos itens para a LLM."""
    return [
        {
            "itemId": item["itemId"],
            "merchantId": item["merchantId"],
            "nome": item["itemName"],
            "loja": item["merchantName"],
            "preco": item["promotionalUnitPrice"],
            "etiquetaDoIfood": item.get("ifoodTag", False),
            "preAnalise": item["quickVerdict"],
        }
        for item in items
    ]


def _options_card(title: str, items: list[dict], tags: list[str], *, alternatives: bool = False) -> dict:
    tag_label = " · ".join(TAG_LABELS.get(tag, tag) for tag in tags)
    for item in items:
        item["ifoodTagLabel"] = tag_label if item.get("ifoodTag") else None
    return {"type": "options", "data": {"title": title, "items": items, "filtersUsed": tags, "alternatives": alternatives}}


async def _search_compatible(session, *, query: str, base_refinements: dict, tags: list[str], merchant_type: str = "RESTAURANT", page_size: int = 8) -> list[dict]:
    """Busca o pedido priorizando a etiqueta do iFood e devolve só itens compatíveis."""
    tagged_items: list[dict] = []
    if tags:
        tagged = await search_offers(
            session, query=query, merchant_type=merchant_type, result_kind="ITEM", page_size=page_size,
            refinements={**base_refinements, "itemRestrictions": tags},
        )
        tagged_items = await _compatible_items(session, tagged["items"], tags)

    plain = await search_offers(
        session, query=query, merchant_type=merchant_type, result_kind="ITEM", page_size=page_size, refinements=base_refinements,
    )
    general_items = await _compatible_items(session, plain["items"], tags)
    tagged_ids = {(item["merchantId"], item["itemId"]) for item in tagged_items}
    general_items = [item for item in general_items if (item["merchantId"], item["itemId"]) not in tagged_ids]
    return (tagged_items + general_items)[:MAX_OPTIONS]


async def _search_merchants(session, query: str, refinements: dict):
    result = await search_offers(session, query=query, merchant_type="RESTAURANT", result_kind="MERCHANT", refinements=refinements)
    merchants = result["merchants"]
    output = {"lojas": [{"merchantId": item["merchantId"], "nome": item["merchantName"]} for item in merchants]}
    return output, {"type": "merchants", "data": {"title": f'Restaurantes para "{query}"', "merchants": merchants}}


async def _search_options(session, args):
    query = args["consulta"]
    use_filters = args.get("priorizarComFiltrosDoIfood", True) is not False
    tags = to_ifood_item_restrictions(session.restrictions) if use_filters else []
    # No demo, sempre inclui lojas fechadas, mesmo que o modelo peça apenasAbertos.
    refinements: dict = {"onlyOpen": not config.demo_mode and args.get("apenasAbertos", True) is True}
    if args.get("precoMaximo"):
        refinements["maxItemPrice"] = args["precoMaximo"]
    if args.get("ordenarPor"):
        refinements["sort"] = args["ordenarPor"]

    if (args.get("tipoResultado") or "ITEM") == "MERCHANT":
        return await _search_merchants(session, query, refinements)

    items = await _search_compatible(session, query=query, base_refinements=refinements, tags=tags)
    if items:
        return {"encontrado": True, "total": len(items), "itens": _items_output(items)}, _options_card(f'Opções para "{query}"', items, tags)

    # Pode haver opções compatíveis que só estão fechadas agora: vale avisar.
    closed_now = []
    if refinements.get("onlyOpen"):
        closed = await _search_compatible(session, query=query, base_refinements={**refinements, "onlyOpen": False}, tags=tags)
        closed_now = [f'{item["itemName"]} ({item["merchantName"]})' for item in closed[:5]]

    # Regra 3: nada compatível com o pedido. Oferece outros pratos que atendem às
    # restrições (etiqueta do iFood) em vez de itens com outra restrição.
    alternatives = []
    if tags:
        browsed = await browse_items(session, merchant_type="RESTAURANT", refinements={**refinements, "itemRestrictions": tags}, page_size=8)
        alternatives = await _compatible_items(session, browsed, tags)

    closed_note = (
        {"compativeisFechadosAgora": closed_now, "observacaoFechados": "Existem opções compatíveis, mas as lojas estão fechadas agora. Avise a pessoa."}
        if closed_now else {}
    )
    if alternatives:
        output = {
            "encontrado": False,
            **closed_note,
            "alternativas": _items_output(alternatives),
            "instrucao": f'Diga que não encontrou "{query}" compatível com as restrições e apresente estas alternativas, '
                         "que atendem às restrições. Não sugira itens incompatíveis.",
        }
        card = _options_card(f'Não encontrei "{query}" compatível. Opções que atendem às suas restrições', alternatives, tags, alternatives=True)
        return output, card

    return {
        "encontrado": False,
        **closed_note,
        "itens": [],
        "instrucao": f'Diga apenas que infelizmente não encontrou "{query}" compatível com as restrições por perto. '
                     "Não sugira itens incompatíveis. Pode oferecer preparar em casa.",
    }, None


SEARCH_OPTIONS = ToolDefinition(
    name="buscar_opcoes",
    description=BUSCAR_OPCOES_PROMPT,
    schema={
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": 'Só a parte descritiva, ex.: "lasanha", "pizza".'},
            "tipoResultado": {"type": "string", "enum": ["ITEM", "MERCHANT"], "description": "Padrão: ITEM."},
            "priorizarComFiltrosDoIfood": {
                "type": "boolean",
                "description": "Usa as etiquetas do iFood equivalentes às restrições (ex.: GLUTEN_FREE). Padrão: true.",
            },
            "precoMaximo": {"type": "number"},
            "ordenarPor": {"type": "string", "enum": ["RELEVANCE", "PRICE", "DISTANCE", "DELIVERY_TIME", "DELIVERY_FEE"]},
            "apenasAbertos": {
                "type": "boolean",
                "description": "Filtra apenas restaurantes abertos. Padrão: true fora do demo e false no demo.",
            },
        },
        "required": ["consulta"],
    },
    execute=_search_options,
)


async def _merchant_menu(session, args):
    query = args.get("consulta") or "pratos"
    tags = to_ifood_item_restrictions(session.restrictions)
    items = await _search_compatible(session, query=query, base_refinements={"merchantId": args["merchantId"]}, tags=tags, page_size=12)
    if not items:
        return {"encontrado": False, "instrucao": "Diga que não encontrou itens compatíveis com as restrições nesta loja."}, None
    title = f'Cardápio: "{args["consulta"]}"' if args.get("consulta") else "Cardápio da loja (itens compatíveis)"
    return {"encontrado": True, "total": len(items), "itens": _items_output(items)}, _options_card(title, items, tags)


MERCHANT_MENU = ToolDefinition(
    name="ver_cardapio_da_loja",
    description=VER_CARDAPIO_DA_LOJA_PROMPT,
    schema={
        "type": "object",
        "properties": {
            "merchantId": {"type": "string"},
            "consulta": {"type": "string", "description": "Texto para filtrar o cardápio. Opcional."},
        },
        "required": ["merchantId"],
    },
    execute=_merchant_menu,
)
