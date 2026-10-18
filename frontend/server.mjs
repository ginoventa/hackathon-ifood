import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, resolve } from 'node:path';
const root = process.cwd();
const portArg = process.argv.indexOf('--port');
const port = Number(process.env.PORT || (portArg >= 0 ? process.argv[portArg + 1] : 5173));
const files = new Set(['index.html', 'styles.css', 'app.js', 'ailo.svg', 'icons.svg', 'loja.html', 'produto.html', 'shop.css', 'shop.js', 'product.js', 'catalog.js']);
const types = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml'
};
createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  const file = path === '/' ? 'index.html' : path.slice(1);
  if (!files.has(file)) {
    res.writeHead(404);
    res.end('Not found');
    return;
  }
  try {
    const data = await readFile(resolve(root, file));
    res.writeHead(200, {
      'Content-Type': types[extname(file)]
    });
    res.end(data);
  } catch {
    res.writeHead(500);
    res.end('Unable to load file');
  }
}).listen(port, '0.0.0.0', () => console.log(`Ailo disponível em http://localhost:${port}`));
