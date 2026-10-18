"""Ferramentas de carrinho.

A LLM pode montar o carrinho, mas o pedido só é enviado quando o usuário
confirma na tela de revisão (rota HTTP própria).
"""

from __future__ import annotations

from ...errors import ValidationError
from ...services.cart import create_cart
from .base import ToolDefinition


def _cart_output(cart: dict) -> dict:
    return {
        "carrinhoCriado": True,
        "loja": cart["merchantName"],
        "itens": [f"{item['quantity']}x {item['name']}" for item in cart["items"]],
        "total": cart["total"] if cart["total"] is not None else cart["subtotal"],
        "alertasAlimentares": len(cart["alerts"]),
        "proximoPasso": "O usuário deve revisar e confirmar o pedido na tela de revisão.",
    }


async def _build_cart(session, args):
    cart = await create_cart(session, args["merchantId"], args.get("itens") or [])
    return _cart_output(cart), {"type": "cart", "data": cart}


BUILD_CART = ToolDefinition(
    name="montar_carrinho",
    description="Cria o carrinho no iFood com itens de UM estabelecimento. Não envia o pedido.",
    schema={
        "type": "object",
        "properties": {
            "merchantId": {"type": "string"},
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "itemId": {"type": "string"},
                        "quantidade": {"type": "integer"},
                        "observacao": {"type": "string", "description": "Ex.: avisar a alergia ao restaurante."},
                        "opcoes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"optionId": {"type": "string"}, "quantidade": {"type": "integer"}},
                                "required": ["optionId"],
                            },
                        },
                    },
                    "required": ["itemId", "quantidade"],
                },
            },
        },
        "required": ["merchantId", "itens"],
    },
    execute=_build_cart,
)


async def _build_grocery_cart(session, args):
    merchant_id = args["merchantId"]
    plan = next((item for item in (session.market_plan or {}).get("merchants", []) if item["merchantId"] == merchant_id), None)
    if not plan or not plan["items"]:
        raise ValidationError("Este mercado não está na última comparação. Busque os ingredientes novamente.")
    cart = await create_cart(session, merchant_id, [{"itemId": item["itemId"], "quantidade": item["quantidade"]} for item in plan["items"]])
    return _cart_output(cart), {"type": "cart", "data": cart}


BUILD_GROCERY_CART = ToolDefinition(
    name="montar_carrinho_do_mercado",
    description="Cria o carrinho com os produtos escolhidos para a receita no mercado indicado (da última comparação).",
    schema={"type": "object", "properties": {"merchantId": {"type": "string"}}, "required": ["merchantId"]},
    execute=_build_grocery_cart,
)
