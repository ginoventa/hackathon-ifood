/**
 * Rotas de revisão e confirmação do pedido.
 *
 * Esta é a ÚNICA forma de enviar um pedido: o usuário revisa itens, alertas
 * alimentares, entrega e pagamento, e clica em "Confirmar pedido".
 */

import { getSession } from '../../sessions/sessionStore.js';
import { getCheckoutOptions, submitOrder, trackOrder } from '../../services/cartService.js';

/** @param {import('../router.js').Router} router */
export function registerOrderRoutes(router) {
  router.add('GET /api/carts/:cartId/checkout', async ({ sessionId, params }) => (
    getCheckoutOptions(getSession(sessionId), params.cartId)
  ));

  router.add('POST /api/orders', async ({ sessionId, body }) => {
    const order = await submitOrder(getSession(sessionId), {
      cartId: body.cartId,
      deliveryMethodId: body.deliveryMethodId,
      timeSlotId: body.timeSlotId,
      paymentMethodId: body.paymentMethodId,
      cardTokenId: body.cardTokenId,
      document: body.document,
      userConfirmed: body.userConfirmed === true,
      alertsAcknowledged: body.alertsAcknowledged === true,
    });
    return { order };
  });

  router.add('GET /api/orders/:orderId/track', async ({ sessionId, params }) => (
    trackOrder(getSession(sessionId), params.orderId)
  ));
}
