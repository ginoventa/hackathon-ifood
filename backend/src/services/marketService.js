/**
 * Fluxo de mercado (seção 2): valida a receita adaptada, busca os ingredientes
 * nos mercados do iFood e compara combinações de produtos e estabelecimentos.
 */

import { toIfoodItemRestrictions } from '../restrictions/catalog.js';
import { analyzeProduct, analyzeRecipeIngredients, VERDICTS } from '../restrictions/analyzer.js';
import { normalizeText } from '../restrictions/textMatching.js';
import { ValidationError } from '../utils/errors.js';
import { getItemDetails, searchOffers } from './catalogService.js';

/** Quantos resultados buscar por ingrediente. */
const RESULTS_PER_INGREDIENT = 10;

/** Quantos mercados entram na comparação final. */
const MERCHANTS_TO_COMPARE = 3;

/** Ordem de preferência entre pareceres (menor é melhor). */
const VERDICT_RANK = {
  [VERDICTS.NO_DECLARED_CONFLICT]: 0,
  [VERDICTS.INSUFFICIENT]: 1,
  [VERDICTS.RISK]: 2,
  [VERDICTS.CONFLICT]: 3,
};

/** Palavras que não identificam o produto ("massa SEM glúten", "molho DE tomate"). */
const NON_HEAD_WORDS = new Set(['de', 'da', 'do', 'com', 'sem', 'e', 'para', 'tipo', 'zero', 'light']);

/**
 * Palavra principal do termo de busca (ex.: "queijo" em "queijo vegetal").
 * Em português, o substantivo principal costuma vir primeiro.
 */
function headWord(searchTerm) {
  return normalizeText(searchTerm).split(' ').find((word) => word.length > 2 && !NON_HEAD_WORDS.has(word)) ?? '';
}

/**
 * Verifica se o produto é mesmo o ingrediente buscado: o nome precisa conter
 * a palavra principal. Evita trocar "queijo vegetal" por "bebida vegetal"
 * só porque é mais barato.
 */
function isRelevant(item, searchTerm) {
  const head = headWord(searchTerm);
  if (!head) {
    return true;
  }
  const stem = head.replace(/(es|s)$/, '');
  return normalizeText(item.itemName).split(' ').some((word) => word.replace(/(es|s)$/, '') === stem);
}

/** Arredonda valores em reais. */
const money = (value) => Math.round(value * 100) / 100;

/**
 * Registra a receita adaptada gerada pela LLM e aplica a trava determinística
 * nos ingredientes. Se algum ingrediente conflitar, a receita NÃO é aceita.
 *
 * @param {object} session
 * @param {object} recipe Receita no formato da ferramenta `registrar_receita`.
 * @returns {{ accepted: boolean, recipe: object, conflicts: object[] }}
 */
export function registerRecipe(session, recipe) {
  if (!recipe?.titulo || !Array.isArray(recipe.ingredientes) || recipe.ingredientes.length === 0) {
    throw new ValidationError('A receita precisa de título e ingredientes.');
  }

  const ingredientChecks = analyzeRecipeIngredients(recipe.ingredientes, session.restrictions);
  const conflicts = ingredientChecks.filter((check) => check.status === VERDICTS.CONFLICT);
  const accepted = conflicts.length === 0;

  const normalized = {
    titulo: recipe.titulo,
    porcoes: recipe.porcoes ?? null,
    tempoMinutos: recipe.tempoMinutos ?? null,
    ingredientes: recipe.ingredientes.map((ingredient, index) => ({
      ...ingredient,
      quantidadeCompra: Math.max(1, Math.round(Number(ingredient.quantidadeCompra) || 1)),
      verificacao: ingredientChecks[index],
    })),
    substituicoes: recipe.substituicoes ?? [],
    modoDePreparo: recipe.modoDePreparo ?? [],
    cuidados: recipe.cuidados ?? [],
  };

  if (accepted) {
    session.recipe = normalized;
  }
  return { accepted, recipe: normalized, conflicts };
}

