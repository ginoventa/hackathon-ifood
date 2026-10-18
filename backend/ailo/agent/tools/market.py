"""Ferramentas do fluxo de mercado (seção 2): receita adaptada e busca de ingredientes."""

from __future__ import annotations

from dataclasses import replace

from ...config import config
from ...services.recipes import demo_recipe_options, select_demo_recipe
from ...errors import ValidationError
from ...restrictions.analyzer import Verdict
from ...services.market import plan_grocery_shopping, register_recipe
from ..system_prompt import (
    BUSCAR_INGREDIENTES_NO_MERCADO_PROMPT,
    REGISTRAR_RECEITA_PROMPT,
)
from .base import ToolDefinition


async def _register_recipe(session, args):
    if not session.restrictions:
        raise ValidationError("Registre as restrições do usuário antes de montar a receita.")
    if config.demo_mode:
        recipe = select_demo_recipe(args["titulo"], session.restrictions, args.get("ingredientesEmCasa", []))
        if recipe is None:
            return {"aceita": False, "motivo": "Não há receita cadastrada com substituições e produtos de referência sem conflito ou aviso de risco para esse pedido. Não gere ingredientes. Ofereça outro prato do catálogo.", "pratosDisponiveis": [option for option in demo_recipe_options() if select_demo_recipe(option["id"], session.restrictions) is not None]}, None
        args = recipe
    result = register_recipe(session, args)
    recipe = result["recipe"]

    if not result["accepted"]:
        # A LLM recebe o motivo e deve corrigir a receita; nada é mostrado ao usuário.
        return {
            "aceita": False,
            "motivo": "Ingredientes incompatíveis com as restrições. Substitua-os e chame registrar_receita novamente.",
            "conflitos": [
                {"ingrediente": conflict["nome"], "restricoes": [f"{item['label']}: {', '.join(item['terms'])}" for item in conflict["conflicts"]]}
                for conflict in result["conflicts"]
            ],
        }, None

    return {
        "aceita": True,
        "receitaId": recipe.get("id"),
        "varianteId": recipe.get("varianteId"),
        "ingredientes": [{"nome": item["nome"], "quantidade": item["quantidade"], "referenciasDemo": item.get("referenciasDemo", []), "analiseReferencias": item.get("analiseReferencias"), "jaTenhoEmCasa": item.get("jaTenhoEmCasa", False)} for item in recipe["ingredientes"]],
        "origem": recipe.get("origem"),
        "substituicoes": recipe["substituicoes"],
        "ingredientesParaConferirRotulo": [item["nome"] for item in recipe["ingredientes"] if item["verificacao"]["needsLabelCheck"]],
        "ingredientesComDuvida": [item["nome"] for item in recipe["ingredientes"] if item["verificacao"]["uncertain"]],
    }, {"type": "recipe", "data": recipe}


REGISTER_RECIPE = ToolDefinition(
    name="registrar_receita",
    description=REGISTRAR_RECEITA_PROMPT,
    schema={
        "type": "object",
        "properties": {
            "titulo": {"type": "string"},
            "porcoes": {"type": "integer"},
            "tempoMinutos": {"type": "integer"},
            "ingredientes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string", "description": 'Ex.: "Massa para lasanha sem glúten".'},
                        "quantidade": {"type": "string", "description": 'Quantidade da receita, ex.: "250 g".'},
                        "busca": {"type": "string", "description": "Termo curto para buscar no mercado."},
                        "quantidadeCompra": {"type": "integer", "description": "Embalagens/unidades a comprar."},
                        "industrializado": {"type": "boolean", "description": "true se o rótulo precisa ser conferido."},
                        "jaTenhoEmCasa": {"type": "boolean"},
                    },
                    "required": ["nome", "quantidade", "busca", "quantidadeCompra"],
                },
            },
            "substituicoes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"original": {"type": "string"}, "substituto": {"type": "string"}, "motivo": {"type": "string"}},
                    "required": ["original", "substituto"],
                },
            },
            "cuidados": {"type": "array", "items": {"type": "string"}, "description": "Rótulos, contato cruzado na cozinha, utensílios."},
        },
        "required": ["titulo", "ingredientes"],
    },
    execute=_register_recipe,
)


async def _grocery_plan(session, _args):
    plan = await plan_grocery_shopping(session)
    merchants = plan["merchants"]
    best = merchants[0] if merchants else None
    return {
        "mercadoRecomendado": best and {
            "merchantId": best["merchantId"],
            "nome": best["merchantName"],
            "cobertura": f"{best['coverage']}/{best['totalIngredients']}",
            "total": best["total"],
            "atingePedidoMinimo": best["meetsMinimum"],
            "produtosParaConferirRotulo": [item["itemName"] for item in best["items"] if item["verdict"] != Verdict.NO_DECLARED_CONFLICT],
        },
        "alternativas": [
            {"merchantId": item["merchantId"], "nome": item["merchantName"], "cobertura": f"{item['coverage']}/{item['totalIngredients']}", "total": item["total"]}
            for item in merchants[1:]
        ],
        "semOpcaoEmNenhumMercado": plan["ingredientsWithoutOption"],
    }, {"type": "market", "data": plan}


GROCERY_PLAN = ToolDefinition(
    name="buscar_ingredientes_no_mercado",
    description=BUSCAR_INGREDIENTES_NO_MERCADO_PROMPT,
    schema={"type": "object", "properties": {}},
    execute=_grocery_plan,
)


if config.demo_mode:
    REGISTER_RECIPE = replace(REGISTER_RECIPE, schema={
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "Prato solicitado ou id do catálogo: " + ", ".join(option["id"] for option in demo_recipe_options()) + ". Para atualizar itens em casa, reutilize receitaId retornado."},
            "ingredientesEmCasa": {"type": "array", "items": {"type": "string"}, "description": "Lista completa dos nomes dos ingredientes que a pessoa já possui, conforme a receita retornada."},
        },
        "required": ["titulo"],
    })
