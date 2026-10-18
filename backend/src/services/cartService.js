/**
 * Carrinho e finalização do pedido (seções 1.5 e 2.5).
 *
 * Regra de segurança central: a LLM pode MONTAR o carrinho, mas nunca enviar
 * o pedido. O envio (`submitOrder`) só acontece pela rota HTTP chamada quando
 * o usuário clica em "Confirmar pedido" na tela de revisão.
 */

import { config } from '../config.js';
import { ifood } from '../ifood/index.js';
import { VERDICTS } from '../restrictions/analyzer.js';
import { AppError, ValidationError } from '../utils/errors.js';

/** Lê o primeiro número encontrado entre vários caminhos possíveis do objeto. */
function pickNumber(source, paths) {
  for (const path of paths) {
    const value = path.split('.').reduce((current, key) => current?.[key], source);
    const number = typeof value === 'object' && value !== null ? Number(value.value ?? value.amount) : Number(value);
    if (value !== undefined && value !== null && Number.isFinite(number)) {
      return number;
    }
  }
  return null;
}

/**
 * Converte a resposta de carrinho do MCP num formato estável para a interface.
 * É tolerante a variações de nomes de campos entre versões do MCP.
 */
export function normalizeCart(raw) {
  const cart = raw?.cart ?? raw?.data ?? raw ?? {};
  const items = (cart.items ?? cart.cartItems ?? []).map((item) => ({
    cartItemId: item.cartItemId ?? item.id ?? null,
    itemId: item.itemId ?? item.catalogItemId ?? null,
    name: item.name ?? item.itemName ?? item.description ?? 'Item',
    quantity: item.quantity ?? 1,
    unitPrice: pickNumber(item, ['unitPrice', 'price', 'unitPrice.value']),
    totalPrice: pickNumber(item, ['totalPrice', 'total', 'subtotal', 'totalPrice.value']),
    customerNote: item.customerNote ?? item.observation ?? null,
    options: (item.options ?? []).map((option) => option.name ?? option.optionName ?? 'Opção'),
  }));

  const totals = cart.totals ?? cart.summary ?? cart.prices ?? cart;
  const subtotal = pickNumber(totals, ['subtotal', 'itemsTotal', 'subTotal', 'itemsAmount']);
  return {
    cartId: cart.cartId ?? cart.id ?? null,
    merchantId: cart.merchant?.merchantId ?? cart.merchantId ?? null,
    merchantName: cart.merchant?.merchantName ?? cart.merchantName ?? null,
    items,
    subtotal: subtotal ?? items.reduce((sum, item) => sum + (item.totalPrice ?? 0), 0),
    deliveryFee: pickNumber(totals, ['deliveryFee', 'deliveryFeeAmount', 'delivery']),
    discount: pickNumber(totals, ['discount', 'discountAmount', 'vouchersDiscount']),
    total: pickNumber(totals, ['total', 'totalAmount', 'orderTotal']),
    deliveryMethodId: cart.deliveryMethod?.deliveryMethodId ?? null,
    paymentMethodId: cart.paymentMethod?.paymentMethodId ?? null,
  };
}

/**
 * Coleta os alertas alimentares dos itens do carrinho, a partir das análises
 * da sessão. Eles aparecem na revisão e exigem ciência do usuário.
 */
function dietaryAlertsFor(session, itemIds) {
  const alerts = [];
  for (const itemId of itemIds) {
    const analysis = session.analyses.get(itemId)
      ?? session.marketPlan?.merchants.flatMap((plan) => plan.items).find((item) => item.itemId === itemId)?.analysis;
    if (!analysis) {
      alerts.push({ itemId, verdict: VERDICTS.INSUFFICIENT, text: 'Este item não foi analisado pelo Ailo.' });
      continue;
    }
    if (analysis.verdict !== VERDICTS.NO_DECLARED_CONFLICT || analysis.missingInfo.length > 0) {
      // Explica só as restrições que pedem atenção; as demais ficam resumidas.
      const concerns = analysis.restrictions.filter((result) => result.verdict !== VERDICTS.NO_DECLARED_CONFLICT);
      alerts.push({
        itemId,
        itemName: analysis.itemName,
        verdict: analysis.verdict,
        text: concerns.length > 0
          ? concerns.map((result) => result.explanation).join(' ')
          : 'Nenhum conflito nas informações disponíveis, mas faltam dados para confirmar.',
        missingInfo: analysis.missingInfo,
        addOnsToAvoid: analysis.addOnsToAvoid,
      });
    }
  }
  return alerts;
}

