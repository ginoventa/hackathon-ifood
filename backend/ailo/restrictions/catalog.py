"""Catálogo de restrições alimentares conhecidas pelo Ailo.

Estas regras são EXPLÍCITAS e DETERMINÍSTICAS: a verificação de segurança
não depende só da LLM. A LLM apenas identifica qual restrição o usuário
descreveu; quem decide se um produto conflita é o analisador
(``analyzer.py``), usando os termos abaixo.

Campos de cada restrição:

- ``type``: categoria clínica (alergia, intolerância, doença celíaca, preferência).
- ``rigor``: nível de investigação. "ALTO" ativa a análise de contato cruzado.
- ``terms``: termos que indicam presença da substância (ingredientes e pratos típicos).
- ``core_terms``: subconjunto com a substância em si ("trigo", "leite"). Quando o
  produto declara "sem glúten", só esses termos indicam contradição; nomes de
  prato como "lasanha" deixam de contar.
- ``uncertain_terms``: termos que PODEM conter a substância ("molho da casa").
- ``ignored_phrases``: expressões que parecem a substância, mas não são ("leite de coco").
- ``free_claims``: declarações de ausência feitas pelo estabelecimento ("sem glúten").
- ``insufficient_claims``: declarações comuns que NÃO bastam para a restrição
  ("zero lactose" não significa sem proteína do leite).
- ``ifood_tags``: filtros ``itemRestrictions`` do MCP do iFood equivalentes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any


class RestrictionType:
    """Tipos clínicos, que o agente deve sempre diferenciar."""

    ALLERGY = "ALERGIA"
    INTOLERANCE = "INTOLERANCIA"
    CELIAC = "DOENCA_CELIACA"
    PREFERENCE = "PREFERENCIA"

    ALL = (ALLERGY, INTOLERANCE, CELIAC, PREFERENCE)


class Rigor:
    """Níveis de rigor da investigação."""

    HIGH = "ALTO"
    MEDIUM = "MEDIO"
    LOW = "BAIXO"


RIGOR_BY_TYPE = {
    RestrictionType.ALLERGY: Rigor.HIGH,
    RestrictionType.CELIAC: Rigor.HIGH,
    RestrictionType.INTOLERANCE: Rigor.MEDIUM,
    RestrictionType.PREFERENCE: Rigor.LOW,
}


@dataclass(frozen=True)
class Restriction:
    """Uma restrição alimentar com todas as regras usadas pelo analisador."""

    id: str
    label: str
    substance: str
    type: str
    terms: tuple[str, ...]
    core_terms: tuple[str, ...] = ()
    uncertain_terms: tuple[str, ...] = ()
    ignored_phrases: tuple[str, ...] = ()
    free_claims: tuple[str, ...] = ()
    insufficient_claims: tuple[str, ...] = ()
    ifood_tags: tuple[str, ...] = ()
    note: str = ""
    custom: bool = False
    user_note: str = ""

    @property
    def rigor(self) -> str:
        return RIGOR_BY_TYPE[self.type]

    @property
    def effective_core_terms(self) -> tuple[str, ...]:
        """Termos centrais; se não definidos, todos os termos contam."""
        return self.core_terms or self.terms

    def summary(self) -> dict[str, str]:
        """Formato curto usado pela LLM e pela interface."""
        return {"id": self.id, "label": self.label, "tipo": self.type, "rigor": self.rigor}


# Listas de termos reaproveitadas por mais de uma restrição.

GLUTEN_TERMS = (
    "gluten", "trigo", "farinha de trigo", "cevada", "centeio", "malte", "semolina", "semola",
    "pao", "paes", "brioche", "baguete", "torrada", "crouton", "bruschetta", "massa", "macarrao",
    "lasanha", "pizza", "espaguete", "spaghetti", "penne", "rigatoni", "fettuccine", "pappardelle",
    "talharim", "tagliatelle", "ravioli", "tortellini", "capeletti", "canelone", "nhoque", "gnocchi",
    "risoni", "empanado", "empanada", "milanesa", "parmegiana", "panqueca", "pastel", "coxinha",
    "esfiha", "bolo", "biscoito", "bolacha", "cookie", "waffle", "croissant", "cerveja", "seitan",
    "cuscuz marroquino", "farinha de rosca", "panko", "shoyu", "molho de soja", "arancini",
    "hamburguer", "sanduiche", "wrap", "tortilha de trigo",
)
GLUTEN_CORE = ("gluten", "trigo", "farinha de trigo", "cevada", "centeio", "malte", "semolina", "semola", "farinha de rosca", "panko")
GLUTEN_UNCERTAIN = ("aveia", "farinha", "molho da casa", "molho especial", "tempero pronto", "caldo", "frito", "empanados")
GLUTEN_IGNORED = (
    "pao de queijo", "farinha de arroz", "farinha de milho", "farinha de mandioca", "farinha de amendoa",
    "massa de arroz", "macarrao de arroz", "pao de arroz", "massa sem gluten", "pizza sem gluten",
)
GLUTEN_FREE_CLAIMS = ("sem gluten", "gluten free", "livre de gluten", "nao contem gluten", "isento de gluten")

DAIRY_TERMS = (
    "leite", "lacteo", "lactea", "queijo", "queijos", "parmesao", "mussarela", "mucarela", "muzarela", "requeijao",
    "manteiga", "creme de leite", "nata", "iogurte", "coalhada", "soro de leite", "whey", "caseina",
    "caseinato", "lactose", "ricota", "burrata", "mascarpone", "cream cheese", "catupiry", "cheddar",
    "gorgonzola", "provolone", "brie", "gouda", "pecorino", "grana padano", "molho branco", "bechamel",
    "alfredo", "quatro queijos", "chantilly", "leite condensado", "doce de leite", "pudim", "brigadeiro",
    "ghee", "gratinado", "gratinada", "fondue", "tiramisu", "sorvete", "milkshake", "cappuccino",
)
DAIRY_CORE = (
    "leite", "lacteo", "lactea", "queijo", "manteiga", "creme de leite", "nata", "iogurte", "soro de leite",
    "whey", "caseina", "caseinato", "lactose", "requeijao", "leite condensado", "leite em po",
)
DAIRY_UNCERTAIN = ("cremoso", "cremosa", "creme", "molho da casa", "molho especial", "chocolate", "margarina")
DAIRY_IGNORED = (
    "leite de coco", "leite de amendoa", "leite de aveia", "leite de arroz", "leite de soja", "leite vegetal",
    "creme de leite de coco", "manteiga de cacau", "manteiga de amendoim", "queijo vegano", "queijo vegetal",
    "requeijao vegano", "manteiga vegana", "creme vegetal", "iogurte vegetal", "iogurte de coco",
)

EGG_TERMS = (
    "ovo", "gema", "clara", "maionese", "merengue", "suspiro", "omelete", "fritada", "carbonara",
    "quiche", "pao de lo", "gemada", "fios de ovos", "ovomaltine",
)
EGG_CORE = ("ovo", "gema", "clara", "albumina")
EGG_UNCERTAIN = ("massa fresca", "empanado", "empanada", "milanesa", "molho da casa", "bolo", "panqueca")

MEAT_TERMS = (
    "carne", "bovina", "bovino", "frango", "galinha", "porco", "suino", "suina", "bacon", "presunto",
    "linguica", "calabresa", "salame", "mortadela", "peru", "pernil", "costela", "file", "file mignon",
    "picanha", "alcatra", "patinho", "acem", "cupim", "ossobuco", "ragu", "bolonhesa", "hamburguer",
    "almondega", "vitelo", "cordeiro", "pato", "parma", "copa", "pepperoni", "peixe", "salmao", "atum",
    "bacalhau", "camarao", "frutos do mar", "lula", "polvo", "anchova", "aliche", "tilapia", "sardinha",
    "caldo de carne", "caldo de galinha", "banha", "torresmo", "gelatina",
)
MEAT_CORE = ("carne", "frango", "porco", "bacon", "presunto", "peixe", "camarao", "gelatina", "banha", "caldo de carne", "caldo de galinha")
MEAT_IGNORED = (
    "carne vegetal", "carne de jaca", "hamburguer vegetal", "hamburguer vegano", "hamburguer de grao de bico",
    "frango vegano", "carne vegana", "proteina vegetal", "hamburguer de cogumelo",
)

# Restrições conhecidas. A chave é o identificador usado em todo o sistema.
RESTRICTIONS: dict[str, Restriction] = {
    restriction.id: restriction
    for restriction in (
        Restriction(
            id="doenca_celiaca", label="Doença celíaca", substance="glúten", type=RestrictionType.CELIAC,
            terms=GLUTEN_TERMS, core_terms=GLUTEN_CORE, uncertain_terms=GLUTEN_UNCERTAIN,
            ignored_phrases=GLUTEN_IGNORED, free_claims=GLUTEN_FREE_CLAIMS, ifood_tags=("GLUTEN_FREE",),
            note="Mesmo traços de glúten podem causar reação. Contato cruzado em fornos, óleo de fritura e utensílios é relevante.",
        ),
        Restriction(
            id="sensibilidade_gluten", label="Intolerância/sensibilidade ao glúten", substance="glúten",
            type=RestrictionType.INTOLERANCE, terms=GLUTEN_TERMS, core_terms=GLUTEN_CORE,
            uncertain_terms=GLUTEN_UNCERTAIN, ignored_phrases=GLUTEN_IGNORED, free_claims=GLUTEN_FREE_CLAIMS,
            ifood_tags=("GLUTEN_FREE",),
        ),
        Restriction(
            id="alergia_leite", label="Alergia à proteína do leite (APLV)", substance="proteína do leite",
            type=RestrictionType.ALLERGY, terms=DAIRY_TERMS, core_terms=DAIRY_CORE, uncertain_terms=DAIRY_UNCERTAIN,
            ignored_phrases=DAIRY_IGNORED,
            free_claims=("sem leite", "sem lacteos", "livre de leite", "vegano", "vegana", "100% vegetal", "plant based"),
            # "Zero lactose" remove o açúcar do leite, mas mantém a proteína: não serve para APLV.
            insufficient_claims=("zero lactose", "sem lactose", "lactose free", "baixa lactose"),
            ifood_tags=("VEGAN",),
            note='"Sem lactose" NÃO significa sem proteína do leite. Para APLV, produtos zero lactose continuam incompatíveis.',
        ),
        Restriction(
            id="intolerancia_lactose", label="Intolerância à lactose", substance="lactose",
            type=RestrictionType.INTOLERANCE,
            terms=tuple(term for term in DAIRY_TERMS if term not in ("caseina", "caseinato")),
            # Com "zero lactose" declarado, laticínios deixam de ser contradição: só a lactose em si conta.
            core_terms=("lactose",),
            uncertain_terms=DAIRY_UNCERTAIN,
            ignored_phrases=(*DAIRY_IGNORED, "zero lactose", "sem lactose"),
            free_claims=("sem lactose", "zero lactose", "lactose free", "sem leite", "vegano", "vegana", "100% vegetal"),
            ifood_tags=("LAC_FREE",),
        ),
        Restriction(
            id="alergia_ovo", label="Alergia a ovo", substance="ovo", type=RestrictionType.ALLERGY,
            terms=EGG_TERMS, core_terms=EGG_CORE, uncertain_terms=EGG_UNCERTAIN,
            ignored_phrases=("maionese vegana", "maionese vegetal", "ovo vegano"),
            free_claims=("sem ovo", "sem ovos", "vegano", "vegana", "100% vegetal"), ifood_tags=("VEGAN",),
        ),
        Restriction(
            id="alergia_amendoim", label="Alergia a amendoim", substance="amendoim", type=RestrictionType.ALLERGY,
            terms=("amendoim", "pacoca", "pe de moleque", "pasta de amendoim", "manteiga de amendoim", "satay", "mendorato"),
            uncertain_terms=("granola", "crocante", "praline", "chocolate", "molho thai", "molho asiatico", "xerem"),
            free_claims=("sem amendoim", "livre de amendoim"),
        ),
        Restriction(
            id="alergia_castanhas", label="Alergia a castanhas e nozes", substance="castanhas/nozes",
            type=RestrictionType.ALLERGY,
            terms=(
                "castanha", "castanha de caju", "castanha do para", "noz", "nozes", "amendoa", "avela", "pistache",
                "macadamia", "peca", "pinoli", "nutella", "marzipan", "praline", "gianduia", "leite de amendoa",
            ),
            uncertain_terms=("pesto", "granola", "crocante", "chocolate", "farofa doce", "mix de graos"),
            free_claims=("sem castanhas", "sem nozes", "livre de castanhas"),
        ),
        Restriction(
            id="alergia_soja", label="Alergia a soja", substance="soja", type=RestrictionType.ALLERGY,
            terms=("soja", "shoyu", "molho de soja", "tofu", "misso", "missoshiru", "edamame", "lecitina de soja", "proteina de soja", "tempeh", "teriyaki"),
            uncertain_terms=("proteina vegetal", "molho oriental", "tempero pronto", "chocolate", "margarina"),
            free_claims=("sem soja", "livre de soja"),
        ),
        Restriction(
            id="alergia_peixe", label="Alergia a peixe", substance="peixe", type=RestrictionType.ALLERGY,
            terms=("peixe", "salmao", "atum", "bacalhau", "tilapia", "sardinha", "anchova", "aliche", "pescada", "merluza", "robalo", "sushi", "sashimi", "molho de peixe", "dashi", "katsuobushi"),
            uncertain_terms=("molho ingles", "worcestershire", "caesar", "temaki", "poke", "frutos do mar"),
            free_claims=("sem peixe",),
        ),
        Restriction(
            id="alergia_frutos_mar", label="Alergia a frutos do mar", substance="crustáceos e moluscos",
            type=RestrictionType.ALLERGY,
            terms=("camarao", "lagosta", "caranguejo", "siri", "lula", "polvo", "mexilhao", "marisco", "ostra", "vieira", "frutos do mar", "paella", "kani"),
            uncertain_terms=("molho de peixe", "tempura", "yakisoba", "moqueca", "bobo"),
            free_claims=("sem frutos do mar",),
        ),
        Restriction(
            id="vegano", label="Vegano", substance="ingredientes de origem animal", type=RestrictionType.PREFERENCE,
            terms=(*MEAT_TERMS, *DAIRY_TERMS, *EGG_TERMS, "mel"), core_terms=(*MEAT_CORE, *DAIRY_CORE, *EGG_CORE, "mel"),
            uncertain_terms=("molho da casa", "caldo", "massa fresca", "chocolate"),
            ignored_phrases=(*MEAT_IGNORED, *DAIRY_IGNORED, "maionese vegana"),
            free_claims=("vegano", "vegana", "100% vegetal", "plant based"), ifood_tags=("VEGAN",),
        ),
        Restriction(
            id="vegetariano", label="Vegetariano", substance="carnes", type=RestrictionType.PREFERENCE,
            terms=MEAT_TERMS, core_terms=MEAT_CORE, uncertain_terms=("caldo", "molho da casa"),
            ignored_phrases=MEAT_IGNORED, free_claims=("vegetariano", "vegetariana", "vegano", "vegana"),
            ifood_tags=("VEGETARIAN",),
        ),
    )
}

CUSTOM_RESTRICTION_ID = "personalizada"


def list_restriction_options() -> list[dict[str, str]]:
    """Lista resumida usada no prompt do agente e na página de perfil."""
    return [{"id": item.id, "label": item.label, "type": item.type} for item in RESTRICTIONS.values()]


def _slug(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    ascii_text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def resolve_restriction(data: dict[str, Any] | None) -> Restriction | None:
    """Monta a restrição completa a partir do que o usuário informou.

    Aceita uma restrição do catálogo (``{"id": "alergia_leite"}``) ou uma
    personalizada (``{"id": "personalizada", "nome", "tipo", "termos"}``),
    como "alergia a kiwi". Retorna ``None`` se a entrada for inválida.
    """
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        return None

    user_note = str(data.get("observacao") or "")
    known = RESTRICTIONS.get(data["id"])
    if known:
        return replace(known, user_note=user_note)

    # Restrição personalizada: precisa de nome e de pelo menos um termo.
    terms = tuple(term.strip() for term in data.get("termos") or [] if isinstance(term, str) and term.strip())
    name = str(data.get("nome") or "").strip()
    if not name or not terms:
        return None

    restriction_type = data.get("tipo") if data.get("tipo") in RestrictionType.ALL else RestrictionType.ALLERGY
    return Restriction(
        id=f"personalizada_{_slug(name)}",
        label=name,
        substance=terms[0],
        type=restriction_type,
        terms=terms,
        core_terms=terms,
        free_claims=tuple(f"sem {term}" for term in terms),
        custom=True,
        user_note=user_note,
    )


def to_ifood_item_restrictions(restrictions: list[Restriction]) -> list[str]:
    """Converte as restrições nos filtros ``itemRestrictions`` do iFood.

    Os filtros servem para PRIORIZAR resultados na busca. Eles não substituem
    a análise do produto: a etiqueta do iFood é tratada como mais uma evidência.
    """
    tags: dict[str, None] = {}
    for restriction in restrictions:
        for tag in restriction.ifood_tags:
            tags[tag] = None
    return list(tags)
