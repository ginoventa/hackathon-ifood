/**
 * Catálogo de restrições alimentares conhecidas pelo Ailo.
 *
 * Estas regras são EXPLÍCITAS e DETERMINÍSTICAS: a verificação de segurança
 * não depende só da LLM. A LLM apenas identifica qual restrição o usuário
 * descreveu; quem decide se um produto conflita é o analisador
 * (`analyzer.js`) usando os termos abaixo.
 *
 * Campos de cada restrição:
 * - type: categoria clínica (alergia, intolerância, doença celíaca ou preferência).
 * - rigor: nível de investigação. "ALTO" ativa a análise de contato cruzado.
 * - terms: termos que indicam presença da substância (ingredientes e pratos típicos).
 * - coreTerms: subconjunto com a substância em si ("trigo", "leite"). Quando o
 *   produto declara "sem glúten", só esses termos indicam contradição; nomes de
 *   prato como "lasanha" deixam de contar. Se ausente, vale a lista `terms`.
 * - uncertainTerms: termos que PODEM conter a substância (ex.: "molho da casa").
 * - ignoredPhrases: expressões que parecem a substância, mas não são ("leite de coco").
 * - freeClaims: declarações de ausência feitas pelo estabelecimento ("sem glúten").
 * - claimIsInsufficient: quando uma declaração comum NÃO basta para a restrição
 *   (ex.: "zero lactose" não significa sem proteína do leite).
 * - ifoodTags: filtros `itemRestrictions` do MCP do iFood equivalentes.
 */

/** Tipos clínicos, que o agente deve sempre diferenciar. */
export const RESTRICTION_TYPES = Object.freeze({
  ALLERGY: 'ALERGIA',
  INTOLERANCE: 'INTOLERANCIA',
  CELIAC: 'DOENCA_CELIACA',
  PREFERENCE: 'PREFERENCIA',
});

/** Níveis de rigor da investigação. */
export const RIGOR = Object.freeze({
  HIGH: 'ALTO',
  MEDIUM: 'MEDIO',
  LOW: 'BAIXO',
});

/** Rigor padrão de cada tipo de restrição. */
const RIGOR_BY_TYPE = {
  [RESTRICTION_TYPES.ALLERGY]: RIGOR.HIGH,
  [RESTRICTION_TYPES.CELIAC]: RIGOR.HIGH,
  [RESTRICTION_TYPES.INTOLERANCE]: RIGOR.MEDIUM,
  [RESTRICTION_TYPES.PREFERENCE]: RIGOR.LOW,
};

// Listas de termos reaproveitadas por mais de uma restrição.

const GLUTEN_TERMS = [
  'gluten', 'trigo', 'farinha de trigo', 'cevada', 'centeio', 'malte', 'semolina', 'semola',
  'pao', 'paes', 'brioche', 'baguete', 'torrada', 'crouton', 'bruschetta', 'massa', 'macarrao',
  'lasanha', 'pizza', 'espaguete', 'spaghetti', 'penne', 'rigatoni', 'fettuccine', 'pappardelle',
  'talharim', 'tagliatelle', 'ravioli', 'tortellini', 'capeletti', 'canelone', 'nhoque', 'gnocchi',
  'risoni', 'empanado', 'empanada', 'milanesa', 'parmegiana', 'panqueca', 'pastel', 'coxinha',
  'esfiha', 'bolo', 'biscoito', 'bolacha', 'cookie', 'waffle', 'croissant', 'cerveja', 'seitan',
  'cuscuz marroquino', 'farinha de rosca', 'panko', 'shoyu', 'molho de soja', 'arancini',
  'hamburguer', 'sanduiche', 'wrap', 'tortilha de trigo',
];
const GLUTEN_CORE = ['gluten', 'trigo', 'farinha de trigo', 'cevada', 'centeio', 'malte', 'semolina', 'semola', 'farinha de rosca', 'panko'];
const GLUTEN_UNCERTAIN = ['aveia', 'farinha', 'molho da casa', 'molho especial', 'tempero pronto', 'caldo', 'frito', 'empanados'];
const GLUTEN_IGNORED = [
  'pao de queijo', 'farinha de arroz', 'farinha de milho', 'farinha de mandioca', 'farinha de amendoa',
  'massa de arroz', 'macarrao de arroz', 'pao de arroz', 'massa sem gluten', 'pizza sem gluten',
];
const GLUTEN_FREE_CLAIMS = ['sem gluten', 'gluten free', 'livre de gluten', 'nao contem gluten', 'isento de gluten'];

