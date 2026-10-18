/**
 * Cliente simulado do MCP do iFood (IFOOD_MODE=mock).
 *
 * Implementa as mesmas ferramentas usadas pelo Ailo e devolve respostas no
 * formato do MCP real. Serve para desenvolver e demonstrar sem conta do iFood
 * e sem gerar pedidos reais. Carrinhos e pedidos ficam apenas em memória.
 */

import { randomUUID } from 'node:crypto';

import { IfoodToolError } from '../../utils/errors.js';
import { normalizeText } from '../../restrictions/textMatching.js';
import { MOCK_ADDRESSES, MOCK_MERCHANTS, MOCK_PAYMENT_METHODS, MOCK_USER } from './mockData.js';

const DEFAULT_PAGE_SIZE = 10;
const MAX_PAGE_SIZE = 25;

/** Remove o plural simples para comparar "tomates" com "tomate". */
function stem(word) {
  return word.length > 3 ? word.replace(/(es|s)$/, '') : word;
}

/** Palavras irrelevantes ignoradas na busca textual. */
const STOP_WORDS = new Set(['de', 'da', 'do', 'das', 'dos', 'com', 'sem', 'e', 'para', 'a', 'o', 'em', 'kg', 'g', 'ml', 'l']);

/** Pontua um texto pela quantidade de palavras da busca que ele contém. */
function relevance(query, text) {
  const words = normalizeText(query).split(' ').filter((word) => word && !STOP_WORDS.has(word)).map(stem);
  const haystack = new Set(normalizeText(text).split(' ').map(stem));
  if (words.length === 0) {
    return 1;
  }
  const matches = words.filter((word) => haystack.has(word)).length;
  return matches / words.length;
}

/** Resumo do estabelecimento, no formato usado dentro dos resultados de busca. */
function merchantSummary(merchant) {
  return {
    deliveryMethod: {
      deliveryMethodId: 'DEFAULT',
      deliveryMethodMode: 'DELIVERY',
      estimatedMinutes: merchant.estimatedMinutes,
      fee: merchant.deliveryFee,
      promotionalFee: merchant.deliveryFee,
    },
    isOpen: true,
    merchantId: merchant.merchantId,
    merchantLogoUrl: merchant.logo,
    merchantName: merchant.merchantName,
    minimumOrderAmount: merchant.minimumOrderAmount,
    ratingCount: merchant.ratingCount,
    reviewRating: merchant.reviewRating,
    straightLineDistanceKm: merchant.straightLineDistanceKm,
  };
}

/** Item no formato de resultado de busca (sem descrição, como no MCP real). */
function itemResult(merchant, item) {
  return {
    itemId: item.itemId,
    itemImageUrl: item.image ?? merchant.logo,
    itemName: item.itemName,
    merchant: merchantSummary(merchant),
    promotionalUnitPrice: item.promotionalUnitPrice ?? item.unitPrice,
    unitPrice: item.unitPrice,
  };
}

/** Pagina uma lista usando um token opaco (base64 do deslocamento). */
function paginate(list, pageSize, nextPageToken) {
  const size = Math.min(Math.max(Number(pageSize) || DEFAULT_PAGE_SIZE, 1), MAX_PAGE_SIZE);
  const offset = nextPageToken ? Number(Buffer.from(nextPageToken, 'base64').toString()) || 0 : 0;
  const page = list.slice(offset, offset + size);
  const hasMore = offset + size < list.length;
  return {
    results: page,
    hasMore,
    ...(hasMore ? { nextPageToken: Buffer.from(String(offset + size)).toString('base64') } : {}),
  };
}

/** Ordena resultados de acordo com `refinements.sort`. */
function sortResults(results, sort) {
  const priceOf = (result) => result.promotionalUnitPrice ?? result.unitPrice ?? 0;
  const merchantOf = (result) => result.merchant ?? result;
  const comparators = {
    PRICE: (a, b) => priceOf(a) - priceOf(b),
    DISTANCE: (a, b) => merchantOf(a).straightLineDistanceKm - merchantOf(b).straightLineDistanceKm,
    DELIVERY_FEE: (a, b) => merchantOf(a).deliveryMethod.fee - merchantOf(b).deliveryMethod.fee,
    DELIVERY_TIME: (a, b) => merchantOf(a).deliveryMethod.estimatedMinutes.max - merchantOf(b).deliveryMethod.estimatedMinutes.max,
  };
  return comparators[sort] ? [...results].sort(comparators[sort]) : results;
}

