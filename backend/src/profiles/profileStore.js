/**
 * Perfil alimentar do usuário (seção 1.1: "mediante autorização").
 *
 * Restrições alimentares são dados de saúde. Por isso:
 * - só são gravadas com consentimento explícito (`consent: true`);
 * - ficam apenas na máquina local (`.data/perfil-alimentar.json`, fora do git);
 * - podem ser apagadas a qualquer momento pela página de perfil.
 */

import { resolveRestriction } from '../restrictions/catalog.js';
import { readJson, removeJson, writeJson } from '../utils/jsonFileStore.js';
import { ValidationError } from '../utils/errors.js';

const PROFILE_FILE = 'perfil-alimentar.json';

/**
 * Lê o perfil salvo.
 * @returns {Promise<{ restrictions: object[], consentAt: string | null, updatedAt: string | null }>}
 */
export async function readProfile() {
  const profile = await readJson(PROFILE_FILE, null);
  return {
    restrictions: Array.isArray(profile?.restrictions) ? profile.restrictions : [],
    consentAt: profile?.consentAt ?? null,
    updatedAt: profile?.updatedAt ?? null,
  };
}

/** Restrições do perfil já resolvidas pelo catálogo (ignora entradas inválidas). */
export async function readProfileRestrictions() {
  const profile = await readProfile();
  return profile.restrictions.map(resolveRestriction).filter(Boolean);
}

/**
 * Salva o perfil. Exige consentimento explícito.
 * @param {object[]} restrictionInputs Restrições no formato de entrada (`{ id, nome?, tipo?, termos?, observacao? }`).
 * @param {boolean} consent
 */
export async function saveProfile(restrictionInputs, consent) {
  if (consent !== true) {
    throw new ValidationError('Para salvar o perfil alimentar, é preciso autorizar o armazenamento.');
  }
  if (!Array.isArray(restrictionInputs)) {
    throw new ValidationError('Lista de restrições inválida.');
  }

  const valid = restrictionInputs.filter((input) => resolveRestriction(input));
  const previous = await readProfile();
  const now = new Date().toISOString();
  const profile = { restrictions: valid, consentAt: previous.consentAt ?? now, updatedAt: now };
  await writeJson(PROFILE_FILE, profile);
  return profile;
}

/** Apaga o perfil e o consentimento. */
export async function deleteProfile() {
  await removeJson(PROFILE_FILE);
}