const DAIRY_TERMS = [
  'leite', 'lacteo', 'lactea', 'queijo', 'queijos', 'parmesao', 'mussarela', 'mucarela', 'muzarela', 'requeijao',
  'manteiga', 'creme de leite', 'nata', 'iogurte', 'coalhada', 'soro de leite', 'whey', 'caseina',
  'caseinato', 'lactose', 'ricota', 'burrata', 'mascarpone', 'cream cheese', 'catupiry', 'cheddar',
  'gorgonzola', 'provolone', 'brie', 'gouda', 'pecorino', 'grana padano', 'molho branco', 'bechamel',
  'alfredo', 'quatro queijos', 'chantilly', 'leite condensado', 'doce de leite', 'pudim', 'brigadeiro',
  'ghee', 'gratinado', 'gratinada', 'fondue', 'tiramisu', 'sorvete', 'milkshake', 'cappuccino',
];
const DAIRY_CORE = [
  'leite', 'lacteo', 'lactea', 'queijo', 'manteiga', 'creme de leite', 'nata', 'iogurte', 'soro de leite',
  'whey', 'caseina', 'caseinato', 'lactose', 'requeijao', 'leite condensado', 'leite em po',
];
const DAIRY_UNCERTAIN = ['cremoso', 'cremosa', 'creme', 'molho da casa', 'molho especial', 'chocolate', 'margarina'];
const DAIRY_IGNORED = [
  'leite de coco', 'leite de amendoa', 'leite de aveia', 'leite de arroz', 'leite de soja', 'leite vegetal',
  'creme de leite de coco', 'manteiga de cacau', 'manteiga de amendoim', 'queijo vegano', 'queijo vegetal',
  'requeijao vegano', 'manteiga vegana', 'creme vegetal', 'iogurte vegetal', 'iogurte de coco',
];

const EGG_TERMS = [
  'ovo', 'gema', 'clara', 'maionese', 'merengue', 'suspiro', 'omelete', 'fritada', 'carbonara',
  'quiche', 'pao de lo', 'gemada', 'fios de ovos', 'ovomaltine',
];
const EGG_CORE = ['ovo', 'gema', 'clara', 'albumina'];
const EGG_UNCERTAIN = ['massa fresca', 'empanado', 'empanada', 'milanesa', 'molho da casa', 'bolo', 'panqueca'];

const MEAT_TERMS = [
  'carne', 'bovina', 'bovino', 'frango', 'galinha', 'porco', 'suino', 'suina', 'bacon', 'presunto',
  'linguica', 'calabresa', 'salame', 'mortadela', 'peru', 'pernil', 'costela', 'file', 'file mignon',
  'picanha', 'alcatra', 'patinho', 'acem', 'cupim', 'ossobuco', 'ragu', 'bolonhesa', 'hamburguer',
  'almondega', 'vitelo', 'cordeiro', 'pato', 'parma', 'copa', 'pepperoni', 'peixe', 'salmao', 'atum',
  'bacalhau', 'camarao', 'frutos do mar', 'lula', 'polvo', 'anchova', 'aliche', 'tilapia', 'sardinha',
  'caldo de carne', 'caldo de galinha', 'banha', 'torresmo', 'gelatina',
];
const MEAT_CORE = ['carne', 'frango', 'porco', 'bacon', 'presunto', 'peixe', 'camarao', 'gelatina', 'banha', 'caldo de carne', 'caldo de galinha'];
const MEAT_IGNORED = [
  'carne vegetal', 'carne de jaca', 'hamburguer vegetal', 'hamburguer vegano', 'hamburguer de grao de bico',
  'frango vegano', 'carne vegana', 'proteina vegetal', 'hamburguer de cogumelo',
];

/**
 * Restrições conhecidas. A chave é o identificador usado em todo o sistema.
 * @type {Record<string, object>}
 */
