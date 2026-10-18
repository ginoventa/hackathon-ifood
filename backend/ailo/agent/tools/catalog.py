"""Ferramentas de busca no catálogo do iFood (seção 1.2 da proposta).

Os resultados são ordenados priorizando a compatibilidade com as restrições:
uma pré-análise rápida (só pelo nome) manda itens com conflito evidente para
o fim da lista, com um aviso.
"""

from __future__ import annotations

from dataclasses import replace

from ...restrictions.analyzer import Verdict, analyze_product
from ...restrictions.catalog import to_ifood_item_restrictions
from ...services.catalog import search_offers
from .base import ToolDefinition

# Ordem de exibição: itens com conflito aparente vão para o fim.
DISPLAY_RANK = {
    Verdict.NO_DECLARED_CONFLICT: 0,
    Verdict.INSUFFICIENT: 1,
    Verdict.RISK: 2,
    Verdict.CONFLICT: 3,
}


def _quick_verdict(session, item: dict) -> str | None:
    """Pré-análise só pelo nome: indicativo para ordenar, não um parecer final.

    Usa apenas a substância em si ("trigo", "leite"): nomes de prato como
    "lasanha" podem ter versões adaptadas e só são julgados na análise completa.
    """
    if not session.restrictions:
        return None
    core_only = [replace(restriction, terms=restriction.effective_core_terms) for restriction in session.restrictions]
    analysis = analyze_product(
        {"itemId": item["itemId"], "itemName": item["itemName"], "merchantName": item["merchantName"]},
        core_only,
        menu_items=[],
        declared_tags=session.declared_tags.get(item["itemId"], []),
    )
    return analysis["verdict"]


async def _run_search(session, *, title: str, **params):
    result = await search_offers(session, **params)

    if result["kind"] == "MERCHANT":
        merchants = result["merchants"]
        output = {"lojas": [{"merchantId": item["merchantId"], "nome": item["merchantName"]} for item in merchants]}
        return output, {"type": "merchants", "data": {"title": title, "merchants": merchants}}

    items = [{**item, "quickVerdict": _quick_verdict(session, item)} for item in result["items"]
             if (item["merchantId"], item["itemId"]) not in session.excluded_items]
    items.sort(key=lambda item: DISPLAY_RANK.get(item["quickVerdict"], 1))
    output = {
        "total": len(items),
        "itens": [
            {
                "itemId": item["itemId"],
                "merchantId": item["merchantId"],
                "nome": item["itemName"],
                "loja": item["merchantName"],
                "preco": item["promotionalUnitPrice"],
                "preAnalisePeloNome": item["quickVerdict"],
            }
            for item in items
        ],
        "observacao": "A pré-análise usa só o nome. A análise completa é feita com analisar_produto.",
    }
    filters = (params.get("refinements") or {}).get("itemRestrictions") or []
    return output, {"type": "options", "data": {"title": title, "items": items, "filtersUsed": filters}}


async def _search_options(session, args):
    use_filters = args.get("priorizarComFiltrosDoIfood", True) is not False
    tags = to_ifood_item_restrictions(session.restrictions) if use_filters else []
    refinements: dict = {"onlyOpen": args.get("apenasAbertos", True) is not False}
    if tags:
        refinements["itemRestrictions"] = tags
    if args.get("precoMaximo"):
        refinements["maxItemPrice"] = args["precoMaximo"]
    if args.get("ordenarPor"):
        refinements["sort"] = args["ordenarPor"]

    search = {
        "title": f'Opções para "{args["consulta"]}"',
        "query": args["consulta"],
        "merchant_type": "RESTAURANT",
        "result_kind": args.get("tipoResultado") or "ITEM",
        "page_size": 8,
    }
    output, card = await _run_search(session, refinements=refinements, **search)

    # Os filtros do iFood podem esconder tudo (ex.: VEGAN para APLV). Nesse caso,
    # busca de novo sem eles: a pré-análise e a análise completa continuam valendo.
    if tags and not (card["data"].get("items") or card["data"].get("merchants")):
        refinements.pop("itemRestrictions")
        output, card = await _run_search(session, refinements=refinements, **search)
        output["observacao"] = (
            "Nenhum resultado com os filtros de restrição do iFood; estes resultados vieram sem filtro. "
            "Analise cada item com analisar_produto antes de recomendar."
        )
    return output, card


SEARCH_OPTIONS = ToolDefinition(
    name="buscar_opcoes",
    description="Busca pratos (ITEM) ou restaurantes (MERCHANT) no iFood perto do usuário. Use para o pedido em restaurante.",
    schema={
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": 'Só a parte descritiva, ex.: "lasanha", "pizza".'},
            "tipoResultado": {"type": "string", "enum": ["ITEM", "MERCHANT"], "description": "Padrão: ITEM."},
            "priorizarComFiltrosDoIfood": {
                "type": "boolean",
                "description": "Usa os filtros do iFood equivalentes às restrições (ex.: GLUTEN_FREE). Padrão: true. Use false se vierem poucos resultados.",
            },
            "precoMaximo": {"type": "number"},
            "ordenarPor": {"type": "string", "enum": ["RELEVANCE", "PRICE", "DISTANCE", "DELIVERY_TIME", "DELIVERY_FEE"]},
            "apenasAbertos": {"type": "boolean", "description": "Padrão: true."},
        },
        "required": ["consulta"],
    },
    execute=_search_options,
)


async def _merchant_menu(session, args):
    query = args.get("consulta")
    return await _run_search(
        session,
        title=f'Cardápio: "{query}"' if query else "Cardápio da loja",
        query=query or "pratos",
        merchant_type="RESTAURANT",
        result_kind="ITEM",
        refinements={"merchantId": args["merchantId"]},
        page_size=12,
    )


MERCHANT_MENU = ToolDefinition(
    name="ver_cardapio_da_loja",
    description="Lista itens de um restaurante específico, opcionalmente filtrando por texto.",
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
