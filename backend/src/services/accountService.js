/**
 * Dados da conta do iFood: usuário e endereço de entrega.
 *
 * O endereço é obrigatório para buscar ofertas (as ferramentas do iFood
 * precisam da localização) e para montar carrinhos.
 */

import { ifood } from '../ifood/index.js';
import { ValidationError } from '../utils/errors.js';

/** Converte um endereço do MCP no formato usado pelo Ailo. */
function toAddress(raw) {
  return {
    addressId: raw.addressId,
    formattedAddress: raw.formattedAddress,
    alias: raw.alias ?? null,
    coordinates: raw.coordinates,
    isLastUsedAddress: Boolean(raw.isLastUsedAddress),
    isMostUsedAddress30d: Boolean(raw.isMostUsedAddress30d),
  };
}

/** Lista os endereços salvos na conta do iFood. */
export async function listAddresses() {
  const response = await ifood.callTool('listAddresses', {});
  return (response.results ?? []).map(toAddress);
}

/**
 * Escolhe o endereço mais provável, seguindo a orientação do próprio MCP:
 * último usado, depois o mais usado nos últimos 30 dias, depois o primeiro.
 */
function pickDefaultAddress(addresses) {
  return addresses.find((address) => address.isLastUsedAddress)
    ?? addresses.find((address) => address.isMostUsedAddress30d)
    ?? addresses[0]
    ?? null;
}

/**
 * Garante que a sessão conheça o usuário e o endereço de entrega.
 * As consultas ao iFood só acontecem na primeira vez.
 * @param {import('../sessions/sessionStore.js').Session} session
 */
export async function ensureAccountContext(session) {
  if (!session.user) {
    const response = await ifood.callTool('getUser', {});
    session.user = { fullName: response?.data?.fullName ?? '' };
  }
  if (!session.address) {
    session.address = pickDefaultAddress(await listAddresses());
  }
  return { user: session.user, address: session.address };
}

/**
 * Troca o endereço de entrega da sessão por outro endereço salvo.
 * @param {object} session
 * @param {string} addressId
 */
export async function selectAddress(session, addressId) {
  const address = (await listAddresses()).find((candidate) => candidate.addressId === addressId);
  if (!address) {
    throw new ValidationError('Endereço não encontrado na sua conta do iFood.');
  }
  session.address = address;
  return address;
}

/**
 * Localização usada nas buscas.
 * @throws {ValidationError} se a conta não tiver endereço salvo.
 */
export function userLocation(session) {
  const coordinates = session.address?.coordinates;
  if (!coordinates) {
    throw new ValidationError('Cadastre um endereço de entrega no app do iFood para que eu possa buscar opções perto de você.');
  }
  return { latitude: coordinates.latitude, longitude: coordinates.longitude };
}

/** Primeiro nome do usuário, para personalizar mensagens. */
export function firstName(session) {
  return (session.user?.fullName ?? '').split(' ')[0] ?? '';
}
