"""Testes do analisador determinístico de restrições."""

from ailo.restrictions.analyzer import FindingKind, Verdict, analyze_product, analyze_recipe_ingredients
from ailo.restrictions.catalog import resolve_restriction
from ailo.restrictions.clarification import build_clarification_message
from ailo.restrictions.text_matching import find_terms

CELIAC = resolve_restriction({"id": "doenca_celiaca"})
MILK_ALLERGY = resolve_restriction({"id": "alergia_leite"})
LACTOSE = resolve_restriction({"id": "intolerancia_lactose"})
VEGETARIAN = resolve_restriction({"id": "vegetariano"})

# Item real do MCP (Peppino Cantina), resumido.
LASANHA_BOLONHESA = {
    "itemId": "lasanha-1",
    "itemName": "Lasanha Bolonhesa",
    "itemDescription": "Lasanha italiana da Cantina, clássica do nosso jeito, ao molho bolonhesa e molho branco, finalizada com parmesão gratinado.",
    "merchantName": "Peppino Cantina",
    "optionGroups": [
        {
            "name": "Gostaria de Queijo Ralado?",
            "minSelections": 0,
            "options": [{"optionId": "opt-queijo", "name": "Queijo Ralado", "description": "Queijo parmesão ralado"}],
        }
    ],
}

GF_PIZZA = {
    "itemId": "p1",
    "itemName": "Pizza Marguerita sem glúten",
    "itemDescription": "Massa sem glúten de farinha de arroz, molho de tomate e manjericão.",
}


def kinds(analysis, index=0):
    return {finding["kind"] for finding in analysis["restrictions"][index]["findings"]}


class TestFindTerms:
    def test_ignora_acentos_e_maiusculas(self):
        assert sorted(find_terms("Farinha de TRIGO e Glúten", ["trigo", "gluten"]).present) == ["gluten", "trigo"]

    def test_reconhece_negacoes_proximas(self):
        result = find_terms("Feito sem queijo e sem leite", ["queijo", "leite"])
        assert result.present == []
        assert sorted(result.negated) == ["leite", "queijo"]

    def test_ignora_expressoes_que_parecem_a_substancia(self):
        assert find_terms("Curry com leite de coco", ["leite"], ["leite de coco"]).present == []


