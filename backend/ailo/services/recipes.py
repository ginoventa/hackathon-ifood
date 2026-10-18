"""Receitas e substituições cadastradas para o pitch, sem geração por LLM."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .packaging import load_local_labels, purchase_quantity

from ..restrictions.text_matching import normalize_text
from ..restrictions.analyzer import analyze_recipe_ingredients, analyze_product, KIND_MARKET, Verdict, VERDICT_SEVERITY

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data/demo_recipes.json'
NUTRITION_PATH = Path(__file__).resolve().parents[1] / 'data/nutrition_reference.json'


def load_demo_recipes():
    return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))


def demo_recipe_options():
    return [{'id': recipe['id'], 'titulo': recipe['titulo']} for recipe in load_demo_recipes()]


def load_nutrition_reference():
    return json.loads(NUTRITION_PATH.read_text(encoding='utf-8'))


def ingredient_profile(ingredient, labels, nutrition_reference):
    """Composição e tabela nutricional (por 100 g) de um ingrediente da troca.

    Prioriza o rótulo de referência (EAN); sem tabela no rótulo, usa a tabela
    aproximada de referência (TACO). Serve de base para a IA explicar a troca.
    """
    label = next((labels[ean] for ean in ingredient.get('produtosReferencia', []) if ean in labels), None)
    composition = (label or {}).get('ingredients') or ', '.join(
        component['nome'] for component in ingredient.get('componentes', [])
    ) or None
    nutrition, source = None, None
    if label and label.get('nutricaoPor100g'):
        nutrition, source = label['nutricaoPor100g'], f"Rótulo: {label['productName']}"
    elif normalize_text(ingredient['nome']) in nutrition_reference:
        nutrition, source = nutrition_reference[normalize_text(ingredient['nome'])], nutrition_reference['_fonte']
    return {
        'nome': ingredient['nome'],
        'produto': (label or {}).get('productName'),
        'produtoFicticio': (label or {}).get('dataKind') == 'mock',
        'composicao': composition,
        'tabelaNutricionalPor100g': nutrition,
        'fonteNutricional': source,
    }


def _matches(query, term):
    return re.search(r'(?<!\w)' + re.escape(normalize_text(term)) + r'(?!\w)', query) is not None


def assess_ingredient(ingredient, restrictions, labels):
    """Resumo verificável: texto da receita e rótulos dos EANs de referência."""
    text_check = analyze_recipe_ingredients([ingredient], restrictions)[0]
    evidence = []
    for ean in ingredient.get('produtosReferencia', []):
        label = labels.get(ean)
        if not label:
            continue
        analysis = analyze_product(
            {'itemId': ean, 'itemName': label['productName']}, restrictions,
            kind=KIND_MARKET, label=label,
        )
        evidence.append({
            'ean': ean, 'nome': label['productName'], 'parecer': analysis['verdict'],
            'contem': label.get('allergens', []), 'podeConter': label.get('traces', []),
            'ingredientes': label.get('ingredients', ''), 'declaracoes': label.get('labels', []),
            'fonte': label['url'], 'observacao': label.get('sourceNote'),
            'restricoes': [result['label'] for result in analysis['restrictions'] if result['verdict'] in (Verdict.CONFLICT, Verdict.RISK)],
            'achados': [finding for result in analysis['restrictions'] for finding in result['findings']],
        })
    eligible = [entry for entry in evidence if entry['parecer'] not in (Verdict.CONFLICT, Verdict.RISK)]
    best = min(evidence, key=lambda entry: VERDICT_SEVERITY[entry['parecer']]) if evidence else None
    status = text_check['status']
    if best and VERDICT_SEVERITY[best['parecer']] > VERDICT_SEVERITY[status]:
        status = best['parecer']
    components = [assess_ingredient(component, restrictions, labels) for component in ingredient.get('componentes', [])]
    for component in components:
        if VERDICT_SEVERITY[component['parecer']] > VERDICT_SEVERITY[status]:
            status = component['parecer']
    blocked = text_check['status'] == Verdict.CONFLICT or (bool(evidence) and not eligible) or any(component['bloqueado'] for component in components)
    return {'parecer': status, 'bloqueado': blocked, 'checagemNome': text_check, 'rotulos': evidence,
            'eansElegiveis': [entry['ean'] for entry in eligible], 'componentes': components,
            'limite': 'Referências locais; a oferta real precisa corresponder ao EAN. Dados incompletos não garantem ausência.'}


def select_demo_recipe(query, restrictions, at_home=()):
    recipes = load_demo_recipes()
    query = normalize_text(query)
    # O id exato permite atualizar a mesma receita. Na linguagem natural,
    # a expressão mais específica vence: pesto antes de macarrão, por exemplo.
    exact = [recipe for recipe in recipes if normalize_text(recipe['id']) == query]
    ranked = []
    for recipe in recipes:
        terms = [recipe['titulo'], *recipe['termos']]
        specificity = max((len(normalize_text(term)) for term in terms if _matches(query, term)), default=0)
        if specificity:
            ranked.append((specificity, recipe))
    if not exact and not ranked:
        return None
    # Não converte um pedido específico incompatível em outro prato genérico.
    recipe = exact[0] if exact else max(ranked, key=lambda item: item[0])[1]
    labels = load_local_labels()
    selected = None
    # Cada opção já contém a lista completa e suas justificativas no JSON.
    # A validação pode recusar uma versão, mas nunca cria outra combinação.
    for variant in recipe.get('variantes', []):
        if all(not assess_ingredient(item, restrictions, labels)['bloqueado'] for item in variant['ingredientes']):
            selected = variant
            break
    if selected is None:
        return None
    ingredients = selected['ingredientes']
    swaps = selected.get('substituicoes', [])
    base_by_name = {item['nome']: item for item in recipe['ingredientes']}
    for swap in swaps:
        original = swap.get('ingredienteOriginal') or base_by_name.get(swap['original']) or {'nome': swap['original']}
        substitute = swap.get('ingredienteSubstituto') or next((item for item in ingredients if item['nome'] == swap['substituto']), {'nome': swap['substituto']})
        swap['evidenciasOriginal'] = assess_ingredient(original, restrictions, labels)
        swap['evidenciasSubstituto'] = assess_ingredient(substitute, restrictions, labels)
        nutrition_reference = load_nutrition_reference()
        swap['comparacao'] = {
            'original': ingredient_profile(original, labels, nutrition_reference),
            'substituto': ingredient_profile(substitute, labels, nutrition_reference),
        }
        assessment = swap['evidenciasOriginal']
        swap['restricoes'] = list(dict.fromkeys(
            [conflict['label'] for conflict in assessment['checagemNome']['conflicts']]
            + [name for label in assessment['rotulos'] for name in label['restricoes']]
        ))
        swap.pop('ingredienteOriginal', None)
        swap.pop('ingredienteSubstituto', None)
    recipe['varianteId'] = selected['id']
    recipe['titulo'] = selected['titulo']
    recipe.pop('variantes', None)
    known = {normalize_text(name) for name in at_home}
    expanded = []
    for item in ingredients:
        components = item.get('componentes')
        if components:
            for component in components:
                component['preparacaoCaseira'] = item['nome']
                if normalize_text(item['nome']) in known:
                    known.add(normalize_text(component['nome']))
                expanded.append(component)
        else:
            expanded.append(item)
    ingredients = expanded
    if any(check['status'] == Verdict.CONFLICT for check in analyze_recipe_ingredients(ingredients, restrictions)):
        return None
    labels = load_local_labels()
    for item in ingredients:
        item['jaTenhoEmCasa'] = normalize_text(item['nome']) in known
        if item['nome'] == 'Água':
            item['jaTenhoEmCasa'] = True
        assessment = assess_ingredient(item, restrictions, labels)
        if assessment['bloqueado']:
            return None
        item['analiseReferencias'] = assessment
        item['produtosReferencia'] = assessment['eansElegiveis']
        item['referenciasDemo'] = [
            {'ean': ean, 'nome': labels[ean]['productName'], 'embalagem': labels[ean]['quantity'],
             'url': labels[ean]['url']} for ean in item.get('produtosReferencia', []) if ean in labels
        ]
        if item['referenciasDemo']:
            item['quantidadeCompra'] = purchase_quantity(item, item['referenciasDemo'][0]['embalagem'])
    recipe['ingredientes'] = ingredients
    recipe['substituicoes'] = swaps
    recipe['origem'] = 'Catálogo local de demonstração'
    recipe['cuidados'].insert(0, 'Origem: catálogo local de demonstração. As trocas são pré-cadastradas; a explicação de cada troca é feita pela IA a partir da composição e da tabela nutricional.')
    return recipe
