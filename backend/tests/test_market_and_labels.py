"""Testes do fluxo de mercado e da consulta de rótulos (sem rede)."""

import pytest

from ailo.agent.tools import market
from ailo.restrictions.analyzer import Verdict
from ailo.restrictions.catalog import resolve_restriction
from ailo.services import labels
from ailo.services.labels import fetch_label as actual_fetch_label
from ailo.sessions import Session


@pytest.mark.asyncio
async def test_label_without_ean_is_searched_by_name(monkeypatch):
    searched = []

    async def by_name(name):
        searched.append(name)
        return {'found': False, 'ean': None}

    monkeypatch.setattr(labels, '_fetch_label_by_name', by_name)
    assert await actual_fetch_label(None, 'Farinha de arroz Urbano 1 kg') == {'found': False, 'ean': None}
    assert searched == ['Farinha de arroz Urbano 1 kg']
    # Sem EAN e sem nome, não há o que consultar.
    assert await actual_fetch_label(None) is None


def test_label_by_name_requires_same_brand():
    hits = [
        {'code': '7896016500268', 'product_name': 'Polvilho Azedo'},
        {'code': '12212781', 'product_name': 'Biscoito oreo', 'brands': ['Oreo']},
    ]
    assert labels._best_name_match('Polvilho Azedo Amafil Pacote 500g', hits) is None
    assert labels._best_name_match('Biscoito Recheado Oreo 90g', hits) == '12212781'


def test_package_quantity_uses_size_published_in_offer_name():
    from ailo.services.market import _build_merchant_plan
    from ailo.services.packaging import purchase_quantity

    ingredient = {'nome': 'Molho de tomate', 'quantidadeCompra': 1, 'quantidadeNecessaria': {'valor': 600, 'unidade': 'g'}}
    assert purchase_quantity(ingredient, '300 g') == 2
    assert purchase_quantity(ingredient, '1 kg') == 1
    assert purchase_quantity(ingredient, '250g') == 3
    merchant = {'merchantId': 'market', 'merchantName': 'Mercado'}
    candidate = {**merchant, 'itemId': 'item', 'itemName': 'Molho 250g', 'price': 4, 'analysis': {'verdict': Verdict.NO_DECLARED_CONFLICT}}
    plan = _build_merchant_plan(merchant, [ingredient], [[candidate]])
    assert plan['items'][0]['quantidade'] == 3
    assert plan['subtotal'] == 12


@pytest.mark.asyncio
async def test_agent_recipe_is_registered_with_its_swaps():
    session = Session(id='real-recipe')
    session.restrictions = [resolve_restriction({'id': 'doenca_celiaca'})]
    result, card = await market._register_recipe(session, {
        'titulo': 'Pizza sem glúten',
        'ingredientes': [{'nome': 'Farinha de arroz', 'quantidade': '200 g', 'busca': 'farinha de arroz', 'quantidadeCompra': 1}],
        'substituicoes': [{'original': 'Farinha de trigo', 'substituto': 'Farinha de arroz', 'motivo': 'Sem glúten.'}],
    })
    assert result['aceita'] is True
    assert card['data']['titulo'] == 'Pizza sem glúten'
    assert result['substituicoes'] == [{'original': 'Farinha de trigo', 'substituto': 'Farinha de arroz', 'motivo': 'Sem glúten.'}]


def test_market_shows_insufficient_items_as_verified_but_keeps_risks():
    from ailo.services.market import _simulate_label_check

    insufficient = {'verdict': Verdict.INSUFFICIENT, 'analysis': {'verdict': Verdict.INSUFFICIENT, 'missingInfo': ['x']}}
    risky = {'verdict': Verdict.RISK, 'analysis': {'verdict': Verdict.RISK, 'missingInfo': ['x']}}
    _simulate_label_check(insufficient)
    _simulate_label_check(risky)
    assert insufficient['labelVerified'] and insufficient['analysis']['verdict'] == Verdict.NO_DECLARED_CONFLICT
    assert risky['verdict'] == Verdict.RISK and 'labelVerified' not in risky
