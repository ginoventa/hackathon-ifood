from dataclasses import replace

import pytest

from ailo.services.labels import fetch_label as actual_fetch_label
from ailo.services import labels
from ailo.services.recipes import select_demo_recipe
from ailo.restrictions.catalog import resolve_restriction
from ailo.agent.tools import market
from ailo.sessions import Session


@pytest.mark.asyncio
async def test_demo_labels_never_call_network(monkeypatch):
    monkeypatch.setattr(labels, 'config', replace(labels.config, demo_mode=True))
    def forbidden(*args, **kwargs):
        raise AssertionError('A demo não deve acessar a rede')
    monkeypatch.setattr(labels.httpx, 'AsyncClient', forbidden)
    known = await actual_fetch_label('7896038350056')
    assert known['traces'] == ['en:soybeans']
    assert known['demo'] is True
    assert (await actual_fetch_label('1234567890123'))['found'] is False
    assert await actual_fetch_label(None) is None


def test_demo_recipe_conflicts_and_home_items():
    restrictions = [resolve_restriction({'id': 'doenca_celiaca'}), resolve_restriction({'id': 'alergia_leite'})]
    recipe = select_demo_recipe('quero lasanha', restrictions, ['Berinjela'])
    assert recipe['ingredientes'][0]['jaTenhoEmCasa'] is True
    assert select_demo_recipe('sushi', restrictions) is None
    custom = resolve_restriction({'id': 'personalizada', 'nome': 'Alergia a berinjela', 'tipo': 'ALERGIA', 'termos': ['berinjela']})
    assert select_demo_recipe('lasanha', [custom]) is None


@pytest.mark.asyncio
async def test_demo_tool_ignores_generated_ingredients(monkeypatch):
    monkeypatch.setattr(market, 'config', replace(market.config, demo_mode=True))
    session = Session(id='demo')
    session.restrictions = [resolve_restriction({'id': 'alergia_leite'})]
    result, card = await market._register_recipe(session, {'titulo': 'lasanha', 'ingredientes': [{'nome': 'leite'}]})
    assert result['aceita'] is True
    assert card['type'] == 'recipe'
    assert all(item['nome'] != 'leite' for item in session.recipe['ingredientes'])
    result, card = await market._register_recipe(session, {'titulo': 'sushi'})
    assert result['aceita'] is False
    assert card is None


@pytest.mark.parametrize('recipe_id', [option['id'] for option in market.demo_recipe_options()])
def test_catalog_adapts_combined_restrictions(recipe_id):
    from ailo.restrictions.analyzer import analyze_recipe_ingredients, Verdict
    restrictions = [resolve_restriction({'id': name}) for name in
                    ['doenca_celiaca', 'alergia_leite', 'alergia_ovo', 'alergia_castanhas', 'vegano']]
    recipe = select_demo_recipe(recipe_id, restrictions)
    if recipe_id in ('pao_queijo', 'pizza', 'coxinha', 'bolo_chocolate', 'cookie'):
        assert recipe is None
        return
    assert recipe is not None, recipe_id
    assert all(check['status'] != Verdict.CONFLICT for check in analyze_recipe_ingredients(recipe['ingredientes'], restrictions))
    assert all('alternativas' not in item for item in recipe['ingredientes'])
    assert all(swap['motivo'] for swap in recipe['substituicoes'])


def test_only_conflicting_ingredients_are_replaced():
    restriction = resolve_restriction({'id': 'alergia_leite'})
    original = select_demo_recipe('panqueca', [])
    adapted = select_demo_recipe('panqueca', [restriction])
    assert original['substituicoes'] == []
    assert any(item['nome'] == 'Ovo' for item in adapted['ingredientes'])
    assert any(item['nome'] == 'Farinha de trigo' for item in adapted['ingredientes'])
    assert [(swap['original'], swap['substituto']) for swap in adapted['substituicoes']] == [('Leite integral', 'Bebida de arroz sem glúten')]
    assert adapted['substituicoes'][0]['restricoes'] == [restriction.label]
    assert original['ingredientes'][1]['nome'] == 'Leite integral'


@pytest.mark.parametrize(('query', 'expected'), [
    ('quero macarrão ao pesto', 'pesto'),
    ('quero lasanha à bolonhesa', 'lasanha_bolonhesa'),
    ('pão de queijo', 'pao_queijo'),
    ('risoto de cogumelos', 'risoto'),
    ('bolo de chocolate sem leite', 'bolo_chocolate'),
])
def test_specific_dish_and_accents(query, expected):
    assert select_demo_recipe(query, [])['id'] == expected


def test_rejects_swap_that_conflicts_with_another_restriction():
    restrictions = [resolve_restriction({'id': 'alergia_leite'}), resolve_restriction({
        'id': 'personalizada', 'nome': 'Alergia a arroz', 'tipo': 'ALERGIA', 'termos': ['arroz']})]
    assert select_demo_recipe('panqueca', restrictions) is None