export class MockIfoodClient {
  mode = 'mock';

  /** Carrinhos em memória, indexados pelo cartId. */
  #carts = new Map();

  /** Pedidos em memória, indexados pelo orderId. */
  #orders = new Map();

  async isAuthenticated() {
    return true;
  }

  async disconnect() {}

  /**
   * Executa uma ferramenta simulada.
   * @param {string} name
   * @param {object} args
   */
  async callTool(name, args = {}) {
    const handler = this.#handlers[name];
    if (!handler) {
      throw new IfoodToolError(name, 'ferramenta não disponível no modo de demonstração.');
    }
    return handler(args);
  }

  // ------------------------------------------------------------------ Busca

  /** Aplica os filtros comuns de busca/navegação sobre todo o catálogo. */
  #filterOffers({ query = '', merchantType, resultKind = 'MERCHANT', refinements = {} }) {
    const restrictions = refinements.itemRestrictions ?? [];
    const merchants = MOCK_MERCHANTS
      .filter((merchant) => !merchantType || merchant.merchantType === merchantType)
      .filter((merchant) => !refinements.merchantId || merchant.merchantId === refinements.merchantId)
      .filter((merchant) => refinements.maxDeliveryFee === undefined || merchant.deliveryFee <= refinements.maxDeliveryFee)
      .filter((merchant) => refinements.minRating === undefined || merchant.reviewRating >= refinements.minRating)
      .filter((merchant) => refinements.maxDistanceKm === undefined || merchant.straightLineDistanceKm <= refinements.maxDistanceKm);

    const items = [];
    for (const merchant of merchants) {
      for (const item of merchant.items) {
        const score = query ? relevance(query, `${item.itemName} ${item.itemDescription}`) : 1;
        const matchesRestrictions = restrictions.every((tag) => item.tags?.includes(tag));
        const withinPrice = refinements.maxItemPrice === undefined || item.unitPrice <= refinements.maxItemPrice;
        // Buscas curtas exigem todas as palavras; buscas longas, a maioria.
        const minimumScore = query && normalizeText(query).split(' ').length > 2 ? 0.6 : 1;
        if (score >= minimumScore && matchesRestrictions && withinPrice) {
          items.push({ score, merchant, item });
        }
      }
    }
    items.sort((a, b) => b.score - a.score);

    if (resultKind === 'ITEM') {
      return sortResults(items.map(({ merchant, item }) => itemResult(merchant, item)), refinements.sort);
    }

