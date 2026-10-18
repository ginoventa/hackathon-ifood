"""Utilitários de texto usados pelo motor de restrições.

Toda comparação é feita sobre texto normalizado (minúsculo, sem acentos e
sem pontuação), para que "Glúten", "gluten" e "GLÚTEN" sejam equivalentes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Palavras que, logo antes de um termo, indicam que ele está AUSENTE ("sem leite").
NEGATION_PATTERNS = ("sem", "zero", "livre de", "isento de", "isenta de", "nao contem", "nao tem", "0%")

# Quantas palavras antes do termo procuramos uma negação ("sem queijo e sem molho").
NEGATION_WINDOW = 3


def normalize_text(text: str | None) -> str:
    """Normaliza um texto para comparação."""
    decomposed = unicodedata.normalize("NFD", str(text or "").lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9%]+", " ", without_accents).strip()


def _is_negated(text: str, index: int) -> bool:
    """Indica se a ocorrência na posição ``index`` está negada pelas palavras anteriores."""
    before = " ".join(text[:index].split()[-NEGATION_WINDOW:])
    return any(
        before == pattern
        or before.endswith(f" {pattern}")
        or before.startswith(f"{pattern} ")
        or f" {pattern} " in before
        for pattern in NEGATION_PATTERNS
    )


@dataclass
class TermMatches:
    """Resultado de uma busca de termos: presentes e negados."""

    present: list[str] = field(default_factory=list)
    negated: list[str] = field(default_factory=list)


def find_terms(raw_text: str | None, terms: list[str], ignored_phrases: list[str] | None = None) -> TermMatches:
    """Procura termos num texto, respeitando limites de palavra e negações.

    Exemplo: em "pão sem glúten", "gluten" aparece como NEGADO; em
    "farinha de trigo", "trigo" aparece como PRESENTE.

    Args:
        raw_text: Texto original (será normalizado).
        terms: Termos procurados (serão normalizados).
        ignored_phrases: Expressões removidas antes da busca
            (ex.: "leite de coco" não conta como leite de vaca).
    """
    text = f" {normalize_text(raw_text)} "
    for phrase in ignored_phrases or []:
        text = text.replace(f" {normalize_text(phrase)} ", " _ ")

    present: dict[str, None] = {}
    negated: dict[str, None] = {}
    for term in terms:
        normalized = normalize_text(term)
        if not normalized:
            continue
        # Aceita plural simples ("ovo" → "ovos", "noz" → "nozes"). O lookahead
        # permite encontrar ocorrências vizinhas separadas por um único espaço.
        pattern = re.compile(rf" {re.escape(normalized)}(?:s|es)?(?= )")
        for match in pattern.finditer(text):
            target = negated if _is_negated(text, match.start() + 1) else present
            target[term] = None

    return TermMatches(present=list(present), negated=list(negated))


def contains_any(raw_text: str | None, phrases: list[str]) -> list[str]:
    """Expressões encontradas no texto, sem considerar negação ("sem glúten", "vegano")."""
    text = f" {normalize_text(raw_text)} "
    return [phrase for phrase in phrases if f" {normalize_text(phrase)} " in text]
