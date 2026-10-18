/**
 * Registro das ferramentas disponíveis para o agente.
 *
 * Cada ferramenta tem:
 * - `declaration`: o que a LLM enxerga (nome, descrição e JSON Schema);
 * - `execute(session, args)`: implementação, que devolve `{ output, card? }`.
 *   `output` volta para a LLM; `card` vai para a interface.
 *
 * Note que `submitOrder` NÃO está aqui de propósito: a LLM nunca envia pedidos.
 */

import { buildCartTool, buildGroceryCartTool } from './cartTools.js';
import { merchantMenuTool, searchOptionsTool } from './catalogTools.js';
import { groceryPlanTool, registerRecipeTool } from './marketTools.js';
import {
  analyzeProductTool,
  clarificationMessageTool,
  establishmentAnswerTool,
  registerRestrictionsTool,
} from './restrictionTools.js';

const TOOLS = [
  registerRestrictionsTool,
  searchOptionsTool,
  merchantMenuTool,
  analyzeProductTool,
  clarificationMessageTool,
  establishmentAnswerTool,
  registerRecipeTool,
  groceryPlanTool,
  buildCartTool,
  buildGroceryCartTool,
];

const toolsByName = new Map(TOOLS.map((tool) => [tool.declaration.name, tool]));

/** Declarações no formato esperado pelo Gemini. */
export const functionDeclarations = TOOLS.map((tool) => tool.declaration);

/**
 * Executa uma ferramenta pelo nome.
 * @returns {Promise<{ output: object, card?: object }>}
 */
export async function executeTool(session, name, args) {
  const tool = toolsByName.get(name);
  if (!tool) {
    return { output: { erro: `Ferramenta desconhecida: ${name}` } };
  }
  return tool.execute(session, args ?? {});
}
