/**
 * Login OAuth 2.0 (Authorization Code + PKCE) na conta do iFood.
 *
 * Fluxo:
 * 1. `startLogin()` descobre os endpoints do iFood, gera o PKCE e abre um
 *    servidor temporário em http://localhost:<callbackPort>/callback.
 * 2. O usuário entra na conta do iFood pelo navegador.
 * 3. O iFood redireciona para /callback com um código, trocado por tokens.
 * 4. Os tokens ficam em `.data/ifood-tokens.json` e são renovados com o
 *    refresh_token quando expiram.
 *
 * Os endpoints são descobertos dinamicamente a partir do MCP
 * (/.well-known/oauth-protected-resource), como pede a especificação do MCP.
 */

import { createHash, randomBytes } from 'node:crypto';
import { createServer } from 'node:http';

import { config } from '../config.js';
import { readJson, removeJson, writeJson } from '../utils/jsonFileStore.js';
import { IfoodAuthError } from '../utils/errors.js';

const TOKENS_FILE = 'ifood-tokens.json';

/** Renova o token um pouco antes de expirar, para evitar falhas no meio de uma chamada. */
const EXPIRY_MARGIN_MS = 60_000;

/** Tempo máximo esperando o usuário concluir o login no navegador. */
const LOGIN_TIMEOUT_MS = 10 * 60_000;

let cachedMetadata = null;
let pendingLogin = null;

/** Codifica bytes em base64url (sem padding), como pede o PKCE. */
function base64Url(buffer) {
  return buffer.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Busca JSON e falha com mensagem clara. */
async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ao buscar ${url}`);
  }
  return response.json();
}

/**
 * Descobre o servidor de autorização do iFood a partir do recurso MCP.
 * @returns {Promise<{ resource: string, authorizationEndpoint: string, tokenEndpoint: string }>}
 */
async function discoverMetadata() {
  if (cachedMetadata) {
    return cachedMetadata;
  }

  const mcpUrl = new URL(config.ifood.mcpUrl);
  const resourceMetadata = await fetchJson(`${mcpUrl.origin}/.well-known/oauth-protected-resource${mcpUrl.pathname}`);
  const issuer = resourceMetadata.authorization_servers?.[0];
  if (!issuer) {
    throw new Error('O MCP do iFood não informou o servidor de autorização.');
  }

  // O iFood publica os endpoints em openid-configuration; tentamos também o padrão OAuth.
  let serverMetadata;
  for (const path of ['/.well-known/openid-configuration', '/.well-known/oauth-authorization-server']) {
    try {
      serverMetadata = await fetchJson(`${issuer}${path}`);
      break;
    } catch {
      // Tenta o próximo caminho de descoberta.
    }
  }
  if (!serverMetadata?.authorization_endpoint || !serverMetadata?.token_endpoint) {
    throw new Error('Não foi possível descobrir os endpoints de login do iFood.');
  }

  cachedMetadata = {
    resource: resourceMetadata.resource ?? config.ifood.mcpUrl,
    authorizationEndpoint: serverMetadata.authorization_endpoint,
    tokenEndpoint: serverMetadata.token_endpoint,
  };
  return cachedMetadata;
}

/** URL de retorno registrada para o client_id do iFood. */
function redirectUri() {
  return `http://localhost:${config.ifood.callbackPort}/callback`;
}

/**
 * Chama o endpoint de token (troca de código ou renovação) e salva o resultado.
 * @param {Record<string, string>} params Parâmetros específicos do grant.
 */
async function requestTokens(params) {
  const metadata = await discoverMetadata();
  const response = await fetch(metadata.tokenEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: new URLSearchParams({ client_id: config.ifood.clientId, resource: metadata.resource, ...params }),
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok || !body.access_token) {
    throw new IfoodAuthError(`O iFood recusou o login (${body.error_description ?? body.error ?? response.status}).`);
  }

  const previous = await readJson(TOKENS_FILE, {});
  const tokens = {
    accessToken: body.access_token,
    // Nem toda renovação devolve um novo refresh_token; mantemos o anterior.
    refreshToken: body.refresh_token ?? previous.refreshToken ?? null,
    expiresAt: body.expires_in ? Date.now() + body.expires_in * 1000 : null,
    obtainedAt: new Date().toISOString(),
  };
  await writeJson(TOKENS_FILE, tokens);
  return tokens;
}

/** Página HTML simples mostrada no navegador ao fim do login. */
function callbackPage(title, message) {
  return `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title><meta http-equiv="refresh" content="3;url=${config.appUrl}"></head>
<body style="font-family:Arial,sans-serif;display:grid;place-items:center;height:100vh;margin:0;background:#f5f5f5">
<main style="background:#fff;border-radius:24px;padding:32px;max-width:420px;text-align:center">
<h1 style="font-size:22px">${title}</h1><p style="color:#666">${message}</p>
<a href="${config.appUrl}" style="color:#f92371">Voltar ao Ailo</a></main></body></html>`;
}

