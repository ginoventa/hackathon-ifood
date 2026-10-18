/**
 * Rotas de status, login no iFood e sessão (usuário, endereço, modo).
 */

import { config, configProblems } from '../../config.js';
import { ifood } from '../../ifood/index.js';
import { logout, startLogin } from '../../ifood/oauth.js';
import { readProfileRestrictions, readProfile } from '../../profiles/profileStore.js';
import { getSession, resetConversation } from '../../sessions/sessionStore.js';
import { ensureAccountContext, listAddresses, selectAddress } from '../../services/accountService.js';
import { summarizeRestrictions } from '../../agent/tools/summaries.js';
import { ValidationError } from '../../utils/errors.js';

/** Estado da sessão enviado à interface. */
async function sessionPayload(session) {
  return {
    sessionId: session.id,
    mode: session.mode,
    user: session.user,
    address: session.address,
    restrictions: summarizeRestrictions(session.restrictions),
    restrictionInputs: session.restrictionInputs,
  };
}

/** @param {import('../router.js').Router} router */
export function registerAccountRoutes(router) {
  router.add('GET /api/status', async () => ({
    ifoodMode: ifood.mode,
    ifoodConnected: await ifood.isAuthenticated(),
    llmConfigured: Boolean(config.gemini.apiKey),
    submitEnabled: config.ifood.allowSubmitOrder,
    problems: configProblems(),
  }));

  router.add('POST /api/auth/ifood/login', async () => {
    if (ifood.mode === 'mock') {
      throw new ValidationError('O modo de demonstração não precisa de login.');
    }
    return startLogin();
  });

  router.add('POST /api/auth/ifood/logout', async () => {
    await ifood.disconnect();
    await logout();
    return { ok: true };
  });

  /**
   * Carrega a sessão: conta do iFood, endereço e restrições do perfil salvo
   * (se o usuário autorizou o armazenamento).
   */
  router.add('GET /api/session', async ({ sessionId }) => {
    const session = getSession(sessionId);
    if (session.restrictions.length === 0) {
      const profile = await readProfile();
      session.restrictions = await readProfileRestrictions();
      session.restrictionInputs = profile.restrictions;
    }
    await ensureAccountContext(session);
    return sessionPayload(session);
  });

  router.add('GET /api/addresses', async () => ({ addresses: await listAddresses() }));

  router.add('POST /api/session/address', async ({ sessionId, body }) => {
    const session = getSession(sessionId);
    await selectAddress(session, body.addressId);
    return sessionPayload(session);
  });

  router.add('POST /api/session/mode', async ({ sessionId, body }) => {
    const session = getSession(sessionId);
    if (!['restaurants', 'market'].includes(body.mode)) {
      throw new ValidationError('Modo inválido.');
    }
    session.mode = body.mode;
    return { mode: session.mode };
  });

  router.add('POST /api/session/reset', async ({ sessionId }) => {
    const session = resetConversation(getSession(sessionId).id);
    return sessionPayload(session);
  });
}
