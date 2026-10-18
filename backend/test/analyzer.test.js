/**
 * Testes do analisador determinístico de restrições.
 * Executar com: npm test (dentro de backend/).
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { resolveRestriction } from '../src/restrictions/catalog.js';
import { analyzeProduct, analyzeRecipeIngredients, VERDICTS, FINDING_KINDS } from '../src/restrictions/analyzer.js';
import { findTerms } from '../src/restrictions/textMatching.js';
import { buildClarificationMessage } from '../src/restrictions/clarificationMessage.js';

const celiac = resolveRestriction({ id: 'doenca_celiaca' });
const milkAllergy = resolveRestriction({ id: 'alergia_leite' });
const lactose = resolveRestriction({ id: 'intolerancia_lactose' });
const vegetarian = resolveRestriction({ id: 'vegetariano' });

/** Item real do MCP (Peppino Cantina), resumido. */
const lasanhaBolonhesa = {
  itemId: 'lasanha-1',
  itemName: 'Lasanha Bolonhesa',
  itemDescription: 'Lasanha italiana da Cantina, clássica do nosso jeito, ao molho bolonhesa e molho branco, finalizada com parmesão gratinado.',
  merchantName: 'Peppino Cantina',
  optionGroups: [
    {
      name: 'Gostaria de Queijo Ralado?',
      minSelections: 0,
      options: [{ optionId: 'opt-queijo', name: 'Queijo Ralado', description: 'Queijo parmesão ralado' }],
    },
  ],
};

describe('textMatching.findTerms', () => {
  it('encontra termos ignorando acentos e maiúsculas', () => {
    assert.deepEqual(findTerms('Farinha de TRIGO e Glúten', ['trigo', 'gluten']).present.sort(), ['gluten', 'trigo']);
  });

  it('reconhece negações próximas ("sem queijo e sem leite")', () => {
    const result = findTerms('Feito sem queijo e sem leite', ['queijo', 'leite']);
    assert.deepEqual(result.present, []);
    assert.deepEqual(result.negated.sort(), ['leite', 'queijo']);
  });

  it('ignora expressões que só parecem a substância', () => {
    assert.deepEqual(findTerms('Curry com leite de coco', ['leite'], ['leite de coco']).present, []);
  });
});

describe('analyzeProduct', () => {
  it('aponta CONFLITO quando a descrição cita a substância', () => {
    const analysis = analyzeProduct(lasanhaBolonhesa, [milkAllergy], { menuItems: [] });
    assert.equal(analysis.verdict, VERDICTS.CONFLICT);
    assert.equal(analysis.canProceed, false);
    assert.equal(analysis.alternatives.length, 3);
  });

  it('separa adicionais opcionais a evitar', () => {
    const analysis = analyzeProduct(lasanhaBolonhesa, [milkAllergy], { menuItems: [] });
    assert.equal(analysis.addOnsToAvoid.length, 1);
    assert.match(analysis.addOnsToAvoid[0], /Queijo Ralado/);
  });

  it('para APLV, "zero lactose" não é suficiente', () => {
    const product = { itemId: 'x', itemName: 'Sobremesa vegetal zero lactose', itemDescription: 'Creme de baunilha zero lactose, feito com açúcar e amido.' };
    const analysis = analyzeProduct(product, [milkAllergy], { menuItems: [] });
    assert.notEqual(analysis.verdict, VERDICTS.NO_DECLARED_CONFLICT);
    assert.ok(analysis.restrictions[0].findings.some((finding) => finding.kind === FINDING_KINDS.INSUFFICIENT_CLAIM));
  });

  it('para intolerância à lactose, "zero lactose" é evidência válida', () => {
    const product = { itemId: 'x', itemName: 'Iogurte natural zero lactose', itemDescription: 'Iogurte integral zero lactose, pote de 170 g, sem adição de açúcar.' };
    const analysis = analyzeProduct(product, [lactose], { kind: 'MERCADO' });
    assert.equal(analysis.verdict, VERDICTS.NO_DECLARED_CONFLICT);
  });

  it('nunca libera alergia/celíaca só pela ausência do termo', () => {
    const product = { itemId: 'x', itemName: 'Risoto de cogumelos', itemDescription: 'Arroz arbóreo com cogumelos frescos.' };
    const analysis = analyzeProduct(product, [celiac], { menuItems: [] });
    assert.equal(analysis.verdict, VERDICTS.INSUFFICIENT);
    assert.ok(analysis.missingInfo.length > 0);
  });

  it('declara "sem glúten" no nome do prato sem gerar contradição', () => {
    const product = { itemId: 'p1', itemName: 'Pizza Marguerita sem glúten', itemDescription: 'Massa sem glúten de farinha de arroz, molho de tomate e manjericão.' };
    const analysis = analyzeProduct(product, [celiac], { menuItems: [product] });
    assert.equal(analysis.verdict, VERDICTS.NO_DECLARED_CONFLICT);
  });

  it('cardápio com trigo vira POSSÍVEL contato cruzado (risco), não conflito', () => {
    const product = { itemId: 'p1', itemName: 'Pizza Marguerita sem glúten', itemDescription: 'Massa sem glúten de farinha de arroz, molho de tomate e manjericão.' };
    const menu = [product, { itemId: 'p2', itemName: 'Pizza Calabresa', itemDescription: 'Massa tradicional de farinha de trigo.' }];
    const analysis = analyzeProduct(product, [celiac], { menuItems: menu });
    assert.equal(analysis.verdict, VERDICTS.RISK);
    const cross = analysis.restrictions[0].crossContact;
    assert.equal(cross.itemsWithSubstance, 1);
  });

  it('confirmação do estabelecimento é evidência adicional, mas não anula conflito', () => {
    const confirmations = [{ itemId: 'lasanha-1', summary: 'Disseram que é seguro', date: '17/10/2026' }];
    const analysis = analyzeProduct(lasanhaBolonhesa, [milkAllergy], { menuItems: [], confirmations });
    assert.equal(analysis.verdict, VERDICTS.CONFLICT);
  });

  it('preferência (vegetariano) aceita ausência de conflito declarado', () => {
    const product = { itemId: 'v', itemName: 'Salada caprese', itemDescription: 'Tomate, muçarela de búfala e manjericão.' };
    const analysis = analyzeProduct(product, [vegetarian]);
    assert.equal(analysis.verdict, VERDICTS.NO_DECLARED_CONFLICT);
  });

  it('o parecer geral é o mais grave entre as restrições', () => {
    const analysis = analyzeProduct(lasanhaBolonhesa, [vegetarian, celiac], { menuItems: [] });
    assert.equal(analysis.verdict, VERDICTS.CONFLICT);
  });
});

