"""Perfil alimentar do usuário (seção 1.1: "mediante autorização").

Restrições alimentares são dados de saúde. Por isso:

- só são gravadas com consentimento explícito (``consent=True``);
- ficam apenas na máquina local (``.data/perfil-alimentar.json``, fora do git);
- podem ser apagadas a qualquer momento pela página de perfil.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import ValidationError
from .restrictions.catalog import Restriction, resolve_restriction
from .storage import read_json, remove_json, write_json

PROFILE_FILE = "perfil-alimentar.json"


def read_profile() -> dict[str, Any]:
    """Lê o perfil salvo: ``{restrictions, consentAt, updatedAt}``."""
    profile = read_json(PROFILE_FILE) or {}
    restrictions = profile.get("restrictions")
    return {
        "restrictions": restrictions if isinstance(restrictions, list) else [],
        "consentAt": profile.get("consentAt"),
        "updatedAt": profile.get("updatedAt"),
    }


def read_profile_restrictions() -> list[Restriction]:
    """Restrições do perfil já resolvidas pelo catálogo (ignora entradas inválidas)."""
    return [restriction for restriction in map(resolve_restriction, read_profile()["restrictions"]) if restriction]


def save_profile(restriction_inputs: Any, consent: Any) -> dict[str, Any]:
    """Salva o perfil. Exige consentimento explícito."""
    if consent is not True:
        raise ValidationError("Para salvar o perfil alimentar, é preciso autorizar o armazenamento.")
    if not isinstance(restriction_inputs, list):
        raise ValidationError("Lista de restrições inválida.")

    valid = [item for item in restriction_inputs if resolve_restriction(item)]
    now = datetime.now(timezone.utc).isoformat()
    profile = {"restrictions": valid, "consentAt": read_profile()["consentAt"] or now, "updatedAt": now}
    write_json(PROFILE_FILE, profile)
    return profile


def delete_profile() -> None:
    """Apaga o perfil e o consentimento."""
    remove_json(PROFILE_FILE)
