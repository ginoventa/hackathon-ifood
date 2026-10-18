/**
 * Ferramentas de busca no catálogo do iFood (seção 1.2).
 *
 * Os resultados são ordenados priorizando a compatibilidade com as
 * restrições: uma pré-análise rápida (só pelo nome) separa itens com
 * conflito evidente, que vão para o fim da lista com um aviso.
 */

import { toIfoodItemRestrictions } from '../../restrictions/catalog.js';
import { analyzeProduct, VERDICTS } from '../../restrictions/analyzer.js';
import { searchOffers } from '../../services/catalogService.js';

/**
 * Pré-análise só pelo nome: é um indicativo para ordenar, não um parecer final.
 * Usa apenas a substância em si ("trigo", "leite"): nomes de prato como
 * "lasanha" podem ter versões adaptadas e só são julgados na análise completa.
 */
function quickVerdict(session, item) {
  if (session.restrictions.length === 0) {
    return null;
  }
  const coreOnly = session.restrictions.map((restriction) => ({ ...restriction, terms: restriction.coreTerms }));
  const analysis = analyzeProduct(
    { itemId: item.itemId, itemName: item.itemName, merchantName: item.merchantName },
    coreOnly,
    { kind: 'RESTAURANTE', menuItems: [], declaredTags: session.declaredTags.get(item.itemId) ?? [] },
  );
  return analysis.verdict;
}

/** Ordem de exibição: itens com conflito aparente vão para o fim. */
const DISPLAY_RANK = {
  [VERDICTS.NO_DECLARED_CONFLICT]: 0,
  [VERDICTS.INSUFFICIENT]: 1,
  [VERDICTS.RISK]: 2,
  [VERDICTS.CONFLICT]: 3,
};

/** Executa a busca e monta a resposta da ferramenta (cartão + resumo). */
async function runSearch(session, params, title) {
  const result = await searchOffers(session, params);

  if (result.kind === 'MERCHANT') {
    return {
      output: { lojas: result.merchants.map((merchant) => ({ merchantId: merchant.merchantId, nome: merchant.merchantName })) },
      card: { type: 'merchants', data: { title, merchants: result.merchants } },
    };
  }

  const items = result.items
    .map((item) => ({ ...item, quickVerdict: quickVerdict(session, item) }))
    .sort((a, b) => (DISPLAY_RANK[a.quickVerdict] ?? 1) - (DISPLAY_RANK[b.quickVerdict] ?? 1));

  return {
    output: {
      total: items.length,
      itens: items.map((item) => ({
        itemId: item.itemId,
        merchantId: item.merchantId,
        nome: item.itemName,
        loja: item.merchantName,
        preco: item.promotionalUnitPrice,
        preAnalisePeloNome: item.quickVerdict,
      })),
      observacao: 'A pré-análise usa só o nome. A análise completa é feita com analisar_produto.',
    },
    card: { type: 'options', data: { title, items, filtersUsed: params.refinements?.itemRestrictions ?? [] } },
  };
}

export const searchOptionsTool = {
  declaration: {
    name: 'buscar_opcoes',
    description: 'Busca pratos (ITEM) ou restaurantes (MERCHANT) no iFood perto do usuário. Use para o pedido em restaurante.',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        consulta: { type: 'string', description: 'Só a parte descritiva, ex.: "lasanha", "pizza".' },
        tipoResultado: { type: 'string', enum: ['ITEM', 'MERCHANT'], description: 'Padrão: ITEM.' },
        priorizarComFiltrosDoIfood: {
          type: 'boolean',
          description: 'Usa os filtros do iFood equivalentes às restrições (ex.: GLUTEN_FREE). Padrão: true. Use false se vierem poucos resultados.',
        },
        precoMaximo: { type: 'number' },
        ordenarPor: { type: 'string', enum: ['RELEVANCE', 'PRICE', 'DISTANCE', 'DELIVERY_TIME', 'DELIVERY_FEE'] },
        apenasAbertos: { type: 'boolean', description: 'Padrão: true.' },
      },
      required: ['consulta'],
    },
  },

  async execute(session, args) {
    const useFilters = args.priorizarComFiltrosDoIfood !== false;
    const tags = useFilters ? toIfoodItemRestrictions(session.restrictions) : [];
    const refinements = {
      onlyOpen: args.apenasAbertos !== false,
      ...(tags.length ? { itemRestrictions: tags } : {}),
      ...(args.precoMaximo ? { maxItemPrice: args.precoMaximo } : {}),
      ...(args.ordenarPor ? { sort: args.ordenarPor } : {}),
    };

    return runSearch(session, {
      query: args.consulta,
      merchantType: 'RESTAURANT',
      resultKind: args.tipoResultado ?? 'ITEM',
      refinements,
      pageSize: 8,
    }, `Opções para "${args.consulta}"`);
  },
};

export const merchantMenuTool = {
  declaration: {
    name: 'ver_cardapio_da_loja',
    description: 'Lista itens de um restaurante específico, opcionalmente filtrando por texto.',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        merchantId: { type: 'string' },
        consulta: { type: 'string', description: 'Texto para filtrar o cardápio. Opcional.' },
      },
      required: ['merchantId'],
    },
  },

  async execute(session, { merchantId, consulta }) {
    return runSearch(session, {
      query: consulta || 'pratos',
      merchantType: 'RESTAURANT',
      resultKind: 'ITEM',
      refinements: { merchantId },
      pageSize: 12,
    }, consulta ? `Cardápio: "${consulta}"` : 'Cardápio da loja');
  },
};