/**
 * Escolhe o melhor candidato de uma lista: parecer mais favorável, depois menor preço.
 * Produtos com CONFLITO nunca são escolhidos.
 */
function bestCandidate(candidates) {
  return candidates
    .filter((candidate) => candidate.analysis.verdict !== VERDICTS.CONFLICT)
    .sort((a, b) => (VERDICT_RANK[a.analysis.verdict] - VERDICT_RANK[b.analysis.verdict]) || (a.price - b.price))[0] ?? null;
}

/** Analisa um resultado de busca de mercado usando apenas o nome (rápido). */
function quickAnalyze(session, item) {
  return analyzeProduct(
    { itemId: item.itemId, itemName: item.itemName, itemDescription: '', merchantName: item.merchantName },
    session.restrictions,
    { kind: 'MERCADO', declaredTags: session.declaredTags.get(item.itemId) ?? [] },
  );
}

/**
 * Busca um ingrediente nos mercados.
 *
 * Faz, em paralelo, uma busca sem filtros e uma busca para CADA filtro de
 * restrição do iFood (ex.: GLUTEN_FREE). Os filtros não são combinados numa
 * única busca porque o iFood os aplica juntos (E lógico), o que esconderia
 * produtos válidos, como carne moída para quem é celíaco e tem APLV.
 * Os itens achados com um filtro ficam marcados com essa etiqueta do iFood.
 */
async function searchIngredient(session, ingredient, merchantId) {
  const tags = toIfoodItemRestrictions(session.restrictions);
  const baseRefinements = { sort: 'PRICE', ...(merchantId ? { merchantId } : {}) };
  const query = ingredient.busca || ingredient.nome;
  const search = (refinements) => searchOffers(session, {
    query, merchantType: 'GROCERIES', resultKind: 'ITEM', pageSize: RESULTS_PER_INGREDIENT, refinements,
  }).catch(() => ({ items: [] }));

  const responses = await Promise.all([
    search(baseRefinements),
    ...tags.map((tag) => search({ ...baseRefinements, itemRestrictions: [tag] })),
  ]);

  // Remove duplicados mantendo a ordem de relevância da busca.
  const unique = new Map();
  for (const item of responses.flatMap((response) => response.items)) {
    if (!unique.has(item.itemId)) {
      unique.set(item.itemId, item);
    }
  }

  return [...unique.values()]
    .filter((item) => item.isOpen !== false && isRelevant(item, query))
    .map((item) => ({ ...item, price: item.promotionalUnitPrice ?? item.unitPrice, analysis: quickAnalyze(session, item) }));
}

/** Monta o resumo de um mercado com o melhor produto para cada ingrediente. */
function buildMerchantPlan(merchant, ingredients, candidatesByIngredient) {
  const items = [];
  const missing = [];

  ingredients.forEach((ingredient, index) => {
    const options = candidatesByIngredient[index].filter((candidate) => candidate.merchantId === merchant.merchantId);
    const chosen = bestCandidate(options);
    if (!chosen) {
      missing.push(ingredient.nome);
      return;
    }
    items.push({
      ingrediente: ingredient.nome,
      quantidade: ingredient.quantidadeCompra,
      itemId: chosen.itemId,
      itemName: chosen.itemName,
      imageUrl: chosen.imageUrl,
      unitPrice: chosen.price,
      totalPrice: money(chosen.price * ingredient.quantidadeCompra),
      verdict: chosen.analysis.verdict,
      analysis: chosen.analysis,
    });
  });

  const subtotal = money(items.reduce((sum, item) => sum + item.totalPrice, 0));
  const deliveryFee = merchant.deliveryFee ?? 0;
  return {
    merchantId: merchant.merchantId,
    merchantName: merchant.merchantName,
    rating: merchant.merchantRating,
    deliveryMinutes: merchant.deliveryMinutes,
    minimumOrderAmount: merchant.minimumOrderAmount,
    coverage: items.length,
    totalIngredients: ingredients.length,
    missing,
    items,
    subtotal,
    deliveryFee,
    total: money(subtotal + deliveryFee),
    meetsMinimum: merchant.minimumOrderAmount == null || subtotal >= merchant.minimumOrderAmount,
  };
}

