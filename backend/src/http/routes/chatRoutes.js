/**
 * Rota da conversa com o agente.
 */

import { runAgentTurn } from '../../agent/agent.js';
import { summarizeRestrictions } from '../../agent/tools/summaries.js';
import { getSession } from '../../sessions/sessionStore.js';
import { ensureAccountContext } from '../../services/accountService.js';
import { ValidationError } from '../../utils/errors.js';

/** Tamanho máximo de uma mensagem do usuário (igual ao limite da interface). */
const MAX_MESSAGE_LENGTH = 2000;

/** Evita duas mensagens simultâneas na mesma sessão, que embaralhariam o histórico. */
const busySessions = new Set();

/** @param {import('../router.js').Router} router */
export function registerChatRoutes(router) {
  router.add('POST /api/chat', async ({ sessionId, body }) => {
    const message = typeof body.message === 'string' ? body.message.trim() : '';
    if (!message) {
      throw new ValidationError('Escreva uma mensagem.');
    }
    if (message.length > MAX_MESSAGE_LENGTH) {
      throw new ValidationError(`A mensagem pode ter até ${MAX_MESSAGE_LENGTH} caracteres.`);
    }

    const session = getSession(sessionId);
    if (busySessions.has(session.id)) {
      throw new ValidationError('Ainda estou respondendo sua mensagem anterior.');
    }
    if (['restaurants', 'market'].includes(body.mode)) {
      session.mode = body.mode;
    }

    busySessions.add(session.id);
    try {
      await ensureAccountContext(session);
      const { reply, cards } = await runAgentTurn(session, message);
      return { reply, cards, restrictions: summarizeRestrictions(session.restrictions) };
    } finally {
      busySessions.delete(session.id);
    }
  });
}
