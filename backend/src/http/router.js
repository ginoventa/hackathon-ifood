/**
 * Roteador HTTP mínimo, sem dependências.
 *
 * Rotas são declaradas como `"MÉTODO /caminho/:parametro"`. Os handlers
 * recebem `{ req, params, query, body, sessionId }` e devolvem um objeto,
 * que é enviado como JSON. Erros `AppError` viram respostas com status e
 * código padronizados.
 */

import { AppError } from '../utils/errors.js';

/** Tamanho máximo do corpo JSON aceito. */
const MAX_BODY_BYTES = 64 * 1024;

/** Lê e interpreta o corpo JSON da requisição. */
async function readJsonBody(req) {
  if (req.method === 'GET' || req.method === 'HEAD') {
    return {};
  }
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      throw new AppError('Requisição muito grande.', { status: 413, code: 'CORPO_GRANDE' });
    }
    chunks.push(chunk);
  }
  if (chunks.length === 0) {
    return {};
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new AppError('JSON inválido.', { status: 400, code: 'JSON_INVALIDO' });
  }
}

/** Envia uma resposta JSON. */
export function sendJson(res, status, payload) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(payload));
}

/** Converte "/api/orders/:orderId" numa expressão regular com grupos nomeados. */
function compilePath(path) {
  const pattern = path.replace(/:([a-zA-Z]+)/g, '(?<$1>[^/]+)');
  return new RegExp(`^${pattern}$`);
}

export class Router {
  #routes = [];

  /**
   * Registra uma rota.
   * @param {string} definition Ex.: "POST /api/chat".
   * @param {(context: object) => Promise<object> | object} handler
   */
  add(definition, handler) {
    const [method, path] = definition.split(' ');
    this.#routes.push({ method, regex: compilePath(path), handler });
    return this;
  }

  /**
   * Tenta atender a requisição. Retorna false se nenhuma rota corresponder.
   * @param {import('node:http').IncomingMessage} req
   * @param {import('node:http').ServerResponse} res
   */
  async handle(req, res) {
    const url = new URL(req.url, 'http://localhost');
    const route = this.#routes.find((candidate) => candidate.method === req.method && candidate.regex.test(url.pathname));
    if (!route) {
      return false;
    }

    try {
      const params = url.pathname.match(route.regex).groups ?? {};
      const body = await readJsonBody(req);
      const sessionId = req.headers['x-session-id'];
      const result = await route.handler({ req, params, query: url.searchParams, body, sessionId });
      sendJson(res, 200, result ?? { ok: true });
    } catch (error) {
      if (error instanceof AppError) {
        sendJson(res, error.status, { error: { code: error.code, message: error.message } });
      } else {
        console.error('[http] Erro inesperado:', error);
        sendJson(res, 500, { error: { code: 'ERRO_INTERNO', message: 'Algo deu errado do nosso lado. Tente novamente.' } });
      }
      if (error?.cause) {
        console.warn('[http] Causa:', error.cause?.message ?? error.cause);
      }
    }
    return true;
  }
}
