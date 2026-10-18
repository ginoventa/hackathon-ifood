/**
 * Analisador determinístico de restrições alimentares.
 *
 * Recebe os dados de um produto (vindos do MCP do iFood) e as restrições do
 * usuário e devolve um parecer ESTRUTURADO, com a origem de cada evidência.
 *
 * Princípios seguidos (ver seção 4 da proposta):
 * - Nunca afirmar que um produto é seguro só porque um alergênico não aparece.
 * - Diferenciar alergia, intolerância, doença celíaca e preferência.
 * - Tratar alergênicos em outros itens do cardápio como POSSÍVEL contato cruzado,
 *   nunca como prova de contaminação.
 * - Sinalizar informação ausente, contraditória ou não verificada.
 * - Priorizar o que o estabelecimento declarou, e não suposições.
 */

import { RIGOR, RESTRICTION_TYPES } from './catalog.js';
import { containsAny, findTerms, normalizeText } from './textMatching.js';

/** Pareceres possíveis, do mais grave para o menos grave. */
export const VERDICTS = Object.freeze({
  CONFLICT: 'CONFLITO',
  RISK: 'RISCO',
  INSUFFICIENT: 'INFORMACAO_INSUFICIENTE',
  NO_DECLARED_CONFLICT: 'SEM_CONFLITO_DECLARADO',
});

const VERDICT_SEVERITY = {
  [VERDICTS.CONFLICT]: 3,
  [VERDICTS.RISK]: 2,
  [VERDICTS.INSUFFICIENT]: 1,
  [VERDICTS.NO_DECLARED_CONFLICT]: 0,
};

/** Tipos de evidência registrados em cada achado. */
export const FINDING_KINDS = Object.freeze({
  INGREDIENT: 'INGREDIENTE',
  UNCERTAIN: 'INGREDIENTE_INCERTO',
  ADD_ON: 'ADICIONAL',
  CONTRADICTION: 'CONTRADICAO',
  FREE_CLAIM: 'DECLARACAO_DE_AUSENCIA',
  INSUFFICIENT_CLAIM: 'DECLARACAO_INSUFICIENTE',
  IFOOD_TAG: 'ETIQUETA_IFOOD',
  CROSS_CONTACT: 'POSSIVEL_CONTATO_CRUZADO',
  CONFIRMATION: 'CONFIRMACAO_DO_ESTABELECIMENTO',
});

/** Caminhos alternativos oferecidos quando há dúvida ou risco (seção 1.4). */
export const ALTERNATIVES = Object.freeze({
  ASK_RESTAURANT: 'CONSULTAR_RESTAURANTE',
  OTHER_PRODUCT: 'ESCOLHER_OUTRO_PRODUTO',
  COOK_AT_HOME: 'PREPARAR_EM_CASA',
});

/** Descrições mais curtas que isto são tratadas como lista de ingredientes incompleta. */
const MIN_DESCRIPTIVE_LENGTH = 45;

/** Limite de itens do cardápio listados como possível contato cruzado. */
const MAX_CROSS_CONTACT_EXAMPLES = 6;

export const DISCLAIMER = 'Esta análise usa apenas as informações publicadas no iFood e as que você informou. '
  + 'Ela apoia sua decisão, mas não certifica a segurança do alimento nem substitui orientação médica.';

/** Avisos de "pode conter": o trecho seguinte lista substâncias de possível contato cruzado. */
const MAY_CONTAIN_PATTERN = /(pode conter|cont[eé]m tra[cç]os de|tra[cç]os de)([^.;!\n]*)/gi;

/** Declarações de preparo compartilhado feitas pelo próprio estabelecimento. */
const SHARED_PREPARATION_PATTERN = /(mesmo forno|mesma fritadeira|mesmo [óo]leo|mesma chapa|cozinha compartilhada|equipamentos? compartilhados?|mesmo ambiente)/i;

/**
 * Separa os avisos de "pode conter" do restante do texto.
 * Assim "pode conter traços de glúten" vira POSSÍVEL contato cruzado,
 * e não ingrediente declarado.
 */
function splitMayContain(text) {
  const warnings = [];
  const cleanText = String(text ?? '').replace(MAY_CONTAIN_PATTERN, (match, _prefix, rest) => {
    warnings.push(rest.trim());
    return ' ';
  });
  return { cleanText, warnings };
}

