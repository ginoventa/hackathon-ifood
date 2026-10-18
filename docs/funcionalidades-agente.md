# Mapa de funcionalidades do agente Ailo

Mapeamento do código atual em 18/10/2026. Descreve a implementação; não representa uma validação de todas as operações no ambiente real do iFood.

## Orquestração

Há um agente principal, criado com `langchain.agents.create_agent` em `backend/ailo/agent/agent.py`. Todos os prompts ficam em `agent/system_prompt.py`: `SYSTEM_PROMPT` orienta o agente e as constantes `<NOME_DA_TOOL>_PROMPT` alimentam as descrições de cada ferramenta no LangChain. Ele usa Gemini (`agent/chat_model.py`) para interpretar mensagens e decidir quais das dez ferramentas registradas em `agent/tools/__init__.py` executar. Os resultados estruturados geram cartões na interface; as decisões alimentares são calculadas pelo analisador determinístico.

## Ferramentas disponíveis à IA

| Funcionalidade | Ferramenta | Entrada principal | Comportamento e resultado | Integração |
| --- | --- | --- | --- | --- |
| Registrar restrições | `registrar_restricoes` | Lista completa de restrições, inclusive personalizadas | Atualiza a sessão, invalida análises quando há mudança e gera cartão apenas quando necessário. Restrições iguais ou vazias não repetem o bloco; perfil já salvo não pede novo consentimento. | Sessão e perfil local |
| Buscar pratos ou restaurantes | `buscar_opcoes` | Consulta; tipo ITEM/MERCHANT; filtros opcionais de preço, ordenação e abertura | Busca por localização, aplica filtros alimentares quando solicitados, ordena produtos por pré-análise do nome e exclui itens descartados da sessão. | MCP `searchOffers` |
| Consultar cardápio | `ver_cardapio_da_loja` | Loja e consulta opcional | Busca itens da loja e apresenta opções; também respeita produtos descartados. | MCP `searchOffers` |
| Analisar produto | `analisar_produto` | Loja, produto e tipo RESTAURANTE/MERCADO | Consulta detalhes, restrições, declarações de ausência, contradições, adicionais e lacunas. Consulta o restante do cardápio quando aplicável. Produz parecer e evidências. | MCP `getItem`; `browseOffers` para cardápio; regras locais |
| Preparar pergunta ao restaurante | `preparar_mensagem_restaurante` | Produto já analisado | Monta mensagem com perguntas sobre ingredientes, preparo e contato cruzado para copiar e enviar manualmente. | Regras locais; não envia mensagens |
| Registrar resposta do restaurante | `registrar_resposta_restaurante` | Loja, produto, resposta informada pela pessoa e restrições opcionais | Guarda a confirmação como evidência adicional e refaz a análise. Não transforma uma confirmação em certificação de segurança. | Sessão, MCP e analisador |
| Montar receita adaptada | `registrar_receita` | Título, ingredientes, quantidades, buscas, substituições e cuidados | Valida ingredientes por regras; recusa receita incompatível para a IA corrigir. Guarda a lista e mostra o cartão sem modo de preparo. | Gemini propõe; regras locais validam |
| Comparar mercados | `buscar_ingredientes_no_mercado` | Receita atual da sessão | Ignora ingredientes já disponíveis em casa, busca com e sem filtros, compara até três mercados, complementa faltantes e reanalisa detalhes do mercado recomendado. Ordena por cobertura e custo total. | MCP `searchOffers` e `getItem` |
| Montar carrinho de restaurante | `montar_carrinho` | Loja, produtos, quantidades, observações e opções | Cria carrinho de uma loja e retorna itens, valores e alertas. Recusa itens com análise CONFLITO. Não envia o pedido. | MCP `createCart` |
| Montar carrinho de mercado | `montar_carrinho_do_mercado` | Mercado escolhido na última comparação | Usa os produtos e quantidades do plano daquele mercado e cria o carrinho. Não envia o pedido. | Plano da sessão e MCP `createCart` |

## Funcionalidades de apoio da aplicação

Estas funções são acionadas pela interface/API e não são ferramentas autônomas da IA.

| Função | Implementação | Comportamento |
| --- | --- | --- |
| Login e logout iFood | `ailo/ifood/oauth.py`; rotas `/api/auth/ifood/*` | OAuth do agente cadastrado, tokens e renovação. |
| Conta e endereço | `services/account.py` | Consulta `getUser` e `listAddresses`, escolhe endereço padrão e permite trocar. |
| Perfil alimentar | `ailo/profiles.py`; `/api/profile` | Consulta, salva com consentimento e exclui o perfil local. |
| Conversa e modos | `ailo/sessions.py`; `/api/chat` | Mantém histórico, restrições, endereço, análises, receita, carrinhos e itens descartados. Alterna Restaurante/Mercado. |
| Nova conversa | `/api/session/reset` | Limpa contexto de compra e histórico, preservando dados de conta, restrições e modo. |
| Evitar cartões repetidos | `frontend/app.js`; `frontend/chat-cards.js` | Atualiza blocos existentes e não renderiza cartão de restrições vazio. |
| Visualizar carrinho | `/api/carts/{cart_id}`; `frontend/checkout.js` | Consulta `getCart`, mostra lista, quantidades, preços, endereço e alertas. |
| Abrir carrinho no iFood | `frontend/checkout.js` | Usa `appDeeplink` devolvido pelo MCP. Sem link válido, mantém a revisão local disponível. Não fabrica URL de carrinho. |
| Revisar entrega e pagamento | `/api/carts/{cart_id}/checkout` | Consulta `getCart`, `getCartDeliveryMethods` e `listPaymentMethods`. |
| Confirmar pedido | `POST /api/orders`; `services/cart.py` | Exige confirmação explícita, ciência dos alertas quando existentes e envio habilitado. Chama `setCartDelivery`, `setCartPayment` e `submitOrder`. |
| Acompanhar pedido | `/api/orders/{order_id}/track` | Consulta o andamento via MCP; a interface atualiza o acompanhamento após finalizar localmente. |

## Pareceres da análise

- `CONFLITO`: ingrediente incompatível declarado.
- `RISCO`: contradição, aviso ou outro indício que exige atenção.
- `INFORMACAO_INSUFICIENTE`: faltam dados para avaliar.
- `SEM_CONFLITO_DECLARADO`: não foi identificado conflito nos dados considerados; não equivale a certificação de segurança.

O analisador mantém a distinção entre alergia ao leite e intolerância à lactose. Para itens tratados como embalados, não infere contato cruzado a partir do preparo da loja; avisos explícitos de rótulo/anúncio continuam considerados. A leitura do cardápio tem limite de páginas e cache, portanto não é uma auditoria de todos os itens ou do ambiente físico.

## Limites importantes

- A IA não dispõe de ferramenta `submitOrder`: o envio depende da ação explícita da pessoa na API/interface.
- Perguntas ao restaurante são preparadas, não enviadas automaticamente.
- A busca usa dados disponíveis no iFood; não obtém automaticamente informações ausentes de ingredientes, fabricação ou cozinha.
- A trava de criação do carrinho bloqueia CONFLITO conhecido; não exige que todos os itens tenham sido analisados previamente. Os alertas da revisão tratam as demais situações.
- O perfil é salvo localmente por instalação; a conversa fica em memória. Isso não implementa um sistema de contas independentes de múltiplos usuários.
- As páginas de loja/produto do protótipo usam catálogo e sacola locais, separados dos carrinhos montados pelo agente no MCP.
