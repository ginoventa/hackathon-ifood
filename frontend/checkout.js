/**
 * Revisão e confirmação do pedido (seções 1.5 e 2.5 da proposta).
 *
 * O usuário revisa itens, alertas alimentares, endereço, entrega e pagamento.
 * O pedido só é enviado quando ele clica em "Confirmar pedido". Se houver
 * alertas, também precisa marcar que leu e decide seguir.
 */

import { api } from './api.js';
import { el, formatMinutes, formatPrice, icon, verdictBadge } from './format.js';

const dialog = document.querySelector('#checkout-dialog');
const body = document.querySelector('#checkout-body');

/** Intervalo de atualização do acompanhamento do pedido. */
const TRACK_INTERVAL_MS = 30_000;
let trackTimer;

/** Nomes amigáveis dos status de pedido mais comuns. */
const ORDER_STATUS = {
  PLACED: 'Pedido enviado',
  CONFIRMED: 'Confirmado pelo estabelecimento',
  PREPARING: 'Em preparo',
  READY_TO_PICKUP: 'Pronto para retirada',
  DISPATCHED: 'Saiu para entrega',
  CONCLUDED: 'Entregue',
  CANCELLED: 'Cancelado',
};

/** Mostra um estado simples (carregando/erro) no corpo do diálogo. */
function showMessage(title, text) {
  body.replaceChildren(el('div', { className: 'checkout-state' }, [el('h2', { text: title }), el('p', { text })]));
}

/** Grupo de opções do tipo rádio (entrega ou pagamento). */
function radioGroup(name, legend, options) {
  return el('fieldset', { className: 'checkout-options' }, [
    el('legend', { text: legend }),
    ...options.map((option, index) => {
      const input = el('input', { attrs: { type: 'radio', name, value: option.value } });
      input.checked = index === 0;
      input.dataset.extra = option.extra ?? '';
      return el('label', { className: 'checkout-option' }, [
        input,
        el('span', {}, [el('strong', { text: option.label }), option.detail ? el('small', { text: option.detail }) : null]),
      ]);
    }),
  ]);
}

/** Lista de alertas alimentares dos itens do carrinho. */
function alertsSection(alerts) {
  return el('section', { className: 'checkout-alerts' }, [
    el('h3', {}, [icon('alert'), 'Alertas alimentares']),
    ...alerts.map((alert) => el('div', { className: 'checkout-alert' }, [
      el('div', { className: 'checkout-alert-title' }, [el('strong', { text: alert.itemName ?? 'Item' }), verdictBadge(alert.verdict)]),
      el('p', { text: alert.text }),
      alert.missingInfo?.length ? el('ul', { className: 'card-list' }, alert.missingInfo.map((info) => el('li', { text: info }))) : null,
    ])),
  ]);
}

/** Tela de sucesso, com acompanhamento periódico do pedido. */
function showOrderPlaced(order) {
  const status = el('p', { className: 'order-status', text: ORDER_STATUS[order.status] ?? order.status ?? 'Pedido enviado' });

  const refresh = async () => {
    try {
      const tracking = await api.trackOrder(order.orderId);
      status.textContent = ORDER_STATUS[tracking.status] ?? tracking.status ?? status.textContent;
    } catch {
      // Mantém o último status conhecido.
    }
  };
  clearInterval(trackTimer);
  trackTimer = setInterval(refresh, TRACK_INTERVAL_MS);

  body.replaceChildren(el('div', { className: 'checkout-state success' }, [
    el('span', { className: 'success-icon' }, [icon('check')]),
    el('h2', { text: 'Pedido enviado ao iFood!' }),
    status,
    el('p', { className: 'card-muted', text: `Número do pedido: ${order.orderId}` }),
    order.message ? el('p', { className: 'card-muted', text: order.message }) : null,
    el('p', { className: 'card-disclaimer', text: 'Se tiver alergia, avise também o estabelecimento ao receber o pedido.' }),
    el('div', { className: 'card-actions' }, [
      el('button', { className: 'card-button primary', text: 'Acompanhar agora', attrs: { type: 'button', 'data-action': 'track' } }),
      el('button', { className: 'card-button', text: 'Fechar', attrs: { type: 'button', 'data-action': 'close' } }),
    ]),
  ]));
  body.querySelector('[data-action="track"]').addEventListener('click', refresh);
  body.querySelector('[data-action="close"]').addEventListener('click', () => dialog.close());
}

