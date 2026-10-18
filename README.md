# Ailo · Hackathon iFood

Recriação responsiva da interface do Ailo a partir dos prints de referência, com HTML, CSS e JavaScript, sem dependências externas.

## Estrutura

O código da interface, os assets e os scripts de desenvolvimento ficam em `frontend/`. Os comandos abaixo podem ser executados na raiz do repositório ou dentro de `frontend/`.

## Executar

```sh
npm run dev
```

Abra http://localhost:5173. Para outra porta: `npm run dev -- --port 3000`.

## Validar e gerar arquivos estáticos

```sh
npm run check
npm run build
```

Os arquivos para hospedagem são gerados em `frontend/dist/`.

## Funcionalidades

- Abertura com o símbolo Ailo, modos Restaurantes e Mercado e fundos rosa/azul.
- Menu, edição de endereço, sugestões e nova conversa.
- Conversa demonstrativa com respostas locais. Não há integração com IA, restaurantes, preços ou pedidos reais. O ponto de integração é a função `sendMessage` em `frontend/app.js`.
- Ditado por voz quando suportado pelo navegador, sujeito à permissão de microfone e ao serviço de reconhecimento do navegador. Geralmente exige HTTPS ou localhost.
- Layout adaptado a celular e desktop, navegação por teclado e preferência por movimento reduzido.

O nome e a identidade visual são reproduzidos para o protótipo da hackathon.

## Loja e produto

- `http://localhost:5173/loja.html`: loja fictícia, cardápio, busca e sacola.
- `http://localhost:5173/produto.html?id=burger`: detalhes, adicionais, observação e quantidade.
- O menu do Ailo tem um link para a loja. A loja também permite voltar ao Ailo.
- Os dados ilustrativos estão em `frontend/catalog.js`. A sacola é armazenada localmente no navegador; não há checkout ou pedidos reais.
- As fotos ilustrativas são carregadas do Unsplash e precisam de conexão com a internet.
