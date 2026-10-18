/**
 * Cliente da API do Ailo (backend em /api).
 *
 * Cada aba do navegador tem seu próprio `sessionId`, enviado no cabeçalho
 * X-Session-Id. Assim o backend guarda o contexto da conversa daquela aba.
 */

const SESSION_KEY = 'ailo-session-id';

/** Erro da API com o código padronizado do backend. */
export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

/** Lê (ou cria) o identificador de sessão desta aba. */
function sessionId() {
  try {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    // Sem sessionStorage (modo privado restrito): usa um id só em memória.
    sessionId.fallback ??= crypto.randomUUID();
    return sessionId.fallback;
  }
}

/**
 * Faz uma requisição JSON à API.
 * @param {string} path Ex.: "/api/chat".
 * @param {{ method?: string, body?: object }} [options]
 */
async function request(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': sessionId(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Sem conexão com o servidor do Ailo. Verifique se ele está rodando (npm run dev).', 'SEM_CONEXAO', 0);
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(payload.error?.message ?? 'Algo deu errado. Tente novamente.', payload.error?.code ?? 'ERRO', response.status);
  }
  return payload;
}

export const api = {
  status: () => request('/api/status'),
  loadSession: () => request('/api/session'),
  resetSession: () => request('/api/session/reset', { method: 'POST' }),
  setMode: (mode) => request('/api/session/mode', { method: 'POST', body: { mode } }),
  listAddresses: () => request('/api/addresses'),
  selectAddress: (addressId) => request('/api/session/address', { method: 'POST', body: { addressId } }),

  sendMessage: (message, mode, excludeItem, clarification) => request('/api/chat', { method: 'POST', body: { message, mode, excludeItem, clarification } }),

  loginIfood: () => request('/api/auth/ifood/login', { method: 'POST' }),
  logoutIfood: () => request('/api/auth/ifood/logout', { method: 'POST' }),

  restrictionCatalog: () => request('/api/restrictions/catalog'),
  getProfile: () => request('/api/profile'),
  saveProfile: (restrictions, consent) => request('/api/profile', { method: 'PUT', body: { restrictions, consent } }),
  deleteProfile: () => request('/api/profile', { method: 'DELETE' }),

  cart: (cartId) => request(`/api/carts/${encodeURIComponent(cartId)}`),
  checkout: (cartId) => request(`/api/carts/${encodeURIComponent(cartId)}/checkout`),
  submitOrder: (order) => request('/api/orders', { method: 'POST', body: order }),
  trackOrder: (orderId) => request(`/api/orders/${encodeURIComponent(orderId)}/track`),
};