@pytest.mark.asyncio
async def test_adapted_recipe_explains_swaps_and_updates_home_items(monkeypatch):
    monkeypatch.setattr(market, 'config', replace(market.config, demo_mode=True))
    session = Session(id='demo-adapted')
    session.restrictions = [resolve_restriction({'id': 'alergia_leite'})]
    result, card = await market._register_recipe(session, {'titulo': 'pizza'})
    assert result['receitaId'] == 'pizza'
    assert result['substituicoes'] == card['data']['substituicoes']
    session.market_plan = {'old': True}
    result, card = await market._register_recipe(session, {'titulo': result['receitaId'], 'ingredientesEmCasa': ['Creme de mandioca']})
    assert session.market_plan is None
    assert any(item['jaTenhoEmCasa'] for item in card['data']['ingredientes'] if item['nome'] == 'Mandioca')


@pytest.mark.asyncio
async def test_real_labels_preserve_conflicts_traces_and_provenance(monkeypatch):
    from ailo.restrictions.analyzer import analyze_product, KIND_MARKET, Verdict, FindingKind
    monkeypatch.setattr(labels, 'config', replace(labels.config, demo_mode=True))
    async def verdict(ean, restriction_id):
        label = await actual_fetch_label(ean)
        analysis = analyze_product({'itemId': ean, 'itemName': label['productName']},
                                   [resolve_restriction({'id': restriction_id})], kind=KIND_MARKET, label=label)
        return label, analysis
    label, analysis = await verdict('7898215151982', 'alergia_leite')
    assert analysis['verdict'] == Verdict.CONFLICT
    assert label['dataKind'] == 'real_product_snapshot'
    assert label['sources'] and label['checkedAt']
    _, analysis = await verdict('7898215151982', 'intolerancia_lactose')
    assert analysis['verdict'] != Verdict.CONFLICT
    _, analysis = await verdict('7898955705049', 'alergia_castanhas')
    assert analysis['verdict'] == Verdict.CONFLICT
    _, analysis = await verdict('7896038350056', 'alergia_soja')
    assert analysis['verdict'] == Verdict.RISK
    _, analysis = await verdict('7896084700584', 'alergia_leite')
    assert analysis['verdict'] == Verdict.RISK
    _, analysis = await verdict('7896084700294', 'alergia_leite')
    assert all(finding['kind'] != FindingKind.LABEL_CLEAR for result in analysis['restrictions'] for finding in result['findings'])


def test_real_catalog_has_valid_eans_and_source_metadata():
    import json
    from pathlib import Path
    catalog = json.loads((Path(labels.__file__).resolve().parents[1] / 'data/demo_labels.json').read_text())
    assert len(catalog) == 16
    for ean, label in catalog.items():
        assert not ean.startswith('789000000')
        assert len(ean) == 13
        checksum = (10 - sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(ean[:-1])) % 10) % 10
        assert checksum == int(ean[-1]), ean
        assert label['ean'] == ean
        assert label['url'] in label['sources']
        assert label['brand'] and label['quantity'] and label['productName']


@pytest.mark.parametrize('recipe_id', ['panqueca', 'macarrao', 'lasanha'])
def test_featured_adapted_recipes_cover_packaged_ingredients(recipe_id):
    restrictions = [resolve_restriction({'id': name}) for name in ['doenca_celiaca', 'alergia_leite', 'alergia_ovo']]
    recipe = select_demo_recipe(recipe_id, restrictions)
    for item in recipe['ingredientes']:
        if item.get('industrializado'):
            assert item['referenciasDemo'], (recipe_id, item['nome'])
    assert not any(item['nome'] == 'Molho de tomate' for item in recipe['ingredientes'])


def test_home_preparations_expand_and_validate_components():
    restrictions = [resolve_restriction({'id': 'alergia_leite'})]
    recipe = select_demo_recipe('pizza', restrictions)
    assert any(item['nome'] == 'Mandioca' and item['preparacaoCaseira'] == 'Creme de mandioca' for item in recipe['ingredientes'])
    assert not any(item['nome'] == 'Creme de mandioca' for item in recipe['ingredientes'])
    restrictions.append(resolve_restriction({'id': 'personalizada', 'nome': 'Alergia a mandioca', 'tipo': 'ALERGIA', 'termos': ['mandioca']}))
    assert select_demo_recipe('pizza', restrictions) is None


def test_package_quantity_uses_selected_offer_not_reference():
    from ailo.services.packaging import purchase_quantity
    from ailo.services.market import _build_merchant_plan
    from ailo.restrictions.analyzer import Verdict
    ingredient = {'nome': 'Molho de tomate', 'quantidadeCompra': 1, 'quantidadeNecessaria': {'valor': 600, 'unidade': 'g'}}
    assert purchase_quantity(ingredient, '300 g') == 2
    assert purchase_quantity(ingredient, '1 kg') == 1
    assert purchase_quantity(ingredient, '250g') == 3
    merchant = {'merchantId': 'market', 'merchantName': 'Mercado'}
    candidate = {**merchant, 'itemId': 'item', 'itemName': 'Molho 250g', 'price': 4, 'analysis': {'verdict': Verdict.NO_DECLARED_CONFLICT}}
    plan = _build_merchant_plan(merchant, [ingredient], [[candidate]])
    assert plan['items'][0]['quantidade'] == 3
    assert plan['subtotal'] == 12
    candidate.update(itemEan='7897517206116', itemName='Molho de tomate bolonhesa vegano Fugini')
    plan = _build_merchant_plan(merchant, [ingredient], [[candidate]])
    assert plan['items'][0]['quantidade'] == 2
    assert plan['subtotal'] == 8