export const RESTRICTIONS = Object.freeze({
  doenca_celiaca: {
    label: 'Doença celíaca',
    substance: 'glúten',
    type: RESTRICTION_TYPES.CELIAC,
    terms: GLUTEN_TERMS,
    coreTerms: GLUTEN_CORE,
    uncertainTerms: GLUTEN_UNCERTAIN,
    ignoredPhrases: GLUTEN_IGNORED,
    freeClaims: GLUTEN_FREE_CLAIMS,
    ifoodTags: ['GLUTEN_FREE'],
    note: 'Mesmo traços de glúten podem causar reação. Contato cruzado em fornos, óleo de fritura e utensílios é relevante.',
  },
  sensibilidade_gluten: {
    label: 'Intolerância/sensibilidade ao glúten',
    substance: 'glúten',
    type: RESTRICTION_TYPES.INTOLERANCE,
    terms: GLUTEN_TERMS,
    coreTerms: GLUTEN_CORE,
    uncertainTerms: GLUTEN_UNCERTAIN,
    ignoredPhrases: GLUTEN_IGNORED,
    freeClaims: GLUTEN_FREE_CLAIMS,
    ifoodTags: ['GLUTEN_FREE'],
  },
  alergia_leite: {
    label: 'Alergia à proteína do leite (APLV)',
    substance: 'proteína do leite',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: DAIRY_TERMS,
    coreTerms: DAIRY_CORE,
    uncertainTerms: DAIRY_UNCERTAIN,
    ignoredPhrases: DAIRY_IGNORED,
    freeClaims: ['sem leite', 'sem lacteos', 'livre de leite', 'vegano', 'vegana', '100% vegetal', 'plant based'],
    // "Zero lactose" remove o açúcar do leite, mas mantém a proteína: não serve para APLV.
    claimIsInsufficient: ['zero lactose', 'sem lactose', 'lactose free', 'baixa lactose'],
    ifoodTags: ['VEGAN'],
    note: '"Sem lactose" NÃO significa sem proteína do leite. Para APLV, produtos zero lactose continuam incompatíveis.',
  },
  intolerancia_lactose: {
    label: 'Intolerância à lactose',
    substance: 'lactose',
    type: RESTRICTION_TYPES.INTOLERANCE,
    terms: DAIRY_TERMS.filter((term) => term !== 'caseina' && term !== 'caseinato'),
    // Com "zero lactose" declarado, laticínios deixam de ser contradição: só a lactose em si conta.
    coreTerms: ['lactose'],
    uncertainTerms: DAIRY_UNCERTAIN,
    ignoredPhrases: [...DAIRY_IGNORED, 'zero lactose', 'sem lactose'],
    freeClaims: ['sem lactose', 'zero lactose', 'lactose free', 'sem leite', 'vegano', 'vegana', '100% vegetal'],
    ifoodTags: ['LAC_FREE'],
  },
  alergia_ovo: {
    label: 'Alergia a ovo',
    substance: 'ovo',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: EGG_TERMS,
    coreTerms: EGG_CORE,
    uncertainTerms: EGG_UNCERTAIN,
    ignoredPhrases: ['maionese vegana', 'maionese vegetal', 'ovo vegano'],
    freeClaims: ['sem ovo', 'sem ovos', 'vegano', 'vegana', '100% vegetal'],
    ifoodTags: ['VEGAN'],
  },
  alergia_amendoim: {
    label: 'Alergia a amendoim',
    substance: 'amendoim',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: ['amendoim', 'pacoca', 'pe de moleque', 'pasta de amendoim', 'manteiga de amendoim', 'satay', 'mendorato'],
    uncertainTerms: ['granola', 'crocante', 'praline', 'chocolate', 'molho thai', 'molho asiatico', 'xerem'],
    freeClaims: ['sem amendoim', 'livre de amendoim'],
    ifoodTags: [],
  },
  alergia_castanhas: {
    label: 'Alergia a castanhas e nozes',
    substance: 'castanhas/nozes',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: [
      'castanha', 'castanha de caju', 'castanha do para', 'noz', 'nozes', 'amendoa', 'avela', 'pistache',
      'macadamia', 'peca', 'pinoli', 'nutella', 'marzipan', 'praline', 'gianduia', 'leite de amendoa',
    ],
    uncertainTerms: ['pesto', 'granola', 'crocante', 'chocolate', 'farofa doce', 'mix de graos'],
    freeClaims: ['sem castanhas', 'sem nozes', 'livre de castanhas'],
    ifoodTags: [],
  },
  alergia_soja: {
    label: 'Alergia a soja',
    substance: 'soja',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: ['soja', 'shoyu', 'molho de soja', 'tofu', 'misso', 'missoshiru', 'edamame', 'lecitina de soja', 'proteina de soja', 'tempeh', 'teriyaki'],
    uncertainTerms: ['proteina vegetal', 'molho oriental', 'tempero pronto', 'chocolate', 'margarina'],
    freeClaims: ['sem soja', 'livre de soja'],
    ifoodTags: [],
  },
  alergia_peixe: {
    label: 'Alergia a peixe',
    substance: 'peixe',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: ['peixe', 'salmao', 'atum', 'bacalhau', 'tilapia', 'sardinha', 'anchova', 'aliche', 'pescada', 'merluza', 'robalo', 'sushi', 'sashimi', 'molho de peixe', 'dashi', 'katsuobushi'],
    uncertainTerms: ['molho ingles', 'worcestershire', 'caesar', 'temaki', 'poke', 'frutos do mar'],
    freeClaims: ['sem peixe'],
    ifoodTags: [],
  },
  alergia_frutos_mar: {
    label: 'Alergia a frutos do mar',
    substance: 'crustáceos e moluscos',
    type: RESTRICTION_TYPES.ALLERGY,
    terms: ['camarao', 'lagosta', 'caranguejo', 'siri', 'lula', 'polvo', 'mexilhao', 'marisco', 'ostra', 'vieira', 'frutos do mar', 'paella', 'kani'],
    uncertainTerms: ['molho de peixe', 'tempura', 'yakisoba', 'moqueca', 'bobó'],
    freeClaims: ['sem frutos do mar'],
    ifoodTags: [],
  },
  vegano: {
    label: 'Vegano',
    substance: 'ingredientes de origem animal',
    type: RESTRICTION_TYPES.PREFERENCE,
    terms: [...MEAT_TERMS, ...DAIRY_TERMS, ...EGG_TERMS, 'mel'],
    coreTerms: [...MEAT_CORE, ...DAIRY_CORE, ...EGG_CORE, 'mel'],
    uncertainTerms: ['molho da casa', 'caldo', 'massa fresca', 'chocolate'],
    ignoredPhrases: [...MEAT_IGNORED, ...DAIRY_IGNORED, 'maionese vegana'],
    freeClaims: ['vegano', 'vegana', '100% vegetal', 'plant based'],
    ifoodTags: ['VEGAN'],
  },
  vegetariano: {
    label: 'Vegetariano',
    substance: 'carnes',
    type: RESTRICTION_TYPES.PREFERENCE,
    terms: MEAT_TERMS,
    coreTerms: MEAT_CORE,
    uncertainTerms: ['caldo', 'molho da casa'],
    ignoredPhrases: MEAT_IGNORED,
    freeClaims: ['vegetariano', 'vegetariana', 'vegano', 'vegana'],
    ifoodTags: ['VEGETARIAN'],
  },
});