class TestAnalyzeProduct:
    def test_conflito_quando_a_descricao_cita_a_substancia(self):
        analysis = analyze_product(LASANHA_BOLONHESA, [MILK_ALLERGY], menu_items=[])
        assert analysis["verdict"] == Verdict.CONFLICT
        assert analysis["canProceed"] is False
        assert len(analysis["alternatives"]) == 3

    def test_adicionais_opcionais_a_evitar(self):
        analysis = analyze_product(LASANHA_BOLONHESA, [MILK_ALLERGY], menu_items=[])
        assert len(analysis["addOnsToAvoid"]) == 1
        assert "Queijo Ralado" in analysis["addOnsToAvoid"][0]

    def test_aplv_zero_lactose_nao_basta(self):
        product = {"itemId": "x", "itemName": "Sobremesa vegetal zero lactose", "itemDescription": "Creme de baunilha zero lactose, feito com açúcar e amido."}
        analysis = analyze_product(product, [MILK_ALLERGY], menu_items=[])
        assert analysis["verdict"] != Verdict.NO_DECLARED_CONFLICT
        assert FindingKind.INSUFFICIENT_CLAIM in kinds(analysis)

    def test_intolerancia_lactose_aceita_zero_lactose(self):
        product = {"itemId": "x", "itemName": "Iogurte natural zero lactose", "itemDescription": "Iogurte integral zero lactose, pote de 170 g, sem adição de açúcar."}
        assert analyze_product(product, [LACTOSE], kind="MERCADO")["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_nunca_libera_alergia_pela_ausencia_do_termo(self):
        product = {"itemId": "x", "itemName": "Risoto de cogumelos", "itemDescription": "Arroz arbóreo com cogumelos frescos."}
        analysis = analyze_product(product, [CELIAC], menu_items=[])
        assert analysis["verdict"] == Verdict.INSUFFICIENT
        assert analysis["missingInfo"]

    def test_sem_gluten_no_nome_do_prato_nao_e_contradicao(self):
        assert analyze_product(GF_PIZZA, [CELIAC], menu_items=[GF_PIZZA])["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_cardapio_com_trigo_e_possivel_contato_cruzado(self):
        menu = [GF_PIZZA, {"itemId": "p2", "itemName": "Pizza Calabresa", "itemDescription": "Massa de farinha de trigo."}]
        analysis = analyze_product(GF_PIZZA, [CELIAC], menu_items=menu)
        assert analysis["verdict"] == Verdict.RISK
        assert analysis["restrictions"][0]["crossContact"]["itemsWithSubstance"] == 1

    def test_confirmacao_do_restaurante_nao_anula_conflito(self):
        confirmations = [{"itemId": "lasanha-1", "summary": "Disseram que é seguro", "date": "17/10/2026"}]
        analysis = analyze_product(LASANHA_BOLONHESA, [MILK_ALLERGY], menu_items=[], confirmations=confirmations)
        assert analysis["verdict"] == Verdict.CONFLICT

    def test_preferencia_aceita_ausencia_de_conflito(self):
        product = {"itemId": "v", "itemName": "Salada caprese", "itemDescription": "Tomate, muçarela de búfala e manjericão."}
        assert analyze_product(product, [VEGETARIAN])["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_parecer_geral_e_o_mais_grave(self):
        assert analyze_product(LASANHA_BOLONHESA, [VEGETARIAN, CELIAC], menu_items=[])["verdict"] == Verdict.CONFLICT

    def test_pode_conter_vira_contato_cruzado(self):
        product = {"itemId": "c", "itemName": "Creme vegetal de aveia", "itemDescription": "100% vegetal, sem leite. Pode conter traços de glúten."}
        analysis = analyze_product(product, [CELIAC], kind="MERCADO")
        assert analysis["verdict"] == Verdict.RISK
        assert FindingKind.CROSS_CONTACT in kinds(analysis)

    def test_mesmo_forno_gera_risco_para_celiacos(self):
        product = {"itemId": "p", "itemName": "Pizza sem glúten", "itemDescription": "Massa sem glúten de farinha de arroz. Assada no mesmo forno das demais pizzas."}
        assert analyze_product(product, [CELIAC], menu_items=[product])["verdict"] == Verdict.RISK

    def test_explicacao_preserva_siglas(self):
        analysis = analyze_product(LASANHA_BOLONHESA, [MILK_ALLERGY], menu_items=[])
        assert "(APLV)" in analysis["restrictions"][0]["explanation"]


class TestCustomRestrictions:
    def test_alergia_personalizada(self):
        kiwi = resolve_restriction({"id": "personalizada", "nome": "Alergia a kiwi", "tipo": "ALERGIA", "termos": ["kiwi"]})
        assert analyze_product({"itemId": "k", "itemName": "Salada de frutas com kiwi"}, [kiwi], menu_items=[])["verdict"] == Verdict.CONFLICT

    def test_rejeita_personalizada_sem_termos(self):
        assert resolve_restriction({"id": "personalizada", "nome": "Algo"}) is None


def test_trava_ingredientes_incompativeis_da_receita():
    result = analyze_recipe_ingredients(
        [{"nome": "Queijo muçarela"}, {"nome": "Queijo vegano"}, {"nome": "Molho de tomate", "industrializado": True}],
        [MILK_ALLERGY],
    )
    assert result[0]["status"] == Verdict.CONFLICT
    assert result[1]["status"] == Verdict.NO_DECLARED_CONFLICT
    assert result[2]["needsLabelCheck"] is True


def test_mensagem_ao_restaurante():
    analysis = analyze_product(LASANHA_BOLONHESA, [MILK_ALLERGY], menu_items=[])
    message = build_clarification_message(analysis, "Beatriz")
    assert "Lasanha Bolonhesa" in message["text"]
    assert "compartilhados" in message["text"]
    assert message["text"].endswith("Beatriz")
