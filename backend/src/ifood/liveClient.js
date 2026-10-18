/**
 * Cliente do MCP real do iFood.
 *
 * Usa o SDK oficial do MCP (transporte Streamable HTTP). O token OAuth é
 * injetado em cada requisição por um `fetch` personalizado, o que permite
 * renová-lo sem recriar a conexão.
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

import { config } from '../config.js';
import { IfoodAuthError, IfoodToolError } from '../utils/errors.js';
import { forceRefresh, getAccessToken, hasStoredLogin } from './oauth.js';

const CLIENT_INFO = { name: 'ailo-hackathon', version: '1.0.0' };

export class LiveIfoodClient {
  mode = 'live';

  /** @type {Client | null} */
  #client = null;

  /** @type {Promise<Client> | null} Conexão em andamento (evita conectar duas vezes). */
  #connecting = null;

  /**
   * `fetch` usado pelo transporte do MCP: adiciona o token e, se o iFood
   * responder 401, renova o token e repete a requisição uma vez.
   */
  #authorizedFetch = async (url, init = {}) => {
    const send = async (token) => {
      const headers = new Headers(init.headers);
      headers.set('Authorization', `Bearer ${token}`);
      return fetch(url, { ...init, headers });
    };

    const response = await send(await getAccessToken());
    if (response.status !== 401) {
      return response;
    }
    return send(await forceRefresh());
  };

  /** Abre (ou reaproveita) a conexão com o MCP. */
  async #connect() {
    if (this.#client) {
      return this.#client;
    }
    if (!this.#connecting) {
      this.#connecting = (async () => {
        const client = new Client(CLIENT_INFO);
        const transport = new StreamableHTTPClientTransport(new URL(config.ifood.mcpUrl), { fetch: this.#authorizedFetch });
        transport.onclose = () => {
          this.#client = null;
        };
        await client.connect(transport);
        this.#client = client;
        return client;
      })().finally(() => {
        this.#connecting = null;
      });
    }
    return this.#connecting;
  }

  /** Indica se há uma conta conectada (tokens salvos). */
  async isAuthenticated() {
    return hasStoredLogin();
  }

  /** Fecha a conexão (usado ao desconectar a conta). */
  async disconnect() {
    await this.#client?.close().catch(() => {});
    this.#client = null;
  }

  /**
   * Executa uma ferramenta do MCP e devolve o JSON da resposta.
   * @param {string} name Nome da ferramenta (ex.: "searchOffers").
   * @param {object} args Argumentos da ferramenta.
   * @returns {Promise<any>}
   */
  async callTool(name, args = {}) {
    let result;
    try {
      const client = await this.#connect();
      result = await client.callTool({ name, arguments: args });
    } catch (error) {
      // Conexão perdida: descarta o cliente para reconectar na próxima chamada.
      this.#client = null;
      if (error instanceof IfoodAuthError || /401|unauthorized/i.test(String(error?.message))) {
        throw error instanceof IfoodAuthError ? error : new IfoodAuthError(undefined, error);
      }
      throw new IfoodToolError(name, 'não foi possível falar com o iFood agora. Tente novamente em instantes.', error);
    }

    const text = (result.content ?? [])
      .filter((part) => part.type === 'text')
      .map((part) => part.text)
      .join('\n');

    if (result.isError) {
      throw new IfoodToolError(name, text || 'erro desconhecido');
    }

    // As ferramentas do iFood respondem JSON em texto; preferimos o conteúdo estruturado quando existir.
    if (result.structuredContent) {
      return result.structuredContent;
    }
    try {
      return JSON.parse(text);
    } catch {
      return { text };
    }
  }
}
