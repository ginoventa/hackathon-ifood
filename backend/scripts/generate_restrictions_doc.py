"""Gera documentação legível do catálogo, sem duplicar suas regras."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from ailo.restrictions.catalog import RESTRICTIONS, RestrictionType  # noqa: E402

OUTPUT = BACKEND_ROOT.parent / 'docs/restricoes-alimentares.md'
TYPE_NAMES = {
    RestrictionType.ALLERGY: 'Alergia',
    RestrictionType.INTOLERANCE: 'Intolerância',
    RestrictionType.CELIAC: 'Doença celíaca',
    RestrictionType.RELIGIOUS: 'Religiosa',
    RestrictionType.PREFERENCE: 'Preferência',
}


def render():
    lines = [
        '# Restrições alimentares do Ailo', '',
        '> Documento gerado automaticamente de `backend/ailo/restrictions/catalog.py`. '
        'Altere as regras no catálogo e execute `npm run docs:restricoes` na raiz do projeto.', '',
        'Este documento descreve as regras implementadas no protótipo. Os termos '
        'são indícios para a análise, não uma lista exaustiva de ingredientes nem certificação de segurança alimentar.', '',
        '## Como ler as regras', '',
        '- **Termos de conflito:** palavras que indicam presença da substância. Incluem nomes de pratos associados a ela.',
        '- **Termos centrais:** usados quando há declaração de ausência; permitem detectar contradições explícitas.',
        '- **Termos de atenção:** palavras cuja composição exige investigação adicional.',
        '- **Expressões ignoradas:** evitam associações incorretas, como tratar leite de coco como leite animal.',
        '- **Declarações de ausência:** alegações reconhecidas pelo motor; não certificam ausência de contato cruzado.',
        '- **Declarações insuficientes:** alegações que não atendem à restrição, como zero lactose para APLV.',
        '- **Filtros do iFood:** ajudam a encontrar candidatos; não substituem a análise.',
        '- **Tags de rótulo:** códigos de alergênicos e declarações usados na integração de rótulos. '
        'Tags de presença também são comparadas com avisos de “pode conter”; esses avisos geram risco, não presença confirmada.',
        '- **Rigor:** calculado pelo tipo da restrição; o nível alto ativa investigação de possível contato cruzado no fluxo de restaurante.', '',
        'Os termos aparecem como cadastrados, geralmente sem acentos. O motor normaliza '
        'maiúsculas, acentos e pontuação e trata negações ao fazer as comparações.', '',
        '## Catálogo', '',
        '| Restrição | Tipo | Rigor | Filtros do iFood |',
        '| --- | --- | --- | --- |',
    ]
    for item in RESTRICTIONS.values():
        tags = ', '.join(f'`{tag}`' for tag in item.ifood_tags) or 'Sem filtro equivalente cadastrado'
        lines.append(f'| [{item.label}](#{item.id}) | {TYPE_NAMES[item.type]} | {item.rigor} | {tags} |')
    fields = [
        ('Termos de conflito', 'terms'),
        ('Termos centrais efetivamente usados', 'effective_core_terms'),
        ('Termos de atenção', 'uncertain_terms'),
        ('Expressões ignoradas', 'ignored_phrases'),
        ('Declarações de ausência reconhecidas', 'free_claims'),
        ('Declarações insuficientes', 'insufficient_claims'),
        ('Filtros do iFood', 'ifood_tags'),
        ('Tags de presença no rótulo', 'label_conflict_tags'),
        ('Tags de ausência no rótulo', 'label_free_tags'),
    ]
    for item in RESTRICTIONS.values():
        lines.extend(['', f'<a id="{item.id}"></a>', '', f'## {item.label}', '',
                      f'**Identificador:** `{item.id}` · **Tipo:** {TYPE_NAMES[item.type]} · **Rigor:** {item.rigor}', '',
                      f'**Substância ou regra:** {item.substance}.', ''])
        if item.note:
            lines.extend([f'**Observação:** {item.note}', ''])
        for title, attr in fields:
            values = getattr(item, attr)
            text = '; '.join(f'`{value}`' for value in values) if values else 'Nenhum cadastrado.'
            lines.extend([f'### {title}', '', text, ''])
    lines.extend([
        '## Restrições personalizadas', '',
        'Além do catálogo, o agente aceita restrições informadas durante a conversa. '
        'A entrada usa `id: personalizada`, `nome`, `tipo` e uma lista de `termos` não vazia. '
        'Os termos informados também são usados como termos centrais. '
        'Não há filtros do iFood ou tags de rótulo específicos cadastrados automaticamente para elas.', '',
        'Os tipos são: ' + ', '.join(f'`{value}`' for value in RestrictionType.ALL) + '.', '',
        '## Atualização', '',
        'Execute na raiz do repositório:', '',
        '```sh', 'npm run docs:restricoes', '```', '',
        'Para conferir se o documento corresponde ao catálogo, sem alterar arquivos:', '',
        '```sh', 'npm run docs:restricoes -- --check', '```', '',
    ])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Confere o documento sem reescrevê-lo.')
    args = parser.parse_args()
    content = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != content:
            print('Documento desatualizado. Execute npm run docs:restricoes.', file=sys.stderr)
            return 1
        print('Documento de restrições atualizado.')
        return 0
    OUTPUT.write_text(content, encoding='utf-8')
    print(f'Gerado: {OUTPUT.relative_to(BACKEND_ROOT.parent)} ({len(RESTRICTIONS)} restrições).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
