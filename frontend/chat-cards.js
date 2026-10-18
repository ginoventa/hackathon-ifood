/**
 * Cartões exibidos na conversa com o Ailo.
 *
 * O backend devolve, junto do texto do agente, cartões estruturados gerados
 * pelas ferramentas (`{ type, data }`). Cada tipo tem um renderizador aqui.
 * Os dados dos cartões vêm de regras determinísticas e do iFood, nunca de
 * texto livre da IA.
 *
 * Os botões dos cartões disparam "ações" recebidas por parâmetro, para que
 * este módulo não dependa da lógica da tela (app.js).
 */

import { el, formatMinutes, formatPrice, icon, RESTRICTION_TYPE_LABELS, VERDICT_INFO, verdictBadge } from './format.js';

/**
 * @typedef {object} CardActions
 * @property {(message: string, display: string) => void} send Envia uma mensagem ao agente.
 * @property {(text: string) => void} fillComposer Preenche o campo de mensagem.
 * @property {(cartId: string) => void} openCheckout Abre a sacola do iFood.
 * @property {(cartId: string) => void} finalizeOrder Abre a finalização (entrega, pagamento e confirmação).
 * @property {(inputs: object[]) => Promise<void>} saveProfile Salva o perfil alimentar.
 * @property {(text: string) => void} toast Mostra um aviso rápido.
 */

/** Botão padrão dos cartões. */
function actionButton(label, onClick, variant = 'secondary') {
  const button = el('button', { className: `card-button ${variant}`, text: label, attrs: { type: 'button' } });
  button.addEventListener('click', onClick);
  return button;
}

/** Contêiner base de um cartão. */
function card(className, children) {
  return el('article', { className: `chat-card ${className}` }, children);
}

/** Lista simples de textos. */
function list(items, className = 'card-list') {
  return el('ul', { className }, items.map((item) => el('li', { text: item })));
}

/** Bloco recolhível (detalhes técnicos, evidências). */
function details(summary, children) {
  return el('details', { className: 'card-details' }, [el('summary', { text: summary }), ...children]);
}

// ---------------------------------------------------------------- Restrições

function renderRestrictions({ restrictions, inputs }, actions) {
  if (!restrictions?.length) {
    return null;
  }

  const chips = el('div', { className: 'restriction-chips' }, restrictions.map((restriction) => (
    el('span', { className: 'restriction-chip' }, [
      el('strong', { text: restriction.label }),
      el('small', { text: RESTRICTION_TYPE_LABELS[restriction.tipo] ?? restriction.tipo }),
    ])
  )));

  // Consentimento explícito antes de guardar dados de saúde (seção 1.1).
  const consent = el('input', { attrs: { type: 'checkbox', id: `consent-${Date.now()}` } });
  const save = actionButton('Salvar no meu perfil', async () => {
    if (!consent.checked) {
      actions.toast('Marque a autorização para salvar seu perfil alimentar.');
      return;
    }
    save.disabled = true;
    try {
      await actions.saveProfile(inputs);
      consent.closest('label').remove();
    save.replaceWith(el('p', { className: 'card-muted', text: 'Restrições salvas no seu perfil.' }));
    } catch (error) {
      save.disabled = false;
      actions.toast(error.message);
    }
  });

  return card('restrictions-card', [
    el('p', { className: 'card-kicker' }, [icon('shield'), 'Restrições consideradas']),
    chips,
    el('label', { className: 'consent-line', attrs: { for: consent.id } }, [
      consent,
      el('span', { text: 'Autorizo guardar estas restrições neste dispositivo para os próximos pedidos.' }),
    ]),
    save,
  ]);
}

// ------------------------------------------------------------------- Busca