    // Para MERCHANT, devolve cada estabelecimento uma vez, na ordem de relevância.
    const seen = new Map();
    for (const { merchant } of items) {
      if (!seen.has(merchant.merchantId)) {
        seen.set(merchant.merchantId, merchantSummary(merchant));
      }
    }
    return sortResults([...seen.values()], refinements.sort);
  }

  #findMerchant(merchantId) {
    const merchant = MOCK_MERCHANTS.find((candidate) => candidate.merchantId === merchantId);
    if (!merchant) {
      throw new IfoodToolError('getMerchant', `estabelecimento ${merchantId} não encontrado.`);
    }
    return merchant;
  }

  #findItem(merchantId, itemId) {
    const merchant = this.#findMerchant(merchantId);
    const item = merchant.items.find((candidate) => candidate.itemId === itemId);
    if (!item) {
      throw new IfoodToolError('getItem', `item ${itemId} não encontrado neste estabelecimento.`);
    }
    return { merchant, item };
  }

  // --------------------------------------------------------------- Carrinho

  /** Calcula o estado completo de um carrinho, no formato devolvido por getCart. */
  #cartView(cart) {
    const merchant = this.#findMerchant(cart.merchantId);
    const items = cart.items.map((cartItem) => {
      const { item } = this.#findItem(cart.merchantId, cartItem.itemId);
      const allOptions = (item.optionGroups ?? []).flatMap((group) => group.options);
      const options = (cartItem.options ?? []).map((selected) => {
        const option = allOptions.find((candidate) => candidate.optionId === selected.optionId);
        return { optionId: selected.optionId, name: option?.name ?? 'Opção', quantity: selected.quantity, unitPrice: option?.additionalPrice ?? 0 };
      });
      const unitPrice = (item.promotionalUnitPrice ?? item.unitPrice)
        + options.reduce((sum, option) => sum + option.unitPrice * option.quantity, 0);
      return {
        cartItemId: cartItem.cartItemId,
        itemId: item.itemId,
        name: item.itemName,
        quantity: cartItem.quantity,
        unitPrice,
        totalPrice: Number((unitPrice * cartItem.quantity).toFixed(2)),
        customerNote: cartItem.customerNote ?? null,
        options,
      };
    });

    const subtotal = Number(items.reduce((sum, item) => sum + item.totalPrice, 0).toFixed(2));
    const deliveryFee = cart.deliveryMethodId === 'TAKEOUT' ? 0 : merchant.deliveryFee;
    return {
      cartId: cart.cartId,
      merchant: { merchantId: merchant.merchantId, merchantName: merchant.merchantName, minimumOrderAmount: merchant.minimumOrderAmount },
      addressId: cart.addressId,
      items,
      deliveryMethod: cart.deliveryMethodId ? { deliveryMethodId: cart.deliveryMethodId } : null,
      paymentMethod: cart.paymentMethodId ? { paymentMethodId: cart.paymentMethodId } : null,
      totals: { subtotal, deliveryFee, discount: 0, total: Number((subtotal + deliveryFee).toFixed(2)) },
    };
  }

  #getCart(cartId) {
    const cart = this.#carts.get(cartId);
    if (!cart) {
      throw new IfoodToolError('getCart', 'carrinho não encontrado.');
    }
    return cart;
  }

  /** Mapa ferramenta → implementação simulada. */
  #handlers = {
    getUser: () => ({ success: true, data: MOCK_USER }),

    listAddresses: () => ({ results: MOCK_ADDRESSES }),

    searchOffers: (args) => {
      const results = this.#filterOffers(args);
      return { resultKind: args.resultKind ?? 'MERCHANT', interpretedQuery: args.query, ...paginate(results, args.pageSize, args.nextPageToken) };
    },

    browseOffers: (args) => {
      const results = this.#filterOffers({ ...args, query: '' });
      return { resultKind: args.resultKind ?? 'MERCHANT', merchantType: args.merchantType, ...paginate(results, args.pageSize, args.nextPageToken) };
    },

    getRecommendations: (args) => {
      const results = this.#filterOffers({ merchantType: args.merchantType, resultKind: args.resultKind, refinements: args.refinements ?? {} });
      return { contentMode: args.contentMode, ...paginate(results, args.pageSize, args.nextPageToken) };
    },

    getMerchant: ({ merchantId }) => {
      const merchant = this.#findMerchant(merchantId);
      return {
        ...merchantSummary(merchant),
        merchantType: merchant.merchantType,
        address: 'São Carlos - SP',
        deliveryMethods: [
          merchantSummary(merchant).deliveryMethod,
          { deliveryMethodId: 'TAKEOUT', deliveryMethodMode: 'TAKEOUT', estimatedMinutes: { min: 20, max: 30 }, fee: 0, promotionalFee: 0 },
        ],
        catalogSummary: { totalItems: merchant.items.length },
        featuredItems: merchant.items.slice(0, 5).map((item) => ({ itemId: item.itemId, itemName: item.itemName, unitPrice: item.unitPrice })),
      };
    },

    getItem: ({ merchantId, itemId }) => {
      const { merchant, item } = this.#findItem(merchantId, itemId);
      return {
        itemId: item.itemId,
        itemName: item.itemName,
        itemDescription: item.itemDescription,
        itemImageUrl: item.image ?? merchant.logo,
        merchantId: merchant.merchantId,
        merchantName: merchant.merchantName,
        merchantMinimumOrderAmount: merchant.minimumOrderAmount,
        optionGroups: item.optionGroups ?? [],
        unitPrice: item.unitPrice,
        promotionalUnitPrice: item.promotionalUnitPrice ?? item.unitPrice,
      };
    },

    createCart: ({ merchantId, addressId, items = [] }) => {
      this.#findMerchant(merchantId);
      if (!MOCK_ADDRESSES.some((address) => address.addressId === addressId)) {
        throw new IfoodToolError('createCart', 'endereço inválido.');
      }
      if (items.length === 0) {
        throw new IfoodToolError('createCart', 'o carrinho precisa de pelo menos um item.');
      }
      const cart = {
        cartId: randomUUID(),
        merchantId,
        addressId,
        items: items.map((item) => {
          this.#findItem(merchantId, item.itemId);
          return { ...item, cartItemId: randomUUID() };
        }),
      };
      this.#carts.set(cart.cartId, cart);
      return this.#cartView(cart);
    },

    getCart: ({ cartId }) => this.#cartView(this.#getCart(cartId)),

    getCartDeliveryMethods: ({ cartId }) => {
      const merchant = this.#findMerchant(this.#getCart(cartId).merchantId);
      return {
        deliveryMethods: [
          { deliveryMethodId: 'DEFAULT', deliveryMethodMode: 'DELIVERY', displayName: 'Entrega padrão', estimatedMinutes: merchant.estimatedMinutes, fee: merchant.deliveryFee, timeSlots: [] },
          { deliveryMethodId: 'TAKEOUT', deliveryMethodMode: 'TAKEOUT', displayName: 'Retirar no local', estimatedMinutes: { min: 20, max: 30 }, fee: 0, timeSlots: [] },
        ],
      };
    },

    setCartDelivery: ({ cartId, deliveryMethodId }) => {
      const cart = this.#getCart(cartId);
      cart.deliveryMethodId = deliveryMethodId;
      return this.#cartView(cart);
    },

    listPaymentMethods: () => ({ paymentMethods: MOCK_PAYMENT_METHODS }),

    setCartPayment: ({ cartId, paymentMethodId, cardTokenId }) => {
      const cart = this.#getCart(cartId);
      cart.paymentMethodId = paymentMethodId;
      cart.cardTokenId = cardTokenId;
      return this.#cartView(cart);
    },

    submitOrder: ({ cartId, userConsent }) => {
      if (userConsent !== true) {
        throw new IfoodToolError('submitOrder', 'o pedido precisa da confirmação explícita do usuário.');
      }
      const cart = this.#getCart(cartId);
      if (!cart.deliveryMethodId || !cart.paymentMethodId) {
        throw new IfoodToolError('submitOrder', 'escolha a forma de entrega e de pagamento.');
      }
      const order = { orderId: randomUUID(), cartId, status: 'PLACED', createdAt: new Date().toISOString(), cart: this.#cartView(cart) };
      this.#orders.set(order.orderId, order);
      this.#carts.delete(cartId);
      return { orderId: order.orderId, status: order.status, message: 'Pedido simulado registrado (modo demonstração).' };
    },

    trackOrder: ({ orderId }) => {
      const order = this.#orders.get(orderId);
      if (!order) {
        throw new IfoodToolError('trackOrder', 'pedido não encontrado.');
      }
      // Simula o avanço do pedido de acordo com o tempo desde a criação.
      const minutes = (Date.now() - Date.parse(order.createdAt)) / 60_000;
      const steps = ['PLACED', 'CONFIRMED', 'PREPARING', 'DISPATCHED', 'CONCLUDED'];
      const status = steps[Math.min(Math.floor(minutes / 2), steps.length - 1)];
      return { orderId, status, events: steps.slice(0, steps.indexOf(status) + 1).map((step) => ({ status: step })) };
    },
  };
}
