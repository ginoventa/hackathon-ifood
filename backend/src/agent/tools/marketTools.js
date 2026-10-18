/**
 * Ferramentas do fluxo de mercado (seção 2): receita adaptada e busca
 * dos ingredientes nos mercados do iFood.
 */

import { ValidationError } from '../../utils/errors.js';
import { planGroceryShopping, registerRecipe } from '../../services/marketService.js';

export const registerRecipeTool = {
  declaration: {
    name: 'registrar_receita',
    description: 'Registra a receita adaptada às restrições ativas. O sistema verifica cada ingrediente e RECUSA a receita se algum conflitar.',
    parametersJsonSchema: {
      type: 'object',
      properties: {
        titulo: { type: 'string' },
        porcoes: { type: 'integer' },
        tempoMinutos: { type: 'integer' },
        ingredientes: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              nome: { type: 'string', description: 'Ex.: "Massa para lasanha sem glúten".' },
              quantidade: { type: 'string', description: 'Quantidade da receita, ex.: "250 g".' },
              busca: { type: 'string', description: 'Termo curto para buscar no mercado.' },
              quantidadeCompra: { type: 'integer', description: 'Embalagens/unidades a comprar.' },
              industrializado: { type: 'boolean', description: 'true se o rótulo precisa ser conferido.' },
              jaTenhoEmCasa: { type: 'boolean' },
            },
            required: ['nome', 'quantidade', 'busca', 'quantidadeCompra'],
          },
        },
        substituicoes: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              original: { type: 'string' },
              substituto: { type: 'string' },
              motivo: { type: 'string' },
            },
            required: ['original', 'substituto'],
          },
        },
        modoDePreparo: { type: 'array', items: { type: 'string' } },
        cuidados: { type: 'array', items: { type: 'string' }, description: 'Rótulos, contato cruzado na cozinha, utensílios.' },
      },
      required: ['titulo', 'ingredientes', 'modoDePreparo'],
    },
  },

  async execute(session, args) {
    if (session.restrictions.length === 0) {
      throw new ValidationError('Registre as restrições do usuário antes de montar a receita.');
    }
    const { accepted, recipe, conflicts } = registerRecipe(session, args);

    if (!accepted) {
      // A LLM recebe o motivo e deve corrigir a receita; nada é mostrado ao usuário.
      return {
        output: {
          aceita: false,
          motivo: 'Ingredientes incompatíveis com as restrições. Substitua-os e chame registrar_receita novamente.',
          conflitos: conflicts.map((conflict) => ({ ingrediente: conflict.nome, restricoes: conflict.conflicts.map((item) => `${item.label}: ${item.terms.join(', ')}`) })),
        },
      };
    }

    return {
      output: {
        aceita: true,
        ingredientesParaConferirRotulo: recipe.ingredientes.filter((ingredient) => ingredient.verificacao.needsLabelCheck).map((ingredient) => ingredient.nome),
        ingredientesComDuvida: recipe.ingredientes.filter((ingredient) => ingredient.verificacao.uncertain.length > 0).map((ingredient) => ingredient.nome),
      },
      card: { type: 'recipe', data: recipe },
    };
  },
};

export const groceryPlanTool = {
  declaration: {
    name: 'buscar_ingredientes_no_mercado',
    description: 'Busca os ingredientes da receita atual nos mercados do iFood e compara preço, compatibilidade, entrega e pedido mínimo.',
    parametersJsonSchema: { type: 'object', properties: {} },
  },

  async execute(session) {
    const plan = await planGroceryShopping(session);
    return {
      output: {
        mercadoRecomendado: plan.merchants[0] && {
          merchantId: plan.merchants[0].merchantId,
          nome: plan.merchants[0].merchantName,
          cobertura: `${plan.merchants[0].coverage}/${plan.merchants[0].totalIngredients}`,
          total: plan.merchants[0].total,
          atingePedidoMinimo: plan.merchants[0].meetsMinimum,
          produtosParaConferirRotulo: plan.merchants[0].items.filter((item) => item.verdict !== 'SEM_CONFLITO_DECLARADO').map((item) => item.itemName),
        },
        alternativas: plan.merchants.slice(1).map((merchant) => ({ merchantId: merchant.merchantId, nome: merchant.merchantName, cobertura: `${merchant.coverage}/${merchant.totalIngredients}`, total: merchant.total })),
        semOpcaoEmNenhumMercado: plan.ingredientsWithoutOption,
      },
      card: { type: 'market', data: plan },
    };
  },
};
