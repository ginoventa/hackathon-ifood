/**
 * Rotas do perfil alimentar (página perfil.html).
 */

import { listRestrictionOptions, resolveRestriction } from '../../restrictions/catalog.js';
import { deleteProfile, readProfile, saveProfile } from '../../profiles/profileStore.js';
import { getSession } from '../../sessions/sessionStore.js';
import { summarizeRestrictions } from '../../agent/tools/summaries.js';

/** @param {import('../router.js').Router} router */
export function registerProfileRoutes(router) {
  router.add('GET /api/restrictions/catalog', () => ({ restrictions: listRestrictionOptions() }));

  router.add('GET /api/profile', async () => {
    const profile = await readProfile();
    return { ...profile, resolved: summarizeRestrictions(profile.restrictions.map(resolveRestriction).filter(Boolean)) };
  });

  /** Salva o perfil (exige consentimento) e aplica as restrições à conversa atual. */
  router.add('PUT /api/profile', async ({ sessionId, body }) => {
    const profile = await saveProfile(body.restrictions, body.consent);
    const session = getSession(sessionId);
    session.restrictions = profile.restrictions.map(resolveRestriction).filter(Boolean);
    session.restrictionInputs = profile.restrictions;
    session.analyses.clear();
    return { ...profile, resolved: summarizeRestrictions(session.restrictions) };
  });

  router.add('DELETE /api/profile', async () => {
    await deleteProfile();
    return { ok: true };
  });
}