/** Encerra o servidor temporário de callback, se houver. */
function closePendingLogin() {
  if (pendingLogin) {
    clearTimeout(pendingLogin.timeout);
    pendingLogin.server.close();
    pendingLogin = null;
  }
}

/**
 * Inicia o login: abre o servidor de callback e devolve a URL de autorização,
 * que deve ser aberta no navegador do usuário.
 * @returns {Promise<{ authorizationUrl: string }>}
 */
export async function startLogin() {
  const metadata = await discoverMetadata();
  closePendingLogin();

  const codeVerifier = base64Url(randomBytes(32));
  const codeChallenge = base64Url(createHash('sha256').update(codeVerifier).digest());
  const state = base64Url(randomBytes(16));

  const authorizationUrl = new URL(metadata.authorizationEndpoint);
  authorizationUrl.search = new URLSearchParams({
    response_type: 'code',
    client_id: config.ifood.clientId,
    redirect_uri: redirectUri(),
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state,
    resource: metadata.resource,
  }).toString();

  const server = createServer(async (req, res) => {
    const url = new URL(req.url, redirectUri());
    if (url.pathname !== '/callback') {
      res.writeHead(404).end();
      return;
    }

    const send = (status, title, message) => {
      res.writeHead(status, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(callbackPage(title, message));
    };

    if (url.searchParams.get('state') !== state) {
      send(400, 'Login não confirmado', 'A resposta do iFood não corresponde a este login. Tente novamente pelo Ailo.');
      return;
    }
    if (url.searchParams.get('error')) {
      send(400, 'Login cancelado', url.searchParams.get('error_description') ?? 'O iFood não autorizou o acesso.');
      closePendingLogin();
      return;
    }

    try {
      await requestTokens({
        grant_type: 'authorization_code',
        code: url.searchParams.get('code') ?? '',
        code_verifier: codeVerifier,
        redirect_uri: redirectUri(),
      });
      send(200, 'Conta do iFood conectada!', 'Você já pode voltar ao Ailo. Redirecionando…');
      console.log('[iFood] Login concluído.');
    } catch (error) {
      send(500, 'Não foi possível concluir o login', error.message);
    } finally {
      closePendingLogin();
    }
  });

  await new Promise((resolvePromise, reject) => {
    server.once('error', (error) => reject(error.code === 'EADDRINUSE'
      ? new Error(`A porta ${config.ifood.callbackPort} está em uso. Feche o outro programa (ex.: outro login do MCP) e tente de novo.`)
      : error));
    server.listen(config.ifood.callbackPort, '127.0.0.1', resolvePromise);
  });

  pendingLogin = { server, timeout: setTimeout(closePendingLogin, LOGIN_TIMEOUT_MS) };
  return { authorizationUrl: authorizationUrl.toString() };
}

/**
 * Retorna um access token válido, renovando-o se necessário.
 * @throws {IfoodAuthError} se o usuário não estiver conectado.
 */
export async function getAccessToken() {
  const tokens = await readJson(TOKENS_FILE, null);
  if (!tokens?.accessToken) {
    throw new IfoodAuthError();
  }

  const isExpired = tokens.expiresAt && Date.now() > tokens.expiresAt - EXPIRY_MARGIN_MS;
  if (!isExpired) {
    return tokens.accessToken;
  }
  if (!tokens.refreshToken) {
    throw new IfoodAuthError('Sua sessão do iFood expirou. Conecte a conta novamente.');
  }

  const renewed = await requestTokens({ grant_type: 'refresh_token', refresh_token: tokens.refreshToken });
  return renewed.accessToken;
}

/** Força a renovação do token (usado quando o MCP responde 401). */
export async function forceRefresh() {
  const tokens = await readJson(TOKENS_FILE, null);
  if (!tokens?.refreshToken) {
    throw new IfoodAuthError('Sua sessão do iFood expirou. Conecte a conta novamente.');
  }
  const renewed = await requestTokens({ grant_type: 'refresh_token', refresh_token: tokens.refreshToken });
  return renewed.accessToken;
}

/** Indica se existe um login salvo. */
export async function hasStoredLogin() {
  const tokens = await readJson(TOKENS_FILE, null);
  return Boolean(tokens?.accessToken);
}

/** Desconecta a conta (apaga os tokens locais). */
export async function logout() {
  closePendingLogin();
  await removeJson(TOKENS_FILE);
}