/** Retorna o parecer mais grave de uma lista. */
function worstVerdict(verdicts) {
  return verdicts.reduce(
    (worst, current) => (VERDICT_SEVERITY[current] > VERDICT_SEVERITY[worst] ? current : worst),
    VERDICTS.NO_DECLARED_CONFLICT,
  );
}

/**
 * Lista os textos do produto que serão analisados, cada um com sua origem.
 * @param {object} product Item no formato do MCP (`getItem`).
 */
function productSources(product, sourceLabel) {
  return [
    { where: 'nome do item', source: sourceLabel, text: splitMayContain(product.itemName).cleanText },
    { where: 'descrição do item', source: sourceLabel, text: splitMayContain(product.itemDescription).cleanText },
  ];
}

/**
 * Analisa os adicionais/opções do item.
 * Adicionais opcionais não tornam o prato incompatível, mas devem ser evitados.
 * Se um grupo OBRIGATÓRIO só tem opções com a substância, o prato conflita.
 */
function analyzeOptionGroups(product, restriction, sourceLabel) {
  const findings = [];

  for (const group of product.optionGroups ?? []) {
    const options = group.options ?? [];
    const conflicting = options.filter((option) => (
      findTerms(`${option.name} ${option.description ?? ''}`, restriction.terms, restriction.ignoredPhrases).present.length > 0
    ));

    if (conflicting.length === 0) {
      continue;
    }

    const isMandatory = (group.minSelections ?? 0) > 0;
    const everyOptionConflicts = conflicting.length === options.length;

    for (const option of conflicting) {
      const { present } = findTerms(`${option.name} ${option.description ?? ''}`, restriction.terms, restriction.ignoredPhrases);
      findings.push({
        kind: isMandatory && everyOptionConflicts ? FINDING_KINDS.INGREDIENT : FINDING_KINDS.ADD_ON,
        terms: present,
        where: `adicional "${option.name}" (grupo "${group.name}"${isMandatory ? ', obrigatório' : ', opcional'})`,
        source: sourceLabel,
        optionId: option.optionId,
      });
    }
  }

  return findings;
}

/**
 * Procura a substância nos OUTROS itens do cardápio do estabelecimento.
 * A presença indica uma possível fonte de contato cruzado, não uma prova.
 */
function analyzeCrossContact(product, restriction, menuItems) {
  const examples = [];

  for (const item of menuItems) {
    if (item.itemId === product.itemId) {
      continue;
    }
    const text = `${item.itemName ?? ''} ${item.itemDescription ?? ''}`;
    const { present } = findTerms(text, restriction.terms, restriction.ignoredPhrases);
    const declaredFree = containsAny(text, restriction.freeClaims).length > 0;
    if (present.length > 0 && !declaredFree) {
      examples.push({ itemName: item.itemName, terms: present });
    }
  }

  return {
    analyzedItems: menuItems.length,
    itemsWithSubstance: examples.length,
    examples: examples.slice(0, MAX_CROSS_CONTACT_EXAMPLES),
  };
}

/**
 * Analisa um produto para UMA restrição.
 * @returns {object} Parecer da restrição com achados, lacunas e explicação.
 */
