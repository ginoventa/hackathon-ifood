/**
 * Resumos compactos enviados de volta à LLM.
 *
 * A interface recebe os dados completos (cartões); a LLM recebe só o
 * essencial para conversar, o que economiza tokens e reduz a chance de ela
 * "reinterpretar" dados que já foram analisados por regras.
 */

/** Restrições ativas em formato curto. */
export function summarizeRestrictions(restrictions) {
  return restrictions.map((restriction) => ({
    id: restriction.id,
    label: restriction.label,
    tipo: restriction.type,
    rigor: restriction.rigor,
  }));
}

/** Parecer de um produto em formato curto. */
export function summarizeAnalysisForModel(analysis) {
  return {
    item: analysis.itemName,
    estabelecimento: analysis.merchantName,
    parecer: analysis.verdict,
    podeSeguirParaRevisao: analysis.canProceed,
    porRestricao: analysis.restrictions.map((result) => ({
      restricao: result.label,
      parecer: result.verdict,
      explicacao: result.explanation,
      evidencias: result.findings.map((finding) => `${finding.kind}: ${finding.terms.join(', ')} (${finding.where}; fonte: ${finding.source})`),
    })),
    adicionaisAEvitar: analysis.addOnsToAvoid,
    informacoesAusentes: analysis.missingInfo,
    alternativas: analysis.alternatives,
    adicionaisObrigatorios: (analysis.optionGroups ?? [])
      .filter((group) => group.minSelections > 0)
      .map((group) => ({ grupo: group.name, opcoes: group.options.map((option) => ({ optionId: option.optionId, nome: option.name })) })),
  };
}