describe('restrições personalizadas', () => {
  it('aceita alergia não catalogada com termos informados', () => {
    const kiwi = resolveRestriction({ id: 'personalizada', nome: 'Alergia a kiwi', tipo: 'ALERGIA', termos: ['kiwi'] });
    const analysis = analyzeProduct({ itemId: 'k', itemName: 'Salada de frutas com kiwi' }, [kiwi], { menuItems: [] });
    assert.equal(analysis.verdict, VERDICTS.CONFLICT);
  });

  it('rejeita restrição personalizada sem termos', () => {
    assert.equal(resolveRestriction({ id: 'personalizada', nome: 'Algo' }), null);
  });
});

describe('analyzeRecipeIngredients', () => {
  it('trava ingredientes incompatíveis da receita gerada pela IA', () => {
    const result = analyzeRecipeIngredients(
      [{ nome: 'Queijo muçarela' }, { nome: 'Queijo vegano' }, { nome: 'Molho de tomate', industrializado: true }],
      [milkAllergy],
    );
    assert.equal(result[0].status, VERDICTS.CONFLICT);
    assert.equal(result[1].status, VERDICTS.NO_DECLARED_CONFLICT);
    assert.equal(result[2].needsLabelCheck, true);
  });
});

describe('buildClarificationMessage', () => {
  it('gera perguntas sobre contato cruzado para alergias', () => {
    const analysis = analyzeProduct(lasanhaBolonhesa, [milkAllergy], { menuItems: [] });
    const message = buildClarificationMessage(analysis, 'Beatriz');
    assert.match(message.text, /Lasanha Bolonhesa/);
    assert.match(message.text, /compartilhados/);
    assert.match(message.text, /Beatriz$/);
  });
});

describe('avisos declarados pelo estabelecimento', () => {
  it('"pode conter traços de glúten" é possível contato cruzado, não ingrediente', () => {
    const product = { itemId: 'c', itemName: 'Creme vegetal de aveia', itemDescription: '100% vegetal, sem leite. Pode conter traços de glúten.' };
    const analysis = analyzeProduct(product, [celiac], { kind: 'MERCADO' });
    assert.equal(analysis.verdict, VERDICTS.RISK);
    assert.ok(analysis.restrictions[0].findings.some((finding) => finding.kind === FINDING_KINDS.CROSS_CONTACT));
  });

  it('"assada no mesmo forno" gera risco para celíacos mesmo com "sem glúten"', () => {
    const product = { itemId: 'p', itemName: 'Pizza sem glúten', itemDescription: 'Massa sem glúten de farinha de arroz. Assada no mesmo forno das demais pizzas.' };
    const analysis = analyzeProduct(product, [celiac], { menuItems: [product] });
    assert.equal(analysis.verdict, VERDICTS.RISK);
  });
});