/** Monta o formulário de revisão a partir dos dados da API. */
function renderReview(cartId, data) {
  const { cart, alerts, address, deliveryMethods, paymentMethods, submitEnabled } = data;

  const delivery = radioGroup('delivery', 'Como receber', deliveryMethods.map((method) => ({
    value: method.deliveryMethodId,
    label: method.label,
    detail: [formatMinutes(method.estimatedMinutes), method.fee === 0 ? 'Grátis' : formatPrice(method.fee)].filter(Boolean).join(' · '),
  })));

  const payment = radioGroup('payment', 'Pagamento', paymentMethods.map((method) => ({
    value: method.paymentMethodId,
    label: method.label,
    extra: method.cardTokenId ?? '',
  })));

  const acknowledge = el('input', { attrs: { type: 'checkbox', id: 'alerts-ack' } });
  const documentInput = el('input', { attrs: { id: 'checkout-document', inputmode: 'numeric', placeholder: 'Somente se o iFood pedir', maxlength: '18' } });
  const error = el('p', { className: 'checkout-error', attrs: { role: 'alert' } });
  error.hidden = true;

  const confirm = el('button', { className: 'card-button primary confirm-order', attrs: { type: 'submit' } }, [
    `Confirmar pedido · ${formatPrice(cart.total ?? cart.subtotal)}`,
  ]);
  confirm.disabled = !submitEnabled;

  const form = el('form', { className: 'checkout-form' }, [
    el('header', { className: 'checkout-header' }, [
      el('h2', { text: 'Revise seu pedido' }),
      el('button', { className: 'icon-button', text: '×', attrs: { type: 'button', 'aria-label': 'Fechar revisão', value: 'close' } }),
    ]),
    el('p', { className: 'card-note warning', text: 'Este pedido será enviado ao iFood. Em contas de teste, evite pagar via PIX: pedidos de teste pagos não são reembolsados.' }),
    el('section', { className: 'checkout-section' }, [
      el('h3', { text: cart.merchantName ?? 'Itens' }),
      el('ul', { className: 'market-items' }, cart.items.map((item) => el('li', {}, [
        el('div', {}, [
          el('strong', { text: `${item.quantity}× ${item.name}` }),
          item.options.length ? el('small', { text: item.options.join(', ') }) : null,
          item.customerNote ? el('small', { text: `Obs.: ${item.customerNote}` }) : null,
        ]),
        el('span', { text: formatPrice(item.totalPrice) }),
      ]))),
      el('div', { className: 'cart-total' }, [el('span', { text: 'Subtotal' }), el('span', { text: formatPrice(cart.subtotal) })]),
      cart.deliveryFee != null ? el('div', { className: 'cart-total' }, [el('span', { text: 'Entrega' }), el('span', { text: formatPrice(cart.deliveryFee) })]) : null,
      el('div', { className: 'cart-total' }, [el('strong', { text: 'Total' }), el('strong', { text: formatPrice(cart.total ?? cart.subtotal) })]),
    ]),
    alerts.length ? alertsSection(alerts) : null,
    el('section', { className: 'checkout-section' }, [
      el('h3', { text: 'Entregar em' }),
      el('p', { text: address?.formattedAddress ?? 'Endereço não definido' }),
    ]),
    delivery,
    payment,
    el('details', { className: 'card-details' }, [
      el('summary', { text: 'CPF/CNPJ na nota' }),
      el('label', { className: 'sr-only', text: 'CPF ou CNPJ', attrs: { for: 'checkout-document' } }),
      documentInput,
    ]),
    alerts.length ? el('label', { className: 'consent-line', attrs: { for: 'alerts-ack' } }, [
      acknowledge,
      el('span', { text: 'Li os alertas alimentares e decido seguir com este pedido.' }),
    ]) : null,
    error,
    confirm,
    !submitEnabled ? el('p', { className: 'card-muted', text: 'O envio de pedidos está desativado neste servidor.' }) : null,
  ]);

  form.querySelector('[value="close"]').addEventListener('click', () => dialog.close());

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.hidden = true;

    if (alerts.length && !acknowledge.checked) {
      error.textContent = 'Confirme que leu os alertas alimentares antes de finalizar.';
      error.hidden = false;
      return;
    }

    const paymentInput = form.querySelector('input[name="payment"]:checked');
    confirm.disabled = true;
    confirm.textContent = 'Enviando pedido…';
    try {
      const { order } = await api.submitOrder({
        cartId,
        deliveryMethodId: form.querySelector('input[name="delivery"]:checked')?.value,
        paymentMethodId: paymentInput?.value,
        cardTokenId: paymentInput?.dataset.extra || undefined,
        document: documentInput.value.trim() || undefined,
        userConfirmed: true,
        alertsAcknowledged: acknowledge.checked,
      });
      showOrderPlaced(order);
    } catch (requestError) {
      error.textContent = requestError.message;
      error.hidden = false;
      // Se o iFood pedir documento, abre o campo automaticamente.
      if (/document|cpf|cnpj/i.test(requestError.message)) {
        form.querySelector('.card-details').open = true;
        documentInput.focus();
      }
      confirm.disabled = false;
      confirm.textContent = `Confirmar pedido · ${formatPrice(cart.total ?? cart.subtotal)}`;
    }
  });

  body.replaceChildren(form);
}

