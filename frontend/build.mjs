import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('dist', {
  recursive: true
});
await Promise.all(['index.html', 'styles.css', 'app.js', 'ailo.svg', 'icons.svg', 'api.js', 'format.js', 'chat-cards.js', 'chat-cards.css', 'checkout.js', 'perfil.html', 'perfil.js', 'perfil.css'].map(file => copyFile(file, `dist/${file}`)));
console.log('Build concluído em dist/');
