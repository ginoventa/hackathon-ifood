"""Configuração compartilhada dos testes."""

from __future__ import annotations

import pytest

from ailo.ifood import client as ifood_client
from ailo.services import catalog as catalog_service
from tests.fakes import FAKE_LABELS, FakeIfoodClient


@pytest.fixture(autouse=True)
def no_external_labels(monkeypatch):
    """Os testes nunca consultam a Open Food Facts: rótulos vêm de FAKE_LABELS."""
    from ailo.services import labels

    async def fake_fetch(ean):
        return FAKE_LABELS.get(ean) if ean else None

    monkeypatch.setattr(labels, "fetch_label", fake_fetch)
    for module in ("ailo.services.analysis", "ailo.services.market", "ailo.agent.tools.catalog"):
        monkeypatch.setattr(f"{module}.fetch_label", fake_fetch)


@pytest.fixture
def fake_ifood():
    """Substitui o cliente do MCP pelo cliente falso durante o teste."""
    original = ifood_client.get_ifood_client()
    fake = FakeIfoodClient()
    ifood_client.set_ifood_client(fake)
    catalog_service._menu_cache.clear()
    catalog_service._tagged_cache.clear()
    yield fake
    ifood_client.set_ifood_client(original)
