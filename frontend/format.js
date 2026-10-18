/**
 * Funções de formatação e criação de elementos compartilhadas pelas telas do Ailo.
 */

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

/** Formata um valor em reais. Retorna "—" para valores ausentes. */
export function formatPrice(value) {
  return Number.isFinite(value) ? currency.format(value) : '—';
}

/** Formata uma faixa de minutos, ex.: "30–45 min". */
export function formatMinutes(range) {
  if (!range) {
    return '';
  }
  return range.min === range.max ? `${range.max} min` : `${range.min}–${range.max} min`;
}

/**
 * Cria um elemento com classe, texto e filhos.
 * Usa textContent (nunca innerHTML) para não executar conteúdo vindo da API.
 *
 * @param {string} tag
 * @param {{ className?: string, text?: string, attrs?: Record<string, string> }} [options]
 * @param {(Node | string | null | false)[]} [children]
 */
export function el(tag, { className, text, attrs } = {}, children = []) {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  if (text !== undefined && text !== null) {
    element.textContent = text;
  }
  for (const [name, value] of Object.entries(attrs ?? {})) {
    element.setAttribute(name, value);
  }
  for (const child of children) {
    if (child) {
      element.append(child);
    }
  }
  return element;
}

/** Cria um ícone SVG do arquivo icons.svg. */
export function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `./icons.svg#${name}`);
  svg.append(use);
  return svg;
}

/** Textos e estilos dos pareceres do analisador. */
export const VERDICT_INFO = {
  CONFLITO: { label: 'Incompatível', className: 'conflict', icon: 'alert' },
  RISCO: { label: 'Possível risco', className: 'risk', icon: 'alert' },
  INFORMACAO_INSUFICIENTE: { label: 'Informação insuficiente', className: 'unknown', icon: 'help' },
  SEM_CONFLITO_DECLARADO: { label: 'Sem conflito declarado', className: 'ok', icon: 'check' },
};

/** Nomes amigáveis dos tipos de restrição. */
export const RESTRICTION_TYPE_LABELS = {
  ALERGIA: 'Alergia',
  INTOLERANCIA: 'Intolerância',
  DOENCA_CELIACA: 'Doença celíaca',
  RELIGIOSA: 'Religiosa',
  PREFERENCIA: 'Preferência',
};

/** Selo colorido com o parecer. */
export function verdictBadge(verdict) {
  const info = VERDICT_INFO[verdict] ?? VERDICT_INFO.INFORMACAO_INSUFICIENTE;
  return el('span', { className: `verdict-badge ${info.className}` }, [icon(info.icon), info.label]);
}
