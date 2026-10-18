"""Quantidade de embalagens a partir da necessidade e do produto identificado."""
from __future__ import annotations

import math
import re


def package_amount(text):
    match = re.search(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(kg|ml|g|l)\b', str(text), re.IGNORECASE)
    if not match:
        return None
    value = float(match[1].replace(',', '.'))
    unit = match[2].lower()
    return value * (1000 if unit in ('kg', 'l') else 1), ('g' if unit in ('g', 'kg') else 'ml')


def purchase_quantity(ingredient, package_text):
    need = ingredient.get('quantidadeNecessaria')
    package = package_amount(package_text)
    if need and package and need['unidade'] == package[1] and package[0] > 0:
        return max(1, math.ceil(need['valor'] / package[0]))
    return ingredient.get('quantidadeCompra', 1)