function renderOptions({ title, items, alternatives }, actions) {
  if (items.length === 0) {
    return card('options-card', [el('p', { className: 'card-muted', text: 'Nenhuma opção encontrada por perto.' })]);
  }

  const carousel = el('div', { className: 'option-carousel' }, items.map((item) => {
    const choose = actionButton('Analisar este', () => actions.send(
      `Escolhi "${item.itemName}" de ${item.merchantName}. Analise para as minhas restrições. [itemId=${item.itemId}, merchantId=${item.merchantId}]`,
      `Quero o ${item.itemName}, de ${item.merchantName}`,
    ), 'primary');

    const price = item.promotionalUnitPrice < item.unitPrice
      ? [el('strong', { text: formatPrice(item.promotionalUnitPrice) }), el('del', { text: formatPrice(item.unitPrice) })]
      : [el('strong', { text: formatPrice(item.unitPrice) })];

    return el('div', { className: 'option-item' }, [
      el('img', { attrs: { src: item.imageUrl ?? './ailo.svg', alt: '', loading: 'lazy' } }),
      el('div', { className: 'option-body' }, [
        item.ifoodTagLabel ? el('span', { className: 'ifood-tag' }, [icon('check'), item.ifoodTagLabel]) : null,
        el('h3', { text: item.itemName }),
        el('p', { className: 'option-store', text: item.merchantName }),
        el('p', { className: 'option-meta', text: [
          item.merchantRating ? `★ ${item.merchantRating.toFixed(1)}` : '',
          formatMinutes(item.deliveryMinutes),
          item.deliveryFee === 0 ? 'Entrega grátis' : '',
        ].filter(Boolean).join(' · ') }),
        el('div', { className: 'option-price' }, price),
        choose,
      ]),
    ]);
  }));

  return card(`options-card${alternatives ? ' alternatives' : ''}`, [
    el('p', { className: 'card-kicker' }, [icon(alternatives ? 'help' : 'search'), title]),
    carousel,
  ]);
}

function renderMerchants({ title, merchants }, actions) {
  return card('options-card', [
    el('p', { className: 'card-kicker' }, [icon('store'), title]),
    el('div', { className: 'merchant-list' }, merchants.map((merchant) => el('div', { className: 'merchant-row' }, [
      el('div', {}, [
        el('strong', { text: merchant.merchantName }),
        el('p', { className: 'card-muted', text: [merchant.rating ? `★ ${merchant.rating.toFixed(1)}` : '', formatMinutes(merchant.deliveryMinutes)].filter(Boolean).join(' · ') }),
      ]),
      actionButton('Ver cardápio', () => actions.send(
        `Mostre o cardápio de ${merchant.merchantName}. [merchantId=${merchant.merchantId}]`,
        `Ver o cardápio de ${merchant.merchantName}`,
      )),
    ]))),
  ]);
}

// ------------------------------------------------------------------ Análise

/** Nomes amigáveis das etiquetas do iFood. */
const IFOOD_TAG_LABELS = { GLUTEN_FREE: 'Sem glúten', LAC_FREE: 'Sem lactose', VEGAN: 'Vegano', VEGETARIAN: 'Vegetariano' };

/** Etiquetas do iFood presentes na análise (ex.: "Sem glúten"). */
function analysisTags(analysis) {
  const tags = analysis.restrictions
    .flatMap((result) => result.findings)
    .filter((finding) => finding.kind === 'ETIQUETA_IFOOD')
    .flatMap((finding) => finding.terms);
  return [...new Set(tags)].map((tag) => IFOOD_TAG_LABELS[tag] ?? tag);
}

/** Selo amarelo "Inseguro": etiqueta do iFood, mas a loja prepara itens com a substância. */
function unsafeBadge() {
  return el('span', { className: 'verdict-badge unsafe' }, [icon('alert'), 'Inseguro']);
}

