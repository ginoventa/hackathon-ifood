/**
 * Testes do laço do agente e das ferramentas, com:
 * - iFood em modo de demonstração (dados simulados);
 * - um "modelo falso" que pede ferramentas em sequência, no lugar do Gemini.
 *
 * Assim validamos o fluxo completo da proposta sem rede e sem custo.
 */

import { after, before, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// O config é lido na importação: as variáveis precisam ser definidas antes.
const dataDir = await mkdtemp(join(tmpdir(), 'ailo-test-'));
process.env.IFOOD_MODE = 'mock';
process.env.DATA_DIR = dataDir;
process.env.ALLOW_SUBMIT_ORDER = 'true';

const { runAgentTurn } = await import('../src/agent/agent.js');
const { getSession } = await import('../src/sessions/sessionStore.js');
const { ensureAccountContext } = await import('../src/services/accountService.js');
const { getCheckoutOptions, submitOrder } = await import('../src/services/cartService.js');

/**
 * Cria um modelo falso: cada chamada devolve o próximo passo do roteiro.
 * Um passo é `{ call: [nome, args] }` (pede ferramenta) ou `{ text }` (responde).
 */
function scriptedModel(steps) {
  const received = [];
  let index = 0;
  const generate = async (contents) => {
    received.push(contents.at(-1));
    const step = steps[index++];
    if (!step) {
      throw new Error('O roteiro do modelo falso acabou.');
    }
    if (step.text) {
      return { content: { role: 'model', parts: [{ text: step.text }] }, functionCalls: [], text: step.text };
    }
    const [name, args] = step.call;
    const functionCall = { id: `call-${index}`, name, args };
    return { content: { role: 'model', parts: [{ functionCall }] }, functionCalls: [functionCall], text: '' };
  };
  return { generate, received };
}

/** Resposta de ferramenta enviada ao modelo no último passo. */
function lastToolOutput(received) {
  return received.at(-1).parts[0].functionResponse.response.output;
}

const LASANHA_BOLONHESA = { merchantId: '00000000-0000-4000-8000-000000000100', itemId: '00000000-0000-4000-8000-000000000101' };
const LASANHA_VEGANA_ARROZ = { merchantId: '00000000-0000-4000-8000-000000000200', itemId: '00000000-0000-4000-8000-000000000202' };

describe('fluxo de restaurante', () => {
  const session = getSession('teste-restaurante-0001');

  before(async () => {
    await ensureAccountContext(session);
  });

  it('registra restrições, busca e analisa um item com conflito', async () => {
    const model = scriptedModel([
      { call: ['registrar_restricoes', { restricoes: [{ id: 'alergia_leite' }] }] },
      { call: ['buscar_opcoes', { consulta: 'lasanha', priorizarComFiltrosDoIfood: false }] },
      { call: ['analisar_produto', LASANHA_BOLONHESA] },
      { text: 'Essa lasanha leva molho branco e muçarela.' },
    ]);

    const result = await runAgentTurn(session, 'Quero lasanha, tenho alergia à proteína do leite', { generate: model.generate });

    assert.equal(result.reply, 'Essa lasanha leva molho branco e muçarela.');
    assert.deepEqual(result.cards.map((card) => card.type), ['restrictions', 'options', 'analysis']);
    assert.equal(result.cards[2].data.verdict, 'CONFLITO');
    assert.equal(lastToolOutput(model.received).parecer, 'CONFLITO');

    // A busca prioriza compatibilidade: itens com conflito aparente nunca vêm antes dos demais.
    const verdicts = result.cards[1].data.items.map((item) => item.quickVerdict);
    const firstConflict = verdicts.indexOf('CONFLITO');
    assert.ok(firstConflict === -1 || verdicts.slice(firstConflict).every((verdict) => verdict === 'CONFLITO'));
  });

  it('bloqueia carrinho com item em conflito', async () => {
    const model = scriptedModel([
      { call: ['montar_carrinho', { merchantId: LASANHA_BOLONHESA.merchantId, itens: [{ itemId: LASANHA_BOLONHESA.itemId, quantidade: 1 }] }] },
      { text: 'Não posso adicionar esse item.' },
    ]);
    const result = await runAgentTurn(session, 'Pode pedir mesmo assim', { generate: model.generate });
    assert.equal(result.cards.length, 0);
    assert.match(lastToolOutput(model.received).erro, /incompatíveis/);
  });

  it('monta o carrinho de um item compatível e só envia o pedido com confirmação', async () => {
    const model = scriptedModel([
      { call: ['analisar_produto', LASANHA_VEGANA_ARROZ] },
      { call: ['montar_carrinho', { merchantId: LASANHA_VEGANA_ARROZ.merchantId, itens: [{ itemId: LASANHA_VEGANA_ARROZ.itemId, quantidade: 1 }] }] },
      { text: 'Carrinho pronto para revisão.' },
    ]);
    const result = await runAgentTurn(session, 'Quero a lasanha vegana de massa de arroz', { generate: model.generate });
    const cart = result.cards.find((card) => card.type === 'cart').data;
    assert.ok(cart.cartId);
    assert.equal(cart.items.length, 1);

    const checkout = await getCheckoutOptions(session, cart.cartId);
    assert.ok(checkout.deliveryMethods.length > 0);
    assert.ok(checkout.paymentMethods.length > 0);

    const orderParams = {
      cartId: cart.cartId,
      deliveryMethodId: checkout.deliveryMethods[0].deliveryMethodId,
      paymentMethodId: checkout.paymentMethods[0].paymentMethodId,
      alertsAcknowledged: true,
    };

    // Sem o clique de confirmação, o pedido é recusado.
    await assert.rejects(() => submitOrder(session, { ...orderParams, userConfirmed: false }), /confirmação/);

    const order = await submitOrder(session, { ...orderParams, userConfirmed: true });
    assert.ok(order.orderId);
  });
});

describe('fluxo de mercado', () => {
  const session = getSession('teste-mercado-00001');

  before(async () => {
    await ensureAccountContext(session);
  });

  const recipeWith = (ingredients) => ({
    titulo: 'Lasanha sem leite',
    porcoes: 4,
    ingredientes: ingredients,
    modoDePreparo: ['Monte as camadas e asse.'],
  });

  it('recusa receita com ingrediente incompatível e aceita a corrigida', async () => {
    const model = scriptedModel([
      { call: ['registrar_restricoes', { restricoes: [{ id: 'alergia_leite' }, { id: 'doenca_celiaca' }] }] },
      {
        call: ['registrar_receita', recipeWith([
          { nome: 'Massa para lasanha sem glúten', quantidade: '400 g', busca: 'massa lasanha sem glúten', quantidadeCompra: 1, industrializado: true },
          { nome: 'Queijo muçarela', quantidade: '200 g', busca: 'muçarela', quantidadeCompra: 1 },
        ])],
      },
      {
        call: ['registrar_receita', recipeWith([
          { nome: 'Massa para lasanha sem glúten', quantidade: '400 g', busca: 'massa lasanha sem glúten', quantidadeCompra: 1, industrializado: true },
          { nome: 'Queijo vegetal de mandioca', quantidade: '200 g', busca: 'queijo vegetal', quantidadeCompra: 1, industrializado: true },
          { nome: 'Molho de tomate', quantidade: '340 g', busca: 'molho de tomate', quantidadeCompra: 1, industrializado: true },
          { nome: 'Carne moída', quantidade: '500 g', busca: 'carne moída', quantidadeCompra: 1 },
        ])],
      },
      { call: ['buscar_ingredientes_no_mercado', {}] },
      { text: 'Encontrei os ingredientes.' },
    ]);

    const result = await runAgentTurn(session, 'Quero fazer lasanha em casa. Tenho APLV e doença celíaca.', { generate: model.generate });

    // A primeira receita foi recusada: só a corrigida aparece na interface.
    const recipeCards = result.cards.filter((card) => card.type === 'recipe');
    assert.equal(recipeCards.length, 1);
    assert.ok(recipeCards[0].data.ingredientes.every((ingredient) => ingredient.verificacao.status !== 'CONFLITO'));

    const plan = result.cards.find((card) => card.type === 'market').data;
    assert.ok(plan.merchants.length > 0);
    const recommended = plan.merchants[0];
    assert.equal(recommended.coverage, 4);
    // Nenhum produto com conflito é escolhido (ex.: muçarela comum, massa com trigo).
    assert.ok(recommended.items.every((item) => item.verdict !== 'CONFLITO'));
  });

  it('monta o carrinho do mercado recomendado', async () => {
    const merchantId = session.marketPlan.merchants[0].merchantId;
    const model = scriptedModel([
      { call: ['montar_carrinho_do_mercado', { merchantId }] },
      { text: 'Carrinho pronto.' },
    ]);
    const result = await runAgentTurn(session, 'Pode montar o carrinho', { generate: model.generate });
    const cart = result.cards.find((card) => card.type === 'cart').data;
    assert.equal(cart.items.length, 4);
    // Produtos industrializados sem rótulo completo geram alertas para conferência.
    assert.ok(cart.alerts.length > 0);
  });
});

after(async () => {
  await rm(dataDir, { recursive: true, force: true });
});
