/**
 * Adaptador do Gemini (SDK oficial @google/genai).
 *
 * Expõe uma única função `generate(contents)` para o laço do agente, que
 * assim não depende diretamente do SDK e pode ser testado com um modelo falso.
 */

import { GoogleGenAI } from '@google/genai';

import { config } from '../config.js';
import { AppError } from '../utils/errors.js';
import { SYSTEM_PROMPT } from './systemPrompt.js';
import { functionDeclarations } from './tools/index.js';

let client = null;

/** Cria o cliente sob demanda, para o servidor subir mesmo sem chave configurada. */
function getClient() {
  if (!config.gemini.apiKey) {
    throw new AppError('A chave do Gemini não está configurada. Defina GEMINI_API_KEY no arquivo .env.', { status: 503, code: 'LLM_NAO_CONFIGURADA' });
  }
  client ??= new GoogleGenAI({ apiKey: config.gemini.apiKey });
  return client;
}

/** Traduz erros do Gemini em mensagens úteis. */
function toAppError(error) {
  const status = error?.status ?? error?.code;
  if (status === 429) {
    return new AppError('O limite de uso do Gemini foi atingido. Aguarde um pouco e tente de novo.', { status: 429, code: 'LLM_LIMITE', cause: error });
  }
  if (status === 400 && /api key/i.test(error?.message ?? '')) {
    return new AppError('A chave do Gemini é inválida. Confira GEMINI_API_KEY no .env.', { status: 503, code: 'LLM_CHAVE_INVALIDA', cause: error });
  }
  return new AppError('Não consegui falar com o Gemini agora. Tente novamente.', { status: 502, code: 'LLM_ERRO', cause: error });
}

/**
 * Gera a próxima resposta do modelo.
 * @param {object[]} contents Histórico no formato `Content` do Gemini.
 * @returns {Promise<{ content: object | null, functionCalls: object[], text: string }>}
 */
export async function generate(contents) {
  // Fora do try: a falta de chave já tem mensagem própria e não deve virar erro genérico.
  const gemini = getClient();
  let response;
  try {
    response = await gemini.models.generateContent({
      model: config.gemini.model,
      contents,
      config: {
        systemInstruction: SYSTEM_PROMPT,
        tools: [{ functionDeclarations }],
        temperature: 0.3,
      },
    });
  } catch (error) {
    throw toAppError(error);
  }

  return {
    // O conteúdo é guardado inteiro no histórico (inclui as "thought signatures" do Gemini).
    content: response.candidates?.[0]?.content ?? null,
    functionCalls: response.functionCalls ?? [],
    text: response.text ?? '',
  };
}
