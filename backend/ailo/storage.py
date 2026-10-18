"""Persistência simples em arquivos JSON dentro de ``config.data_dir``.

Suficiente para o MVP (um usuário por instalação). Os arquivos ficam fora
do git e são gravados com permissão restrita (0600), pois guardam tokens e
dados de saúde.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .config import config

logger = logging.getLogger(__name__)


def read_json(file_name: str, default: Any = None) -> Any:
    """Lê um arquivo JSON. Retorna ``default`` se ele não existir ou estiver inválido."""
    path = config.data_dir / file_name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Não foi possível ler %s: %s", file_name, error)
        return default


def write_json(file_name: str, value: Any) -> None:
    """Grava um valor como JSON de forma atômica (arquivo temporário + rename)."""
    config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = config.data_dir / file_name
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, target)


def remove_json(file_name: str) -> None:
    """Remove um arquivo de dados, se existir."""
    (config.data_dir / file_name).unlink(missing_ok=True)
