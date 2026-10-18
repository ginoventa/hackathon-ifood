"""Analisador determinístico de restrições alimentares.

Recebe os dados de um produto (vindos do MCP do iFood) e as restrições do
usuário e devolve um parecer ESTRUTURADO, com a origem de cada evidência.

Princípios seguidos (seção 4 da proposta):

- Nunca afirmar que um produto é seguro só porque um alergênico não aparece.
- Diferenciar alergia, intolerância, doença celíaca e preferência.
- Tratar alergênicos em outros itens do cardápio como POSSÍVEL contato
  cruzado, nunca como prova de contaminação.
- Sinalizar informação ausente, contraditória ou não verificada.
- Priorizar o que o estabelecimento declarou, e não suposições.

As chaves dos dicionários de saída usam camelCase porque vão direto para a
interface (JavaScript).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .catalog import Restriction, RestrictionType, Rigor
from .text_matching import contains_any, find_terms, normalize_text


class Verdict:
    """Pareceres possíveis, do mais grave para o menos grave."""

    CONFLICT = "CONFLITO"
    RISK = "RISCO"
    INSUFFICIENT = "INFORMACAO_INSUFICIENTE"
    NO_DECLARED_CONFLICT = "SEM_CONFLITO_DECLARADO"


VERDICT_SEVERITY = {
    Verdict.CONFLICT: 3,
    Verdict.RISK: 2,
    Verdict.INSUFFICIENT: 1,
    Verdict.NO_DECLARED_CONFLICT: 0,
}


class FindingKind:
    """Tipos de evidência registrados em cada achado."""

    INGREDIENT = "INGREDIENTE"
    UNCERTAIN = "INGREDIENTE_INCERTO"
    ADD_ON = "ADICIONAL"
    CONTRADICTION = "CONTRADICAO"
    FREE_CLAIM = "DECLARACAO_DE_AUSENCIA"
    INSUFFICIENT_CLAIM = "DECLARACAO_INSUFICIENTE"
    IFOOD_TAG = "ETIQUETA_IFOOD"
    CROSS_CONTACT = "POSSIVEL_CONTATO_CRUZADO"
    CONFIRMATION = "CONFIRMACAO_DO_ESTABELECIMENTO"
    # O rótulo foi consultado e não marca a substância (nem em "pode conter").
    LABEL_CLEAR = "ROTULO_SEM_A_SUBSTANCIA"


# Caminhos alternativos oferecidos quando há dúvida ou risco (seção 1.4).
ALTERNATIVES = ["CONSULTAR_RESTAURANTE", "ESCOLHER_OUTRO_PRODUTO", "PREPARAR_EM_CASA"]

# Descrições mais curtas que isto são tratadas como lista de ingredientes incompleta.
MIN_DESCRIPTIVE_LENGTH = 45

# Limite de itens do cardápio listados como possível contato cruzado.
MAX_CROSS_CONTACT_EXAMPLES = 6

KIND_RESTAURANT = "RESTAURANTE"
KIND_MARKET = "MERCADO"

DISCLAIMER = (
    "Esta análise usa apenas as informações publicadas no iFood e as que você informou. "
    "Ela apoia sua decisão, mas não certifica a segurança do alimento nem substitui orientação médica."
)

# Avisos de "pode conter": o trecho seguinte lista substâncias de possível contato cruzado.
MAY_CONTAIN_PATTERN = re.compile(r"(pode conter|cont[eé]m tra[cç]os de|tra[cç]os de)([^.;!\n]*)", re.IGNORECASE)

# Declarações de preparo compartilhado feitas pelo próprio estabelecimento.
SHARED_PREPARATION_PATTERN = re.compile(
    r"(mesmo forno|mesma fritadeira|mesmo [óo]leo|mesma chapa|cozinha compartilhada|equipamentos? compartilhados?|mesmo ambiente)",
    re.IGNORECASE,
)

TYPE_LABELS = {
    RestrictionType.ALLERGY: "alergia",
    RestrictionType.INTOLERANCE: "intolerância",
    RestrictionType.CELIAC: "doença celíaca",
    RestrictionType.RELIGIOUS: "restrição religiosa",
    RestrictionType.PREFERENCE: "preferência alimentar",
}


def _split_may_contain(text: str | None) -> tuple[str, list[str]]:
    """Separa os avisos de "pode conter" do restante do texto.

    Assim "pode conter traços de glúten" vira POSSÍVEL contato cruzado, e não
    ingrediente declarado.
    """
    warnings: list[str] = []

    def collect(match: re.Match) -> str:
        warnings.append(match.group(2).strip())
        return " "

    return MAY_CONTAIN_PATTERN.sub(collect, str(text or "")), warnings


def _worst_verdict(verdicts: list[str]) -> str:
    return max(verdicts, key=VERDICT_SEVERITY.__getitem__, default=Verdict.NO_DECLARED_CONFLICT)


# Nomes legíveis dos alergênicos e selos da Open Food Facts.
LABEL_TAG_NAMES = {
    "en:gluten": "glúten", "en:contains-gluten": "contém glúten", "en:milk": "leite", "en:contains-milk": "contém leite",
    "en:contains-lactose": "contém lactose", "en:eggs": "ovo", "en:peanuts": "amendoim", "en:nuts": "castanhas",
    "en:soybeans": "soja", "en:fish": "peixe", "en:crustaceans": "crustáceos", "en:molluscs": "moluscos",
    "en:sesame-seeds": "gergelim", "en:no-gluten": "sem glúten", "en:gluten-free": "sem glúten",
    "en:no-lactose": "sem lactose", "en:lactose-free": "sem lactose", "en:no-milk": "sem leite", "en:dairy-free": "sem laticínios",
    "en:vegan": "vegano", "en:vegetarian": "vegetariano", "en:halal": "halal", "en:kosher": "kosher",
    "en:no-eggs": "sem ovo", "en:no-peanuts": "sem amendoim", "en:no-nuts": "sem castanhas", "en:no-soy": "sem soja",
    "en:no-sesame": "sem gergelim",
}


def _tag_name(tag: str) -> str:
    return LABEL_TAG_NAMES.get(tag, tag.split(":", 1)[-1].replace("-", " "))


def _label_findings(label: dict | None, restriction: Restriction, terms: list[str], ignored: list[str]) -> tuple[list[dict], bool, bool]:
    """Evidências vindas do rótulo do produto (consultado fora do iFood).

    Returns:
        ``(achados, selo_de_ausência, rótulo_sem_a_substância)``.
    """
    if not label or not label.get("found"):
        return [], False, False

    source = label.get("source") or f"Rótulo do produto (Open Food Facts, EAN {label.get('ean')})"
    note = label.get("sourceNote") or ("Dados fictícios para demonstração; não representam um rótulo real." if label.get("demo") else "Base colaborativa: confira também a embalagem.")
    conflict_tags = set(restriction.label_conflict_tags)
    findings = []

    declared = [tag for tag in [*label.get("allergens", []), *label.get("labels", [])] if tag in conflict_tags]
    if declared:
        findings.append(_finding(FindingKind.INGREDIENT, [_tag_name(tag) for tag in declared], "rótulo: alergênicos declarados", source, note=note))

    traces = [tag for tag in label.get("traces", []) if tag in conflict_tags]
    if traces:
        findings.append(_finding(FindingKind.CROSS_CONTACT, [_tag_name(tag) for tag in traces], 'rótulo: aviso "pode conter"', source, note=note))

    free = [tag for tag in label.get("labels", []) if tag in restriction.label_free_tags]
    if free:
        findings.append(_finding(FindingKind.FREE_CLAIM, [_tag_name(tag) for tag in free], "rótulo: selo", source, note=note))

    ingredients = label.get("ingredients") or ""
    from_ingredients = []
    if ingredients:
        clean_text, _ = _split_may_contain(ingredients)
        search_terms = list(restriction.effective_core_terms) if free else terms
        from_ingredients = find_terms(clean_text, search_terms, ignored).present
        if from_ingredients:
            findings.append(_finding(FindingKind.INGREDIENT, from_ingredients, "rótulo: lista de ingredientes", source, note=note))

    # O rótulo só "libera" quando traz dados de alergênicos/ingredientes e nada marca a substância.
    has_data = bool(label.get("allergens") or label.get("traces") or ingredients)
    is_clear = bool(conflict_tags) and has_data and label.get("allergenStatementComplete", True) and not (declared or traces or from_ingredients)
    if is_clear:
        findings.append(_finding(
            FindingKind.LABEL_CLEAR, [], f"rótulo sem {restriction.substance} nos alergênicos e no \"pode conter\"", source, note=note,
        ))
    return findings, bool(free), is_clear


def _lower_first(text: str) -> str:
    """Deixa só a primeira letra minúscula, preservando siglas: "Alergia (APLV)" → "alergia (APLV)"."""
    return text[:1].lower() + text[1:]


def _finding(kind: str, terms: list[str], where: str, source: str, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "terms": terms, "where": where, "source": source, **extra}


def _analyze_option_groups(product: dict, restriction: Restriction, source_label: str) -> list[dict]:
    """Analisa os adicionais do item.

    Adicionais opcionais não tornam o prato incompatível, mas devem ser
    evitados. Se um grupo OBRIGATÓRIO só tem opções com a substância, o prato conflita.
    """
    findings = []
    for group in product.get("optionGroups") or []:
        options = group.get("options") or []
        matches = [
            (option, find_terms(f"{option.get('name', '')} {option.get('description') or ''}", list(restriction.terms), list(restriction.ignored_phrases)).present)
            for option in options
        ]
        conflicting = [(option, terms) for option, terms in matches if terms]
        if not conflicting:
            continue

        is_mandatory = (group.get("minSelections") or 0) > 0
        every_option_conflicts = len(conflicting) == len(options)
        for option, terms in conflicting:
            findings.append(_finding(
                FindingKind.INGREDIENT if is_mandatory and every_option_conflicts else FindingKind.ADD_ON,
                terms,
                f'adicional "{option.get("name")}" (grupo "{group.get("name")}", {"obrigatório" if is_mandatory else "opcional"})',
                source_label,
                optionId=option.get("optionId"),
            ))
    return findings


def _analyze_cross_contact(product: dict, restriction: Restriction, menu_items: list[dict]) -> dict:
    """Procura a substância nos OUTROS itens do cardápio do estabelecimento.

    A presença indica uma possível fonte de contato cruzado, não uma prova.
    """
    examples = []
    for item in menu_items:
        if item.get("itemId") == product.get("itemId"):
            continue
        # Itens com a etiqueta do iFood para esta restrição (ex.: GLUTEN_FREE) não são
        # fonte de contato cruzado, mesmo que o nome cite "pizza" ou "massa".
        if any(tag in restriction.ifood_tags for tag in item.get("tags") or []):
            continue
        text = f"{item.get('itemName') or ''} {item.get('itemDescription') or ''}"
        present = find_terms(text, list(restriction.terms), list(restriction.ignored_phrases)).present
        declared_free = bool(contains_any(text, list(restriction.free_claims)))
        if present and not declared_free:
            examples.append({"itemName": item.get("itemName"), "terms": present})

    return {
        "analyzedItems": len(menu_items),
        "itemsWithSubstance": len(examples),
        "examples": examples[:MAX_CROSS_CONTACT_EXAMPLES],
    }


def _decide_verdict(restriction: Restriction, findings: list[dict], missing_info: list[str], *, has_valid_claim: bool, has_confirmation: bool) -> str:
    """Regras de decisão do parecer de uma restrição.

    A ordem importa: conflitos declarados vencem qualquer declaração de ausência.
    """
    kinds = {finding["kind"] for finding in findings}

    if FindingKind.INGREDIENT in kinds:
        return Verdict.CONFLICT
    if FindingKind.CONTRADICTION in kinds:
        # Informação contraditória: declara ausência, mas cita a substância.
        return Verdict.RISK
    if FindingKind.INSUFFICIENT_CLAIM in kinds and not has_valid_claim and not has_confirmation:
        # Ex.: APLV + "zero lactose": a declaração não cobre a restrição.
        return Verdict.RISK
    if FindingKind.UNCERTAIN in kinds and not has_confirmation:
        return Verdict.RISK
    if FindingKind.CROSS_CONTACT in kinds and not has_confirmation:
        return Verdict.RISK

    # Sem conflito encontrado. Preferências aceitam a ausência de conflito declarado.
    if restriction.rigor == Rigor.LOW:
        return Verdict.NO_DECLARED_CONFLICT
    # Para intolerâncias e alergias, é preciso alguma evidência positiva.
    if has_valid_claim or has_confirmation:
        return Verdict.NO_DECLARED_CONFLICT
    if restriction.rigor == Rigor.MEDIUM and not missing_info:
        return Verdict.NO_DECLARED_CONFLICT
    return Verdict.INSUFFICIENT


def _explain(restriction: Restriction, verdict: str, findings: list[dict]) -> str:
    """Gera uma explicação curta e determinística para a interface."""

    def terms_of(kind: str) -> list[str]:
        collected: dict[str, None] = {}
        for finding in findings:
            if finding["kind"] == kind:
                collected.update(dict.fromkeys(finding["terms"]))
        return list(collected)

    label = _lower_first(restriction.label)
    if verdict == Verdict.CONFLICT:
        who = "o rótulo declara" if any(f["kind"] == FindingKind.INGREDIENT and "rótulo" in f["where"] for f in findings) else "o estabelecimento cita"
        return (
            f"Incompatível com {label} ({TYPE_LABELS[restriction.type]}): "
            f"{who} {', '.join(terms_of(FindingKind.INGREDIENT))}."
        )
    if verdict == Verdict.RISK:
        reasons = []
        if terms_of(FindingKind.CONTRADICTION):
            reasons.append(f"informação contraditória (declara ausência, mas cita {', '.join(terms_of(FindingKind.CONTRADICTION))})")
        if terms_of(FindingKind.INSUFFICIENT_CLAIM) and not terms_of(FindingKind.FREE_CLAIM):
            reasons.append(f'"{", ".join(terms_of(FindingKind.INSUFFICIENT_CLAIM))}" não garante ausência de {restriction.substance}')
        if terms_of(FindingKind.UNCERTAIN):
            reasons.append(f"ingredientes que podem conter {restriction.substance} ({', '.join(terms_of(FindingKind.UNCERTAIN))})")
        if any(finding["kind"] == FindingKind.CROSS_CONTACT for finding in findings):
            cross_findings = [finding for finding in findings if finding["kind"] == FindingKind.CROSS_CONTACT]
            if any("rótulo" in finding["where"] for finding in cross_findings):
                reasons.append(f'o rótulo declara "pode conter {restriction.substance}"')
            if any('aviso "pode conter" no anúncio' in finding["where"] for finding in cross_findings):
                reasons.append(f'o anúncio declara "pode conter {restriction.substance}"')
            if any('"pode conter"' not in finding["where"] for finding in cross_findings):
                reasons.append(
                    f"há indícios de contato cruzado com {restriction.substance} "
                    "(outros itens do cardápio ou preparo compartilhado; não é prova de contaminação)"
                )
        return f"Possível risco para {label}: {'; '.join(reasons)}."
    if verdict == Verdict.INSUFFICIENT:
        return (
            f"Não há informações suficientes para avaliar {label}. Nenhum ingrediente incompatível foi citado, "
            f"mas isso não garante a ausência de {restriction.substance}."
        )
    if any(finding["kind"] == FindingKind.LABEL_CLEAR for finding in findings):
        return (
            f"O rótulo consultado não marca {restriction.substance} (nem em \"pode conter\"). "
            "Confira a embalagem ao receber: a base de rótulos é colaborativa."
        )
    return f"Nenhum conflito com {label} nas informações disponíveis. Isso não é uma garantia de segurança."


def is_packaged_product(product: dict, kind: str) -> bool:
    """Produtos de mercado e itens explicitamente embalados não usam o preparo da loja como evidência."""
    return kind == KIND_MARKET or bool(product.get("itemEan")) or any(
        product.get(field) is True
        for field in ("industrializado", "isIndustrialized", "isPackaged", "sealedPackage")
    )


def has_absence_claim(product: dict, restriction: Restriction, declared_tags: list[str]) -> bool:
    text = f"{product.get('itemName') or ''} {product.get('itemDescription') or ''}"
    return bool(contains_any(text, list(restriction.free_claims + restriction.insufficient_claims))) or any(
        tag in restriction.ifood_tags for tag in declared_tags
    )


def _analyze_restriction(product: dict, restriction: Restriction, context: dict) -> dict:
    """Analisa um produto para UMA restrição."""
    merchant = product.get("merchantName")
    source_label = (
        f"Anúncio do produto no iFood ({merchant or 'mercado'})"
        if context["kind"] == KIND_MARKET
        else f"Cardápio do estabelecimento no iFood ({merchant or 'restaurante'})"
    )
    findings: list[dict] = []
    missing_info: list[str] = []
    full_text = f"{product.get('itemName') or ''} {product.get('itemDescription') or ''}"
    terms = list(restriction.terms)
    ignored = list(restriction.ignored_phrases)

    # 1. Declarações de ausência ("sem glúten") e insuficientes ("zero lactose" para APLV).
    claims = contains_any(full_text, list(restriction.free_claims))
    insufficient_claims = contains_any(full_text, list(restriction.insufficient_claims))
    valid_claims = [claim for claim in claims if claim not in insufficient_claims]
    for claim in valid_claims:
        findings.append(_finding(FindingKind.FREE_CLAIM, [claim], "nome/descrição", source_label))
    for claim in insufficient_claims:
        findings.append(_finding(
            FindingKind.INSUFFICIENT_CLAIM, [claim], "nome/descrição", source_label,
            note=restriction.note or f'"{claim}" não garante a ausência de {restriction.substance}.',
        ))

    # 2. Etiquetas do iFood (o item apareceu numa busca filtrada por GLUTEN_FREE, por exemplo).
    matching_tags = [tag for tag in context.get("declared_tags") or [] if tag in restriction.ifood_tags]
    for tag in matching_tags:
        findings.append(_finding(FindingKind.IFOOD_TAG, [tag], "filtro de busca", "Classificação do iFood (itemRestrictions)"))

    # 2b. Rótulo do produto industrializado (consulta externa pelo código de barras).
    label = context.get("label")
    label_found, label_free, label_clear = _label_findings(label, restriction, terms, ignored)
    findings.extend(label_found)

    # 3. Ingredientes no nome e na descrição. Se o produto declara ausência
    #    (texto, etiqueta do iFood ou selo do rótulo), nomes de prato ("lasanha",
    #    "pizza", "massa") deixam de contar e só a substância em si ("trigo") indica contradição.
    has_valid_claim = bool(valid_claims or matching_tags or label_free)
    terms_to_search = list(restriction.effective_core_terms) if has_valid_claim else terms
    for where, raw in (("nome do item", product.get("itemName")), ("descrição do item", product.get("itemDescription"))):
        clean_text, _ = _split_may_contain(raw)
        present = find_terms(clean_text, terms_to_search, ignored).present
        if present:
            findings.append(_finding(FindingKind.CONTRADICTION if has_valid_claim else FindingKind.INGREDIENT, present, where, source_label))

        # Termos ambíguos ("creme") são resolvidos por uma declaração de ausência ("sem leite").
        if not has_valid_claim:
            uncertain = [term for term in find_terms(clean_text, list(restriction.uncertain_terms), ignored).present if term not in present]
            if uncertain:
                findings.append(_finding(FindingKind.UNCERTAIN, uncertain, where, source_label))

    # 3b. Avisos declarados pelo estabelecimento: "pode conter" e preparo compartilhado.
    _, warnings = _split_may_contain(full_text)
    for warning in warnings:
        present = find_terms(warning, terms, ignored).present
        if present:
            findings.append(_finding(FindingKind.CROSS_CONTACT, present, 'aviso "pode conter" no anúncio', source_label))
    packaged = is_packaged_product(product, context["kind"])
    shared = None if packaged else SHARED_PREPARATION_PATTERN.search(full_text)
    if shared and restriction.rigor != Rigor.LOW:
        findings.append(_finding(
            FindingKind.CROSS_CONTACT, [shared.group(0).lower()], "preparo compartilhado declarado pelo estabelecimento", source_label,
        ))

    # 4. Adicionais e opções.
    findings.extend(_analyze_option_groups(product, restriction, source_label))

    # 5. Confirmações do estabelecimento informadas pelo usuário (evidência adicional).
    confirmations = [
        confirmation for confirmation in context.get("confirmations") or []
        if confirmation["itemId"] == product.get("itemId")
        and (not confirmation.get("restrictionIds") or restriction.id in confirmation["restrictionIds"])
    ]
    for confirmation in confirmations:
        findings.append(_finding(
            FindingKind.CONFIRMATION, [], "resposta do estabelecimento", f"Informado pelo usuário em {confirmation['date']}",
            note=confirmation["summary"],
        ))

    # 6. Contato cruzado pelo cardápio: só para restrições de rigor alto em restaurantes.
    cross_contact = None
    if not packaged and (restriction.rigor == Rigor.HIGH or has_valid_claim or insufficient_claims):
        menu_items = context.get("menu_items")
        if menu_items is not None:
            cross_contact = _analyze_cross_contact(product, restriction, menu_items)
            if cross_contact["itemsWithSubstance"]:
                example_terms = list(dict.fromkeys(term for example in cross_contact["examples"] for term in example["terms"]))
                findings.append(_finding(
                    FindingKind.CROSS_CONTACT, example_terms[:6],
                    f"{cross_contact['itemsWithSubstance']} de {cross_contact['analyzedItems']} itens do cardápio analisados",
                    "Cardápio do estabelecimento no iFood",
                ))
        else:
            missing_info.append("Não foi possível consultar o restante do cardápio para avaliar contato cruzado.")

    # 7. Lacunas de informação.
    has_confirmation = bool(confirmations)
    # Só conta como rótulo consultado se a base trouxer alergênicos, selos ou ingredientes.
    has_label = bool(label and label.get("found") and (
        label.get("allergens") or label.get("traces") or label.get("labels") or label.get("ingredients")
    ))
    if len(normalize_text(product.get("itemDescription"))) < MIN_DESCRIPTIVE_LENGTH and not has_confirmation and not has_label:
        missing_info.append(
            'O anúncio não traz a lista de ingredientes nem os avisos de alergênicos ("pode conter"). Confira o rótulo.'
            if packaged
            else "A descrição do item não traz a lista completa de ingredientes."
        )
    if restriction.rigor == Rigor.HIGH and not has_confirmation and not (packaged and has_label):
        missing_info.append(
            f'Avisos de "pode conter {restriction.substance}" só aparecem na embalagem; o iFood não informa.'
            if packaged
            else "O iFood não informa procedimentos de preparo, armazenamento ou equipamentos compartilhados."
        )

    verdict = _decide_verdict(
        restriction, findings, missing_info, has_valid_claim=has_valid_claim or label_clear, has_confirmation=has_confirmation,
    )
    return {
        "restrictionId": restriction.id,
        "label": restriction.label,
        "type": restriction.type,
        "rigor": restriction.rigor,
        "substance": restriction.substance,
        "verdict": verdict,
        "findings": findings,
        "missingInfo": missing_info,
        "crossContact": cross_contact,
        "explanation": _explain(restriction, verdict, findings),
    }


def analyze_product(
    product: dict,
    restrictions: list[Restriction],
    *,
    kind: str = KIND_RESTAURANT,
    menu_items: list[dict] | None = None,
    declared_tags: list[str] | None = None,
    confirmations: list[dict] | None = None,
    label: dict | None = None,
) -> dict:
    """Analisa um produto para todas as restrições do usuário.

    Args:
        product: Item no formato do MCP (``getItem``): itemId, itemName,
            itemDescription, merchantId, merchantName, optionGroups.
        restrictions: Restrições já resolvidas (``resolve_restriction``).
        kind: ``"RESTAURANTE"`` ou ``"MERCADO"``.
        menu_items: Outros itens do cardápio (contato cruzado).
        declared_tags: Etiquetas ``itemRestrictions`` do iFood para o item.
        confirmations: Respostas do estabelecimento informadas pelo usuário.
        label: Rótulo do produto industrializado (``services.labels.fetch_label``).
    """
    context = {
        "kind": kind,
        "menu_items": menu_items,
        "declared_tags": declared_tags,
        "confirmations": confirmations,
        "label": label,
    }
    results = [_analyze_restriction(product, restriction, context) for restriction in restrictions]
    verdict = _worst_verdict([result["verdict"] for result in results]) if results else Verdict.INSUFFICIENT

    # Adicionais a evitar, para mostrar na revisão do pedido.
    add_ons: dict[Any, str] = {}
    for result in results:
        for finding in result["findings"]:
            if finding["kind"] == FindingKind.ADD_ON:
                add_ons[finding.get("optionId")] = finding["where"]

    can_proceed = verdict == Verdict.NO_DECLARED_CONFLICT
    return {
        "itemId": product.get("itemId"),
        "itemName": product.get("itemName"),
        "merchantId": product.get("merchantId"),
        "merchantName": product.get("merchantName"),
        "kind": kind,
        "verdict": verdict,
        "canProceed": can_proceed,
        "restrictions": results,
        "addOnsToAvoid": list(add_ons.values()),
        "missingInfo": list(dict.fromkeys(info for result in results for info in result["missingInfo"])),
        "alternatives": [] if can_proceed else list(ALTERNATIVES),
        "disclaimer": DISCLAIMER,
        "analyzedAt": datetime.now(timezone.utc).isoformat(),
    }


def analyze_recipe_ingredients(ingredients: list[dict], restrictions: list[Restriction]) -> list[dict]:
    """Verifica os ingredientes de uma receita gerada pela IA.

    É a "trava" determinística: a receita não é aceita se algum ingrediente
    cita a substância restrita.
    """
    checks = []
    for ingredient in ingredients:
        name = str(ingredient.get("nome") or "")
        conflicts, uncertain = [], []
        for restriction in restrictions:
            declared_free = bool(contains_any(name, list(restriction.free_claims)))
            terms = list(restriction.effective_core_terms if declared_free else restriction.terms)
            present = find_terms(name, terms, list(restriction.ignored_phrases)).present
            if present:
                conflicts.append({"restrictionId": restriction.id, "label": restriction.label, "terms": present})
            maybe = find_terms(name, list(restriction.uncertain_terms), list(restriction.ignored_phrases)).present
            if maybe:
                uncertain.append({"restrictionId": restriction.id, "label": restriction.label, "terms": maybe})

        needs_label_check = bool(ingredient.get("industrializado")) and any(r.rigor != Rigor.LOW for r in restrictions)
        status = Verdict.CONFLICT if conflicts else (Verdict.RISK if uncertain else Verdict.NO_DECLARED_CONFLICT)
        checks.append({
            "nome": name,
            "conflicts": conflicts,
            "uncertain": uncertain,
            "needsLabelCheck": needs_label_check,
            "status": status,
        })
    return checks