/** Lista resumida usada na declaração de ferramentas da LLM e no frontend. */
export function listRestrictionOptions() {
  return Object.entries(RESTRICTIONS).map(([id, restriction]) => ({
    id,
    label: restriction.label,
    type: restriction.type,
  }));
}

/**
 * Monta a definição completa de uma restrição a partir do que o usuário informou.
 *
 * Aceita uma restrição do catálogo (`{ id }`) ou uma restrição personalizada
 * (`{ id: 'personalizada', nome, tipo, termos }`), como "alergia a kiwi".
 *
 * @param {{ id: string, nome?: string, tipo?: string, termos?: string[], observacao?: string }} input
 * @returns {object | null} Restrição resolvida ou null se inválida.
 */
export function resolveRestriction(input) {
  if (!input || typeof input.id !== 'string') {
    return null;
  }

  const known = RESTRICTIONS[input.id];
  if (known) {
    return {
      id: input.id,
      ...known,
      rigor: RIGOR_BY_TYPE[known.type],
      coreTerms: known.coreTerms ?? known.terms,
      ignoredPhrases: known.ignoredPhrases ?? [],
      uncertainTerms: known.uncertainTerms ?? [],
      freeClaims: known.freeClaims ?? [],
      claimIsInsufficient: known.claimIsInsufficient ?? [],
      userNote: input.observacao ?? '',
    };
  }

  // Restrição personalizada: precisa de nome e de pelo menos um termo.
  const terms = (input.termos ?? []).filter((term) => typeof term === 'string' && term.trim());
  if (!input.nome || terms.length === 0) {
    return null;
  }

  const type = Object.values(RESTRICTION_TYPES).includes(input.tipo) ? input.tipo : RESTRICTION_TYPES.ALLERGY;
  const slug = input.nome.toLowerCase().normalize('NFD').replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

  return {
    id: `personalizada_${slug}`,
    label: input.nome,
    substance: terms[0],
    type,
    rigor: RIGOR_BY_TYPE[type],
    terms,
    coreTerms: terms,
    uncertainTerms: [],
    ignoredPhrases: [],
    freeClaims: terms.map((term) => `sem ${term}`),
    claimIsInsufficient: [],
    ifoodTags: [],
    custom: true,
    userNote: input.observacao ?? '',
  };
}

/**
 * Converte as restrições do usuário nos filtros `itemRestrictions` do iFood.
 *
 * Os filtros servem para PRIORIZAR resultados na busca. Eles não substituem a
 * análise do produto: a etiqueta do iFood é tratada como mais uma evidência.
 */
export function toIfoodItemRestrictions(restrictions) {
  const tags = new Set();
  for (const restriction of restrictions) {
    for (const tag of restriction.ifoodTags ?? []) {
      tags.add(tag);
    }
  }
  return [...tags];
}
