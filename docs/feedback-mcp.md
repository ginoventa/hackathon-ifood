# Feedback sobre o MCP do iFood (entregável 06)

Pontos observados durante o desenvolvimento do Ailo, com o MCP `consumer-mcp.ifood.com.br/marketplace`. A equipe deve completar este documento com o que encontrar durante o hackathon.

## Dados de produto

1. **Não há ingredientes nem alergênicos estruturados.** A descrição de `getItem` promete "curated attributes (dietary, allergens, descriptors)", mas os itens consultados (restaurante e mercado) trazem só `itemName`, `itemDescription` e `optionGroups`. Para quem tem alergia, essa é a principal lacuna.
2. **Anúncios de mercado quase não têm descrição.** Exemplo: um macarrão sem glúten com descrição "Pacote 500g". Sem lista de ingredientes e sem avisos de "pode conter", não dá para avaliar contato cruzado.
3. **`itemRestrictions` funciona como filtro, mas não aparece na resposta.** Só sabemos que um item é `GLUTEN_FREE` se ele veio de uma busca filtrada. Seria útil receber as etiquetas no próprio item (busca e `getItem`).
4. **Vários filtros `itemRestrictions` são combinados com E lógico.** Para quem tem várias restrições (ex.: celíaco e APLV), filtrar por `GLUTEN_FREE` + `VEGAN` esconde produtos válidos, como carne moída. Precisamos fazer uma busca por filtro.
5. **`browseOffers`/`searchOffers` com `resultKind=ITEM` não trazem descrição.** Para avaliar o cardápio inteiro (contato cruzado), teríamos que chamar `getItem` item a item.
6. **Não há informação de preparo do estabelecimento:** cozinha compartilhada, fritadeira exclusiva, protocolo para alérgicos. Um campo simples ("possui preparo separado para alérgicos?") já ajudaria muito.
7. **Não há canal para perguntar ao restaurante antes do pedido.** O agente gera a mensagem, mas o usuário precisa encontrar outro meio para enviá-la.

## Autenticação

8. **A descoberta OAuth só funciona por `openid-configuration`.** `https://id.ifood.com.br/.well-known/oauth-authorization-server` responde 400, enquanto `/.well-known/openid-configuration` funciona. Clientes MCP que seguem a especificação tentam primeiro o endpoint OAuth.
9. **Não há registro dinâmico de cliente** (`registration_endpoint` ausente). Cada time precisa cadastrar um agente, esperar a aprovação e copiar Client ID e Client Secret. Só então é possível criar a conta de teste.
10. **A documentação diverge entre páginas.** O `llms-full.txt` cita `auth.ifood.com` e `dev-auth.ifood.com.br` e diz que clientes públicos não precisam de `client_secret`. Já o guia de Implementação usa `id.ifood.com.br` e exige `client_secret` na troca e na renovação. Também há escopos `user:read`/`discovery:read` num lugar e `mcp.*` em outro.
11. **A Redirect URL padrão das ferramentas (`http://localhost:8080/callback`) conflita com outros programas** na mesma porta, como o login de MCP de outro cliente aberto ao mesmo tempo.
12. **O erro de login é pouco explicativo.** Quando o agente não envia `client_secret`, o usuário de teste só percebe que "não consegue logar". Uma mensagem como "cliente requer autenticação" ajudaria.

## Ergonomia das ferramentas

13. **Os esquemas usam `"##default"` como valor padrão** em vários campos (`createCart`, `updateCartItem`). Isso confunde LLMs e validadores de JSON Schema.
14. **Tipos como `["string", "null"]` e `format: uuid`** não são aceitos por todos os provedores de function calling (ex.: Gemini). Tivemos de reescrever as declarações à mão.
15. **Pedidos de teste pagos não são reembolsados.** O sandbox poderia oferecer um meio de pagamento simulado, para testar o `submitOrder` sem risco.
16. **Os `agentHints` são úteis** (ex.: escolha do endereço por histórico de uso). Vale manter e expandir.