/** Garante que o carrinho foi criado nesta sessão (evita manipular carrinhos alheios). */
function requireOwnCart(session, cartId) {
  const entry = session.carts.get(cartId);
  if (!entry) {
    throw new ValidationError('Carrinho não encontrado nesta conversa.');
  }
  return entry;
}

/**
 * Cria o carrinho no iFood. Bloqueia itens com CONFLITO declarado.
 * @param {object} session
 * @param {{ merchantId: string, items: { itemId: string, quantidade: number, observacao?: string, opcoes?: { optionId: string, quantidade?: number }[] }[] }} params
 */
export async function createCart(session, { merchantId, items }) {
  if (!session.address?.addressId) {
    throw new ValidationError('Escolha um endereço de entrega antes de montar o carrinho.');
  }
  if (!Array.isArray(items) || items.length === 0) {
    throw new ValidationError('Informe ao menos um item para o carrinho.');
  }

  // Trava determinística: nenhum item com conflito declarado entra no carrinho.
  const blocked = items.filter((item) => session.analyses.get(item.itemId)?.verdict === VERDICTS.CONFLICT);
  if (blocked.length > 0) {
    throw new ValidationError('Há itens incompatíveis com as suas restrições. Eles não podem ser adicionados ao carrinho.');
  }

  const raw = await ifood.callTool('createCart', {
    merchantId,
    addressId: session.address.addressId,
    items: items.map((item) => ({
      itemId: item.itemId,
      quantity: Math.max(1, Math.round(Number(item.quantidade) || 1)),
      ...(item.observacao ? { customerNote: String(item.observacao).slice(0, 140) } : {}),
      ...(item.opcoes?.length ? { options: item.opcoes.map((option) => ({ optionId: option.optionId, quantity: option.quantidade ?? 1 })) } : {}),
    })),
  });

  const cart = normalizeCart(raw);
  if (!cart.cartId) {
    throw new AppError('O iFood não retornou o identificador do carrinho.', { status: 502, code: 'IFOOD_CARRINHO_INVALIDO' });
  }
  cart.merchantId ??= merchantId;
  session.carts.set(cart.cartId, { merchantId: cart.merchantId, itemIds: items.map((item) => item.itemId), createdAt: Date.now() });

  return { ...cart, alerts: dietaryAlertsFor(session, items.map((item) => item.itemId)) };
}

/**
 * Dados da tela de revisão: carrinho atualizado, formas de entrega e de pagamento.
 */
export async function getCheckoutOptions(session, cartId) {
  const entry = requireOwnCart(session, cartId);
  const [cartRaw, deliveryRaw, paymentRaw] = await Promise.all([
    ifood.callTool('getCart', { cartId }),
    ifood.callTool('getCartDeliveryMethods', { cartId }),
    ifood.callTool('listPaymentMethods', { merchantId: entry.merchantId }),
  ]);

  const deliveryMethods = (deliveryRaw.deliveryMethods ?? deliveryRaw.results ?? []).map((method) => ({
    deliveryMethodId: method.deliveryMethodId,
    mode: method.deliveryMethodMode ?? method.mode ?? null,
    label: method.displayName ?? (method.deliveryMethodMode === 'TAKEOUT' ? 'Retirar no local' : 'Entrega'),
    fee: method.promotionalFee ?? method.fee ?? null,
    estimatedMinutes: method.estimatedMinutes ?? null,
    timeSlots: (method.timeSlots ?? []).map((slot) => ({ id: slot.timeSlotId ?? slot.id, label: slot.displayName ?? slot.label ?? '' })),
  }));

  const paymentMethods = (paymentRaw.paymentMethods ?? []).map((method) => ({
    paymentMethodId: method.paymentMethodId,
    kind: method.kind,
    label: method.displayName ?? method.kind,
    cardTokenId: method.cardTokenId ?? null,
  }));

  return {
    cart: normalizeCart(cartRaw),
    alerts: dietaryAlertsFor(session, entry.itemIds),
    address: session.address,
    deliveryMethods,
    paymentMethods,
    submitEnabled: config.ifood.allowSubmitOrder,
    mode: ifood.mode,
  };
}

