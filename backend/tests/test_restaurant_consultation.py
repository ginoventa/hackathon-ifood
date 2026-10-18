import pytest

from ailo.api.routes import chat
from ailo.errors import ValidationError
from ailo.restrictions.analyzer import analyze_product
from ailo.restrictions.catalog import resolve_restriction
from ailo.sessions import get_session


@pytest.mark.asyncio
async def test_consultation_uses_selected_analysis_without_model_or_ifood(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('Consulta não deve depender do modelo ou de nova consulta ao iFood')

    monkeypatch.setattr('ailo.api.routes.run_agent_turn', forbidden)
    monkeypatch.setattr('ailo.api.routes.ensure_account_context', forbidden)
    session = get_session('consultation-test')
    session.restrictions = [resolve_restriction({'id': 'alergia_leite'})]
    session.analyses['pizza'] = analyze_product(
        {'itemId': 'pizza', 'merchantId': 'restaurant', 'itemName': 'Pizza', 'merchantName': 'Pizzaria', 'description': 'Queijo e tomate'},
        session.restrictions,
    )
    response = await chat({'message': 'Consultar o restaurante', 'clarification': {'itemId': 'pizza', 'merchantId': 'restaurant'}}, session.id)
    assert response['cards'][0]['type'] == 'clarification'
    assert 'Pizza' in response['cards'][0]['data']['text']
    assert response['cards'][0]['data']['questions']
    assert session.busy is False
    with pytest.raises(ValidationError):
        await chat({'message': 'Consultar', 'clarification': {'itemId': 'pizza', 'merchantId': 'other'}}, session.id)
    assert session.busy is False
