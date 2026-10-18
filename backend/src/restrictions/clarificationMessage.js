/**
 * Gera a mensagem de esclarecimento que o usuário pode enviar ao restaurante
 * (seção 1.4, alternativa "Consultar o restaurante").
 *
 * O texto é montado a partir do parecer do analisador, e não pela LLM, para
 * garantir que as perguntas certas sejam feitas para cada tipo de restrição.
 */

import { RIGOR, RESTRICTION_TYPES } from './catalog.js';
import { FINDING_KINDS } from './analyzer.js';

/** Perguntas específicas por tipo de restrição. */
const QUESTIONS_BY_TYPE = {
  [RESTRICTION_TYPES.CELIAC]: (substance) => [
    `O prato leva ${substance} em algum ingrediente, inclusive molhos, temperos e empanados?`,
    'Ele é preparado em superfícies, panelas, formas ou fornos separados dos itens com farinha de trigo?',
    'O óleo de fritura e os utensílios são compartilhados com itens com glúten?',
  ],
  [RESTRICTION_TYPES.ALLERGY]: (substance) => [
    `O prato contém ${substance} ou derivados em algum ingrediente, inclusive molhos, temperos e finalizações?`,
    `Os ingredientes industrializados usados têm aviso de "pode conter ${substance}"?`,
    `Há equipamentos, utensílios ou superfícies compartilhados com preparações que levam ${substance}?`,
  ],
  [RESTRICTION_TYPES.INTOLERANCE]: (substance) => [
    `O prato contém ${substance} em algum ingrediente, inclusive molhos e finalizações?`,
    'É possível preparar sem esses ingredientes?',
  ],
  [RESTRICTION_TYPES.PREFERENCE]: (substance) => [
    `O prato leva ${substance} em algum ingrediente, inclusive caldos e molhos?`,
  ],
};

/**
 * Monta a mensagem para o estabelecimento.
 * @param {object} analysis Resultado de `analyzeProduct`.
 * @param {string} [customerName] Nome do usuário, para assinar a mensagem.
 * @returns {{ text: string, questions: string[] }}
 */
export function buildClarificationMessage(analysis, customerName = '') {
  const questions = [];

  for (const result of analysis.restrictions) {
    const typeQuestions = QUESTIONS_BY_TYPE[result.type] ?? QUESTIONS_BY_TYPE[RESTRICTION_TYPES.ALLERGY];
    questions.push(...typeQuestions(result.substance));

    // Perguntas sobre os pontos específicos encontrados na análise.
    for (const finding of result.findings) {
      if (finding.kind === FINDING_KINDS.UNCERTAIN) {
        questions.push(`Os itens "${finding.terms.join('", "')}" contêm ${result.substance}?`);
      }
      if (finding.kind === FINDING_KINDS.CONTRADICTION) {
        questions.push(`A descrição cita "${finding.terms.join('", "')}". Pode confirmar se o prato é mesmo livre de ${result.substance}?`);
      }
    }
  }

  const uniqueQuestions = [...new Set(questions)];
  const restrictionsText = analysis.restrictions
    .map((result) => result.label.charAt(0).toLowerCase() + result.label.slice(1))
    .join(' e ');
  const isSevere = analysis.restrictions.some((result) => result.rigor === RIGOR.HIGH);

  const lines = [
    'Olá! Tudo bem?',
    '',
    `Tenho interesse no item "${analysis.itemName}", mas tenho ${restrictionsText}.`,
    isSevere ? 'Como mesmo pequenas quantidades podem me fazer mal, gostaria de confirmar alguns pontos antes de pedir:' : 'Antes de pedir, gostaria de confirmar:',
    '',
    ...uniqueQuestions.map((question, index) => `${index + 1}. ${question}`),
    '',
    'Muito obrigado(a) pela atenção!',
  ];

  if (customerName) {
    lines.push(customerName);
  }

  return { text: lines.join('\n'), questions: uniqueQuestions };
}
