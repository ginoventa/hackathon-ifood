# Ailo · Assistente iFood para restrições alimentares

Agente de IA que ajuda pessoas com **alergias, intolerâncias, doença celíaca e preferências alimentares** a pedir comida no iFood. O Ailo investiga cardápios, reconhece incertezas, explica riscos e oferece caminhos alternativos: consultar o restaurante, escolher outro produto ou preparar em casa com ingredientes do mercado.

Projeto do Hackathon SEMCOMP × iFood 2026 ("Vendendo com Agentes").

## Como rodar

Requisitos: Node.js 20 ou superior.

```sh
npm run setup          # instala as dependências do backend
cp .env.example .env   # depois preencha GEMINI_API_KEY
npm run dev            # http://localhost:5173
```

Na primeira vez, clique em **Conectar iFood** na tela inicial (ou rode `npm run login`) e entre na sua conta. O login usa OAuth com PKCE; os tokens ficam em `backend/.data/`, fora do git.

### Modo demonstração (sem conta do iFood)

```sh
npm run demo
```

Esse modo usa dados simulados de restaurantes e mercados de São Carlos (`backend/src/ifood/mock/`). Os pedidos também são simulados. A chave do Gemini continua necessária para conversar.

### Testes

```sh
npm test
```

Os testes cobrem o analisador de restrições e os dois fluxos completos do agente. No lugar do Gemini entra um "modelo falso" com roteiro fixo, então eles rodam sem rede e sem custo.

## Como funciona

```
Navegador (frontend/)  ──HTTP──▶  Backend Node (backend/src/)
                                   ├─ agent/        Gemini + ferramentas (tool calling)
                                   ├─ restrictions/ Regras determinísticas de restrições
                                   ├─ services/     Busca, análise, mercado, carrinho
                                   └─ ifood/        MCP do iFood (OAuth) ou dados simulados
```

1. O usuário escreve o que quer comer e suas restrições.
2. O **Gemini** interpreta a mensagem e chama ferramentas: `registrar_restricoes`, `buscar_opcoes`, `analisar_produto`, `preparar_mensagem_restaurante`, `registrar_receita`, `buscar_ingredientes_no_mercado`, `montar_carrinho`…
3. As ferramentas consultam o **MCP do iFood** e aplicam o **analisador determinístico**. A LLM não decide sozinha se um produto é seguro.
4. A interface mostra **cartões** com os dados verificados: opções, parecer com evidências, mensagem ao restaurante, receita, comparação de mercados e carrinho.
5. O pedido **só é enviado** quando o usuário revisa tudo e clica em "Confirmar pedido". A LLM não tem acesso a `submitOrder`.

### Regras de segurança implementadas no código

| Regra da proposta | Onde |
| --- | --- |
| Diferenciar alergia, intolerância, celíaca e preferência (rigor diferente) | `restrictions/catalog.js` |
| Não afirmar segurança pela ausência de um termo | `analyzer.js` → `INFORMACAO_INSUFICIENTE` para alergias sem evidência positiva |
| Alergênico em outro item do cardápio = possível contato cruzado, não prova | `analyzer.js` → `analyzeCrossContact` |
| "Sem lactose" não serve para APLV | `catalog.js` → `claimIsInsufficient` |
| Informar a origem de cada evidência | Cada achado tem `where` e `source` |
| Receita da IA validada por regras | `analyzeRecipeIngredients`: receita com conflito é recusada |
| Itens com conflito não entram no carrinho | `services/cartService.js` |
| Confirmação do restaurante é evidência adicional, não certificação | `recordEstablishmentConfirmation`: não anula `CONFLITO` |
| Compra só com confirmação explícita | Rota `POST /api/orders` + ciência dos alertas |
| Perfil alimentar só com autorização | `profiles/profileStore.js` exige `consent: true` |

## Estrutura de pastas

```
backend/
  src/
    server.js                 Entrada: API + arquivos da interface
    config.js                 Variáveis de ambiente
    agent/                    Agente (Gemini)
      agent.js                Laço de conversa e execução de ferramentas
      geminiClient.js         Adaptador do SDK @google/genai
      systemPrompt.js         Instruções do agente
      tools/                  Ferramentas por assunto (restrições, catálogo, mercado, carrinho)
    restrictions/             Motor de regras (sem IA)
      catalog.js              Restrições, termos e etiquetas do iFood
      analyzer.js             Parecer de produtos e receitas
      clarificationMessage.js Mensagem para o restaurante
      textMatching.js         Normalização e busca de termos com negação ("sem leite")
    services/                 Regras de negócio usadas pelas ferramentas e rotas
    ifood/                    Cliente MCP real (OAuth) e cliente simulado
    sessions/                 Contexto da conversa por aba
    profiles/                 Perfil alimentar persistido com consentimento
    http/                     Roteador, arquivos estáticos e rotas /api
  test/                       Testes (node:test)
frontend/
  index.html, app.js          Conversa com o Ailo
  chat-cards.js/.css          Cartões da conversa
  checkout.js                 Revisão e confirmação do pedido
  perfil.html/.js/.css        Perfil alimentar
  api.js, format.js           Cliente da API e utilitários
  loja.html, produto.html…    Loja ilustrativa (protótipo original)
docs/
  feedback-mcp.md             Entregável 06: dores reais com o MCP do iFood
```

## Variáveis de ambiente

Veja `.env.example`. As principais:

- `GEMINI_API_KEY`: chave do Gemini (https://aistudio.google.com/apikey). `API_KEY` também é aceita.
- `GEMINI_MODEL`: padrão `gemini-flash-latest`.
- `IFOOD_MODE`: `live` (MCP real) ou `mock` (demonstração).
- `ALLOW_SUBMIT_ORDER`: `true` permite enviar pedidos reais após a confirmação do usuário.

## API

| Método | Rota | Uso |
| --- | --- | --- |
| GET | `/api/status` | Modo do iFood, conexão e configuração |
| POST | `/api/auth/ifood/login` | Inicia o login OAuth (retorna a URL) |
| GET | `/api/session` | Usuário, endereço e restrições da sessão |
| POST | `/api/chat` | Mensagem ao agente → `{ reply, cards, restrictions }` |
| GET/PUT/DELETE | `/api/profile` | Perfil alimentar (PUT exige `consent: true`) |
| GET | `/api/carts/:cartId/checkout` | Dados da tela de revisão |
| POST | `/api/orders` | Envia o pedido (exige `userConfirmed: true`) |
| GET | `/api/orders/:orderId/track` | Acompanhamento |

Todas as rotas usam o cabeçalho `X-Session-Id`, gerado por aba no navegador.

## Limitações conhecidas

- O MCP do iFood não traz lista de ingredientes nem alergênicos estruturados. A análise usa nome, descrição e adicionais, e por isso alergias graves quase sempre terminam em "informação insuficiente" ou "possível risco". Isso é intencional.
- A busca de contato cruzado lê até 75 itens do cardápio, só pelo nome (a listagem do MCP não traz descrições).
- Sessões ficam em memória: reiniciar o servidor apaga as conversas. O perfil alimentar e o login persistem.
- O formato da resposta de carrinho do MCP real não foi validado com um carrinho real (a criação de carrinho de teste foi bloqueada durante o desenvolvimento). `normalizeCart` aceita variações de nomes de campos.
