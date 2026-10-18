/**
 * Ponto único de acesso ao iFood.
 *
 * O resto do sistema só conhece a interface `{ mode, callTool(name, args),
 * isAuthenticated(), disconnect() }` e não sabe se fala com o MCP real ou com
 * os dados simulados. A escolha é feita pela variável IFOOD_MODE.
 */

import { config } from '../config.js';
import { LiveIfoodClient } from './liveClient.js';
import { MockIfoodClient } from './mock/mockClient.js';

/** Instância compartilhada por todo o servidor. */
export const ifood = config.ifood.mode === 'mock' ? new MockIfoodClient() : new LiveIfoodClient();
