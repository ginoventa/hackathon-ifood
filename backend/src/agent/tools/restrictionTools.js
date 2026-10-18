/**
 * Ferramentas do agente ligadas às restrições alimentares:
 * registrar restrições, analisar um produto e lidar com o restaurante.
 */

import { RESTRICTIONS, RESTRICTION_TYPES, resolveRestriction } from '../../restrictions/catalog.js';
import { ValidationError } from '../../utils/errors.js';
import { analyzeSelectedItem, clarificationFor, recordEstablishmentConfirmation } from '../../services/analysisService.js';
import { summarizeAnalysisForModel, summarizeRestrictions } from './summaries.js';

export const registerRestrictionsTool = {
  declaration: {
    name: 'registrar_restricoes',
    description: 'Define as restrições alimentares ATIVAS da conversa. Envie sempre a lista completa (substitui a anterior).',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        restricoes: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string', enum: [...Object.keys(RESTRICTIONS), 'personalizada'], description: 'Id do catálogo ou "personalizada".' },
              nome: { type: 'string', description: 'Só para personalizada. Ex.: "Alergia a kiwi".' },
              tipo: { type: 'string', enum: Object.values(RESTRICTION_TYPES), description: 'Só para personalizada.' },
              termos: { type: 'array', items: { type: 'string' }, description: 'Só para personalizada: palavras que indicam a substância.' },
              observacao: { type: 'string', description: 'Detalhe dito pelo usuário, se houver.' },
            },
            required: ['id'],
          },
        },
      },
      required: ['restricoes'],
    },
  },

  async execute(session, { restricoes = [] }) {
    const resolved = restricoes.map(resolveRestriction);
    const invalid = restricoes.filter((_, index) => !resolved[index]);
    if (invalid.length > 0) {
      throw new ValidationError(`Restrições inválidas: ${JSON.stringify(invalid)}. Restrições personalizadas precisam de nome e termos.`);
    }

    session.restrictions = resolved;
    session.restrictionInputs = restricoes;
    // Análises antigas foram feitas com outras restrições e deixam de valer.
    session.analyses.clear();

    const summary = summarizeRestrictions(resolved);
    return {
      output: { restricoesAtivas: summary },
      card: { type: 'restrictions', data: { restrictions: summary, inputs: restricoes } },
    };
  },
};

export const analyzeProductTool = {
  declaration: {
    name: 'analisar_produto',
    description: 'Analisa um item escolhido pelo usuário contra as restrições ativas: ingredientes declarados, adicionais, cardápio (contato cruzado) e lacunas. Retorna um parecer determinístico.',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        merchantId: { type: 'string' },
        itemId: { type: 'string' },
        tipo: { type: 'string', enum: ['RESTAURANTE', 'MERCADO'], description: 'Padrão: RESTAURANTE.' },
      },
      required: ['merchantId', 'itemId'],
    },
  },

  async execute(session, { merchantId, itemId, tipo = 'RESTAURANTE' }) {
    const analysis = await analyzeSelectedItem(session, { merchantId, itemId, kind: tipo });
    return {
      output: summarizeAnalysisForModel(analysis),
      card: { type: 'analysis', data: analysis },
    };
  },
};

export const clarificationMessageTool = {
  declaration: {
    name: 'preparar_mensagem_restaurante',
    description: 'Gera a mensagem para o usuário enviar ao restaurante, confirmando ingredientes, preparo e contato cruzado do item analisado.',
    parametersJsonSchema: {
      type: 'object',
      properties: { itemId: { type: 'string' } },
      required: ['itemId'],
    },
  },

  async execute(session, { itemId }) {
    const message = clarificationFor(session, itemId);
    return {
      output: { mensagemGerada: true, perguntas: message.questions.length },
      card: { type: 'clarification', data: message },
    };
  },
};

export const establishmentAnswerTool = {
  declaration: {
    name: 'registrar_resposta_restaurante',
    description: 'Registra o que o restaurante respondeu (contado pelo usuário) e refaz a análise do item. É evidência adicional, não certificação.',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        itemId: { type: 'string' },
        merchantId: { type: 'string' },
        resumo: { type: 'string', description: 'Resumo fiel do que o restaurante disse.' },
      },
      required: ['itemId', 'merchantId', 'resumo'],
    },
  },

  async execute(session, { itemId, merchantId, resumo }) {
    recordEstablishmentConfirmation(session, { itemId, summary: resumo });
    const analysis = await analyzeSelectedItem(session, { merchantId, itemId });
    return {
      output: summarizeAnalysisForModel(analysis),
      card: { type: 'analysis', data: analysis },
    };
  },
};
