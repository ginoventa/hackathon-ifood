"""Carrinho e finalização do pedido (seções 1.5 e 2.5 da proposta).

Regra de segurança central: a LLM pode MONTAR o carrinho, mas nunca enviar
o pedido. O envio (``submitOrder``) só acontece pela rota HTTP chamada quando
o usuário clica em "Confirmar pedido" na tela de revisão.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from ..config import config
from ..errors import AppError, ValidationError
from ..ifood.client import get_ifood_client
from ..restrictions.analyzer import Verdict
from ..sessions import Session

# Tamanho máximo da observação enviada ao restaurante.
MAX_NOTE_LENGTH = 140


def _pick_number(source: Any, paths: list[str]) -> float | None:
    """Primeiro número encontrado entre vários caminhos possíveis do objeto."""
    for path in paths:
        value: Any = source
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, dict):
            value = value.get("value", value.get("amount"))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def normalize_cart(raw: dict) -> dict[str, Any]:
    """Converte a resposta de carrinho do MCP num formato estável para a interface.

    É tolerante a variações de nomes de campos entre versões do MCP.
    """
    cart = raw.get("cart") or raw.get("data") or raw or {}
    items = [
        {
            "cartItemId": item.get("cartItemId") or item.get("id"),
            "itemId": item.get("itemId") or item.get("catalogItemId"),
            "name": item.get("name") or item.get("itemName") or item.get("description") or "Item",
            "quantity": item.get("quantity") or 1,
            "unitPrice": _pick_number(item, ["unitPrice", "price"]),
            "totalPrice": _pick_number(item, ["totalPrice", "total", "subtotal"]),
            "customerNote": item.get("customerNote") or item.get("observation"),
            "options": [option.get("name") or option.get("optionName") or "Opção" for option in item.get("options") or []],
        }
        for item in cart.get("items") or cart.get("cartItems") or []
    ]
    totals = cart.get("totals") or cart.get("summary") or cart.get("prices") or cart
    subtotal = _pick_number(totals, ["subtotal", "itemsTotal", "subTotal", "itemsAmount"])
    merchant = cart.get("merchant") or {}
    return {
        "cartId": cart.get("cartId") or cart.get("id"),
        "appDeeplink": cart.get("appDeeplink") or raw.get("appDeeplink"),
        "merchantId": merchant.get("merchantId") or cart.get("merchantId"),
        "merchantName": merchant.get("merchantName") or cart.get("merchantName"),
        "items": items,
        "subtotal": subtotal if subtotal is not None else sum(item["totalPrice"] or 0 for item in items),
        "deliveryFee": _pick_number(totals, ["deliveryFee", "deliveryFeeAmount", "delivery"]),
        "discount": _pick_number(totals, ["discount", "discountAmount", "vouchersDiscount"]),
        "total": _pick_number(totals, ["total", "totalAmount", "orderTotal"]),
        "deliveryMethodId": (cart.get("deliveryMethod") or {}).get("deliveryMethodId"),
        "paymentMethodId": (cart.get("paymentMethod") or {}).get("paymentMethodId"),
    }


def _analysis_for(session: Session, item_id: str) -> dict | None:
    """Última análise do item, vinda do fluxo de restaurante ou do de mercado."""
    if item_id in session.analyses:
        return session.analyses[item_id]
    for plan in (session.market_plan or {}).get("merchants", []):
        for item in plan["items"]:
            if item["itemId"] == item_id:
                return item["analysis"]
    return None


def dietary_alerts_for(session: Session, item_ids: list[str]) -> list[dict]:
    """Alertas alimentares dos itens do carrinho (exigem ciência do usuário na revisão)."""
    alerts = []
    for item_id in item_ids:
        analysis = _analysis_for(session, item_id)
        if analysis is None:
            alerts.append({"itemId": item_id, "verdict": Verdict.INSUFFICIENT, "text": "Este item não foi analisado pelo Ailo."})
            continue
        if analysis["verdict"] != Verdict.NO_DECLARED_CONFLICT or analysis["missingInfo"]:
            # Explica só as restrições que pedem atenção; as demais ficam resumidas.
            concerns = [result for result in analysis["restrictions"] if result["verdict"] != Verdict.NO_DECLARED_CONFLICT]
            alerts.append({
                "itemId": item_id,
                "itemName": analysis["itemName"],
                "verdict": analysis["verdict"],
                "text": " ".join(result["explanation"] for result in concerns)
                if concerns else "Nenhum conflito nas informações disponíveis, mas faltam dados para confirmar.",
                "missingInfo": analysis["missingInfo"],
                "addOnsToAvoid": analysis["addOnsToAvoid"],
            })
    return alerts


def _require_own_cart(session: Session, cart_id: str) -> dict:
    """Garante que o carrinho foi criado nesta sessão (evita manipular carrinhos alheios)."""
    entry = session.carts.get(cart_id)
    if entry is None:
        raise ValidationError("Carrinho não encontrado nesta conversa.")
    return entry


async def create_cart(session: Session, merchant_id: str, items: list[dict]) -> dict:
    """Cria o carrinho no iFood. Bloqueia itens com CONFLITO declarado.

    Args:
        items: ``[{"itemId", "quantidade", "observacao"?, "opcoes"?: [{"optionId", "quantidade"?}]}]``.
    """
    if not (session.address or {}).get("addressId"):
        raise ValidationError("Escolha um endereço de entrega antes de montar o carrinho.")
    if not items:
        raise ValidationError("Informe ao menos um item para o carrinho.")

    # Trava determinística: nenhum item com conflito declarado entra no carrinho.
    if any((session.analyses.get(item["itemId"]) or {}).get("verdict") == Verdict.CONFLICT for item in items):
        raise ValidationError("Há itens incompatíveis com as suas restrições. Eles não podem ser adicionados ao carrinho.")

    cart_items = []
    for item in items:
        cart_item: dict[str, Any] = {"itemId": item["itemId"], "quantity": max(1, round(float(item.get("quantidade") or 1)))}
        if item.get("observacao"):
            cart_item["customerNote"] = str(item["observacao"])[:MAX_NOTE_LENGTH]
        if item.get("opcoes"):
            cart_item["options"] = [{"optionId": option["optionId"], "quantity": option.get("quantidade") or 1} for option in item["opcoes"]]
        cart_items.append(cart_item)

    raw = await get_ifood_client().call_tool(
        "createCart", {"merchantId": merchant_id, "addressId": session.address["addressId"], "items": cart_items},
    )
    cart = normalize_cart(raw)
    if not cart["cartId"]:
        raise AppError("O iFood não retornou o identificador do carrinho.", status=502, code="IFOOD_CARRINHO_INVALIDO")
    cart["merchantId"] = cart["merchantId"] or merchant_id

    item_ids = [item["itemId"] for item in items]
    session.carts[cart["cartId"]] = {"merchantId": cart["merchantId"], "itemIds": item_ids}
    return {**cart, "alerts": dietary_alerts_for(session, item_ids)}


async def get_cart_preview(session: Session, cart_id: str) -> dict:
    """Consulta somente os itens do carrinho e seu link oficial para o app iFood."""
    entry = _require_own_cart(session, cart_id)
    raw = await get_ifood_client().call_tool("getCart", {"cartId": cart_id})
    return {
        "cart": normalize_cart(raw),
        "alerts": dietary_alerts_for(session, entry["itemIds"]),
        "address": session.address,
    }


async def get_checkout_options(session: Session, cart_id: str) -> dict:
    """Dados da tela de revisão: carrinho, formas de entrega e de pagamento."""
    entry = _require_own_cart(session, cart_id)
    ifood = get_ifood_client()
    cart_raw, delivery_raw, payment_raw = await asyncio.gather(
        ifood.call_tool("getCart", {"cartId": cart_id}),
        ifood.call_tool("getCartDeliveryMethods", {"cartId": cart_id}),
        ifood.call_tool("listPaymentMethods", {"merchantId": entry["merchantId"]}),
    )

    delivery_methods = [
        {
            "deliveryMethodId": method.get("deliveryMethodId"),
            "mode": method.get("deliveryMethodMode") or method.get("mode"),
            "label": method.get("displayName") or ("Retirar no local" if method.get("deliveryMethodMode") == "TAKEOUT" else "Entrega"),
            "fee": method.get("promotionalFee", method.get("fee")),
            "estimatedMinutes": method.get("estimatedMinutes"),
            "timeSlots": [
                {"id": slot.get("timeSlotId") or slot.get("id"), "label": slot.get("displayName") or slot.get("label") or ""}
                for slot in method.get("timeSlots") or []
            ],
        }
        for method in delivery_raw.get("deliveryMethods") or delivery_raw.get("results") or []
    ]
    payment_methods = [
        {
            "paymentMethodId": method.get("paymentMethodId"),
            "kind": method.get("kind"),
            "label": method.get("displayName") or method.get("kind"),
            "cardTokenId": method.get("cardTokenId"),
        }
        for method in payment_raw.get("paymentMethods") or []
    ]

    return {
        "cart": normalize_cart(cart_raw),
        "alerts": dietary_alerts_for(session, entry["itemIds"]),
        "address": session.address,
        "deliveryMethods": delivery_methods,
        "paymentMethods": payment_methods,
        "submitEnabled": config.ifood.allow_submit_order,
    }


async def submit_order(session: Session, params: dict) -> dict:
    """Envia o pedido. Chamado SOMENTE pela rota HTTP de confirmação do usuário.

    ``params``: cartId, deliveryMethodId, timeSlotId?, paymentMethodId,
    cardTokenId?, document?, userConfirmed, alertsAcknowledged.
    """
    if not config.ifood.allow_submit_order:
        raise AppError("O envio de pedidos está desativado neste servidor (ALLOW_SUBMIT_ORDER=false).", status=403, code="PEDIDO_DESATIVADO")
    if params.get("userConfirmed") is not True:
        raise ValidationError("O pedido só é enviado com a sua confirmação explícita.")

    cart_id = params.get("cartId") or ""
    entry = _require_own_cart(session, cart_id)
    if dietary_alerts_for(session, entry["itemIds"]) and params.get("alertsAcknowledged") is not True:
        raise ValidationError("Leia e confirme os alertas alimentares antes de finalizar.")
    if not params.get("deliveryMethodId") or not params.get("paymentMethodId"):
        raise ValidationError("Escolha a forma de entrega e de pagamento.")

    ifood = get_ifood_client()
    delivery_args = {"cartId": cart_id, "deliveryMethodId": params["deliveryMethodId"]}
    if params.get("timeSlotId"):
        delivery_args["selectedTimeSlotId"] = params["timeSlotId"]
    await ifood.call_tool("setCartDelivery", delivery_args)

    payment_args = {"cartId": cart_id, "paymentMethodId": params["paymentMethodId"]}
    if params.get("cardTokenId"):
        payment_args["cardTokenId"] = params["cardTokenId"]
    await ifood.call_tool("setCartPayment", payment_args)

    submit_args: dict[str, Any] = {"cartId": cart_id, "userConsent": True}
    if params.get("document"):
        submit_args["document"] = re.sub(r"\D", "", str(params["document"]))
    result = await ifood.call_tool("submitOrder", submit_args)

    data = result.get("data") or {}
    order = {
        "orderId": result.get("orderId") or data.get("orderId"),
        "status": result.get("status") or data.get("status"),
        "message": result.get("message"),
        # Dados de pagamento (ex.: código Pix) quando o iFood os devolver.
        "payment": result.get("payment") or result.get("pix") or data.get("payment"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    session.orders.append(order)
    session.carts.pop(cart_id, None)
    return order


async def track_order(session: Session, order_id: str) -> dict:
    """Acompanha um pedido feito nesta sessão."""
    if not any(order["orderId"] == order_id for order in session.orders):
        raise ValidationError("Pedido não encontrado nesta conversa.")
    result = await get_ifood_client().call_tool("trackOrder", {"orderId": order_id})
    status = result.get("status") or result.get("currentStatus") or (result.get("data") or {}).get("status")
    # Segundo a documentação, o status vem como objeto { code, description }.
    if isinstance(status, dict):
        status = status.get("code") or status.get("description")
    return {"orderId": order_id, "status": status, "events": result.get("events") or result.get("statusEvents") or []}