/** Aceita somente links oficiais do iFood devolvidos pelo MCP. */
export function safeIfoodCartUrl(value) {
  if (typeof value !== 'string' || !value.trim()) {
    return null;
  }

  try {
    const url = new URL(value);
    const officialHost = ['ifood.com.br', 'ifood-sandbox.com.br'].some((domain) => (
      url.hostname === domain || url.hostname.endsWith(`.${domain}`)
    ));

    if (url.username || url.password) {
      return null;
    }

    return url.protocol === 'ifood:' || (url.protocol === 'https:' && officialHost)
      ? url.href
      : null;
  } catch {
    return null;
  }
}

/** Mostra a lista efetivamente adicionada ao carrinho no iFood. */
function renderCartPreview(cartId, { cart, alerts, address }) {
  const close = el('button', {
    className: 'icon-button',
    text: '×',
    attrs: { type: 'button', 'aria-label': 'Fechar carrinho' },
  });
  close.addEventListener('click', () => dialog.close());
  const link = safeIfoodCartUrl(cart.appDeeplink);
  const review = el('button', {
    className: 'card-button secondary',
    text: 'Revisar entrega e pagamento aqui',
    attrs: { type: 'button' },
  });
  review.addEventListener('click', async () => {
    showMessage('Carregando revisão…', 'Consultando entrega e pagamento.');
    try {
      renderReview(cartId, await api.checkout(cartId));
    } catch (error) {
      showMessage('Não foi possível abrir a revisão', error.message);
    }
  });

  body.replaceChildren(el('section', { className: 'checkout-form cart-preview' }, [
    el('header', { className: 'checkout-header' }, [
      el('div', {}, [
        el('p', { className: 'card-kicker', text: 'Sua sacola no iFood' }),
        el('h2', { text: cart.merchantName || 'Carrinho' }),
      ]),
      close,
    ]),
    cart.items.length
      ? el('ul', { className: 'market-items cart-preview-items' }, cart.items.map((item) => (
        el('li', {}, [
          el('div', {}, [
            el('strong', { text: `${item.quantity}× ${item.name}` }),
            item.options?.length ? el('small', { text: item.options.join(', ') }) : null,
            item.customerNote ? el('small', { text: item.customerNote }) : null,
          ]),
          el('span', { text: formatPrice(item.totalPrice) }),
        ])
      )))
      : el('p', { className: 'card-muted', text: 'Este carrinho está vazio.' }),
    el('div', { className: 'cart-total' }, [
      el('span', { text: 'Subtotal dos produtos' }),
      el('strong', { text: formatPrice(cart.subtotal) }),
    ]),
    cart.deliveryFee != null ? el('div', { className: 'cart-total' }, [
      el('span', { text: 'Entrega' }),
      el('span', { text: formatPrice(cart.deliveryFee) }),
    ]) : null,
    el('div', { className: 'cart-total' }, [
      el('strong', { text: 'Total' }),
      el('strong', { text: formatPrice(cart.total ?? cart.subtotal) }),
    ]),
    address?.formattedAddress ? el('p', { className: 'card-muted', text: address.formattedAddress }) : null,
    alerts?.length ? alertsSection(alerts) : null,
    link && cart.items.length ? el('a', {
      className: 'card-button primary ifood-cart-link',
      text: 'Abrir carrinho no iFood',
      attrs: { href: link, target: '_blank', rel: 'noopener noreferrer' },
    }) : el('p', {
      className: 'card-muted',
      text: cart.items.length
        ? 'O iFood não disponibilizou um link para este carrinho. Você pode revisar o pedido aqui.'
        : 'Adicione produtos antes de continuar.',
    }),
    cart.items.length ? review : null,
  ]));
}

/** Abre a janela do carrinho, consultando os itens atuais no iFood. */
export async function openCheckout(cartId) {
  clearInterval(trackTimer);
  showMessage('Carregando seu carrinho…', 'Consultando os produtos adicionados no iFood.');
  if (!dialog.open) {
    dialog.showModal();
  }
  try {
    renderCartPreview(cartId, await api.cart(cartId));
  } catch (error) {
    showMessage('Não foi possível abrir o carrinho', error.message);
    const close = el('button', {
      className: 'card-button',
      text: 'Fechar',
      attrs: { type: 'button' },
    });
    close.addEventListener('click', () => dialog.close());
    body.firstElementChild.append(close);
  }
}

/**
 * Abre direto a finalização: entrega e pagamento vêm do MCP do iFood
 * (getCartDeliveryMethods, listPaymentMethods) e o envio usa submitOrder,
 * sempre depois do clique em "Confirmar pedido".
 */
export async function finalizeOrder(cartId) {
  clearInterval(trackTimer);
  showMessage('Preparando a finalização…', 'Consultando entrega e pagamento no iFood.');
  if (!dialog.open) {
    dialog.showModal();
  }
  try {
    renderReview(cartId, await api.checkout(cartId));
  } catch (error) {
    showMessage('Não foi possível finalizar o pedido', error.message);
    const close = el('button', { className: 'card-button', text: 'Fechar', attrs: { type: 'button' } });
    close.addEventListener('click', () => dialog.close());
    body.firstElementChild.append(close);
  }
}

dialog.addEventListener('close', () => clearInterval(trackTimer));
