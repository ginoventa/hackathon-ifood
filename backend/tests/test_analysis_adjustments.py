"""Regressões de declarações de ausência, embalagens e troca de produto."""

import pytest

from ailo.agent.tools import catalog as catalog_tools
from ailo.restrictions.analyzer import FindingKind, analyze_product
from ailo.restrictions.catalog import resolve_restriction
from ailo.services import analysis as analysis_service
from ailo.sessions import Session


@pytest.mark.parametrize("restriction_id,name,consults_menu", [
    # Intolerância e preferência: basta o item não ter a substância.
    ("intolerancia_lactose", "Burger sem lactose", False),
    ("vegetariano", "Burger vegetariano", False),
    # Alergia, doença celíaca e religiosas: traços importam (contato cruzado).
    ("alergia_frutos_mar", "Burger de grão-de-bico", True),
    ("religiao_sem_porco", "Burger sem porco", True),
])
async def test_menu_is_consulted_only_when_cross_contact_matters(monkeypatch, restriction_id, name, consults_menu):
    session = Session(id="test-absence-menu")
    session.restrictions = [resolve_restriction({"id": restriction_id})]
    calls = []

    async def item_details(*args):
        return {"itemId": "chosen", "merchantId": "store", "itemName": name}

    async def menu_items(*args):
        calls.append(args)
        return []

    monkeypatch.setattr(analysis_service, "get_item_details", item_details)
    monkeypatch.setattr(analysis_service, "get_menu_items", menu_items)
    result = await analysis_service.analyze_selected_item(session, "store", "chosen")
    assert len(calls) == (1 if consults_menu else 0)
    assert not any("restante do cardápio" in text for text in result["missingInfo"])


def test_celiac_and_vegetarian_cross_contact_only_for_gluten():
    product = {"itemId": "p", "itemName": "Risoto de cogumelos sem glúten", "itemDescription": "Arroz arbóreo, cogumelos e azeite."}
    menu = [{"itemId": "a", "itemName": "Bife à parmegiana", "itemDescription": "carne empanada com farinha de trigo"},
            {"itemId": "b", "itemName": "Picanha grelhada", "itemDescription": "carne bovina"}]
    restrictions = [resolve_restriction({"id": "doenca_celiaca"}), resolve_restriction({"id": "vegetariano"})]
    results = {r["restrictionId"]: r for r in analyze_product(product, restrictions, menu_items=menu)["restrictions"]}
    # Glúten: a parmegiana é possível fonte de contato cruzado.
    assert results["doenca_celiaca"]["crossContact"]["itemsWithSubstance"] == 1
    # Vegetariano: carne em outros pratos não importa.
    assert results["vegetariano"]["crossContact"] is None
    assert not any(f["kind"] == FindingKind.CROSS_CONTACT for f in results["vegetariano"]["findings"])


def test_packaged_item_does_not_infer_contact_from_store_preparation():
    product = {
        "itemId": "sealed", "itemName": "Biscoito sem glúten",
        "itemDescription": "Pacote lacrado. Loja utiliza o mesmo forno para outros itens.",
        "isPackaged": True,
    }
    result = analyze_product(
        product, [resolve_restriction({"id": "doenca_celiaca"})],
        menu_items=[{"itemId": "bread", "itemName": "Pão de trigo"}],
    )
    restriction = result["restrictions"][0]
    assert restriction["crossContact"] is None
    assert not any(finding["kind"] == FindingKind.CROSS_CONTACT for finding in restriction["findings"])
    assert not any("equipamentos compartilhados" in text for text in result["missingInfo"])


def test_packaged_item_keeps_explicit_manufacturer_warning():
    product = {
        "itemId": "sealed", "itemName": "Biscoito sem glúten",
        "itemDescription": "Pacote lacrado. Pode conter traços de leite.",
        "isPackaged": True,
    }
    result = analyze_product(product, [resolve_restriction({"id": "alergia_leite"})])
    assert any(
        finding["kind"] == FindingKind.CROSS_CONTACT and 'aviso "pode conter"' in finding["where"]
        for finding in result["restrictions"][0]["findings"]
    )


async def test_packaged_item_does_not_fetch_restaurant_menu(monkeypatch):
    session = Session(id="test-packaged-menu")
    session.restrictions = [resolve_restriction({"id": "doenca_celiaca"})]

    async def details(*args):
        return {"itemId": "sealed", "itemName": "Biscoito sem glúten", "sealedPackage": True}

    async def menu(*args):
        pytest.fail("Produto lacrado não deve consultar o preparo de outros itens da loja")

    monkeypatch.setattr(analysis_service, "get_item_details", details)
    monkeypatch.setattr(analysis_service, "get_menu_items", menu)
    await analysis_service.analyze_selected_item(session, "store", "sealed")


async def test_other_product_excludes_chosen_item_from_cards_and_model(monkeypatch):
    session = Session(id="test-other-product")
    session.excluded_items.add(("store", "chosen"))

    async def search(*args, **kwargs):
        return {"kind": "ITEM", "items": [
            {"merchantId": "store", "itemId": "chosen", "itemName": "Escolhido", "merchantName": "Loja", "promotionalUnitPrice": 10},
            {"merchantId": "store", "itemId": "other", "itemName": "Outro", "merchantName": "Loja", "promotionalUnitPrice": 12},
        ]}

    monkeypatch.setattr(catalog_tools, "search_offers", search)
    output, card = await catalog_tools._search_options(session, {"consulta": "burger"})
    assert [item["itemId"] for item in output["itens"]] == ["other"]
    assert [item["itemId"] for item in card["data"]["items"]] == ["other"]


@pytest.mark.parametrize("name,packaged", [
    ("Biscoito Bauducco Cookies Chocolate 100g", True),
    ("Vinho Tinto Casillero del Diablo 750ml", True),
    ("Coca-Cola Lata 350ml", True),
    ("Pizza Marguerita 200g", False),
    ("Lasanha à bolonhesa", False),
])
def test_sealed_industrialized_product_has_no_recipe_option(name, packaged):
    result = analyze_product({"itemId": "x", "itemName": name}, [resolve_restriction({"id": "doenca_celiaca"})])
    assert result["packaged"] is packaged
    if not result["canProceed"]:
        assert ("PREPARAR_EM_CASA" in result["alternatives"]) is not packaged
