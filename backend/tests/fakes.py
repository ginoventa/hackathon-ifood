"""Dublês de teste: cliente falso do iFood e modelo de chat com roteiro.

Usados SOMENTE nos testes automatizados. O app em execução sempre fala com o
MCP real do iFood.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ailo.errors import IfoodToolError
from ailo.restrictions.text_matching import normalize_text

CATALOG = json.loads((Path(__file__).parent / "fixtures" / "ifood_catalog.json").read_text(encoding="utf-8"))

STOP_WORDS = {"de", "da", "do", "das", "dos", "com", "sem", "e", "para", "a", "o", "em", "kg", "g", "ml", "l"}


def _stem(word: str) -> str:
    return word[:-2] if len(word) > 3 and word.endswith("es") else (word[:-1] if len(word) > 3 and word.endswith("s") else word)


def _relevance(query: str, text: str) -> float:
    """Fração das palavras da busca presentes no texto."""
    words = [_stem(word) for word in normalize_text(query).split() if word not in STOP_WORDS]
    haystack = {_stem(word) for word in normalize_text(text).split()}
    return sum(word in haystack for word in words) / len(words) if words else 1.0


def _merchant_summary(merchant: dict) -> dict:
    return {
        "deliveryMethod": {
            "deliveryMethodId": "DEFAULT", "deliveryMethodMode": "DELIVERY",
            "estimatedMinutes": merchant["estimatedMinutes"], "fee": merchant["deliveryFee"], "promotionalFee": merchant["deliveryFee"],
        },
        "isOpen": True,
        "merchantId": merchant["merchantId"],
        "merchantLogoUrl": merchant["logo"],
        "merchantName": merchant["merchantName"],
        "minimumOrderAmount": merchant["minimumOrderAmount"],
        "reviewRating": merchant["reviewRating"],
        "straightLineDistanceKm": merchant["straightLineDistanceKm"],
    }


def _paginate(results: list, page_size: Any, token: str | None) -> dict:
    size = min(max(int(page_size or 10), 1), 25)
    offset = int(base64.b64decode(token).decode()) if token else 0
    page = results[offset:offset + size]
    has_more = offset + size < len(results)
    payload = {"results": page, "hasMore": has_more}
    if has_more:
        payload["nextPageToken"] = base64.b64encode(str(offset + size).encode()).decode()
    return payload


class FakeIfoodClient:
    """Imita as ferramentas do MCP do iFood com um catálogo fixo (formatos reais)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._carts: dict[str, dict] = {}
        self._orders: dict[str, dict] = {}

    async def is_authenticated(self) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        self.calls.append((name, args))
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise IfoodToolError(name, "ferramenta não disponível no cliente falso.")
        return handler(args)

    # --------------------------------------------------------------- busca

    def _filter(self, *, query="", merchant_type=None, result_kind="MERCHANT", refinements=None) -> list[dict]:
        refinements = refinements or {}
        tags = refinements.get("itemRestrictions") or []
        found = []
        for merchant in CATALOG["merchants"]:
            if merchant_type and merchant["merchantType"] != merchant_type:
                continue
            if refinements.get("merchantId") and merchant["merchantId"] != refinements["merchantId"]:
                continue
            for item in merchant["items"]:
                score = _relevance(query, f"{item['itemName']} {item.get('itemDescription', '')}") if query else 1.0
                minimum = 0.6 if query and len(normalize_text(query).split()) > 2 else 1.0
                if score >= minimum and all(tag in item.get("tags", []) for tag in tags):
                    found.append((score, merchant, item))
        found.sort(key=lambda entry: -entry[0])

        if result_kind == "ITEM":
            results = [
                {
                    "itemId": item["itemId"], "itemImageUrl": item.get("image", merchant["logo"]), "itemName": item["itemName"],
                    "merchant": _merchant_summary(merchant), "unitPrice": item["unitPrice"],
                    "promotionalUnitPrice": item.get("promotionalUnitPrice", item["unitPrice"]),
                }
                for _, merchant, item in found
            ]
            if refinements.get("sort") == "PRICE":
                results.sort(key=lambda result: result["promotionalUnitPrice"])
            return results
        unique = {}
        for _, merchant, _item in found:
            unique.setdefault(merchant["merchantId"], _merchant_summary(merchant))
        return list(unique.values())

    def _merchant(self, merchant_id: str) -> dict:
        for merchant in CATALOG["merchants"]:
            if merchant["merchantId"] == merchant_id:
                return merchant
        raise IfoodToolError("getMerchant", "estabelecimento não encontrado.")

    def _item(self, merchant_id: str, item_id: str) -> tuple[dict, dict]:
        merchant = self._merchant(merchant_id)
        for item in merchant["items"]:
            if item["itemId"] == item_id:
                return merchant, item
        raise IfoodToolError("getItem", "item não encontrado.")

    def _tool_getUser(self, _args):
        return {"success": True, "data": CATALOG["user"]}

    def _tool_listAddresses(self, _args):
        return {"results": CATALOG["addresses"]}

    def _tool_searchOffers(self, args):
        results = self._filter(query=args["query"], merchant_type=args.get("merchantType"), result_kind=args.get("resultKind", "MERCHANT"), refinements=args.get("refinements"))
        return _paginate(results, args.get("pageSize"), args.get("nextPageToken"))

    def _tool_browseOffers(self, args):
        results = self._filter(merchant_type=args.get("merchantType"), result_kind=args.get("resultKind", "MERCHANT"), refinements=args.get("refinements"))
        return _paginate(results, args.get("pageSize"), args.get("nextPageToken"))

    def _tool_getItem(self, args):
        merchant, item = self._item(args["merchantId"], args["itemId"])
        return {
            "itemId": item["itemId"], "itemName": item["itemName"], "itemDescription": item.get("itemDescription", ""),
            "itemImageUrl": item.get("image", merchant["logo"]), "merchantId": merchant["merchantId"],
            "merchantName": merchant["merchantName"], "optionGroups": item.get("optionGroups", []),
            "unitPrice": item["unitPrice"], "promotionalUnitPrice": item.get("promotionalUnitPrice", item["unitPrice"]),
        }

    # ------------------------------------------------------------- carrinho

    def _cart_view(self, cart: dict) -> dict:
        merchant = self._merchant(cart["merchantId"])
        items = []
        for entry in cart["items"]:
            _, item = self._item(cart["merchantId"], entry["itemId"])
            price = item.get("promotionalUnitPrice", item["unitPrice"])
            items.append({
                "cartItemId": entry["cartItemId"], "itemId": item["itemId"], "name": item["itemName"],
                "quantity": entry["quantity"], "unitPrice": price, "totalPrice": round(price * entry["quantity"], 2), "options": [],
            })
        subtotal = round(sum(item["totalPrice"] for item in items), 2)
        fee = 0 if cart.get("deliveryMethodId") == "TAKEOUT" else merchant["deliveryFee"]
        return {
            "cartId": cart["cartId"], "merchant": {"merchantId": merchant["merchantId"], "merchantName": merchant["merchantName"]},
            "items": items, "totals": {"subtotal": subtotal, "deliveryFee": fee, "total": round(subtotal + fee, 2)},
        }

    def _tool_createCart(self, args):
        cart = {
            "cartId": str(uuid.uuid4()), "merchantId": args["merchantId"], "addressId": args["addressId"],
            "items": [{**item, "cartItemId": str(uuid.uuid4())} for item in args["items"]],
        }
        self._carts[cart["cartId"]] = cart
        return self._cart_view(cart)

    def _tool_getCart(self, args):
        return self._cart_view(self._carts[args["cartId"]])

    def _tool_getCartDeliveryMethods(self, args):
        merchant = self._merchant(self._carts[args["cartId"]]["merchantId"])
        return {"deliveryMethods": [
            {"deliveryMethodId": "DEFAULT", "deliveryMethodMode": "DELIVERY", "estimatedMinutes": merchant["estimatedMinutes"], "fee": merchant["deliveryFee"]},
            {"deliveryMethodId": "TAKEOUT", "deliveryMethodMode": "TAKEOUT", "estimatedMinutes": {"min": 20, "max": 30}, "fee": 0},
        ]}

    def _tool_listPaymentMethods(self, _args):
        return {"paymentMethods": CATALOG["paymentMethods"]}

    def _tool_setCartDelivery(self, args):
        self._carts[args["cartId"]]["deliveryMethodId"] = args["deliveryMethodId"]
        return self._cart_view(self._carts[args["cartId"]])

    def _tool_setCartPayment(self, args):
        self._carts[args["cartId"]]["paymentMethodId"] = args["paymentMethodId"]
        return self._cart_view(self._carts[args["cartId"]])

    def _tool_submitOrder(self, args):
        if args.get("userConsent") is not True:
            raise IfoodToolError("submitOrder", "sem consentimento.")
        order_id = str(uuid.uuid4())
        self._orders[order_id] = self._carts.pop(args["cartId"])
        return {"orderId": order_id, "status": "PLACED"}

    def _tool_trackOrder(self, args):
        return {"orderId": args["orderId"], "status": {"code": "CONFIRMED", "description": "Confirmado"}, "events": []}


class ScriptedChatModel(BaseChatModel):
    """Modelo de chat falso compatível com o LangChain.

    Cada chamada devolve o próximo passo do roteiro:
    ``{"call": (nome, argumentos)}`` pede uma ferramenta; ``{"text": "..."}`` responde.
    """

    steps: list[dict]
    index: int = 0
    received: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-test-model"

    def bind_tools(self, tools, **kwargs):
        """O agente associa as ferramentas ao modelo; o roteiro já sabe quais chamar."""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.received.append(list(messages))
        if self.index >= len(self.steps):
            raise RuntimeError("O roteiro do modelo falso acabou.")
        step = self.steps[self.index]
        self.index += 1
        if "text" in step:
            message = AIMessage(content=step["text"])
        else:
            name, args = step["call"]
            message = AIMessage(content="", tool_calls=[{"id": f"call-{self.index}", "name": name, "args": args, "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    def last_tool_output(self) -> dict:
        """Conteúdo (já como objeto) da última resposta de ferramenta enviada ao modelo."""
        tool_message = next(message for message in reversed(self.received[-1]) if isinstance(message, ToolMessage))
        return json.loads(tool_message.content)
