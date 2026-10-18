/**
 * Ponto de entrada do backend do Ailo.
 *
 * Um único servidor entrega a interface (pasta frontend/) e a API (/api/*).
 * Execute com `npm run dev` na raiz do repositório.
 */

import { createServer } from 'node:http';

import { config, configProblems } from './config.js';
import { Router, sendJson } from './http/router.js';
import { serveStatic } from './http/staticFiles.js';
import { registerAccountRoutes } from './http/routes/accountRoutes.js';
import { registerChatRoutes } from './http/routes/chatRoutes.js';
import { registerOrderRoutes } from './http/routes/orderRoutes.js';
import { registerProfileRoutes } from './http/routes/profileRoutes.js';

const router = new Router();
registerAccountRoutes(router);
registerChatRoutes(router);
registerProfileRoutes(router);
registerOrderRoutes(router);

const server = createServer(async (req, res) => {
  // Cabeçalhos básicos de segurança para todas as respostas.
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'same-origin');

  if (await router.handle(req, res)) {
    return;
  }
  if (await serveStatic(req, res)) {
    return;
  }
  if (req.url.startsWith('/api/')) {
    sendJson(res, 404, { error: { code: 'ROTA_INEXISTENTE', message: 'Rota não encontrada.' } });
    return;
  }
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Página não encontrada');
});

server.listen(config.port, () => {
  console.log(`Ailo disponível em http://localhost:${config.port}`);
  console.log(`iFood: modo ${config.ifood.mode === 'mock' ? 'DEMONSTRAÇÃO (dados simulados)' : 'REAL (MCP do iFood)'}`);
  for (const problem of configProblems()) {
    console.warn(`Atenção: ${problem}`);
  }
});

// Encerramento limpo com Ctrl+C.
process.on('SIGINT', () => {
  server.close(() => process.exit(0));
});
