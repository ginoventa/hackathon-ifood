/**
 * Utilitários de texto usados pelo motor de restrições.
 *
 * Toda comparação é feita sobre texto normalizado (minúsculo, sem acentos e
 * sem pontuação) para que "Glúten", "gluten" e "GLÚTEN" sejam equivalentes.
 */

/** Palavras que, logo antes de um termo, indicam que ele está AUSENTE ("sem leite"). */
const NEGATION_PATTERNS = [
  'sem',
  'zero',
  'livre de',
  'isento de',
  'isenta de',
  'nao contem',
  'nao tem',
  '0%',
];

/** Quantas palavras antes do termo procuramos uma negação ("sem queijo e sem molho"). */
const NEGATION_WINDOW = 3;

/**
 * Normaliza um texto para comparação.
 * @param {string} text
 * @returns {string}
 */
export function normalizeText(text) {
  return String(text ?? '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9%]+/g, ' ')
    .trim();
}

/** Escapa um texto para ser usado dentro de uma expressão regular. */
function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Verifica se a ocorrência de um termo, na posição informada, está negada
 * por uma das expressões de NEGATION_PATTERNS nas palavras anteriores.
 * @param {string} text Texto já normalizado.
 * @param {number} index Posição inicial do termo encontrado.
 */
function isNegated(text, index) {
  const before = text.slice(0, index).trim().split(' ').slice(-NEGATION_WINDOW).join(' ');
  return NEGATION_PATTERNS.some((pattern) => (
    before === pattern
    || before.endsWith(` ${pattern}`)
    || before.startsWith(`${pattern} `)
    || before.includes(` ${pattern} `)
  ));
}

/**
 * Procura termos em um texto, respeitando limites de palavra e negações.
 *
 * Exemplo: em "pão sem glúten" o termo "gluten" é encontrado como NEGADO,
 * enquanto em "farinha de trigo" o termo "trigo" é encontrado como PRESENTE.
 *
 * @param {string} rawText Texto original (será normalizado).
 * @param {string[]} terms Termos procurados (serão normalizados).
 * @param {string[]} [ignoredPhrases] Expressões removidas antes da busca
 *   (ex.: "leite de coco" não deve contar como leite de vaca).
 * @returns {{ present: string[], negated: string[] }}
 */
export function findTerms(rawText, terms, ignoredPhrases = []) {
  let text = ` ${normalizeText(rawText)} `;

  for (const phrase of ignoredPhrases) {
    const normalizedPhrase = normalizeText(phrase);
    text = text.replace(new RegExp(` ${escapeRegExp(normalizedPhrase)} `, 'g'), ' _ ');
  }

  const present = new Set();
  const negated = new Set();

  for (const term of terms) {
    const normalizedTerm = normalizeText(term);
    if (!normalizedTerm) {
      continue;
    }

    // Aceita plural simples ("ovo" → "ovos", "noz" → "nozes").
    const pattern = new RegExp(` ${escapeRegExp(normalizedTerm)}(s|es)? `, 'g');
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (isNegated(text, match.index + 1)) {
        negated.add(term);
      } else {
        present.add(term);
      }
      // Permite encontrar ocorrências sobrepostas separadas por um único espaço.
      pattern.lastIndex = match.index + 1;
    }
  }

  return { present: [...present], negated: [...negated] };
}

/**
 * Indica se o texto contém alguma das expressões (sem considerar negação).
 * Útil para "declarações" como "sem glúten" ou "vegano".
 */
export function containsAny(rawText, phrases) {
  const text = ` ${normalizeText(rawText)} `;
  return phrases.filter((phrase) => text.includes(` ${normalizeText(phrase)} `));
}
