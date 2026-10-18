"""Orquestra a verificação de um produto (seção 1.3 da proposta).

Busca os detalhes no iFood, consulta o cardápio quando a restrição exige
maior rigor e aplica o analisador determinístico.
"""

from __future__ import annotations

import logging
from datetime import date

from ..errors import AppError, ValidationError
from ..restrictions.analyzer import KIND_RESTAURANT, analyze_product
from ..restrictions.catalog import Rigor
from ..restrictions.clarification import build_clarification_message
from ..sessions import Session
from .account import first_name
from .catalog import get_item_details, get_menu_items

logger = logging.getLogger(__name__)


def _require_restrictions(session: Session) -> None:
    if not session.restrictions:
        raise ValidationError("Antes de analisar, preciso saber quais são as suas restrições alimentares.")


async def analyze_selected_item(session: Session, merchant_id: str, item_id: str, kind: str = KIND_RESTAURANT) -> dict:
    """Analisa um item escolhido pelo usuário e guarda o parecer na sessão."""
    _require_restrictions(session)
    product = await get_item_details(session, merchant_id, item_id)

    # Restrições de rigor alto exigem olhar o restante do cardápio (contato cruzado).
    menu_items = None
    if kind == KIND_RESTAURANT and any(restriction.rigor == Rigor.HIGH for restriction in session.restrictions):
        try:
            menu_items = await get_menu_items(session, merchant_id)
        except AppError as error:
            # Sem o cardápio, a análise continua e registra a lacuna de informação.
            logger.warning("Não foi possível ler o cardápio: %s", error.message)

    analysis = analyze_product(
        product,
        session.restrictions,
        kind=kind,
        menu_items=menu_items,
        declared_tags=session.declared_tags.get(item_id, []),
        confirmations=session.confirmations,
    )

    # Dados extras para a interface e para montar o carrinho.
    analysis["imageUrl"] = product.get("itemImageUrl")
    analysis["unitPrice"] = product.get("promotionalUnitPrice", product.get("unitPrice"))
    analysis["optionGroups"] = [
        {
            "optionGroupId": group.get("optionGroupId"),
            "name": group.get("name"),
            "minSelections": group.get("minSelections") or 0,
            "maxSelections": group.get("maxSelections") or 1,
            "options": [
                {"optionId": option.get("optionId"), "name": option.get("name"), "additionalPrice": option.get("additionalPrice") or 0}
                for option in group.get("options") or []
            ],
        }
        for group in product.get("optionGroups") or []
    ]

    session.analyses[item_id] = analysis
    return analysis


def clarification_for(session: Session, item_id: str) -> dict:
    """Gera a mensagem para o restaurante a partir da última análise do item."""
    analysis = session.analyses.get(item_id)
    if analysis is None:
        raise ValidationError("Analise o item antes de preparar a mensagem para o restaurante.")
    message = build_clarification_message(analysis, first_name(session))
    return {"itemId": item_id, "itemName": analysis["itemName"], "merchantName": analysis["merchantName"], **message}


def record_establishment_confirmation(session: Session, item_id: str, summary: str, restriction_ids: list[str] | None = None) -> dict:
    """Registra a resposta do estabelecimento contada pelo usuário.

    Ela entra como EVIDÊNCIA ADICIONAL na próxima análise, nunca como certificação.
    """
    if item_id not in session.analyses:
        raise ValidationError("Só é possível registrar a resposta de um item já analisado.")
    confirmation = {
        "itemId": item_id,
        "summary": str(summary or "")[:500],
        "restrictionIds": restriction_ids or [],
        "date": date.today().strftime("%d/%m/%Y"),
    }
    session.confirmations.append(confirmation)
    return confirmation
