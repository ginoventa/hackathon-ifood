/**
 * Sessões de conversa em memória.
 *
 * Cada aba do navegador gera um `sessionId` e o envia em toda requisição.
 * A sessão guarda o histórico com a LLM e o CONTEXTO ESTRUTURADO da conversa
 * (restrições, análises, receita, carrinhos), que permite trocar do fluxo de
 * restaurante para o de mercado sem o usuário repetir informações (seção 3).
 */

import { randomUUID } from 'node:crypto';

/** Sessões sem uso por mais tempo que isto são descartadas. */
const SESSION_TTL_MS = 6 * 60 * 60 * 1000;

/** Intervalo da limpeza de sessões expiradas. */
const CLEANUP_INTERVAL_MS = 15 * 60 * 1000;

/** Formato aceito para identificadores vindos do navegador. */
const SESSION_ID_PATTERN = /^[a-zA-Z0-9-]{8,64}$/;

/** @type {Map<string, Session>} */
const sessions = new Map();

/**
 * @typedef {object} Session
 * @property {string} id
 * @property {number} updatedAt
 * @property {'restaurants'|'market'} mode Modo escolhido na interface.
 * @property {object[]} history Histórico no formato `Content` do Gemini.
 * @property {object[]} restrictions Restrições resolvidas (catálogo).
 * @property {object[]} restrictionInputs Restrições como informadas (para salvar no perfil).
 * @property {object | null} address Endereço de entrega escolhido.
 * @property {object | null} user Dados do usuário no iFood.
 * @property {Map<string, string[]>} declaredTags Etiquetas do iFood por item (filtros de busca).
 * @property {Map<string, object>} products Dados completos dos itens consultados.
 * @property {Map<string, object>} analyses Últimas análises por item.
 * @property {object[]} confirmations Confirmações dos estabelecimentos informadas pelo usuário.
 * @property {object | null} recipe Receita adaptada atual.
 * @property {object | null} marketPlan Última comparação de mercados.
 * @property {Map<string, object>} carts Carrinhos criados nesta sessão.
 * @property {object[]} orders Pedidos enviados nesta sessão.
 */

/** Cria uma sessão vazia. */
function createSession(id) {
  return {
    id,
    updatedAt: Date.now(),
    mode: 'restaurants',
    history: [],
    restrictions: [],
    restrictionInputs: [],
    address: null,
    user: null,
    declaredTags: new Map(),
    products: new Map(),
    analyses: new Map(),
    confirmations: [],
    recipe: null,
    marketPlan: null,
    carts: new Map(),
    orders: [],
  };
}

/**
 * Busca a sessão pelo id, criando-a se necessário.
 * Ids inválidos geram uma sessão nova com id do servidor.
 * @param {string | undefined} sessionId
 * @returns {Session}
 */
export function getSession(sessionId) {
  const id = typeof sessionId === 'string' && SESSION_ID_PATTERN.test(sessionId) ? sessionId : randomUUID();
  let session = sessions.get(id);
  if (!session) {
    session = createSession(id);
    sessions.set(id, session);
  }
  session.updatedAt = Date.now();
  return session;
}

/**
 * Reinicia a conversa mantendo o que é do usuário (endereço e restrições).
 * Usado no botão "Nova conversa".
 */
export function resetConversation(sessionId) {
  const previous = sessions.get(sessionId);
  const session = createSession(sessionId);
  if (previous) {
    session.address = previous.address;
    session.user = previous.user;
    session.restrictions = previous.restrictions;
    session.restrictionInputs = previous.restrictionInputs;
    session.mode = previous.mode;
  }
  sessions.set(sessionId, session);
  return session;
}

/** Registra as etiquetas do iFood de itens que vieram de uma busca filtrada. */
export function rememberDeclaredTags(session, itemIds, tags) {
  if (!tags?.length) {
    return;
  }
  for (const itemId of itemIds) {
    const current = new Set(session.declaredTags.get(itemId) ?? []);
    tags.forEach((tag) => current.add(tag));
    session.declaredTags.set(itemId, [...current]);
  }
}

// Limpeza periódica. `unref` impede que o timer segure o processo aberto.
setInterval(() => {
  const limit = Date.now() - SESSION_TTL_MS;
  for (const [id, session] of sessions) {
    if (session.updatedAt < limit) {
      sessions.delete(id);
    }
  }
}, CLEANUP_INTERVAL_MS).unref();