function analyzeRestriction(product, restriction, context) {
  const sourceLabel = context.kind === 'MERCADO'
    ? `Anúncio do produto no iFood (${product.merchantName ?? 'mercado'})`
    : `Cardápio do estabelecimento no iFood (${product.merchantName ?? 'restaurante'})`;
  const findings = [];
  const missingInfo = [];
  const fullText = `${product.itemName ?? ''} ${product.itemDescription ?? ''}`;

  // 1. Declarações de ausência ("sem glúten") e declarações insuficientes ("zero lactose" para APLV).
  const claims = containsAny(fullText, restriction.freeClaims);
  const insufficientClaims = containsAny(fullText, restriction.claimIsInsufficient);
  const validClaims = claims.filter((claim) => !insufficientClaims.includes(claim));

  for (const claim of validClaims) {
    findings.push({ kind: FINDING_KINDS.FREE_CLAIM, terms: [claim], where: 'nome/descrição', source: sourceLabel });
  }
  for (const claim of insufficientClaims) {
    findings.push({
      kind: FINDING_KINDS.INSUFFICIENT_CLAIM,
      terms: [claim],
      where: 'nome/descrição',
      source: sourceLabel,
      note: restriction.note ?? `"${claim}" não garante a ausência de ${restriction.substance}.`,
    });
  }

  // 2. Etiquetas do iFood (o item apareceu numa busca filtrada por GLUTEN_FREE, por exemplo).
  const matchingTags = (context.declaredTags ?? []).filter((tag) => restriction.ifoodTags.includes(tag));
  for (const tag of matchingTags) {
    findings.push({ kind: FINDING_KINDS.IFOOD_TAG, terms: [tag], where: 'filtro de busca', source: 'Classificação do iFood (itemRestrictions)' });
  }

  // 3. Ingredientes no nome e na descrição.
  //    Se o produto declara ausência, nomes de prato ("lasanha") deixam de contar
  //    e só a substância em si ("trigo") indica contradição.
  const hasValidClaim = validClaims.length > 0 || matchingTags.length > 0;
  const termsToSearch = hasValidClaim ? restriction.coreTerms : restriction.terms;
  for (const source of productSources(product, sourceLabel)) {
    const { present } = findTerms(source.text, termsToSearch, restriction.ignoredPhrases);
    if (present.length > 0) {
      findings.push({
        kind: hasValidClaim ? FINDING_KINDS.CONTRADICTION : FINDING_KINDS.INGREDIENT,
        terms: present,
        where: source.where,
        source: source.source,
      });
    }

    // Termos ambíguos ("creme") são resolvidos por uma declaração de ausência ("sem leite").
    const uncertain = hasValidClaim ? [] : findTerms(source.text, restriction.uncertainTerms, restriction.ignoredPhrases).present
      .filter((term) => !present.includes(term));
    if (uncertain.length > 0) {
      findings.push({ kind: FINDING_KINDS.UNCERTAIN, terms: uncertain, where: source.where, source: source.source });
    }
  }

  // 3b. Avisos declarados pelo estabelecimento: "pode conter" e preparo compartilhado.
  const { warnings } = splitMayContain(fullText);
  for (const warning of warnings) {
    const { present } = findTerms(warning, restriction.terms, restriction.ignoredPhrases);
    if (present.length > 0) {
      findings.push({ kind: FINDING_KINDS.CROSS_CONTACT, terms: present, where: 'aviso "pode conter" no anúncio', source: sourceLabel });
    }
  }
  const sharedPreparation = fullText.match(SHARED_PREPARATION_PATTERN);
  if (sharedPreparation && restriction.rigor !== RIGOR.LOW) {
    findings.push({
      kind: FINDING_KINDS.CROSS_CONTACT,
      terms: [sharedPreparation[0].toLowerCase()],
      where: 'preparo compartilhado declarado pelo estabelecimento',
      source: sourceLabel,
    });
  }

  // 4. Adicionais e opções.
  findings.push(...analyzeOptionGroups(product, restriction, sourceLabel));

  // 5. Confirmações do estabelecimento registradas pelo usuário (evidência adicional).
  const confirmations = (context.confirmations ?? []).filter((confirmation) => (
    confirmation.itemId === product.itemId
    && (!confirmation.restrictionIds?.length || confirmation.restrictionIds.includes(restriction.id))
  ));
  for (const confirmation of confirmations) {
    findings.push({
      kind: FINDING_KINDS.CONFIRMATION,
      terms: [],
      where: 'resposta do estabelecimento',
      source: `Informado pelo usuário em ${confirmation.date}`,
      note: confirmation.summary,
    });
  }

  // 6. Contato cruzado: só para restrições de rigor alto em restaurantes.
  let crossContact = null;
  if (restriction.rigor === RIGOR.HIGH && context.kind !== 'MERCADO') {
    if (Array.isArray(context.menuItems) && context.menuItems.length > 0) {
      crossContact = analyzeCrossContact(product, restriction, context.menuItems);
      if (crossContact.itemsWithSubstance > 0) {
        findings.push({
          kind: FINDING_KINDS.CROSS_CONTACT,
          terms: [...new Set(crossContact.examples.flatMap((example) => example.terms))].slice(0, 6),
          where: `${crossContact.itemsWithSubstance} de ${crossContact.analyzedItems} itens do cardápio analisados`,
          source: 'Cardápio do estabelecimento no iFood',
        });
      }
    } else {
      missingInfo.push('Não foi possível consultar o restante do cardápio para avaliar contato cruzado.');
    }
  }

  // 7. Lacunas de informação.
  const hasConfirmation = confirmations.length > 0;
  const description = normalizeText(product.itemDescription);
  if (description.length < MIN_DESCRIPTIVE_LENGTH && !hasConfirmation) {
    missingInfo.push(context.kind === 'MERCADO'
      ? 'O anúncio não traz a lista de ingredientes nem os avisos de alergênicos ("pode conter"). Confira o rótulo.'
      : 'A descrição do item não traz a lista completa de ingredientes.');
  }
  if (restriction.rigor === RIGOR.HIGH && !hasConfirmation) {
    missingInfo.push(context.kind === 'MERCADO'
      ? `Avisos de "pode conter ${restriction.substance}" só aparecem na embalagem; o iFood não informa.`
      : 'O iFood não informa procedimentos de preparo, armazenamento ou equipamentos compartilhados.');
  }

  const verdict = decideVerdict(restriction, findings, missingInfo, { hasValidClaim, hasConfirmation });

  return {
    restrictionId: restriction.id,
    label: restriction.label,
    type: restriction.type,
    rigor: restriction.rigor,
    substance: restriction.substance,
    verdict,
    findings,
    missingInfo,
    crossContact,
    explanation: explain(restriction, verdict, findings),
  };
}