/** Ordena planos: mais ingredientes cobertos, depois menor custo total. */
const comparePlans = (a, b) => (b.coverage - a.coverage) || (a.total - b.total);

/**
 * Busca e compara os ingredientes da receita atual nos mercados do iFood.
 * @param {object} session
 * @returns {Promise<object>} Plano de compra com o mercado recomendado e alternativas.
 */
export async function planGroceryShopping(session) {
  const recipe = session.recipe;
  if (!recipe) {
    throw new ValidationError('Primeiro preciso montar a receita adaptada.');
  }
  // Itens que a pessoa já tem em casa não entram na compra.
  const ingredients = recipe.ingredientes.filter((ingredient) => !ingredient.jaTenhoEmCasa);

  // 1. Busca geral de cada ingrediente, em paralelo.
  const candidatesByIngredient = await Promise.all(ingredients.map((ingredient) => searchIngredient(session, ingredient)));

  // 2. Agrupa por mercado e escolhe os mais promissores.
  const merchants = new Map();
  candidatesByIngredient.flat().forEach((candidate) => merchants.set(candidate.merchantId, candidate));
  let plans = [...merchants.values()]
    .map((merchant) => buildMerchantPlan(merchant, ingredients, candidatesByIngredient))
    .sort(comparePlans)
    .slice(0, MERCHANTS_TO_COMPARE);

  // 3. Nos mercados finalistas, procura especificamente os ingredientes que faltaram.
  await Promise.all(plans.map(async (plan) => {
    const missingIndexes = ingredients
      .map((ingredient, index) => (plan.missing.includes(ingredient.nome) ? index : -1))
      .filter((index) => index >= 0);
    const extra = await Promise.all(missingIndexes.map((index) => searchIngredient(session, ingredients[index], plan.merchantId)));
    missingIndexes.forEach((ingredientIndex, position) => candidatesByIngredient[ingredientIndex].push(...extra[position]));
  }));
  plans = plans
    .map((plan) => buildMerchantPlan(merchants.get(plan.merchantId), ingredients, candidatesByIngredient))
    .sort(comparePlans);

  // 4. Reanalisa os produtos do mercado recomendado com a descrição completa.
  //    Se a descrição revelar conflito, o produto sai do plano.
  const recommended = plans[0] ?? null;
  if (recommended) {
    await Promise.all(recommended.items.map(async (item) => {
      try {
        const details = await getItemDetails(session, recommended.merchantId, item.itemId);
        item.analysis = analyzeProduct(details, session.restrictions, {
          kind: 'MERCADO',
          declaredTags: session.declaredTags.get(item.itemId) ?? [],
        });
        item.verdict = item.analysis.verdict;
      } catch {
        // Mantém a análise rápida (só pelo nome) se o detalhe falhar.
      }
    }));

    const conflicting = recommended.items.filter((item) => item.verdict === VERDICTS.CONFLICT);
    if (conflicting.length > 0) {
      recommended.items = recommended.items.filter((item) => item.verdict !== VERDICTS.CONFLICT);
      recommended.missing.push(...conflicting.map((item) => item.ingrediente));
      recommended.coverage = recommended.items.length;
      recommended.subtotal = money(recommended.items.reduce((sum, item) => sum + item.totalPrice, 0));
      recommended.total = money(recommended.subtotal + recommended.deliveryFee);
      recommended.meetsMinimum = recommended.minimumOrderAmount == null || recommended.subtotal >= recommended.minimumOrderAmount;
    }
  }

  const plan = {
    recipeTitle: recipe.titulo,
    recommendedMerchantId: recommended?.merchantId ?? null,
    merchants: plans,
    ingredientsWithoutOption: ingredients
      .map((ingredient) => ingredient.nome)
      .filter((name) => plans.every((merchantPlan) => merchantPlan.missing.includes(name))),
    createdAt: new Date().toISOString(),
  };
  session.marketPlan = plan;
  return plan;
}
