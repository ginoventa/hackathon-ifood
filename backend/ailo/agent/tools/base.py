"""Estrutura comum das ferramentas do agente."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ...sessions import Session

# Uma ferramenta devolve (saída para a LLM, cartão para a interface ou None).
ToolResult = tuple[dict[str, Any], dict[str, Any] | None]


@dataclass(frozen=True)
class ToolDefinition:
    """Definição de uma ferramenta do Ailo.

    Attributes:
        name: Nome visto pela LLM.
        description: Quando e para que usar a ferramenta.
        schema: JSON Schema dos argumentos.
        execute: Implementação ``async (session, args) -> (output, card)``.
    """

    name: str
    description: str
    schema: dict[str, Any]
    execute: Callable[[Session, dict[str, Any]], Awaitable[ToolResult]]


def summarize_restrictions(restrictions: list) -> list[dict[str, str]]:
    """Restrições ativas em formato curto."""
    return [restriction.summary() for restriction in restrictions]


def summarize_analysis_for_model(analysis: dict) -> dict[str, Any]:
    """Parecer de um produto em formato compacto para a LLM.

    A interface recebe os dados completos (cartão); a LLM recebe só o
    essencial, o que economiza tokens e reduz a chance de ela "reinterpretar"
    dados que já foram analisados por regras.
    """
    return {
        "item": analysis["itemName"],
        "estabelecimento": analysis["merchantName"],
        "parecer": analysis["verdict"],
        "podeSeguirParaRevisao": analysis["canProceed"],
        "porRestricao": [
            {
                "restricao": result["label"],
                "parecer": result["verdict"],
                "explicacao": result["explanation"],
                "evidencias": [
                    f"{finding['kind']}: {', '.join(finding['terms'])} ({finding['where']}; fonte: {finding['source']})"
                    for finding in result["findings"]
                    if finding["kind"] not in {"ADICIONAL", "ETIQUETA_IFOOD"}
                ],
            }
            for result in analysis["restrictions"]
        ],
        "informacoesAusentes": analysis["missingInfo"],
        "alternativas": analysis["alternatives"],
        "adicionaisObrigatorios": [
            {"grupo": group["name"], "opcoes": [{"optionId": option["optionId"], "nome": option["name"]} for option in group["options"]]}
            for group in analysis.get("optionGroups", [])
            if group["minSelections"] > 0
        ],
    }