/**
 * Envia o pedido. Chamado SOMENTE pela rota HTTP de confirmação do usuário.
 * @param {object} session
 * @param {object} params
 * @param {string} params.cartId
 * @param {string} params.deliveryMethodId
 * @param {string} [params.timeSlotId]
 * @param {string} params.paymentMethodId
 * @param {string} [params.cardTokenId]
 * @param {string} [params.document] CPF/CNPJ, se o iFood exigir.
 * @param {boolean} params.userConfirmed Clique explícito em "Confirmar pedido".
 * @param {boolean} params.alertsAcknowledged Ciência dos alertas alimentares.
 */
export async function submitOrder(session, params) {
  if (!config.ifood.allowSubmitOrder) {
    throw new AppError('O envio de pedidos está desativado neste servidor (ALLOW_SUBMIT_ORDER=false).', { status: 403, code: 'PEDIDO_DESATIVADO' });
  }
  if (params.userConfirmed !== true) {
    throw new ValidationError('O pedido só é enviado com a sua confirmação explícita.');
  }

  const entry = requireOwnCart(session, params.cartId);
  const alerts = dietaryAlertsFor(session, entry.itemIds);
  if (alerts.length > 0 && params.alertsAcknowledged !== true) {
    throw new ValidationError('Leia e confirme os alertas alimentares antes de finalizar.');
  }
  if (!params.deliveryMethodId || !params.paymentMethodId) {
    throw new ValidationError('Escolha a forma de entrega e de pagamento.');
  }

  await ifood.callTool('setCartDelivery', {
    cartId: params.cartId,
    deliveryMethodId: params.deliveryMethodId,
    ...(params.timeSlotId ? { selectedTimeSlotId: params.timeSlotId } : {}),
  });
  await ifood.callTool('setCartPayment', {
    cartId: params.cartId,
    paymentMethodId: params.paymentMethodId,
    ...(params.cardTokenId ? { cardTokenId: params.cardTokenId } : {}),
  });

  const result = await ifood.callTool('submitOrder', {
    cartId: params.cartId,
    userConsent: true,
    ...(params.document ? { document: String(params.document).replace(/\D/g, '') } : {}),
  });

  const order = {
    orderId: result.orderId ?? result.data?.orderId ?? null,
    status: result.status ?? result.data?.status ?? null,
    message: result.message ?? null,
    // Dados de pagamento (ex.: código Pix) quando o iFood os devolver.
    payment: result.payment ?? result.pix ?? result.data?.payment ?? null,
    createdAt: new Date().toISOString(),
  };
  session.orders.push(order);
  session.carts.delete(params.cartId);
  return order;
}

/** Acompanha um pedido feito nesta sessão. */
export async function trackOrder(session, orderId) {
  if (!session.orders.some((order) => order.orderId === orderId)) {
    throw new ValidationError('Pedido não encontrado nesta conversa.');
  }
  const result = await ifood.callTool('trackOrder', { orderId });
  return {
    orderId,
    status: result.status ?? result.currentStatus ?? result.data?.status ?? null,
    events: result.events ?? result.statusEvents ?? result.data?.events ?? [],
  };
}
