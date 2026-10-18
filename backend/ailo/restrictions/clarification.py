"""Mensagem de esclarecimento para o restaurante.

Seção 1.4 da proposta, alternativa "Consultar o restaurante". O texto é
montado a partir do parecer do analisador, e não pela LLM, para garantir
que as perguntas certas sejam feitas para cada tipo de restrição.
"""

from __future__ import annotations

from .analyzer import FindingKind
from .catalog import RestrictionType, Rigor


def _questions_for(restriction_type: str, substance: str) -> list[str]:
    """Perguntas específicas para cada tipo de restrição."""
    if restriction_type == RestrictionType.CELIAC:
        return [
            f"O prato leva {substance} em algum ingrediente, inclusive molhos, temperos e empanados?",
            "Ele é preparado em superfícies, panelas, formas ou fornos separados dos itens com farinha de trigo?",
            "O óleo de fritura e os utensílios são compartilhados com itens com glúten?",
        ]
    if restriction_type == RestrictionType.INTOLERANCE:
        return [
            f"O prato contém {substance} em algum ingrediente, inclusive molhos e finalizações?",
            "É possível preparar sem esses ingredientes?",
        ]
    if restriction_type == RestrictionType.RELIGIOUS:
        return [
            f"O prato contém {substance} ou derivados (inclusive caldos, banha, gelatina e temperos)?",
            "Ele é preparado com utensílios, panelas e superfícies separados?",
            "O estabelecimento ou os ingredientes têm certificação (por exemplo, halal ou kosher)?",
        ]
    if restriction_type == RestrictionType.PREFERENCE:
        return [f"O prato leva {substance} em algum ingrediente, inclusive caldos e molhos?"]
    return [
        f"O prato contém {substance} ou derivados em algum ingrediente, inclusive molhos, temperos e finalizações?",
        f'Os ingredientes industrializados usados têm aviso de "pode conter {substance}"?',
        f"Há equipamentos, utensílios ou superfícies compartilhados com preparações que levam {substance}?",
    ]


def build_clarification_message(analysis: dict, customer_name: str = "") -> dict:
    """Monta a mensagem para o estabelecimento a partir do parecer.

    Returns:
        ``{"text": str, "questions": list[str]}``.
    """
    questions: list[str] = []
    for result in analysis["restrictions"]:
        questions.extend(_questions_for(result["type"], result["substance"]))
        # Perguntas sobre os pontos específicos encontrados na análise.
        for finding in result["findings"]:
            terms = '", "'.join(finding["terms"])
            if finding["kind"] == FindingKind.UNCERTAIN:
                questions.append(f'Os itens "{terms}" contêm {result["substance"]}?')
            if finding["kind"] == FindingKind.CONTRADICTION:
                questions.append(f'A descrição cita "{terms}". Pode confirmar se o prato é mesmo livre de {result["substance"]}?')

    unique_questions = list(dict.fromkeys(questions))
    restrictions_text = " e ".join(result["label"][:1].lower() + result["label"][1:] for result in analysis["restrictions"])
    is_severe = any(result["rigor"] == Rigor.HIGH for result in analysis["restrictions"])

    lines = [
        "Olá! Tudo bem?",
        "",
        f'Tenho interesse no item "{analysis["itemName"]}", mas tenho {restrictions_text}.',
        "Como mesmo pequenas quantidades podem me fazer mal, gostaria de confirmar alguns pontos antes de pedir:"
        if is_severe else "Antes de pedir, gostaria de confirmar:",
        "",
        *[f"{index}. {question}" for index, question in enumerate(unique_questions, start=1)],
        "",
        "Muito obrigado(a) pela atenção!",
    ]
    if customer_name:
        lines.append(customer_name)

    return {"text": "\n".join(lines), "questions": unique_questions}
