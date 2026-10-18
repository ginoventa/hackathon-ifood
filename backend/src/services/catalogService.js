/**
 * Consultas ao catálogo do iFood (busca, detalhes e cardápio completo),
 * já adaptadas ao formato usado pelo agente e pela interface.
 */

import { ifood } from '../ifood/index.js';
import { rememberDeclaredTags } from '../sessions/sessionStore.js';
import { userLocation } from './accountService.js';

/** Páginas de cardápio consultadas para avaliar contato cruzado (25 itens cada). */
const MENU_PAGES = 3;
const MENU_PAGE_SIZE = 25;

/** Cache de cardápios: evita refazer a mesma varredura em poucos minutos. */
const MENU_CACHE_TTL_MS = 10 * 60 * 1000;
const menuCache = new Map();

/** Resume um resultado de busca do tipo ITEM. */
export function summarizeItemResult(result) {
  return {
    itemId: result.itemId,
    itemName: result.itemName,
    imageUrl: result.itemImageUrl ?? null,
    unitPrice: result.unitPrice,
    promotionalUnitPrice: result.promotionalUnitPrice ?? result.unitPrice,
    merchantId: result.merchant?.merchantId,
    merchantName: result.merchant?.merchantName,
    merchantRating: result.merchant?.reviewRating ?? null,
    distanceKm: result.merchant?.straightLineDistanceKm ?? null,
    isOpen: result.merchant?.isOpen ?? true,
    deliveryFee: result.merchant?.deliveryMethod?.promotionalFee ?? result.merchant?.deliveryMethod?.fee ?? null,
    deliveryMinutes: result.merchant?.deliveryMethod?.estimatedMinutes ?? null,
    minimumOrderAmount: result.merchant?.minimumOrderAmount ?? null,
  };
}

/** Resume um resultado de busca do tipo MERCHANT. */
export function summarizeMerchantResult(result) {
  return {
    merchantId: result.merchantId,
    merchantName: result.merchantName,
    logoUrl: result.merchantLogoUrl ?? null,
    rating: result.reviewRating ?? null,
    distanceKm: result.straightLineDistanceKm ?? null,
    isOpen: result.isOpen ?? true,
    deliveryFee: result.deliveryMethod?.promotionalFee ?? result.deliveryMethod?.fee ?? null,
    deliveryMinutes: result.deliveryMethod?.estimatedMinutes ?? null,
    minimumOrderAmount: result.minimumOrderAmount ?? null,
  };
}

/**
 * Busca ofertas por texto. Se a busca usou filtros `itemRestrictions`, os
 * itens retornados ficam marcados na sessão com essas etiquetas do iFood.
 *
 * @param {object} session
 * @param {object} params
 * @param {string} params.query
 * @param {string} [params.merchantType]
 * @param {'ITEM'|'MERCHANT'} [params.resultKind]
 * @param {object} [params.refinements]
 * @param {number} [params.pageSize]
 */
export async function searchOffers(session, { query, merchantType, resultKind = 'ITEM', refinements = {}, pageSize = 8 }) {
  const response = await ifood.callTool('searchOffers', {
    query,
    merchantType,
    resultKind,
    refinements,
    pageSize,
    userLocation: userLocation(session),
  });

  const results = response.results ?? [];
  if (resultKind === 'ITEM') {
    rememberDeclaredTags(session, results.map((result) => result.itemId), refinements.itemRestrictions);
    return { kind: 'ITEM', items: results.map(summarizeItemResult), hasMore: Boolean(response.hasMore) };
  }
  return { kind: 'MERCHANT', merchants: results.map(summarizeMerchantResult), hasMore: Boolean(response.hasMore) };
}

/**
 * Detalhes completos de um item (descrição e adicionais). Guarda na sessão.
 * @returns {Promise<object>} Item no formato do MCP (`getItem`).
 */
export async function getItemDetails(session, merchantId, itemId) {
  const item = await ifood.callTool('getItem', { merchantId, itemId, userLocation: userLocation(session) });
  session.products.set(itemId, item);
  return item;
}

/**
 * Lê o cardápio do estabelecimento (até MENU_PAGES páginas), usado para
 * procurar possíveis fontes de contato cruzado.
 * @param {object} session
 * @param {string} merchantId
 * @param {string} merchantType
 * @returns {Promise<{ itemId: string, itemName: string }[]>}
 */
export async function getMenuItems(session, merchantId, merchantType = 'RESTAURANT') {
  const cached = menuCache.get(merchantId);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.items;
  }

  const items = [];
  let nextPageToken;
  for (let page = 0; page < MENU_PAGES; page += 1) {
    const response = await ifood.callTool('browseOffers', {
      merchantType,
      resultKind: 'ITEM',
      pageSize: MENU_PAGE_SIZE,
      refinements: { merchantId },
      userLocation: userLocation(session),
      ...(nextPageToken ? { nextPageToken } : {}),
    });
    items.push(...(response.results ?? []).map((result) => ({ itemId: result.itemId, itemName: result.itemName })));
    nextPageToken = response.nextPageToken;
    if (!response.hasMore || !nextPageToken) {
      break;
    }
  }

  menuCache.set(merchantId, { items, expiresAt: Date.now() + MENU_CACHE_TTL_MS });
  return items;
}
