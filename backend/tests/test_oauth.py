"""Testes do login OAuth do agente (sem rede: o endpoint de token é simulado)."""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from ailo import config as config_module
from ailo.ifood import oauth


@pytest.fixture
def agent_credentials(monkeypatch, tmp_path):
    """Credenciais fictícias do agente, dados em pasta temporária e Redirect URL no próprio app."""
    ifood = dataclasses.replace(
        config_module.config.ifood,
        client_id="cliente-teste",
        client_secret="segredo-teste",
        redirect_uri=f"http://localhost:{config_module.config.port}/callback",
    )
    fake_config = dataclasses.replace(config_module.config, ifood=ifood, data_dir=tmp_path)
    for module in (oauth, config_module):
        monkeypatch.setattr(module, "config", fake_config)
    monkeypatch.setattr("ailo.storage.config", fake_config)
    yield fake_config
    oauth.logout()


@pytest.fixture
def token_endpoint(monkeypatch):
    """Simula o POST /token do iFood e guarda os parâmetros recebidos."""
    calls: list[dict] = []
    counter = {"value": 0}

    def fake_post(url, data=None, **_kwargs):
        calls.append({"url": url, **data})
        counter["value"] += 1
        body = {"access_token": f"acesso-{counter['value']}", "refresh_token": f"renovacao-{counter['value']}", "expires_in": 3600}
        return httpx.Response(200, json=body)

    monkeypatch.setattr(oauth.httpx, "post", fake_post)
    return calls


def test_troca_do_codigo_envia_client_secret_e_code_verifier(agent_credentials, token_endpoint):
    url = oauth.start_login()
    state = httpx.URL(url).params["state"]

    success, _ = oauth.finish_login({"code": "codigo-123", "state": state})

    assert success
    exchange = token_endpoint[0]
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["client_id"] == "cliente-teste"
    assert exchange["client_secret"] == "segredo-teste"
    assert exchange["code_verifier"]
    assert exchange["redirect_uri"] == agent_credentials.ifood.redirect_uri
    assert oauth.get_access_token() == "acesso-1"


def test_state_invalido_e_rejeitado(agent_credentials, token_endpoint):
    oauth.start_login()
    success, message = oauth.finish_login({"code": "codigo-123", "state": "forjado"})
    assert not success
    assert "não corresponde" in message
    assert token_endpoint == []


def test_renovacao_rotaciona_tokens_e_envia_client_secret(agent_credentials, token_endpoint):
    url = oauth.start_login()
    oauth.finish_login({"code": "codigo", "state": httpx.URL(url).params["state"]})

    # Força a expiração do token atual.
    tokens = oauth.read_json(oauth.TOKENS_FILE)
    tokens["expiresAt"] = 0
    oauth.write_json(oauth.TOKENS_FILE, tokens)

    assert oauth.get_access_token() == "acesso-2"
    refresh = token_endpoint[-1]
    assert refresh["grant_type"] == "refresh_token"
    assert refresh["refresh_token"] == "renovacao-1"
    assert refresh["client_secret"] == "segredo-teste"
    assert oauth.read_json(oauth.TOKENS_FILE)["refreshToken"] == "renovacao-2"


def test_sem_credenciais_o_login_explica_o_que_falta(monkeypatch):
    ifood = dataclasses.replace(config_module.config.ifood, client_id="", client_secret="")
    monkeypatch.setattr(oauth, "config", dataclasses.replace(config_module.config, ifood=ifood))
    with pytest.raises(Exception, match="IFOOD_CLIENT_SECRET"):
        oauth.start_login()
