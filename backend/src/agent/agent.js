/**
 * Laço principal do agente.
 *
 * A cada mensagem do usuário:
 * 1. envia o histórico ao modelo;
 * 2. se o modelo pedir ferramentas, executa-as e devolve os resultados;
 * 3. repete até o modelo responder em texto (ou atingir o limite de rodadas).
 *
 * Os cartões gerados pelas ferramentas são devolvidos à interface junto
 * com o texto final, na ordem em que foram produzidos.
 */

import { config } from '../config.js';
import { AppError } from '../utils/errors.js';
import { generate as geminiGenerate } from './geminiClient.js';
import { executeTool } from './tools/index.js';

/** Quantidade máxima de mensagens guardadas no histórico. */
const MAX_HISTORY_CONTENTS = 60;

const MODE_LABELS = { restaurants: 'Restaurantes', market: 'Mercado (preparo em casa)' };

/** Uma mensagem é "início de turno" se for texto do usuário (e não resposta de ferramenta). */
function isUserTurnStart(content) {
  return content.role === 'user' && content.parts?.some((part) => typeof part.text === 'string');
}

/**
 * Corta o histórico antigo sem separar uma chamada de ferramenta da sua
 * resposta: o corte sempre começa num turno do usuário.
 */
function trimHistory(history) {
  if (history.length <= MAX_HISTORY_CONTENTS) {
    return history;
  }
  let start = history.length - MAX_HISTORY_CONTENTS;
  while (start < history.length && !isUserTurnStart(history[start])) {
    start += 1;
  }
  return history.slice(start);
}

/** Contexto enviado junto da mensagem para o modelo saber o estado da interface. */
function contextNote(session) {
  const restrictions = session.restrictions.length
    ? session.restrictions.map((restriction) => restriction.label).join(', ')
    : 'nenhuma informada ainda';
  return `[Contexto do app: modo ${MODE_LABELS[session.mode] ?? session.mode}; restrições ativas: ${restrictions}; entrega em ${session.address?.alias ?? session.address?.formattedAddress ?? 'endereço não definido'}]`;
}

/** Converte um erro de ferramenta em resposta que o modelo consegue tratar. */
function toolErrorOutput(error) {
  if (error instanceof AppError && error.code === 'IFOOD_LOGIN_NECESSARIO') {
    // Login é um problema para o usuário resolver: interrompe o turno.
    throw error;
  }
  return { erro: error instanceof AppError ? error.message : 'Falha inesperada ao executar a ferramenta.' };
}

/**
 * Processa uma mensagem do usuário.
 * @param {import('../sessions/sessionStore.js').Session} session
 * @param {string} message Texto do usuário (pode conter identificadores entre colchetes).
 * @param {{ generate?: typeof geminiGenerate }} [dependencies] Permite injetar um modelo falso nos testes.
 * @returns {Promise<{ reply: string, cards: object[] }>}
 */
export async function runAgentTurn(session, message, { generate = geminiGenerate } = {}) {
  const contents = [...session.history, { role: 'user', parts: [{ text: `${contextNote(session)}\n${message}` }] }];
  const cards = [];
  let reply = '';

  for (let round = 0; round < config.gemini.maxToolRounds; round += 1) {
    const response = await generate(contents);
    if (!response.content) {
      reply = 'Não consegui gerar uma resposta agora. Pode tentar reformular?';
      break;
    }
    contents.push(response.content);

    if (response.functionCalls.length === 0) {
      reply = response.text.trim();
      break;
    }

    // Executa as ferramentas pedidas, em ordem, e devolve todos os resultados juntos.
    const responseParts = [];
    for (const call of response.functionCalls) {
      let output;
      try {
        const result = await executeTool(session, call.name, call.args);
        output = result.output;
        if (result.card) {
          cards.push(result.card);
        }
      } catch (error) {
        console.warn(`[agente] Ferramenta ${call.name} falhou:`, error.message);
        output = toolErrorOutput(error);
      }
      responseParts.push({ functionResponse: { id: call.id, name: call.name, response: { output } } });
    }
    contents.push({ role: 'user', parts: responseParts });
  }

  if (!reply) {
    reply = cards.length > 0
      ? 'Confira as informações acima. Como quer seguir?'
      : 'Precisei de muitas etapas para responder. Pode detalhar um pouco mais o que você quer?';
  }

  // O histórico precisa terminar numa fala do modelo para alternar corretamente no próximo turno.
  if (contents.at(-1)?.role !== 'model') {
    contents.push({ role: 'model', parts: [{ text: reply }] });
  }

  session.history = trimHistory(contents);
  return { reply, cards };
}
