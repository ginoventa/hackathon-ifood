"""Tabela nutricional de referência para comparar as trocas de ingredientes.

As receitas adaptadas são sugeridas pela IA, que propõe trocas como
"farinha de trigo → farinha de arroz". Para a IA explicar a troca com dados,
cada lado recebe a tabela nutricional aproximada (por 100 g) da TACO
(Tabela Brasileira de Composição de Alimentos), quando o ingrediente consta nela.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..restrictions.text_matching import normalize_text

REFERENCE_PATH = Path(__file__).resolve().parents[1] / "data/nutrition_reference.json"


@lru_cache(maxsize=1)
def _load_reference() -> dict:
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def ingredient_profile(name: str) -> dict:
    """Tabela de referência de um ingrediente, procurando o nome mais específico.

    Ex.: "Farinha de arroz integral" usa a linha "farinha de arroz".
    """
    reference = _load_reference()
    text = f" {normalize_text(name)} "
    matches = [key for key in reference if not key.startswith("_") and f" {key} " in text]
    key = max(matches, key=len, default=None)
    return {
        "nome": name,
        "tabelaNutricionalPor100g": reference[key] if key else None,
        "fonteNutricional": reference["_fonte"] if key else None,
    }


def swap_comparison(swap: dict) -> dict:
    """Comparação nutricional do ingrediente original e do substituto de uma troca."""
    return {"original": ingredient_profile(swap["original"]), "substituto": ingredient_profile(swap["substituto"])}
