"""Testes do agente LangChain e das ferramentas.

Usam o cliente falso do iFood e um modelo de chat com roteiro no lugar do
Gemini, para validar os fluxos da proposta sem rede e sem custo.
"""

from __future__ import annotations

import pytest

from ailo.agent.agent import run_agent_turn
from ailo.services.account import ensure_account_context
from ailo.services.cart import get_checkout_options, submit_order
from ailo.sessions import get_session
from tests.fakes import ScriptedChatModel

LASANHA_BOLONHESA = {"merchantId": "00000000-0000-4000-8000-000000000100", "itemId": "00000000-0000-4000-8000-000000000101"}
LASANHA_VEGANA_ARROZ = {"merchantId": "00000000-0000-4000-8000-000000000200", "itemId": "00000000-0000-4000-8000-000000000202"}


def model(*steps):
    return ScriptedChatModel(steps=list(steps))


def recipe_with(ingredients):
    return {"titulo": "Lasanha sem leite", "porcoes": 4, "ingredientes": ingredients, "modoDePreparo": ["Monte as camadas e asse."]}


@pytest.fixture
async def session(fake_ifood, request):
    current = get_session(f"teste-{request.node.name[:40]}".replace("_", "-"))
    await ensure_account_context(current)
    return current


async def test_registra_busca_e_analisa_item_com_conflito(session):
    llm = model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "alergia_leite"}]})},
        {"call": ("buscar_opcoes", {"consulta": "lasanha", "priorizarComFiltrosDoIfood": False})},
        {"call": ("analisar_produto", LASANHA_BOLONHESA)},
        {"text": "Essa lasanha leva molho branco e muçarela."},
    )
    result = await run_agent_turn(session, "Quero lasanha, tenho alergia à proteína do leite", model=llm)

    assert result["reply"] == "Essa lasanha leva molho branco e muçarela."
    assert [card["type"] for card in result["cards"]] == ["restrictions", "options", "analysis"]
    assert result["cards"][2]["data"]["verdict"] == "CONFLITO"
    assert llm.last_tool_output()["parecer"] == "CONFLITO"

    # A busca prioriza compatibilidade: itens com conflito aparente nunca vêm antes dos demais.
    verdicts = [item["quickVerdict"] for item in result["cards"][1]["data"]["items"]]
    if "CONFLITO" in verdicts:
        assert all(verdict == "CONFLITO" for verdict in verdicts[verdicts.index("CONFLITO"):])


async def test_bloqueia_carrinho_com_item_em_conflito(session):
    await run_agent_turn(session, "APLV", model=model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "alergia_leite"}]})},
        {"call": ("analisar_produto", LASANHA_BOLONHESA)},
        {"text": "ok"},
    ))
    llm = model(
        {"call": ("montar_carrinho", {"merchantId": LASANHA_BOLONHESA["merchantId"], "itens": [{"itemId": LASANHA_BOLONHESA["itemId"], "quantidade": 1}]})},
        {"text": "Não posso adicionar esse item."},
    )
    result = await run_agent_turn(session, "Pode pedir mesmo assim", model=llm)
    assert result["cards"] == []
    assert "incompatíveis" in llm.last_tool_output()["erro"]


async def test_carrinho_compativel_so_envia_pedido_com_confirmacao(session):
    result = await run_agent_turn(session, "Quero a lasanha vegana de massa de arroz", model=model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "alergia_leite"}]})},
        {"call": ("analisar_produto", LASANHA_VEGANA_ARROZ)},
        {"call": ("montar_carrinho", {"merchantId": LASANHA_VEGANA_ARROZ["merchantId"], "itens": [{"itemId": LASANHA_VEGANA_ARROZ["itemId"], "quantidade": 1}]})},
        {"text": "Carrinho pronto para revisão."},
    ))
    cart = next(card["data"] for card in result["cards"] if card["type"] == "cart")
    assert cart["cartId"] and len(cart["items"]) == 1

    checkout = await get_checkout_options(session, cart["cartId"])
    assert checkout["deliveryMethods"] and checkout["paymentMethods"]

    params = {
        "cartId": cart["cartId"],
        "deliveryMethodId": checkout["deliveryMethods"][0]["deliveryMethodId"],
        "paymentMethodId": checkout["paymentMethods"][0]["paymentMethodId"],
        "alertsAcknowledged": True,
    }
    # Sem o clique de confirmação, o pedido é recusado.
    with pytest.raises(Exception, match="confirmação"):
        await submit_order(session, {**params, "userConfirmed": False})

    order = await submit_order(session, {**params, "userConfirmed": True})
    assert order["orderId"]