function renderAnalysis(analysis, actions) {
  const ids = `[itemId=${analysis.itemId}, merchantId=${analysis.merchantId}]`;
  const alert = analysis.crossContactAlert;

  const restrictionBlocks = analysis.restrictions.map((result) => el('section', { className: 'analysis-restriction' }, [
    el('div', { className: 'analysis-restriction-header' }, [
      el('strong', { text: result.label }),
      alert?.restriction === result.label ? unsafeBadge() : verdictBadge(result.verdict),
    ]),
    // Com o alerta "Inseguro", a explicação já está na caixa amarela abaixo.
    alert?.restriction === result.label ? null : el('p', { text: result.explanation }),

  ]));

  const buttons = analysis.canProceed
    ? [actionButton('Seguir para o pedido', () => actions.send(
      `Quero pedir este item. Monte o carrinho com 1 unidade. ${ids}`,
      'Quero seguir com o pedido',
    ), 'primary')]
    : [
      actionButton('Escolher outro produto', () => actions.send(
        `Quero outro produto compatível, diferente de "${analysis.itemName}".`,
        'Quero escolher outro produto',
        { itemId: analysis.itemId, merchantId: analysis.merchantId },
      )),
      // Industrializado fechado (biscoito, vinho...): não há receita, só outro produto.
      analysis.alternatives.includes('PREPARAR_EM_CASA') ? actionButton('Preparar em casa', () => actions.send(
        `Prefiro preparar em casa uma versão de "${analysis.itemName}" adaptada às minhas restrições.`,
        'Prefiro preparar em casa',
      ), 'primary') : null,
    ];

  return card(`analysis-card ${VERDICT_INFO[analysis.verdict]?.className ?? ''}`, [
    el('div', { className: 'analysis-header' }, [
      analysis.imageUrl ? el('img', { attrs: { src: analysis.imageUrl, alt: '' } }) : null,
      el('div', {}, [
        el('p', { className: 'card-kicker', text: analysis.merchantName }),
        el('h3', { text: analysis.itemName }),
        alert ? unsafeBadge() : verdictBadge(analysis.verdict),
        analysisTags(analysis).length
          ? el('span', { className: 'ifood-tag' }, [icon('check'), `Etiqueta do iFood: ${analysisTags(analysis).join(' · ')}`])
          : null,
      ]),
    ]),
    analysis.labelUrl
      ? el('a', { className: 'label-link', text: 'Ver o rótulo consultado (Open Food Facts)', attrs: { href: analysis.labelUrl, target: '_blank', rel: 'noopener' } })
      : null,
    ...restrictionBlocks,
    alert ? el('div', { className: 'card-note unsafe' }, [
      el('strong', { text: `Possível contato cruzado com ${alert.substance}` }),
      el('p', { text: 'Mesmo com a etiqueta do iFood, o estabelecimento prepara itens como:' }),
      list(alert.examples),
      el('p', { className: 'card-muted', text: 'Isso indica possível contato cruzado, não prova de contaminação.' }),
    ]) : null,
    analysis.missingInfo.length ? el('div', { className: 'card-note' }, [el('strong', { text: 'O que ainda não sabemos' }), list(analysis.missingInfo)]) : null,
    el('div', { className: 'card-actions' }, buttons),
    el('p', { className: 'card-disclaimer', text: analysis.disclaimer }),
  ]);
}

function renderClarification({ itemName, merchantName, text }, actions) {
  const copy = actionButton('Copiar mensagem', async () => {
    try {
      await navigator.clipboard.writeText(text);
      actions.toast('Mensagem copiada. Envie pelo chat do pedido ou pelo telefone do restaurante.');
    } catch {
      actions.toast('Não consegui copiar automaticamente. Selecione o texto e copie.');
    }
  }, 'primary');
  copy.prepend(icon('copy'));

  return card('clarification-card', [
    el('p', { className: 'card-kicker' }, [icon('chat'), `Mensagem para ${merchantName}`]),
    el('p', { className: 'card-muted', text: `Sobre: ${itemName}` }),
    el('p', { className: 'card-muted', text: 'Copie as perguntas e envie ao restaurante pelo canal de contato disponível no iFood.' }),
    el('pre', { className: 'clarification-text', text }),
    el('div', { className: 'card-actions' }, [
      copy,
    ]),
    el('p', { className: 'card-disclaimer', text: 'A resposta do restaurante é uma evidência adicional, não uma certificação de segurança.' }),
  ]);
}

// ------------------------------------------------------------ Receita/mercado

/** Linhas da tabela nutricional (por 100 g) usadas na comparação das trocas. */
const NUTRIENTS = [
  ['energiaKcal', 'Energia', 'kcal'],
  ['carboidratosG', 'Carboidratos', 'g'],
  ['proteinasG', 'Proteínas', 'g'],
  ['gordurasTotaisG', 'Gorduras totais', 'g'],
  ['fibrasG', 'Fibras', 'g'],
  ['sodioMg', 'Sódio', 'mg'],
];

/** Valor nutricional formatado ou "—" quando não há dado. */
function nutrientValue(table, key, unit) {
  const value = table?.[key];
  return typeof value === 'number' ? `${value.toLocaleString('pt-BR')} ${unit}` : '—';
}

