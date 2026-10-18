"""Regressões da sacola e do reaproveitamento do perfil alimentar."""

import pytest

from ailo.agent.tools import restrictions as restriction_tools
from ailo.agent.tools.market import REGISTER_RECIPE
from ailo.errors import ValidationError
from ailo.restrictions.catalog import resolve_restriction
from ailo.services.cart import get_cart_preview, normalize_cart
from ailo.sessions import Session


async def test_same_profile_restrictions_do_not_repeat_consent_card():
    session = Session(id="profile-repeat-test")
    session.restrictions = [resolve_restriction({"id": "doenca_celiaca"})]
    session.analyses["item"] = {"verdict": "RISCO"}
    output, card = await restriction_tools._register_restrictions(
        session, {"restricoes": [{"id": "doenca_celiaca"}]},
    )
    assert card is None
    assert output["restricoesAtivas"][0]["id"] == "doenca_celiaca"
    assert "item" in session.analyses


async def test_empty_registration_preserves_existing_restrictions():
    session = Session(id="profile-empty-test")
    session.restrictions = [resolve_restriction({"id": "doenca_celiaca"})]
    _, card = await restriction_tools._register_restrictions(session, {"restricoes": []})
    assert card is None
    assert session.restrictions[0].id == "doenca_celiaca"


async def test_saved_profile_does_not_request_consent_when_registered(monkeypatch):
    session = Session(id="profile-saved-test")
    celiac = resolve_restriction({"id": "doenca_celiaca"})
    monkeypatch.setattr(restriction_tools, "read_profile", lambda: {"consentAt": "2026-10-18"})
    monkeypatch.setattr(restriction_tools, "read_profile_restrictions", lambda: [celiac])
    output, card = await restriction_tools._register_restrictions(
        session, {"restricoes": [{"id": "doenca_celiaca"}]},
    )
    assert card is None
    assert output["jaSalvasNoPerfil"] is True
    assert session.restrictions == [celiac]


def test_cart_keeps_official_deeplink_and_item_list():
    raw = {"cart": {
        "cartId": "cart-test",
        "appDeeplink": "ifood://cart/cart-test",
        "items": [{"itemId": "rice", "name": "Arroz", "quantity": 2, "totalPrice": 20}],
    }}
    cart = normalize_cart(raw)
    assert cart["appDeeplink"] == "ifood://cart/cart-test"
    assert cart["items"][0]["quantity"] == 2
    assert cart["subtotal"] == 20


async def test_cart_preview_only_reads_cart_not_payment(fake_ifood):
    session = Session(id="cart-preview-test")
    merchant_id = "00000000-0000-4000-8000-000000000100"
    raw = await fake_ifood.call_tool("createCart", {
        "merchantId": merchant_id,
        "addressId": "test-address",
        "items": [{"itemId": "00000000-0000-4000-8000-000000000101", "quantity": 1}],
    })
    session.carts[raw["cartId"]] = {"merchantId": merchant_id, "itemIds": []}
    fake_ifood.calls.clear()
    response = await get_cart_preview(session, raw["cartId"])
    assert "cart" in response
    assert [name for name, _ in fake_ifood.calls] == ["getCart"]


async def test_cart_preview_rejects_another_session_cart(fake_ifood):
    with pytest.raises(ValidationError):
        await get_cart_preview(Session(id="other-session"), "unknown-cart")
    assert not fake_ifood.calls


def test_recipe_does_not_request_preparation_steps():
    assert "modoDePreparo" not in REGISTER_RECIPE.schema["properties"]
    assert "modoDePreparo" not in REGISTER_RECIPE.schema["required"]
