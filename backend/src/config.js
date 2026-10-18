/**
 * Configuração central do backend, lida das variáveis de ambiente.
 *
 * O arquivo `.env` na raiz do repositório é carregado pelo próprio Node
 * (flag --env-file-if-exists nos scripts do package.json).
 * Veja `.env.example` para a lista completa de variáveis.
 */

import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const backendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** Lê uma variável de ambiente, com valor padrão. Remove espaços acidentais. */
function env(name, fallback = '') {
  const value = process.env[name];
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : fallback;
}

/** Converte "true"/"false" em booleano. */
function envFlag(name, fallback) {
  const value = env(name);
  if (!value) {
    return fallback;
  }
  return ['1', 'true', 'sim', 'yes'].includes(value.toLowerCase());
}

const port = Number(env('PORT', '5173'));

export const config = Object.freeze({
  /** Porta do servidor web (API + interface). */
  port,

  /** Pasta com a interface (HTML/CSS/JS) servida pelo backend. */
  frontendDir: resolve(backendRoot, '..', 'frontend'),

  /** Pasta para dados locais: tokens do iFood e perfis alimentares (fora do git). */
  dataDir: resolve(backendRoot, env('DATA_DIR', '.data')),

  gemini: {
    // Aceita API_KEY por compatibilidade com o .env original do projeto.
    apiKey: env('GEMINI_API_KEY', env('API_KEY')),
    model: env('GEMINI_MODEL', 'gemini-flash-latest'),
    /** Máximo de rodadas de ferramenta por mensagem, para evitar laços infinitos. */
    maxToolRounds: Number(env('AGENT_MAX_TOOL_ROUNDS', '10')),
  },

  ifood: {
    /** "live" usa o MCP real do iFood; "mock" usa dados simulados (demonstração offline). */
    mode: env('IFOOD_MODE', 'live') === 'mock' ? 'mock' : 'live',
    mcpUrl: env('IFOOD_MCP_URL', 'https://consumer-mcp.ifood.com.br/marketplace'),
    clientId: env('IFOOD_CLIENT_ID', 'v1QQLHbVAuTz-kbov2vCst8bt2oxu8qh'),
    /** O client_id do iFood só aceita retorno em http://localhost:<porta>/callback. */
    callbackPort: Number(env('IFOOD_OAUTH_CALLBACK_PORT', '8080')),
    /** Envio real do pedido (submitOrder). Sempre exige confirmação explícita na interface. */
    allowSubmitOrder: envFlag('ALLOW_SUBMIT_ORDER', true),
  },

  /** URL pública da interface, usada para voltar ao app após o login do iFood. */
  appUrl: env('APP_URL', `http://localhost:${port}`),
});

/** Lista problemas de configuração que impedem o agente de funcionar. */
export function configProblems() {
  const problems = [];
  if (!config.gemini.apiKey) {
    problems.push('Defina GEMINI_API_KEY no arquivo .env (crie uma chave em https://aistudio.google.com/apikey).');
  }
  return problems;
}
