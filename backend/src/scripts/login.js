/**
 * Login no iFood pelo terminal: `npm run login` (na pasta backend/).
 *
 * Alternativa ao botão "Conectar iFood" da interface. Mostra a URL de login,
 * espera o retorno do navegador e salva os tokens em .data/.
 */

import { hasStoredLogin, logout, startLogin } from '../ifood/oauth.js';

const POLL_INTERVAL_MS = 1000;
const TIMEOUT_MS = 10 * 60 * 1000;

await logout();
const { authorizationUrl } = await startLogin();

console.log('Abra esta URL no navegador e entre na sua conta do iFood:\n');
console.log(authorizationUrl);
console.log('\nAguardando o login…');

const startedAt = Date.now();
while (!(await hasStoredLogin())) {
  if (Date.now() - startedAt > TIMEOUT_MS) {
    console.error('Tempo esgotado. Rode o comando de novo.');
    process.exit(1);
  }
  await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
}

console.log('Conta do iFood conectada! Agora rode `npm run dev` na raiz do projeto.');
process.exit(0);
