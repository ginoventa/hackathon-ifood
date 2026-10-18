"""Ferramentas do fluxo de mercado (seção 2): receita adaptada e busca de ingredientes."""

from __future__ import annotations

from ...errors import ValidationError
from ...restrictions.analyzer import Verdict
from ...services.market import plan_grocery_shopping, register_recipe
from .base import ToolDefinition


async def _register_recipe(session, args):
    if not session.restrictions:
        raise ValidationError("Registre as restrições do usuário antes de montar a receita.")
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
        "ingredientesParaConferirRotulo": [item["nome"] for item in recipe["ingredientes"] if item["verificacao"]["needsLabelCheck"]],
        "ingredientesComDuvida": [item["nome"] for item in recipe["ingredientes"] if item["verificacao"]["uncertain"]],
    }, {"type": "recipe", "data": recipe}


REGISTER_RECIPE = ToolDefinition(
    name="registrar_receita",
    description="Registra a receita adaptada às restrições ativas. O sistema verifica cada ingrediente e RECUSA a receita se algum conflitar.",
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
    description="Busca os ingredientes da receita atual nos mercados do iFood e compara preço, compatibilidade, entrega e pedido mínimo.",
    schema={"type": "object", "properties": {}},
    execute=_grocery_plan,
)