def test_labels_reject_substitute_with_soy_trace():
    restrictions = [resolve_restriction({'id': name}) for name in ['doenca_celiaca', 'alergia_soja']]
    # Rice flour is a reasonable culinary alternative here, but this exact
    # reference carries a soy trace warning and cannot be chosen automatically.
    assert select_demo_recipe('panqueca', restrictions) is None


def test_swaps_include_both_label_sources_and_composition():
    recipe = select_demo_recipe('panqueca', [resolve_restriction({'id': 'alergia_leite'})])
    swap = recipe['substituicoes'][0]
    original = swap['evidenciasOriginal']['rotulos'][0]
    substitute = swap['evidenciasSubstituto']['rotulos'][0]
    assert original['ean'] == '7898215151708'
    assert 'en:milk' in original['contem']
    assert substitute['ean'] == '7896084700294'
    assert original['fonte'] and substitute['fonte']
    assert original['ingredientes'] and substitute['ingredientes']
    assert substitute['parecer'] != 'CONFLITO'


def test_conflict_only_in_label_triggers_swap(monkeypatch):
    from ailo.services import recipes
    from copy import deepcopy
    catalog = recipes.load_demo_recipes()
    panqueca = next(item for item in catalog if item['id'] == 'panqueca')
    panqueca['variantes'][0]['ingredientes'][1]['nome'] = 'Bebida para receita'
    for variant in panqueca['variantes']:
        for swap in variant['substituicoes']:
            if swap['original'] == 'Leite integral':
                swap['original'] = 'Bebida para receita'
                swap['ingredienteOriginal']['nome'] = 'Bebida para receita'
    monkeypatch.setattr(recipes, 'load_demo_recipes', lambda: deepcopy(catalog))
    recipe = recipes.select_demo_recipe('panqueca', [resolve_restriction({'id': 'alergia_leite'})])
    assert recipe['substituicoes'][0]['original'] == 'Bebida para receita'
    assert recipe['substituicoes'][0]['evidenciasOriginal']['parecer'] == 'CONFLITO'


def test_one_conflicting_reference_does_not_disqualify_other_reference():
    from ailo.services.recipes import assess_ingredient
    from ailo.services.packaging import load_local_labels
    result = assess_ingredient({'nome': 'Bebida vegetal', 'produtosReferencia': ['7898955705049', '7896084700294']},
                              [resolve_restriction({'id': 'alergia_castanhas'})], load_local_labels())
    assert result['eansElegiveis'] == ['7896084700294']
    assert result['parecer'] != 'CONFLITO'


def test_demo_selects_complete_stored_variant():
    from ailo.services.recipes import load_demo_recipes
    base = next(recipe for recipe in load_demo_recipes() if recipe['id'] == 'panqueca')
    for ids in ([], ['alergia_leite'], ['alergia_leite', 'doenca_celiaca', 'alergia_ovo']):
        selected = select_demo_recipe('panqueca', [resolve_restriction({'id': key}) for key in ids])
        stored = next(variant for variant in base['variantes'] if variant['id'] == selected['varianteId'])
        assert [(item['nome'], item['quantidade']) for item in selected['ingredientes']] == [(item['nome'], item['quantidade']) for item in stored['ingredientes']]
        assert not any('alternativas' in item for item in stored['ingredientes'])
    assert select_demo_recipe('panqueca', [])['varianteId'] == 'base'
    assert select_demo_recipe('panqueca', [resolve_restriction({'id': 'alergia_leite'})])['varianteId'] == 'sem_leite'


@pytest.mark.asyncio
async def test_non_demo_accepts_agent_recipe_without_local_selection(monkeypatch):
    monkeypatch.setattr(market, 'config', replace(market.config, demo_mode=False))
    def forbidden(*args, **kwargs):
        raise AssertionError('Fluxo real não pode selecionar receita mockada')
    monkeypatch.setattr(market, 'select_demo_recipe', forbidden)
    session = Session(id='real-recipe')
    session.restrictions = [resolve_restriction({'id': 'alergia_leite'})]
    result, card = await market._register_recipe(session, {
        'titulo': 'Salada sugerida pelo agente',
        'ingredientes': [{'nome': 'Tomate', 'quantidade': '2 unidades', 'busca': 'tomate', 'quantidadeCompra': 1}],
    })
    assert result['aceita'] is True
    assert card['data']['titulo'] == 'Salada sugerida pelo agente'
    assert card['data'].get('varianteId') is None
