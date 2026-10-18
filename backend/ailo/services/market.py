"""Fluxo de mercado (seção 2 da proposta).

Valida a receita adaptada, busca os ingredientes nos mercados do iFood e
compara combinações de produtos e estabelecimentos.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from ..config import config
from ..errors import AppError, ValidationError
from ..restrictions.analyzer import KIND_MARKET, Verdict, analyze_product, analyze_recipe_ingredients
from ..restrictions.catalog import to_ifood_item_restrictions
from ..restrictions.text_matching import normalize_text
from ..sessions import Session
from .catalog import get_item_details, search_offers
from .labels import fetch_label
from .packaging import purchase_quantity

# Quantos resultados buscar por ingrediente.
RESULTS_PER_INGREDIENT = 10

# Quantos mercados entram na comparação final.
MERCHANTS_TO_COMPARE = 3

# Ordem de preferência entre pareceres (menor é melhor).
VERDICT_RANK = {
    Verdict.NO_DECLARED_CONFLICT: 0,
    Verdict.INSUFFICIENT: 1,
    Verdict.RISK: 2,
    Verdict.CONFLICT: 3,
}

# Palavras que não identificam o produto ("massa SEM glúten", "molho DE tomate").
NON_HEAD_WORDS = {"de", "da", "do", "com", "sem", "e", "para", "tipo", "zero", "light"}


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


def _stem(word: str) -> str:
    return re.sub(r"(es|s)$", "", word)


def _head_word(search_term: str) -> str:
    """Palavra principal do termo de busca ("queijo" em "queijo vegetal").

    Em português, o substantivo principal costuma vir primeiro.
    """
    return next((word for word in normalize_text(search_term).split() if len(word) > 2 and word not in NON_HEAD_WORDS), "")


# Produtos que não são comida, mesmo citando um ingrediente ("sabonete com óleo de abacate").
NON_FOOD_WORDS = {
    "sabonete", "shampoo", "xampu", "condicionador", "hidratante", "creme dental", "desodorante",
    "detergente", "amaciante", "sabao", "limpador", "desinfetante", "esponja", "racao", "petisco para caes",
    "vela", "perfume", "colonia", "repelente", "protetor solar", "maquiagem", "brinquedo", "fralda",
    "lenco umedecido", "papel higienico", "oleo corporal", "oleo capilar", "locao",
}

# A palavra principal precisa estar entre as primeiras palavras do nome do produto:
# "Leite Integral Italac" é leite; "Biscoito Rosquinha Sabor Leite" não é.
HEAD_WORD_WINDOW = 3

# Tipos de produto que, antes do ingrediente, indicam outro produto ("Pão de Queijo", "Creme de Leite").
PRODUCT_TYPE_WORDS = {
    "pao", "biscoito", "bolacha", "bolo", "salgadinho", "molho", "tempero", "sorvete", "chocolate", "bebida",
    "iogurte", "doce", "creme", "farofa", "mistura", "pasta", "sopa", "caldo", "achocolatado", "suco",
    "refrigerante", "barra", "cereal", "torrada", "wafer", "snack", "petisco", "sabor", "aroma", "essencia",
}


def _is_relevant(item: dict, search_term: str) -> bool:
    """O produto é mesmo o ingrediente buscado?

    Regras, todas sobre o nome do produto:
    - não pode ser um item que não é comida (sabonete, detergente...);
    - a palavra principal do termo ("leite", "oleo") deve estar entre as
      primeiras palavras do nome (a 1ª pode ser a marca);
    - "sabor leite" ou "aroma de queijo" não contam como o ingrediente.

    Evita trocar "queijo vegetal" por "bebida vegetal" só porque é mais barato.
    """
    name = normalize_text(item.get("itemName"))
    if any(f" {word} " in f" {name} " for word in NON_FOOD_WORDS):
        return False
    head = _head_word(search_term)
    if not head:
        return True
    words = [word for word in name.split() if word not in NON_HEAD_WORDS]
    positions = [index for index, word in enumerate(words) if _stem(word) == _stem(head)]
    if not positions or positions[0] >= HEAD_WORD_WINDOW:
        return False
    # O que vem antes do ingrediente pode ser a marca, mas não outro tipo de produto.
    return not any(_stem(word) in {_stem(kind) for kind in PRODUCT_TYPE_WORDS} for word in words[:positions[0]])


def register_recipe(session: Session, recipe: dict) -> dict[str, Any]:
    """Registra a receita da LLM aplicando a trava determinística nos ingredientes.

    Se algum ingrediente conflitar, a receita NÃO é aceita.

    Returns:
        ``{"accepted": bool, "recipe": dict, "conflicts": list}``.
    """
    ingredients = recipe.get("ingredientes")
    if not recipe.get("titulo") or not isinstance(ingredients, list) or not ingredients:
        raise ValidationError("A receita precisa de título e ingredientes.")

    checks = analyze_recipe_ingredients(ingredients, session.restrictions)
    conflicts = [check for check in checks if check["status"] == Verdict.CONFLICT]

    normalized = {
        "titulo": recipe["titulo"],
        "porcoes": recipe.get("porcoes"),
        "tempoMinutos": recipe.get("tempoMinutos"),
        "ingredientes": [
            {
                **ingredient,
                "quantidadeCompra": max(1, round(float(ingredient.get("quantidadeCompra") or 1))),
                "verificacao": check,
            }
            for ingredient, check in zip(ingredients, checks)
        ],
        "substituicoes": recipe.get("substituicoes") or [],
        "cuidados": recipe.get("cuidados") or [],
    }
    if not conflicts:
        session.recipe = normalized
        session.market_plan = None
    return {"accepted": not conflicts, "recipe": normalized, "conflicts": conflicts}


def _quick_analyze(session: Session, item: dict) -> dict:
    """Análise rápida de um resultado de busca, só pelo nome."""
    return analyze_product(
        {"itemId": item["itemId"], "itemName": item["itemName"], "itemDescription": "", "merchantName": item["merchantName"]},
        session.restrictions,
        kind=KIND_MARKET,
        declared_tags=session.declared_tags.get(item["itemId"], []),
    )


async def _safe_search(session: Session, query: str, refinements: dict) -> list[dict]:
    """Busca de mercado que não derruba a comparação inteira se uma consulta falhar."""
    try:
        result = await search_offers(
            session, query=query, merchant_type="GROCERIES", result_kind="ITEM",
            page_size=RESULTS_PER_INGREDIENT, refinements=refinements,
        )
        return result["items"]
    except AppError:
        return []


async def _search_ingredient(session: Session, ingredient: dict, merchant_id: str | None = None) -> list[dict]:
    """Busca um ingrediente; sem nenhum produto relevante, tenta só a palavra principal.

    Ex.: "óleo vegetal" traz sabonetes no iFood; "óleo" traz óleo de soja e de girassol.
    """
    query = ingredient.get("busca") or ingredient["nome"]
    found = await _search_ingredient_query(session, query, merchant_id)
    head = _head_word(query)
    if not found and head and head != normalize_text(query):
        found = await _search_ingredient_query(session, head, merchant_id)
    return found


async def _search_ingredient_query(session: Session, query: str, merchant_id: str | None = None) -> list[dict]:
    """Busca um ingrediente nos mercados.

    Faz, em paralelo, uma busca sem filtros e uma para CADA filtro de restrição
    do iFood (ex.: GLUTEN_FREE). Os filtros não são combinados numa única busca
    porque o iFood os aplica juntos (E lógico), o que esconderia produtos
    válidos, como carne moída para quem é celíaco e tem APLV.
    """
    # Com INCLUDE_CLOSED_STORES (testes), lojas fechadas também entram na comparação.
    base = {"sort": "PRICE", "onlyOpen": not config.include_closed_stores, **({"merchantId": merchant_id} if merchant_id else {})}
    tags = to_ifood_item_restrictions(session.restrictions)
    responses = await asyncio.gather(
        _safe_search(session, query, base),
        *[_safe_search(session, query, {**base, "itemRestrictions": [tag]}) for tag in tags],
    )

    # Remove duplicados mantendo a ordem de relevância da busca.
    unique: dict[str, dict] = {}
    for item in (item for items in responses for item in items):
        unique.setdefault(item["itemId"], item)

    return [
        {**item, "price": item.get("promotionalUnitPrice") or item.get("unitPrice") or 0, "analysis": _quick_analyze(session, item)}
        for item in unique.values()
        if (config.include_closed_stores or item.get("isOpen") is not False) and _is_relevant(item, query)
    ]


def _best_candidate(candidates: list[dict]) -> dict | None:
    """Parecer mais favorável, depois menor preço. Produtos com CONFLITO nunca são escolhidos."""
    allowed = [candidate for candidate in candidates if candidate["analysis"]["verdict"] != Verdict.CONFLICT]
    allowed.sort(key=lambda candidate: (VERDICT_RANK[candidate["analysis"]["verdict"]], candidate["price"]))
    return allowed[0] if allowed else None


def _build_merchant_plan(merchant: dict, ingredients: list[dict], candidates_by_ingredient: list[list[dict]]) -> dict:
    """Resumo de um mercado com o melhor produto para cada ingrediente."""
    items, missing = [], []
    for ingredient, candidates in zip(ingredients, candidates_by_ingredient):
        chosen = _best_candidate([candidate for candidate in candidates if candidate["merchantId"] == merchant["merchantId"]])
        if chosen is None:
            missing.append(ingredient["nome"])
            continue
        # Usa o tamanho publicado no nome da oferta ("Molho 340g").
        quantity = purchase_quantity(ingredient, chosen["itemName"])
        items.append({
            "ingrediente": ingredient["nome"],
            "quantidade": quantity,
            "itemEan": chosen.get("itemEan"),
            "itemId": chosen["itemId"],
            "itemName": chosen["itemName"],
            "imageUrl": chosen.get("imageUrl"),
            "unitPrice": chosen["price"],
            "totalPrice": _money(chosen["price"] * quantity),
            "verdict": chosen["analysis"]["verdict"],
            "analysis": chosen["analysis"],
        })

    return _with_totals({
        "merchantId": merchant["merchantId"],
        "merchantName": merchant["merchantName"],
        "rating": merchant.get("merchantRating"),
        "deliveryMinutes": merchant.get("deliveryMinutes"),
        "minimumOrderAmount": merchant.get("minimumOrderAmount"),
        "deliveryFee": merchant.get("deliveryFee") or 0,
        "totalIngredients": len(ingredients),
        "missing": missing,
        "items": items,
    })


def _simulate_label_check(item: dict) -> None:
    """Apresentação (SIMULATE_LABEL_CHECK): mostra o rótulo como verificado.

    A maioria dos anúncios não traz código de barras nem ingredientes, e a base
    aberta quase não tem produtos brasileiros; para a apresentação, itens sem
    conflito nem risco aparecem como "rótulo verificado". Conflitos e riscos
    reais nunca são escondidos, e o cartão avisa que a verificação é simulada.
    """
    analysis = item["analysis"]
    if item["verdict"] != Verdict.INSUFFICIENT:
        return
    item["verdict"] = Verdict.NO_DECLARED_CONFLICT
    item["labelVerified"] = True
    item["labelSimulated"] = True
    item["analysis"] = {**analysis, "verdict": Verdict.NO_DECLARED_CONFLICT, "canProceed": True, "missingInfo": [], "alternatives": [], "labelSimulated": True}


def _with_totals(plan: dict) -> dict:
    """Recalcula cobertura, subtotal, total e pedido mínimo de um plano."""
    plan["coverage"] = len(plan["items"])
    plan["subtotal"] = _money(sum(item["totalPrice"] for item in plan["items"]))
    plan["total"] = _money(plan["subtotal"] + plan["deliveryFee"])
    minimum = plan.get("minimumOrderAmount")
    plan["meetsMinimum"] = minimum is None or plan["subtotal"] >= minimum
    return plan


def _plan_order(plan: dict) -> tuple:
    """Mais ingredientes cobertos primeiro, depois menor custo total."""
    return (-plan["coverage"], plan["total"])


async def plan_grocery_shopping(session: Session) -> dict:
    """Busca e compara os ingredientes da receita atual nos mercados do iFood."""
    recipe = session.recipe
    if not recipe:
        raise ValidationError("Primeiro preciso montar a receita adaptada.")
    # Itens que a pessoa já tem em casa não entram na compra.
    ingredients = [ingredient for ingredient in recipe["ingredientes"] if not ingredient.get("jaTenhoEmCasa")]

    # 1. Busca geral de cada ingrediente, em paralelo.
    candidates_by_ingredient = list(await asyncio.gather(*[_search_ingredient(session, item) for item in ingredients]))

    # 2. Agrupa por mercado e escolhe os mais promissores.
    merchants: dict[str, dict] = {}
    for candidate in (candidate for group in candidates_by_ingredient for candidate in group):
        merchants[candidate["merchantId"]] = candidate
    plans = sorted(
        (_build_merchant_plan(merchant, ingredients, candidates_by_ingredient) for merchant in merchants.values()),
        key=_plan_order,
    )[:MERCHANTS_TO_COMPARE]

    # 3. Nos finalistas, procura especificamente os ingredientes que faltaram.
    for plan in plans:
        missing_indexes = [index for index, item in enumerate(ingredients) if item["nome"] in plan["missing"]]
        extra = await asyncio.gather(*[_search_ingredient(session, ingredients[index], plan["merchantId"]) for index in missing_indexes])
        for index, found in zip(missing_indexes, extra):
            candidates_by_ingredient[index].extend(found)
    plans = sorted(
        (_build_merchant_plan(merchants[plan["merchantId"]], ingredients, candidates_by_ingredient) for plan in plans),
        key=_plan_order,
    )

    # 4. Reanalisa os produtos do mercado recomendado com a descrição completa.
    #    Se a descrição revelar conflito, o produto sai do plano.
    recommended = plans[0] if plans else None
    if recommended:
        async def reanalyze(item: dict) -> None:
            try:
                details = await get_item_details(session, recommended["merchantId"], item["itemId"])
            except AppError:
                return  # Mantém a análise rápida (só pelo nome).
            # Produto industrializado: consulta o rótulo (alergênicos e "pode conter") pelo código de barras.
            label = await fetch_label(details.get("itemEan") or item.get("itemEan"), details.get("itemName") or item.get("itemName"))
            item["itemEan"] = details.get("itemEan") or item.get("itemEan")
            ingredient = next(entry for entry in ingredients if entry["nome"] == item["ingrediente"])
            package_text = label.get("quantity") if label and label.get("found") else None
            item["quantidade"] = purchase_quantity(ingredient, package_text or details.get("itemName") or item["itemName"])
            item["totalPrice"] = _money(item["unitPrice"] * item["quantidade"])
            item["analysis"] = analyze_product(
                details, session.restrictions, kind=KIND_MARKET,
                declared_tags=session.declared_tags.get(item["itemId"], []), label=label,
            )
            item["verdict"] = item["analysis"]["verdict"]
            if label and label.get("found"):
                item["labelUrl"] = label["url"]

        await asyncio.gather(*[reanalyze(item) for item in recommended["items"]])
        conflicting = [item for item in recommended["items"] if item["verdict"] == Verdict.CONFLICT]
        if conflicting:
            recommended["items"] = [item for item in recommended["items"] if item["verdict"] != Verdict.CONFLICT]
            recommended["missing"].extend(item["ingrediente"] for item in conflicting)
        _with_totals(recommended)

    if config.simulate_label_check:
        for merchant_plan in plans:
            for item in merchant_plan["items"]:
                _simulate_label_check(item)

    plan = {
        "recipeTitle": recipe["titulo"],
        "recommendedMerchantId": recommended["merchantId"] if recommended else None,
        "merchants": plans,
        "ingredientsWithoutOption": [
            item["nome"] for item in ingredients if all(item["nome"] in merchant_plan["missing"] for merchant_plan in plans)
        ],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    session.market_plan = plan
    return plan
