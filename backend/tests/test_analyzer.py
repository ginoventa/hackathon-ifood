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
        assert analysis["alternatives"] == ["ESCOLHER_OUTRO_PRODUTO", "PREPARAR_EM_CASA"]

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


class TestRotulo:
    """Rótulo de produto industrializado (Open Food Facts)."""

    PRODUCT = {"itemId": "m", "itemName": "Molho de tomate 340g", "itemDescription": "Sachê 340g", "itemEan": "789"}

    def label(self, **extra):
        return {"found": True, "ean": "789", "allergens": [], "traces": [], "labels": [], "ingredients": "tomate, sal", **extra}

    def test_alergenico_declarado_no_rotulo_e_conflito(self):
        analysis = analyze_product(self.PRODUCT, [CELIAC], kind="MERCADO", label=self.label(allergens=["en:gluten"]))
        assert analysis["verdict"] == Verdict.CONFLICT
        assert "rótulo declara" in analysis["restrictions"][0]["explanation"]

    def test_pode_conter_no_rotulo_e_risco(self):
        analysis = analyze_product(self.PRODUCT, [CELIAC], kind="MERCADO", label=self.label(traces=["en:gluten"]))
        assert analysis["verdict"] == Verdict.RISK

    def test_rotulo_sem_a_substancia_libera_com_aviso(self):
        analysis = analyze_product(self.PRODUCT, [CELIAC, MILK_ALLERGY], kind="MERCADO", label=self.label())
        assert analysis["verdict"] == Verdict.NO_DECLARED_CONFLICT
        assert FindingKind.LABEL_CLEAR in kinds(analysis)
        assert "embalagem" in analysis["restrictions"][0]["explanation"]

    def test_selo_sem_gluten_no_rotulo_ignora_nome_de_massa(self):
        product = {"itemId": "p", "itemName": "Macarrão parafuso 500g", "itemDescription": "Pacote", "itemEan": "789"}
        analysis = analyze_product(product, [CELIAC], kind="MERCADO", label=self.label(labels=["en:no-gluten"], ingredients="farinha de arroz"))
        assert analysis["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_rotulo_nao_encontrado_mantem_aviso_de_conferir_embalagem(self):
        analysis = analyze_product(self.PRODUCT, [CELIAC], kind="MERCADO", label={"found": False, "ean": "789"})
        assert analysis["verdict"] == Verdict.INSUFFICIENT
        assert any("rótulo" in info for info in analysis["missingInfo"])


class TestEtiquetaDoIfood:
    def test_etiqueta_dispensa_nome_de_prato(self):
        product = {"itemId": "pz", "itemName": "Pizza de Calabresa Grande", "itemDescription": "Massa artesanal, molho e calabresa."}
        analysis = analyze_product(product, [CELIAC], menu_items=[], declared_tags=["GLUTEN_FREE"])
        assert analysis["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_sem_etiqueta_nome_de_prato_conta(self):
        product = {"itemId": "pz", "itemName": "Pizza de Calabresa Grande", "itemDescription": "Massa artesanal, molho e calabresa."}
        assert analyze_product(product, [CELIAC], menu_items=[])["verdict"] == Verdict.CONFLICT

    def test_itens_etiquetados_do_cardapio_nao_sao_contato_cruzado(self):
        product = {"itemId": "a", "itemName": "Pizza de Frango", "itemDescription": "Massa de arroz."}
        menu = [product, {"itemId": "b", "itemName": "Pizza de Calabresa", "tags": ["GLUTEN_FREE"]}]
        analysis = analyze_product(product, [CELIAC], menu_items=menu, declared_tags=["GLUTEN_FREE"])
        assert analysis["verdict"] == Verdict.NO_DECLARED_CONFLICT


class TestRestricoesReligiosas:
    def test_sem_porco_detecta_derivados(self):
        restriction = resolve_restriction({"id": "religiao_sem_porco"})
        product = {"itemId": "f", "itemName": "Feijoada completa", "itemDescription": "Feijão preto com paio e costelinha."}
        assert analyze_product(product, [restriction], menu_items=[])["verdict"] == Verdict.CONFLICT

    def test_linguica_de_frango_nao_e_porco(self):
        restriction = resolve_restriction({"id": "religiao_sem_porco"})
        product = {"itemId": "l", "itemName": "Linguiça de frango grelhada", "itemDescription": "Linguiça de frango com arroz, feijão e salada verde da casa."}
        assert analyze_product(product, [restriction], menu_items=[])["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_halal_carne_sem_certificacao_e_risco(self):
        restriction = resolve_restriction({"id": "halal"})
        product = {"itemId": "c", "itemName": "Frango grelhado", "itemDescription": "Peito de frango grelhado com arroz e legumes no vapor."}
        assert analyze_product(product, [restriction], menu_items=[])["verdict"] == Verdict.RISK

    def test_halal_certificado(self):
        restriction = resolve_restriction({"id": "halal"})
        product = {"itemId": "c", "itemName": "Frango grelhado halal", "itemDescription": "Peito de frango com certificado halal, arroz e legumes."}
        assert analyze_product(product, [restriction], menu_items=[])["verdict"] == Verdict.NO_DECLARED_CONFLICT

    def test_restricao_religiosa_personalizada(self):
        restriction = resolve_restriction({"id": "personalizada", "nome": "Jainismo: sem raízes", "tipo": "RELIGIOSA", "termos": ["cebola", "alho", "batata"]})
        assert restriction.type == "RELIGIOSA"
        product = {"itemId": "s", "itemName": "Sopa de legumes", "itemDescription": "Abóbora, cenoura, batata e cebola."}
        assert analyze_product(product, [restriction], menu_items=[])["verdict"] == Verdict.CONFLICT


def test_rotulo_sem_dados_mantem_aviso_de_conferir_embalagem():
    product = {"itemId": "m", "itemName": "Batata original 104g", "itemDescription": "Tubo", "itemEan": "789"}
    empty = {"found": True, "ean": "789", "allergens": [], "traces": [], "labels": [], "ingredients": ""}
    analysis = analyze_product(product, [CELIAC], kind="MERCADO", label=empty)
    assert analysis["verdict"] == Verdict.INSUFFICIENT
    assert any("rótulo" in info for info in analysis["missingInfo"])


# Item real do MCP (Pop Vegan Food - Pinheiros), resumido: etiqueta GLUTEN_FREE,
# mas a mesma pizza também é vendida com massa tradicional.
POP_VEGAN_PIZZA = {
    "itemId": "pizza-individual",
    "itemName": "Pizza Individual",
    "itemDescription": "Nossas pizzinhas sem trigo e massa tradicional têm 18cm de diâmetro (tamanho individual).",
    "merchantName": "Pop Vegan Food - Pinheiros",
    "optionGroups": [
        {
            "name": "Pizza Individual",
            "minSelections": 1,
            "options": [
                {"optionId": "baiana", "name": "Baiana - Massa Sem Trigo", "description": "Molho de tomate e mussarela. Alergênicos: Contém soja."},
                {"optionId": "veganella", "name": "Veganella - Massa Sem Trigo", "description": "Creme de avelã. Pode conter centeio, cevada e aveia."},
                {"optionId": "pistache", "name": "Pistache - Massa Tradicional", "description": "Contém derivados de trigo e de soja. Contém glúten."},
            ],
        }
    ],
}


def test_item_etiquetado_com_opcao_tradicional_e_inseguro_e_nao_incompativel():
    menu = [
        {"itemId": "coxinha", "itemName": "Coxinha de jaca", "itemDescription": ""},
        {"itemId": "lasanha", "itemName": "Lasanha vegana", "itemDescription": "Massa de trigo"},
        {"itemId": "brownie", "itemName": "Brownie sem glúten", "itemDescription": "", "tags": ["GLUTEN_FREE"]},
    ]
    analysis = analyze_product(POP_VEGAN_PIZZA, [CELIAC], menu_items=menu, declared_tags=["GLUTEN_FREE"])

    # "Massa Sem Trigo" não conflita: só a opção tradicional (e o "pode conter") vira adicional a evitar.
    assert analysis["verdict"] == Verdict.RISK
    assert len(analysis["addOnsToAvoid"]) == 2
    # Alerta "Inseguro" com dois exemplos do cardápio, ignorando itens etiquetados.
    assert analysis["crossContactAlert"]["examples"] == ["Coxinha de jaca", "Lasanha vegana"]
    assert "“Coxinha de jaca” e “Lasanha vegana”" in analysis["restrictions"][0]["explanation"]


def test_sem_outros_itens_com_gluten_exemplos_vem_das_opcoes_do_item():
    analysis = analyze_product(POP_VEGAN_PIZZA, [CELIAC], menu_items=[], declared_tags=["GLUTEN_FREE"])
    assert "Pistache - Massa Tradicional" in analysis["crossContactAlert"]["examples"]


def test_item_etiquetado_sem_fonte_de_contato_cruzado_nao_tem_alerta():
    product = {**POP_VEGAN_PIZZA, "optionGroups": POP_VEGAN_PIZZA["optionGroups"][:1]}
    product["optionGroups"] = [{**product["optionGroups"][0], "options": product["optionGroups"][0]["options"][:1]}]
    analysis = analyze_product(product, [CELIAC], menu_items=[], declared_tags=["GLUTEN_FREE"])
    assert analysis["crossContactAlert"] is None