/**
 * Regras de decisão do parecer de uma restrição.
 * A ordem importa: conflitos declarados vencem qualquer declaração de ausência.
 */
function decideVerdict(restriction, findings, missingInfo, { hasValidClaim, hasConfirmation }) {
  const has = (kind) => findings.some((finding) => finding.kind === kind);

  if (has(FINDING_KINDS.INGREDIENT)) {
    return VERDICTS.CONFLICT;
  }
  if (has(FINDING_KINDS.CONTRADICTION)) {
    // Informação contraditória: declara ausência, mas cita a substância.
    return VERDICTS.RISK;
  }
  if (has(FINDING_KINDS.INSUFFICIENT_CLAIM) && !hasValidClaim && !hasConfirmation) {
    // Ex.: APLV + "zero lactose" — a declaração não cobre a restrição.
    return VERDICTS.RISK;
  }
  if (has(FINDING_KINDS.UNCERTAIN) && !hasConfirmation) {
    return VERDICTS.RISK;
  }
  if (has(FINDING_KINDS.CROSS_CONTACT) && !hasConfirmation) {
    return VERDICTS.RISK;
  }

  // Sem conflito encontrado. Preferências aceitam a ausência de conflito declarado.
  if (restriction.rigor === RIGOR.LOW) {
    return VERDICTS.NO_DECLARED_CONFLICT;
  }
  // Para intolerâncias e alergias, é preciso alguma evidência positiva.
  if (hasValidClaim || hasConfirmation) {
    return VERDICTS.NO_DECLARED_CONFLICT;
  }
  if (restriction.rigor === RIGOR.MEDIUM && missingInfo.length === 0) {
    return VERDICTS.NO_DECLARED_CONFLICT;
  }
  return VERDICTS.INSUFFICIENT;
}