/** Composição e tabela nutricional do original e do substituto de uma troca. */
function swapComparison({ original, substituto }) {
  const hasTable = original.tabelaNutricionalPor100g || substituto.tabelaNutricionalPor100g;
  const sources = [...new Set([original.fonteNutricional, substituto.fonteNutricional].filter(Boolean))];
  return details('Composição e tabela nutricional', [
    ...[original, substituto].map((side) => el('p', { className: 'card-muted' }, [
      el('strong', { text: `${side.nome}${side.produto ? ` (${side.produto}${side.produtoFicticio ? ', fictício' : ''})` : ''}: ` }),
      side.composicao ?? 'composição não disponível',
    ])),
    hasTable ? el('table', { className: 'nutrition-table' }, [
      el('thead', {}, [el('tr', {}, [
        el('th', { text: 'Por 100 g' }), el('th', { text: original.nome }), el('th', { text: substituto.nome }),
      ])]),
      el('tbody', {}, NUTRIENTS.map(([key, label, unit]) => el('tr', {}, [
        el('td', { text: label }),
        el('td', { text: nutrientValue(original.tabelaNutricionalPor100g, key, unit) }),
        el('td', { text: nutrientValue(substituto.tabelaNutricionalPor100g, key, unit) }),
      ]))),
    ]) : el('p', { className: 'card-muted', text: 'Tabela nutricional não disponível para esta troca.' }),
    ...sources.map((source) => el('p', { className: 'card-disclaimer', text: source })),
  ]);
}

function renderRecipe(recipe, actions) {
  const ingredients = el('ul', { className: 'ingredient-list' }, recipe.ingredientes.map((ingredient) => {
    const check = ingredient.verificacao;
    const tags = [];
    if (check.status !== 'SEM_CONFLITO_DECLARADO') {
      tags.push(verdictBadge(check.status));
    }
    if (check.labelChecked) {
      tags.push(el('span', { className: 'label-tag ok', text: 'Rótulo verificado' }));
    } else if (check.needsLabelCheck) {
      tags.push(el('span', { className: 'label-tag', text: 'Confira o rótulo' }));
    }
    if (ingredient.jaTenhoEmCasa) {
      tags.push(el('span', { className: 'label-tag muted', text: 'Já tenho' }));
    }
    return el('li', {}, [
      el('span', { text: `${ingredient.quantidade} · ${ingredient.nome}` }),
      ingredient.referenciasDemo?.length ? el('span', { className: 'card-muted', text: `Referência: ${ingredient.referenciasDemo.map((item) => `${item.nome} (${item.embalagem})`).join(' ou ')}` }) : null,
      ingredient.preparacaoCaseira ? el('span', { className: 'card-muted', text: `Para ${ingredient.preparacaoCaseira}` }) : null,
      ingredient.observacao ? el('span', { className: 'card-muted', text: ingredient.observacao }) : null,
      tags.length ? el('span', { className: 'ingredient-tags' }, tags) : null,
    ]);
  }));

  return card('recipe-card', [
    el('p', { className: 'card-kicker' }, [icon('home'), 'Receita adaptada']),
    el('h3', { text: recipe.titulo }),
    el('p', { className: 'card-muted', text: [recipe.porcoes ? `${recipe.porcoes} porções` : '', recipe.tempoMinutos ? `${recipe.tempoMinutos} min` : ''].filter(Boolean).join(' · ') }),
    el('h4', { text: 'Ingredientes' }),
    ingredients,
    recipe.substituicoes.length ? el('div', { className: 'card-note' }, [
      el('strong', { text: 'Substituições' }),
      ...recipe.substituicoes.map((swap) => el('div', { className: 'swap' }, [
        el('p', { text: `${swap.original} → ${swap.substituto}` }),
        swap.comparacao ? swapComparison(swap.comparacao) : null,
      ])),
    ]) : null,
    recipe.cuidados.length ? el('div', { className: 'card-note warning' }, [el('strong', { text: 'Cuidados' }), list(recipe.cuidados)]) : null,
    el('div', { className: 'card-actions' }, [
      actionButton('Aprovar lista', () => actions.send('Aprovo a lista de ingredientes. Pode buscar no mercado.', 'Aprovar lista'), 'primary'),
    ]),
    el('p', { className: 'card-disclaimer', text: 'Receita sugerida pela IA e verificada por regras do Ailo. Confira sempre os rótulos dos produtos.' }),
  ]);
}