async def test_fluxo_de_mercado_recusa_receita_incompativel_e_monta_carrinho(session):
    llm = model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "alergia_leite"}, {"id": "doenca_celiaca"}]})},
        {"call": ("registrar_receita", recipe_with([
            {"nome": "Massa para lasanha sem glúten", "quantidade": "400 g", "busca": "massa lasanha sem glúten", "quantidadeCompra": 1, "industrializado": True},
            {"nome": "Queijo muçarela", "quantidade": "200 g", "busca": "muçarela", "quantidadeCompra": 1},
        ]))},
        {"call": ("registrar_receita", recipe_with([
            {"nome": "Massa para lasanha sem glúten", "quantidade": "400 g", "busca": "massa lasanha sem glúten", "quantidadeCompra": 1, "industrializado": True},
            {"nome": "Queijo vegetal de mandioca", "quantidade": "200 g", "busca": "queijo vegetal", "quantidadeCompra": 1, "industrializado": True},
            {"nome": "Molho de tomate", "quantidade": "340 g", "busca": "molho de tomate", "quantidadeCompra": 1, "industrializado": True},
            {"nome": "Carne moída", "quantidade": "500 g", "busca": "carne moída", "quantidadeCompra": 1},
        ]))},
        {"call": ("buscar_ingredientes_no_mercado", {})},
        {"text": "Encontrei os ingredientes."},
    )
    result = await run_agent_turn(session, "Quero fazer lasanha em casa. Tenho APLV e doença celíaca.", model=llm)

    # A primeira receita foi recusada: só a corrigida aparece na interface.
    recipes = [card for card in result["cards"] if card["type"] == "recipe"]
    assert len(recipes) == 1
    assert all(item["verificacao"]["status"] != "CONFLITO" for item in recipes[0]["data"]["ingredientes"])

    plan = next(card["data"] for card in result["cards"] if card["type"] == "market")
    best = plan["merchants"][0]
    assert best["coverage"] == 4
    # O "queijo vegetal" não pode virar "bebida vegetal" só por ser mais barato.
    assert any("Queijo" in item["itemName"] for item in best["items"])
    assert all(item["verdict"] != "CONFLITO" for item in best["items"])

    result = await run_agent_turn(session, "Pode montar o carrinho", model=model(
        {"call": ("montar_carrinho_do_mercado", {"merchantId": best["merchantId"]})},
        {"text": "Carrinho pronto."},
    ))
    cart = next(card["data"] for card in result["cards"] if card["type"] == "cart")
    assert len(cart["items"]) == 4
    # Produtos industrializados sem rótulo completo geram alertas para conferência.
    assert cart["alerts"]


async def test_historico_e_mantido_entre_turnos(session):
    await run_agent_turn(session, "Oi", model=model({"text": "Olá!"}))
    llm = model({"text": "De novo!"})
    await run_agent_turn(session, "Oi de novo", model=llm)
    # O segundo turno recebe a conversa anterior.
    assert any("Olá!" == getattr(message, "content", None) for message in llm.received[0])


async def test_busca_mostra_so_itens_com_etiqueta_do_ifood_quando_existem(session):
    llm = model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "doenca_celiaca"}]})},
        {"call": ("buscar_opcoes", {"consulta": "lasanha"})},
        {"text": "ok"},
    )
    result = await run_agent_turn(session, "Quero lasanha, sou celíaca", model=llm)
    items = next(card["data"]["items"] for card in result["cards"] if card["type"] == "options")
    # Todas as opções têm a etiqueta GLUTEN_FREE; "lasanha" no nome não conta como conflito.
    assert items and all(item["ifoodTag"] for item in items)
    assert all(item["quickVerdict"] != "CONFLITO" for item in items)


async def test_busca_nunca_recomenda_item_com_outra_restricao(session):
    llm = model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "alergia_leite"}, {"id": "doenca_celiaca"}]})},
        # Não existe pizza calabresa vegana e sem glúten no catálogo de teste.
        {"call": ("buscar_opcoes", {"consulta": "pizza calabresa"})},
        {"text": "ok"},
    )
    result = await run_agent_turn(session, "Quero pizza de calabresa", model=llm)
    output = llm.last_tool_output()
    assert output["encontrado"] is False
    # As alternativas atendem às restrições pela etiqueta do iFood (VEGAN e GLUTEN_FREE).
    alternatives = next(card["data"] for card in result["cards"] if card["type"] == "options")
    assert alternatives["alternatives"] is True
    assert {item["itemName"] for item in alternatives["items"]} <= {"Lasanha Vegana de Abobrinha", "Lasanha Vegana de Massa de Arroz"}


async def test_sem_alternativas_diz_que_nao_encontrou(session):
    llm = model(
        {"call": ("registrar_restricoes", {"restricoes": [{"id": "alergia_amendoim"}, {"id": "halal"}]})},
        {"call": ("buscar_opcoes", {"consulta": "pizza calabresa"})},
        {"text": "Infelizmente não encontrei."},
    )
    result = await run_agent_turn(session, "Quero pizza de calabresa", model=llm)
    assert llm.last_tool_output()["encontrado"] is False
    assert not [card for card in result["cards"] if card["type"] == "options"]
