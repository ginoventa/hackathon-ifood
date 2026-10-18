"""Configuração compartilhada dos testes."""

from __future__ import annotations

import pytest

from ailo.ifood import client as ifood_client
from ailo.services import catalog as catalog_service
from tests.fakes import FakeIfoodClient


@pytest.fixture
def fake_ifood():
    """Substitui o cliente do MCP pelo cliente falso durante o teste."""
    original = ifood_client.get_ifood_client()
    fake = FakeIfoodClient()
    ifood_client.set_ifood_client(fake)
    catalog_service._menu_cache.clear()
    yield fake
    ifood_client.set_ifood_client(original)