/** Deixa só a primeira letra minúscula, preservando siglas: "Alergia (APLV)" → "alergia (APLV)". */
function lowerFirst(text) {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** Gera uma explicação curta e determinística para a interface. */
function explain(restriction, verdict, findings) {
  const termsOf = (kind) => [...new Set(findings.filter((finding) => finding.kind === kind).flatMap((finding) => finding.terms))];
  const typeLabel = {
    [RESTRICTION_TYPES.ALLERGY]: 'alergia',
    [RESTRICTION_TYPES.INTOLERANCE]: 'intolerância',
    [RESTRICTION_TYPES.CELIAC]: 'doença celíaca',
    [RESTRICTION_TYPES.PREFERENCE]: 'preferência alimentar',
  }[restriction.type];

  switch (verdict) {
    case VERDICTS.CONFLICT:
      return `Incompatível com ${lowerFirst(restriction.label)} (${typeLabel}): o estabelecimento cita ${termsOf(FINDING_KINDS.INGREDIENT).join(', ')}.`;
    case VERDICTS.RISK: {
      const reasons = [];
      if (termsOf(FINDING_KINDS.CONTRADICTION).length) {
        reasons.push(`informação contraditória (declara ausência, mas cita ${termsOf(FINDING_KINDS.CONTRADICTION).join(', ')})`);
      }
      if (termsOf(FINDING_KINDS.INSUFFICIENT_CLAIM).length && !termsOf(FINDING_KINDS.FREE_CLAIM).length) {
        reasons.push(`"${termsOf(FINDING_KINDS.INSUFFICIENT_CLAIM).join('", "')}" não garante ausência de ${restriction.substance}`);
      }
      if (termsOf(FINDING_KINDS.UNCERTAIN).length) {
        reasons.push(`ingredientes que podem conter ${restriction.substance} (${termsOf(FINDING_KINDS.UNCERTAIN).join(', ')})`);
      }
      if (findings.some((finding) => finding.kind === FINDING_KINDS.CROSS_CONTACT)) {
        reasons.push(`o cardápio tem outros itens com ${restriction.substance}, o que é uma possível fonte de contato cruzado (não é prova de contaminação)`);
      }
      return `Possível risco para ${lowerFirst(restriction.label)}: ${reasons.join('; ')}.`;
    }
    case VERDICTS.INSUFFICIENT:
      return `Não há informações suficientes para avaliar ${lowerFirst(restriction.label)}. Nenhum ingrediente incompatível foi citado, mas isso não garante a ausência de ${restriction.substance}.`;
    default:
      return `Nenhum conflito com ${lowerFirst(restriction.label)} nas informações disponíveis. Isso não é uma garantia de segurança.`;
  }
}

/**
 * Analisa um produto para todas as restrições do usuário.
 *
 * @param {object} product Item no formato do MCP (`getItem`): itemId, itemName,
 *   itemDescription, merchantId, merchantName, optionGroups.
 * @param {object[]} restrictions Restrições já resolvidas (`resolveRestriction`).
 * @param {object} [context]
 * @param {'RESTAURANTE'|'MERCADO'} [context.kind]
 * @param {object[]} [context.menuItems] Outros itens do cardápio (contato cruzado).
 * @param {string[]} [context.declaredTags] Etiquetas `itemRestrictions` do iFood.
 * @param {object[]} [context.confirmations] Confirmações do estabelecimento.
 */
export function analyzeProduct(product, restrictions, context = {}) {
  const normalizedContext = { kind: 'RESTAURANTE', ...context };
  const results = restrictions.map((restriction) => analyzeRestriction(product, restriction, normalizedContext));
  const verdict = results.length > 0 ? worstVerdict(results.map((result) => result.verdict)) : VERDICTS.INSUFFICIENT;

  // Adicionais a evitar, para mostrar na revisão do pedido.
  const addOnsToAvoid = [...new Map(results
    .flatMap((result) => result.findings)
    .filter((finding) => finding.kind === FINDING_KINDS.ADD_ON)
    .map((finding) => [finding.optionId, finding.where])).values()];

  const canProceed = verdict === VERDICTS.NO_DECLARED_CONFLICT;

  return {
    itemId: product.itemId,
    itemName: product.itemName,
    merchantId: product.merchantId,
    merchantName: product.merchantName,
    kind: normalizedContext.kind,
    verdict,
    canProceed,
    restrictions: results,
    addOnsToAvoid,
    missingInfo: [...new Set(results.flatMap((result) => result.missingInfo))],
    alternatives: canProceed ? [] : Object.values(ALTERNATIVES),
    disclaimer: DISCLAIMER,
    analyzedAt: new Date().toISOString(),
  };
}

/**
 * Verifica os ingredientes de uma receita gerada pela IA.
 * Usado como "trava" determinística: a receita não é exibida como compatível
 * se algum ingrediente cita a substância restrita.
 *
 * @param {{ nome: string, industrializado?: boolean }[]} ingredients
 * @param {object[]} restrictions
 */
export function analyzeRecipeIngredients(ingredients, restrictions) {
  return ingredients.map((ingredient) => {
    const conflicts = [];
    const uncertain = [];

    for (const restriction of restrictions) {
      const declaredFree = containsAny(ingredient.nome, restriction.freeClaims).length > 0;
      const terms = declaredFree ? restriction.coreTerms : restriction.terms;
      const { present } = findTerms(ingredient.nome, terms, restriction.ignoredPhrases);
      if (present.length > 0) {
        conflicts.push({ restrictionId: restriction.id, label: restriction.label, terms: present });
      }
      const maybe = findTerms(ingredient.nome, restriction.uncertainTerms, restriction.ignoredPhrases).present;
      if (maybe.length > 0) {
        uncertain.push({ restrictionId: restriction.id, label: restriction.label, terms: maybe });
      }
    }

    const needsLabelCheck = Boolean(ingredient.industrializado)
      && restrictions.some((restriction) => restriction.rigor !== RIGOR.LOW);

    return {
      nome: ingredient.nome,
      conflicts,
      uncertain,
      needsLabelCheck,
      status: conflicts.length > 0 ? VERDICTS.CONFLICT : (uncertain.length > 0 ? VERDICTS.RISK : VERDICTS.NO_DECLARED_CONFLICT),
    };
  });
}