function renderMarket(plan, actions) {
  if (plan.merchants.length === 0) {
    return card('market-card', [el('p', { className: 'card-muted', text: 'Não encontrei esses ingredientes nos mercados próximos.' })]);
  }

  const merchantBlock = (merchant, isRecommended) => el('section', { className: `market-merchant${isRecommended ? ' recommended' : ''}` }, [
    el('div', { className: 'market-merchant-header' }, [
      el('div', {}, [
        isRecommended ? el('span', { className: 'recommended-tag', text: 'Melhor combinação' }) : null,
        el('h3', { text: merchant.merchantName }),
        el('p', { className: 'card-muted', text: [
          `${merchant.coverage}/${merchant.totalIngredients} ingredientes`,
          formatMinutes(merchant.deliveryMinutes),
          merchant.deliveryFee === 0 ? 'Entrega grátis' : `Entrega ${formatPrice(merchant.deliveryFee)}`,
        ].filter(Boolean).join(' · ') }),
      ]),
      el('strong', { className: 'market-total', text: formatPrice(merchant.total) }),
    ]),
    el('ul', { className: 'market-items' }, merchant.items.map((item) => el('li', {}, [
      el('div', {}, [
        el('span', { className: 'market-ingredient', text: item.ingrediente }),
        el('strong', { text: `${item.quantidade}× ${item.itemName}` }),
        item.labelVerified
          ? el('span', { className: 'label-tag ok', text: 'Rótulo verificado' })
          : item.verdict !== 'SEM_CONFLITO_DECLARADO' ? verdictBadge(item.verdict) : null,
      ]),
      el('span', { text: formatPrice(item.totalPrice) }),
    ]))),
    merchant.missing.length ? el('p', { className: 'card-note warning', text: `Não encontrado aqui: ${merchant.missing.join(', ')}` }) : null,
    !merchant.meetsMinimum ? el('p', { className: 'card-note warning', text: `Pedido mínimo deste mercado: ${formatPrice(merchant.minimumOrderAmount)}.` }) : null,
    actionButton(isRecommended ? 'Montar carrinho aqui' : 'Escolher este mercado', () => actions.send(
      `Monte o carrinho no mercado ${merchant.merchantName}. [merchantId=${merchant.merchantId}]`,
      `Montar o carrinho no ${merchant.merchantName}`,
    ), isRecommended ? 'primary' : 'secondary'),
  ]);

  const [recommended, ...others] = plan.merchants;
  return card('market-card', [
    el('p', { className: 'card-kicker' }, [icon('cart'), `Ingredientes para ${plan.recipeTitle}`]),
    merchantBlock(recommended, true),
    others.length ? details(`Comparar com outros ${others.length} mercado(s)`, others.map((merchant) => merchantBlock(merchant, false))) : null,
    plan.ingredientsWithoutOption.length
      ? el('p', { className: 'card-note warning', text: `Sem opção nos mercados próximos: ${plan.ingredientsWithoutOption.join(', ')}.` })
      : null,
    el('p', { className: 'card-disclaimer', text: plan.merchants.some((merchant) => merchant.items.some((item) => item.labelSimulated))
      ? 'Apresentação: a verificação dos rótulos é simulada. Confira sempre a embalagem.'
      : 'Os anúncios de mercado raramente trazem a lista de ingredientes. Produtos sinalizados devem ter o rótulo conferido.' }),
  ]);
}

// ----------------------------------------------------------------- Carrinho

function renderCart(cart, actions) {
  return card('cart-card', [
    el('p', { className: 'card-kicker' }, [icon('cart'), 'Carrinho montado']),
    el('h3', { text: cart.merchantName ?? 'Seu carrinho' }),
    el('ul', { className: 'market-items' }, cart.items.map((item) => el('li', {}, [
      el('strong', { text: `${item.quantity}× ${item.name}` }),
      el('span', { text: formatPrice(item.totalPrice) }),
    ]))),
    el('div', { className: 'cart-total' }, [el('span', { text: 'Total' }), el('strong', { text: formatPrice(cart.total ?? cart.subtotal) })]),
    cart.alerts.length ? el('p', { className: 'card-note warning', text: `${cart.alerts.length} alerta(s) alimentar(es) para revisar antes de finalizar.` }) : null,
    el('div', { className: 'card-actions' }, [
      actionButton('Finalizar pedido', () => actions.finalizeOrder(cart.cartId), 'primary'),
    ]),
    el('p', { className: 'card-disclaimer', text: 'Na próxima tela você escolhe entrega e pagamento. O pedido só é enviado ao iFood quando você confirmar.' }),
  ]);
}

const RENDERERS = {
  restrictions: renderRestrictions,
  options: renderOptions,
  merchants: renderMerchants,
  analysis: renderAnalysis,
  clarification: renderClarification,
  recipe: renderRecipe,
  market: renderMarket,
  cart: renderCart,
};

/**
 * Cria o elemento de um cartão. Tipos desconhecidos são ignorados.
 * @param {{ type: string, data: object }} cardData
 * @param {CardActions} actions
 * @returns {HTMLElement | null}
 */
export function renderCard(cardData, actions) {
  const renderer = RENDERERS[cardData.type];
  return renderer ? renderer(cardData.data, actions) : null;
}
