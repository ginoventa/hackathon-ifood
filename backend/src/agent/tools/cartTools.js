/**
 * Ferramentas de carrinho. A LLM pode montar o carrinho, mas o pedido só é
 * enviado quando o usuário confirma na tela de revisão (rota HTTP própria).
 */

import { ValidationError } from '../../utils/errors.js';
import { createCart } from '../../services/cartService.js';

/** Resumo do carrinho para a LLM. */
function cartOutput(cart) {
  return {
    carrinhoCriado: true,
    loja: cart.merchantName,
    itens: cart.items.map((item) => `${item.quantity}x ${item.name}`),
    total: cart.total ?? cart.subtotal,
    alertasAlimentares: cart.alerts.length,
    proximoPasso: 'O usuário deve revisar e confirmar o pedido na tela de revisão.',
  };
}

export const buildCartTool = {
  declaration: {
    name: 'montar_carrinho',
    description: 'Cria o carrinho no iFood com itens de UM estabelecimento. Não envia o pedido.',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        merchantId: { type: 'string' },
        itens: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              itemId: { type: 'string' },
              quantidade: { type: 'integer' },
              observacao: { type: 'string', description: 'Ex.: avisar a alergia ao restaurante.' },
              opcoes: {
                type: 'array',
                items: {
                  type: 'object',
                  properties: { optionId: { type: 'string' }, quantidade: { type: 'integer' } },
                  required: ['optionId'],
                },
              },
            },
            required: ['itemId', 'quantidade'],
          },
        },
      },
      required: ['merchantId', 'itens'],
    },
  },

  async execute(session, { merchantId, itens }) {
    const cart = await createCart(session, { merchantId, items: itens });
    return { output: cartOutput(cart), card: { type: 'cart', data: cart } };
  },
};

export const buildGroceryCartTool = {
  declaration: {
    name: 'montar_carrinho_do_mercado',
    description: 'Cria o carrinho com os produtos escolhidos para a receita no mercado indicado (da última comparação).',
    parametersJsonSchema: {
      type: 'object',
      properties: { merchantId: { type: 'string' } },
      required: ['merchantId'],
    },
  },

  async execute(session, { merchantId }) {
    const plan = session.marketPlan?.merchants.find((merchant) => merchant.merchantId === merchantId);
    if (!plan || plan.items.length === 0) {
      throw new ValidationError('Este mercado não está na última comparação. Busque os ingredientes novamente.');
    }
    const cart = await createCart(session, {
      merchantId,
      items: plan.items.map((item) => ({ itemId: item.itemId, quantidade: item.quantidade })),
    });
    return { output: cartOutput(cart), card: { type: 'cart', data: cart } };
  },
};
