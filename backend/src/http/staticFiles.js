/**
 * Entrega dos arquivos da interface (pasta frontend/).
 * Bloqueia acesso fora da pasta e arquivos de desenvolvimento.
 */

import { readFile } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';

import { config } from '../config.js';

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.json': 'application/json; charset=utf-8',
};

/** Arquivos da pasta frontend/ que não fazem parte da interface publicada. */
const BLOCKED_FILES = new Set(['server.mjs', 'build.mjs', 'package.json']);

/**
 * Tenta servir um arquivo estático. Retorna false se não encontrar.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 */
export async function serveStatic(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    return false;
  }

  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const relative = pathname === '/' ? 'index.html' : pathname.slice(1);
  const filePath = resolve(config.frontendDir, relative);
  const contentType = CONTENT_TYPES[extname(filePath)];

  // Impede "../" para sair da pasta da interface.
  const insideFrontend = filePath.startsWith(config.frontendDir + sep);
  if (!insideFrontend || !contentType || BLOCKED_FILES.has(relative) || relative.split('/').some((part) => part.startsWith('.') || part === 'node_modules' || part === 'dist')) {
    return false;
  }

  try {
    const data = await readFile(filePath);
    res.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-cache' });
    res.end(req.method === 'HEAD' ? undefined : data);
    return true;
  } catch {
    return false;
  }
}
