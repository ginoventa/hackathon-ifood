/**
 * Orquestra a verificação de um produto (seção 1.3):
 * busca os detalhes no iFood, consulta o cardápio quando a restrição exige
 * maior rigor e aplica o analisador determinístico.
 */

import { RIGOR } from '../restrictions/catalog.js';
import { analyzeProduct } from '../restrictions/analyzer.js';
import { buildClarificationMessage } from '../restrictions/clarificationMessage.js';
import { ValidationError } from '../utils/errors.js';
import { firstName } from './accountService.js';
import { getItemDetails, getMenuItems } from './catalogService.js';

/** Garante que a sessão já tenha restrições definidas antes de analisar. */
function requireRestrictions(session) {
  if (session.restrictions.length === 0) {
    throw new ValidationError('Antes de analisar, preciso saber quais são as suas restrições alimentares.');
  }
}

/**
 * Analisa um item escolhido pelo usuário.
 * @param {object} session
 * @param {{ merchantId: string, itemId: string, kind?: 'RESTAURANTE'|'MERCADO' }} params
 */
export async function analyzeSelectedItem(session, { merchantId, itemId, kind = 'RESTAURANTE' }) {
  requireRestrictions(session);

  const product = await getItemDetails(session, merchantId, itemId);

  // Restrições de rigor alto exigem olhar o restante do cardápio (contato cruzado).
  const needsMenu = kind === 'RESTAURANTE' && session.restrictions.some((restriction) => restriction.rigor === RIGOR.HIGH);
  let menuItems = null;
  if (needsMenu) {
    try {
      menuItems = await getMenuItems(session, merchantId, 'RESTAURANT');
    } catch (error) {
      // Sem o cardápio, a análise continua e registra a lacuna de informação.
      console.warn('[análise] Não foi possível ler o cardápio:', error.message);
    }
  }

  const analysis = analyzeProduct(product, session.restrictions, {
    kind,
    menuItems,
    declaredTags: session.declaredTags.get(itemId) ?? [],
    confirmations: session.confirmations,
  });

  // Dados extras úteis para a interface e para montar o carrinho.
  analysis.imageUrl = product.itemImageUrl ?? null;
  analysis.unitPrice = product.promotionalUnitPrice ?? product.unitPrice ?? null;
  analysis.optionGroups = (product.optionGroups ?? []).map((group) => ({
    optionGroupId: group.optionGroupId,
    name: group.name,
    minSelections: group.minSelections ?? 0,
    maxSelections: group.maxSelections ?? 1,
    options: (group.options ?? []).map((option) => ({ optionId: option.optionId, name: option.name, additionalPrice: option.additionalPrice ?? 0 })),
  }));

  session.analyses.set(itemId, analysis);
  return analysis;
}

/**
 * Gera a mensagem para o restaurante a partir da última análise do item.
 * @returns {{ itemId: string, itemName: string, merchantName: string, text: string, questions: string[] }}
 */
export function clarificationFor(session, itemId) {
  const analysis = session.analyses.get(itemId);
  if (!analysis) {
    throw new ValidationError('Analise o item antes de preparar a mensagem para o restaurante.');
  }
  const message = buildClarificationMessage(analysis, firstName(session));
  return { itemId, itemName: analysis.itemName, merchantName: analysis.merchantName, ...message };
}

/**
 * Registra a resposta do estabelecimento informada pelo usuário.
 * Ela entra como EVIDÊNCIA ADICIONAL na próxima análise, nunca como certificação.
 */
export function recordEstablishmentConfirmation(session, { itemId, summary, restrictionIds = [] }) {
  if (!session.analyses.has(itemId)) {
    throw new ValidationError('Só é possível registrar a resposta de um item já analisado.');
  }
  const confirmation = {
    itemId,
    summary: String(summary ?? '').slice(0, 500),
    restrictionIds,
    date: new Date().toLocaleDateString('pt-BR'),
  };
  session.confirmations.push(confirmation);
  return confirmation;
}
