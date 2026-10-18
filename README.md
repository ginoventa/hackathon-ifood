# Ailo · Assistente iFood para restrições alimentares

Agente de IA que ajuda pessoas com **alergias, intolerâncias, doença celíaca e preferências alimentares** a pedir comida no iFood. O Ailo investiga cardápios, reconhece incertezas, explica riscos e oferece caminhos alternativos: consultar o restaurante, escolher outro produto ou preparar em casa com ingredientes do mercado.

Projeto do Hackathon SEMCOMP × iFood 2026 ("Vendendo com Agentes"). Todos os dados vêm do **MCP do iFood**; não há modo de demonstração.

## Pré-requisitos

- Python 3.11+ e [uv](https://docs.astral.sh/uv/) (gerenciador de pacotes Python).
- Uma LLM, à escolha (`LLM_PROVIDER` no `.env`):
  - **ChatGPT (padrão):** usa a sua assinatura do ChatGPT (ex.: Plus), sem pagar tokens de API. Faça login com `npm run login-chatgpt`.
  - **Gemini:** chave em https://aistudio.google.com/apikey (`LLM_PROVIDER=gemini`).
- Um **agente aprovado** no [MCP Portal do iFood](https://mcp-developer.ifood.com.br) e uma **conta de teste**:
  1. [Crie o agente](https://mcp-developer.ifood.com.br/pt-BR/docs/guides/first-steps/agent), com a Redirect URL `http://localhost:8080/callback` (ou outra; veja abaixo).
  2. Depois da aprovação, copie o **Client ID** e gere o **Client Secret** em *Credenciais de acesso*. O segredo aparece uma única vez.
  3. [Crie uma conta de teste](https://mcp-developer.ifood.com.br/pt-BR/docs/guides/first-steps/test-account). O login dela usa o OTP exibido no próprio portal.

## Como rodar

```sh
npm run setup          # instala as dependências Python (uv sync)
cp .env.example .env   # preencha IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET
npm run login-chatgpt  # entra na conta do ChatGPT (abre o navegador)
npm run dev            # http://localhost:5173
```

O login do ChatGPT fica em `backend/.data/chatgpt-auth.json` (fora do git) e é renovado automaticamente. Sem navegador local, use `npm run login-chatgpt -- --device`.

### ChatGPT como LLM: atenção

O modo `chatgpt` usa o `_ChatOpenAICodex` do `langchain-openai`, uma integração **experimental e não oficial**: ela acessa o backend do Codex (`chatgpt.com/backend-api/codex`), e não a API pública da OpenAI.

- O uso conta nos **limites do seu plano** (não é ilimitado) e pode mudar sem aviso. Cabe a quem usa respeitar os termos da OpenAI.
- Só alguns modelos são aceitos. Numa conta Plus (out/2026): `gpt-5.6-terra` (padrão), `gpt-5.6-luna`, `gpt-5.6-sol`, `gpt-6-luna`, `gpt-6-sol`. Nomes como `gpt-5.5` são recusados. Ajuste em `CHATGPT_MODEL`.
- Para algo estável, volte ao Gemini (`LLM_PROVIDER=gemini`) ou use a API oficial da OpenAI. Basta trocar `agent/chat_model.py`.

Na interface, clique em **Conectar iFood** e entre com a conta de teste. O e-mail ou telefone dela aparece no portal, assim como o código OTP (*Gerar código*).

### Redirect URL

`IFOOD_REDIRECT_URI` precisa ser **exatamente** a Redirect URL cadastrada no agente.

- `http://localhost:8080/callback` (padrão): durante o login, o Ailo abre um servidor temporário na porta 8080. Feche outros programas que usem essa porta, como o login de MCP do Claude Code.
- `http://localhost:5173/callback`: o retorno cai no próprio servidor do Ailo. Cadastre essa URL no agente para usar essa opção.

Também é possível logar pelo terminal com `npm run login`.

### Testes

```sh
npm test
```

Os testes (pytest) cobrem o analisador de restrições, o login OAuth (com o endpoint de token simulado) e os fluxos completos do agente. Neles, um cliente falso do iFood e um chat model falso do LangChain substituem os serviços reais (`backend/tests/fakes.py`), então rodam sem rede e sem custo. Esses dados fictícios existem **só nos testes**.

## Como funciona

```
Navegador (frontend/)  ──HTTP──▶  Backend Python (backend/ailo/, FastAPI)
                                   ├─ agent/         LangChain create_agent + ChatGPT (_ChatOpenAICodex) ou Gemini
                                   ├─ restrictions/  Regras determinísticas de restrições
                                   ├─ services/      Busca, análise, mercado, carrinho
                                   └─ ifood/         MCP do iFood via langchain-mcp-adapters + OAuth do agente
```

- **Agente:** `create_agent` (pacote `langchain`) com o modelo escolhido em `LLM_PROVIDER`: `_ChatOpenAICodex` (`langchain-openai`, assinatura do ChatGPT) ou `ChatGoogleGenerativeAI` (`langchain-google-genai`). As ferramentas do Ailo são `StructuredTool` com `response_format="content_and_artifact"`: a saída vai para a LLM e o cartão da interface viaja como artefato.
- **iFood:** o `MultiServerMCPClient` (`langchain-mcp-adapters`) conecta a `https://consumer-mcp.ifood.com.br/marketplace`. O token do agente é injetado por um `httpx.Auth`, que também o renova quando o iFood responde 401.
- **Login:** OAuth 2.1 com PKCE, como no [guia de implementação](https://mcp-developer.ifood.com.br/pt-BR/docs/guides/authentication/implementacao). A troca do código e a renovação enviam `client_id` + `client_secret`, os tokens são rotacionados a cada renovação e revogados ao desconectar.
- As ferramentas do iFood **não** vão direto para a LLM: os serviços do Ailo as chamam e aplicam as regras de restrição antes.

Fluxo de uma mensagem:

1. O usuário escreve o que quer comer e suas restrições.
2. A LLM (ChatGPT ou Gemini), orquestrada pelo agente do LangChain, chama ferramentas: `registrar_restricoes`, `buscar_opcoes`, `analisar_produto`, `preparar_mensagem_restaurante`, `registrar_receita`, `buscar_ingredientes_no_mercado`, `montar_carrinho`…
3. As ferramentas consultam o MCP do iFood e aplicam o **analisador determinístico**. A LLM não decide sozinha se um produto é seguro.
4. A interface mostra **cartões** com os dados verificados: opções, parecer com evidências, mensagem ao restaurante, receita, comparação de mercados e carrinho.
5. O pedido **só é enviado** quando o usuário revisa tudo e clica em "Confirmar pedido". A LLM não tem acesso a `submitOrder`.

### Regras de segurança implementadas no código

| Regra da proposta | Onde |
| --- | --- |
| Diferenciar alergia, intolerância, celíaca e preferência (rigor diferente) | `restrictions/catalog.py` |
| Não afirmar segurança pela ausência de um termo | `analyzer.py` → `INFORMACAO_INSUFICIENTE` para alergias sem evidência positiva |
| Alergênico em outro item do cardápio = possível contato cruzado, não prova | `analyzer.py` → `_analyze_cross_contact` |
| "Sem lactose" não serve para APLV | `catalog.py` → `insufficient_claims` |
| Informar a origem de cada evidência | Cada achado tem `where` e `source` |
| Receita da IA validada por regras | `analyze_recipe_ingredients`: receita com conflito é recusada |
| Itens com conflito não entram no carrinho | `services/cart.py` |
| Confirmação do restaurante é evidência adicional, não certificação | `record_establishment_confirmation`: não anula `CONFLITO` |
| Compra só com confirmação explícita | Rota `POST /api/orders` + ciência dos alertas |
| Perfil alimentar só com autorização | `profiles.py` exige `consent=True` |
| Etiqueta do iFood tem prioridade | `tools/catalog.py`: com etiqueta (ex.: GLUTEN_FREE), só itens etiquetados são recomendados e nomes de prato ("pizza", "massa") não contam; itens etiquetados do cardápio não são contato cruzado |
| Nunca recomendar item com outra restrição | `tools/catalog.py`: itens com conflito são descartados; sem opção compatível, mostra alternativas que atendem às restrições ou diz que não encontrou (e avisa se as compatíveis estão fechadas) |
| Rótulo de industrializados | `services/labels.py`: consulta a Open Food Facts pelo código de barras (alergênicos, "pode conter", selos e ingredientes) |

### Restrições religiosas e menos comuns

O catálogo inclui, além das alergias e intolerâncias comuns: **sem carne de porco** (islamismo, judaísmo, adventismo), **halal**, **kosher**, **sem carne bovina** (hinduísmo), **alergia a gergelim** e **intolerância à frutose**. Restrições religiosas usam o tipo `RELIGIOSA` e exigem evidência positiva: no halal, por exemplo, carne sem certificação é "possível risco". Qualquer outra regra (jejum, jainismo, alergia a kiwi...) pode ser cadastrada no perfil como **Outra restrição**, com tipo e palavras-chave.

### Rótulo de produtos industrializados

Quando o item tem código de barras (EAN), o Ailo consulta o rótulo na [Open Food Facts](https://world.openfoodfacts.org):

- alergênico declarado ("contém glúten") → **incompatível**;
- "pode conter" → **possível risco**;
- selo de ausência ("sem glúten", "vegano", "halal") → evidência a favor;
- rótulo com dados e sem a substância → "sem conflito declarado", com o lembrete de conferir a embalagem;
- produto fora da base ou sem dados → continua o aviso "confira o rótulo".

A Open Food Facts é colaborativa: os dados são tratados como evidência, nunca como certificação.

## Estrutura de pastas

```
backend/                        Python (uv)
  pyproject.toml                Dependências: FastAPI, LangChain, langchain-google-genai, langchain-mcp-adapters
  ailo/
    main.py                     Entrada: API + arquivos da interface
    config.py                   Variáveis de ambiente (.env)
    errors.py, storage.py       Erros padronizados e persistência local
    sessions.py, profiles.py    Contexto da conversa e perfil alimentar
    login.py                    Login pelo terminal
    api/routes.py               Rotas /api
    agent/
      agent.py                  create_agent: conversa, ferramentas e cartões
      chat_model.py             ChatGPT (_ChatOpenAICodex) ou Gemini (trocar de LLM = mudar só aqui)
    login_chatgpt.py            Login na conta do ChatGPT
      system_prompt.py          Instruções do agente
      tools/                    Ferramentas por assunto (restrições, catálogo, mercado, carrinho)
    restrictions/               Motor de regras (sem IA)
      catalog.py                Restrições, termos e etiquetas do iFood
      analyzer.py               Parecer de produtos e receitas
      clarification.py          Mensagem para o restaurante
      text_matching.py          Normalização e busca de termos com negação ("sem leite")
    services/                   Regras de negócio usadas pelas ferramentas e rotas
    ifood/
      oauth.py                  Login OAuth 2.1 + PKCE do agente
      client.py                 MCP do iFood via LangChain
  tests/                        pytest (com cliente e modelo falsos)
frontend/
  index.html, app.js            Conversa com o Ailo
  chat-cards.js/.css            Cartões da conversa
  checkout.js                   Revisão e confirmação do pedido
  perfil.html/.js/.css          Perfil alimentar
  api.js, format.js             Cliente da API e utilitários
  loja.html, produto.html…      Loja ilustrativa (protótipo original)
docs/
  feedback-mcp.md               Entregável 06: dores reais com o MCP do iFood
```

## Variáveis de ambiente

Veja `.env.example`. As principais:

- `LLM_PROVIDER`: `chatgpt` (padrão) ou `gemini`.
- `CHATGPT_MODEL`: modelo do ChatGPT (padrão `gpt-5.6-terra`).
- `GEMINI_API_KEY` / `GEMINI_MODEL`: só para `LLM_PROVIDER=gemini`.
- `IFOOD_CLIENT_ID` / `IFOOD_CLIENT_SECRET`: credenciais do agente no MCP Portal.
- `IFOOD_REDIRECT_URI`: Redirect URL cadastrada no agente.
- `IFOOD_SCOPES`: escopos técnicos liberados para o agente (opcional).
- `ALLOW_SUBMIT_ORDER`: `true` permite enviar o pedido após a confirmação do usuário. Pedidos de teste pagos (ex.: via PIX) **não são reembolsados**.

## API

| Método | Rota | Uso |
| --- | --- | --- |
| GET | `/api/status` | Conexão com o iFood e configuração |
| POST | `/api/auth/ifood/login` | Inicia o login OAuth (retorna a URL) |
| POST | `/api/auth/ifood/logout` | Revoga os tokens e desconecta |
| GET | `/api/session` | Usuário, endereço e restrições da sessão |
| POST | `/api/chat` | Mensagem ao agente → `{ reply, cards, restrictions }` |
| GET/PUT/DELETE | `/api/profile` | Perfil alimentar (PUT exige `consent: true`) |
| GET | `/api/carts/{cartId}/checkout` | Dados da tela de revisão |
| POST | `/api/orders` | Envia o pedido (exige `userConfirmed: true`) |
| GET | `/api/orders/{orderId}/track` | Acompanhamento |

Todas as rotas usam o cabeçalho `X-Session-Id`, gerado por aba no navegador.

## Limitações conhecidas

- O MCP do iFood não traz lista de ingredientes nem alergênicos estruturados. A análise usa nome, descrição e adicionais, e por isso alergias graves quase sempre terminam em "informação insuficiente" ou "possível risco". Isso é intencional.
- A busca de contato cruzado lê até 75 itens do cardápio, só pelo nome (a listagem do MCP não traz descrições).
- Sessões ficam em memória: reiniciar o servidor apaga as conversas. O perfil alimentar e o login persistem em `backend/.data/`.
- O formato da resposta de carrinho do MCP ainda não foi validado com um carrinho real. `normalize_cart` aceita variações de nomes de campos.
