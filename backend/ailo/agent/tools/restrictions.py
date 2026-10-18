"""Ferramentas ligadas às restrições: registrar, analisar produto e lidar com o restaurante."""

from __future__ import annotations

import json
from dataclasses import asdict

from ...errors import ValidationError
from ...profiles import read_profile, read_profile_restrictions
from ...restrictions.catalog import CUSTOM_RESTRICTION_ID, RESTRICTIONS, RestrictionType, resolve_restriction
from ...services.analysis import analyze_selected_item, clarification_for, record_establishment_confirmation
from ..system_prompt import (
    ANALISAR_PRODUTO_PROMPT,
    PREPARAR_MENSAGEM_RESTAURANTE_PROMPT,
    REGISTRAR_RESPOSTA_RESTAURANTE_PROMPT,
    REGISTRAR_RESTRICOES_PROMPT,
)
from .base import ToolDefinition, summarize_analysis_for_model, summarize_restrictions


def _restriction_signature(restrictions):
    return sorted(json.dumps(asdict(item), sort_keys=True, ensure_ascii=False) for item in restrictions)


async def _register_restrictions(session, args):
    inputs = args.get("restricoes") or []
    if not inputs:
        return {"restricoesAtivas": summarize_restrictions(session.restrictions)}, None

    resolved = [resolve_restriction(item) for item in inputs]
    invalid = [item for item, restriction in zip(inputs, resolved) if restriction is None]
    if invalid:
        raise ValidationError(f"Restrições inválidas: {json.dumps(invalid, ensure_ascii=False)}. Restrições personalizadas precisam de nome e termos.")

    if _restriction_signature(resolved) == _restriction_signature(session.restrictions):
        return {"restricoesAtivas": summarize_restrictions(resolved)}, None

    profile_saved = bool(read_profile().get("consentAt")) and (
        _restriction_signature(resolved) == _restriction_signature(read_profile_restrictions())
    )
    session.restrictions = resolved
    session.restriction_inputs = inputs
    # Análises antigas foram feitas com outras restrições e deixam de valer.
    session.analyses.clear()
    summary = summarize_restrictions(resolved)
    output = {"restricoesAtivas": summary, "jaSalvasNoPerfil": profile_saved}
    card = None if profile_saved else {"type": "restrictions", "data": {"restrictions": summary, "inputs": inputs}}
    return output, card


REGISTER_RESTRICTIONS = ToolDefinition(
    name="registrar_restricoes",
    description=REGISTRAR_RESTRICOES_PROMPT,
    schema={
        "type": "object",
        "properties": {
            "restricoes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": [*RESTRICTIONS, CUSTOM_RESTRICTION_ID], "description": 'Id do catálogo ou "personalizada".'},
                        "nome": {"type": "string", "description": 'Só para personalizada. Ex.: "Alergia a kiwi".'},
                        "tipo": {"type": "string", "enum": list(RestrictionType.ALL), "description": "Só para personalizada."},
                        "termos": {"type": "array", "items": {"type": "string"}, "description": "Só para personalizada: palavras que indicam a substância."},
                        "observacao": {"type": "string", "description": "Detalhe dito pelo usuário, se houver."},
                    },
                    "required": ["id"],
                },
            }
        },
        "required": ["restricoes"],
    },
    execute=_register_restrictions,
)


async def _analyze_product(session, args):
    analysis = await analyze_selected_item(session, args["merchantId"], args["itemId"], args.get("tipo") or "RESTAURANTE")
    return summarize_analysis_for_model(analysis), {"type": "analysis", "data": analysis}


ANALYZE_PRODUCT = ToolDefinition(
    name="analisar_produto",
    description=ANALISAR_PRODUTO_PROMPT,
    schema={
        "type": "object",
        "properties": {
            "merchantId": {"type": "string"},
            "itemId": {"type": "string"},
            "tipo": {"type": "string", "enum": ["RESTAURANTE", "MERCADO"], "description": "Padrão: RESTAURANTE."},
        },
        "required": ["merchantId", "itemId"],
    },
    execute=_analyze_product,
)


async def _clarification_message(session, args):
    message = clarification_for(session, args["itemId"])
    return {"mensagemGerada": True, "perguntas": len(message["questions"])}, {"type": "clarification", "data": message}


CLARIFICATION_MESSAGE = ToolDefinition(
    name="preparar_mensagem_restaurante",
    description=PREPARAR_MENSAGEM_RESTAURANTE_PROMPT,
    schema={"type": "object", "properties": {"itemId": {"type": "string"}}, "required": ["itemId"]},
    execute=_clarification_message,
)


async def _establishment_answer(session, args):
    record_establishment_confirmation(session, args["itemId"], args["resumo"])
    analysis = await analyze_selected_item(session, args["merchantId"], args["itemId"])
    return summarize_analysis_for_model(analysis), {"type": "analysis", "data": analysis}


ESTABLISHMENT_ANSWER = ToolDefinition(
    name="registrar_resposta_restaurante",
    description=REGISTRAR_RESPOSTA_RESTAURANTE_PROMPT,
    schema={
        "type": "object",
        "properties": {
            "itemId": {"type": "string"},
            "merchantId": {"type": "string"},
            "resumo": {"type": "string", "description": "Resumo fiel do que o restaurante disse."},
        },
        "required": ["itemId", "merchantId", "resumo"],
    },
    execute=_establishment_answer,
)
