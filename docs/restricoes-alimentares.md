# Restrições alimentares do Ailo

> Documento gerado automaticamente de `backend/ailo/restrictions/catalog.py`. Altere as regras no catálogo e execute `npm run docs:restricoes` na raiz do projeto.

Este documento descreve as regras implementadas no protótipo. Os termos são indícios para a análise, não uma lista exaustiva de ingredientes nem certificação de segurança alimentar.

## Como ler as regras

- **Termos de conflito:** palavras que indicam presença da substância. Incluem nomes de pratos associados a ela.
- **Termos centrais:** usados quando há declaração de ausência; permitem detectar contradições explícitas.
- **Termos de atenção:** palavras cuja composição exige investigação adicional.
- **Expressões ignoradas:** evitam associações incorretas, como tratar leite de coco como leite animal.
- **Declarações de ausência:** alegações reconhecidas pelo motor; não certificam ausência de contato cruzado.
- **Declarações insuficientes:** alegações que não atendem à restrição, como zero lactose para APLV.
- **Filtros do iFood:** ajudam a encontrar candidatos; não substituem a análise.
- **Tags de rótulo:** códigos de alergênicos e declarações usados na integração de rótulos. Tags de presença também são comparadas com avisos de “pode conter”; esses avisos geram risco, não presença confirmada.
- **Rigor:** calculado pelo tipo da restrição; o nível alto ativa investigação de possível contato cruzado no fluxo de restaurante.

Os termos aparecem como cadastrados, geralmente sem acentos. O motor normaliza maiúsculas, acentos e pontuação e trata negações ao fazer as comparações.

## Catálogo

| Restrição | Tipo | Rigor | Filtros do iFood |
| --- | --- | --- | --- |
| [Doença celíaca](#doenca_celiaca) | Doença celíaca | ALTO | `GLUTEN_FREE` |
| [Intolerância/sensibilidade ao glúten](#sensibilidade_gluten) | Intolerância | MEDIO | `GLUTEN_FREE` |
| [Alergia à proteína do leite (APLV)](#alergia_leite) | Alergia | ALTO | `VEGAN` |
| [Intolerância à lactose](#intolerancia_lactose) | Intolerância | MEDIO | `LAC_FREE` |
| [Alergia a ovo](#alergia_ovo) | Alergia | ALTO | `VEGAN` |
| [Alergia a amendoim](#alergia_amendoim) | Alergia | ALTO | Sem filtro equivalente cadastrado |
| [Alergia a castanhas e nozes](#alergia_castanhas) | Alergia | ALTO | Sem filtro equivalente cadastrado |
| [Alergia a soja](#alergia_soja) | Alergia | ALTO | Sem filtro equivalente cadastrado |
| [Alergia a peixe](#alergia_peixe) | Alergia | ALTO | Sem filtro equivalente cadastrado |
| [Alergia a frutos do mar](#alergia_frutos_mar) | Alergia | ALTO | Sem filtro equivalente cadastrado |
| [Alergia a gergelim](#alergia_gergelim) | Alergia | ALTO | Sem filtro equivalente cadastrado |
| [Intolerância à frutose](#intolerancia_frutose) | Intolerância | MEDIO | Sem filtro equivalente cadastrado |
| [Sem carne de porco (islamismo, judaísmo, adventismo)](#religiao_sem_porco) | Religiosa | MEDIO | Sem filtro equivalente cadastrado |
| [Halal (islamismo)](#halal) | Religiosa | MEDIO | Sem filtro equivalente cadastrado |
| [Kosher / casher (judaísmo)](#kosher) | Religiosa | MEDIO | Sem filtro equivalente cadastrado |
| [Sem carne bovina (hinduísmo)](#sem_carne_bovina) | Religiosa | MEDIO | Sem filtro equivalente cadastrado |
| [Vegano](#vegano) | Preferência | BAIXO | `VEGAN` |
| [Vegetariano](#vegetariano) | Preferência | BAIXO | `VEGETARIAN` |

<a id="doenca_celiaca"></a>

## Doença celíaca

**Identificador:** `doenca_celiaca` · **Tipo:** Doença celíaca · **Rigor:** ALTO

**Substância ou regra:** glúten.

**Observação:** Mesmo traços de glúten podem causar reação. Contato cruzado em fornos, óleo de fritura e utensílios é relevante.

### Termos de conflito

`gluten`; `trigo`; `farinha de trigo`; `cevada`; `centeio`; `malte`; `semolina`; `semola`; `pao`; `paes`; `brioche`; `baguete`; `torrada`; `crouton`; `bruschetta`; `massa`; `macarrao`; `lasanha`; `pizza`; `espaguete`; `spaghetti`; `penne`; `rigatoni`; `fettuccine`; `pappardelle`; `talharim`; `tagliatelle`; `ravioli`; `tortellini`; `capeletti`; `canelone`; `nhoque`; `gnocchi`; `risoni`; `empanado`; `empanada`; `milanesa`; `parmegiana`; `panqueca`; `pastel`; `coxinha`; `esfiha`; `bolo`; `biscoito`; `bolacha`; `cookie`; `waffle`; `croissant`; `cerveja`; `seitan`; `cuscuz marroquino`; `farinha de rosca`; `panko`; `shoyu`; `molho de soja`; `arancini`; `hamburguer`; `sanduiche`; `wrap`; `tortilha de trigo`

### Termos centrais efetivamente usados

`gluten`; `trigo`; `farinha de trigo`; `cevada`; `centeio`; `malte`; `semolina`; `semola`; `farinha de rosca`; `panko`

### Termos de atenção

`aveia`; `farinha`; `molho da casa`; `molho especial`; `tempero pronto`; `caldo`; `frito`; `empanados`

### Expressões ignoradas

`pao de queijo`; `farinha de arroz`; `farinha de milho`; `farinha de mandioca`; `farinha de amendoa`; `massa de arroz`; `macarrao de arroz`; `pao de arroz`; `massa sem gluten`; `pizza sem gluten`

### Declarações de ausência reconhecidas

`sem gluten`; `gluten free`; `livre de gluten`; `nao contem gluten`; `isento de gluten`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

`GLUTEN_FREE`

### Tags de presença no rótulo

`en:gluten`; `en:contains-gluten`

### Tags de ausência no rótulo

`en:no-gluten`; `en:gluten-free`


<a id="sensibilidade_gluten"></a>

## Intolerância/sensibilidade ao glúten

**Identificador:** `sensibilidade_gluten` · **Tipo:** Intolerância · **Rigor:** MEDIO

**Substância ou regra:** glúten.

### Termos de conflito

`gluten`; `trigo`; `farinha de trigo`; `cevada`; `centeio`; `malte`; `semolina`; `semola`; `pao`; `paes`; `brioche`; `baguete`; `torrada`; `crouton`; `bruschetta`; `massa`; `macarrao`; `lasanha`; `pizza`; `espaguete`; `spaghetti`; `penne`; `rigatoni`; `fettuccine`; `pappardelle`; `talharim`; `tagliatelle`; `ravioli`; `tortellini`; `capeletti`; `canelone`; `nhoque`; `gnocchi`; `risoni`; `empanado`; `empanada`; `milanesa`; `parmegiana`; `panqueca`; `pastel`; `coxinha`; `esfiha`; `bolo`; `biscoito`; `bolacha`; `cookie`; `waffle`; `croissant`; `cerveja`; `seitan`; `cuscuz marroquino`; `farinha de rosca`; `panko`; `shoyu`; `molho de soja`; `arancini`; `hamburguer`; `sanduiche`; `wrap`; `tortilha de trigo`

### Termos centrais efetivamente usados

`gluten`; `trigo`; `farinha de trigo`; `cevada`; `centeio`; `malte`; `semolina`; `semola`; `farinha de rosca`; `panko`

### Termos de atenção

`aveia`; `farinha`; `molho da casa`; `molho especial`; `tempero pronto`; `caldo`; `frito`; `empanados`

### Expressões ignoradas

`pao de queijo`; `farinha de arroz`; `farinha de milho`; `farinha de mandioca`; `farinha de amendoa`; `massa de arroz`; `macarrao de arroz`; `pao de arroz`; `massa sem gluten`; `pizza sem gluten`

### Declarações de ausência reconhecidas

`sem gluten`; `gluten free`; `livre de gluten`; `nao contem gluten`; `isento de gluten`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

`GLUTEN_FREE`

### Tags de presença no rótulo

`en:gluten`; `en:contains-gluten`

### Tags de ausência no rótulo

`en:no-gluten`; `en:gluten-free`


<a id="alergia_leite"></a>

## Alergia à proteína do leite (APLV)

**Identificador:** `alergia_leite` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** proteína do leite.

**Observação:** "Sem lactose" NÃO significa sem proteína do leite. Para APLV, produtos zero lactose continuam incompatíveis.

### Termos de conflito

`leite`; `lacteo`; `lactea`; `queijo`; `queijos`; `parmesao`; `mussarela`; `mucarela`; `muzarela`; `requeijao`; `manteiga`; `creme de leite`; `nata`; `iogurte`; `coalhada`; `soro de leite`; `whey`; `caseina`; `caseinato`; `lactose`; `ricota`; `burrata`; `mascarpone`; `cream cheese`; `catupiry`; `cheddar`; `gorgonzola`; `provolone`; `brie`; `gouda`; `pecorino`; `grana padano`; `molho branco`; `bechamel`; `alfredo`; `quatro queijos`; `chantilly`; `leite condensado`; `doce de leite`; `pudim`; `brigadeiro`; `ghee`; `gratinado`; `gratinada`; `fondue`; `tiramisu`; `sorvete`; `milkshake`; `cappuccino`

### Termos centrais efetivamente usados

`leite`; `lacteo`; `lactea`; `queijo`; `manteiga`; `creme de leite`; `nata`; `iogurte`; `soro de leite`; `whey`; `caseina`; `caseinato`; `lactose`; `requeijao`; `leite condensado`; `leite em po`

### Termos de atenção

`cremoso`; `cremosa`; `creme`; `molho da casa`; `molho especial`; `chocolate`; `margarina`

### Expressões ignoradas

`leite de coco`; `leite de amendoa`; `leite de aveia`; `leite de arroz`; `leite de soja`; `leite vegetal`; `creme de leite de coco`; `manteiga de cacau`; `manteiga de amendoim`; `queijo vegano`; `queijo vegetal`; `requeijao vegano`; `manteiga vegana`; `creme vegetal`; `iogurte vegetal`; `iogurte de coco`

### Declarações de ausência reconhecidas

`sem leite`; `sem lacteos`; `livre de leite`; `vegano`; `vegana`; `100% vegetal`; `plant based`

### Declarações insuficientes

`zero lactose`; `sem lactose`; `lactose free`; `baixa lactose`

### Filtros do iFood

`VEGAN`

### Tags de presença no rótulo

`en:milk`; `en:contains-milk`

### Tags de ausência no rótulo

`en:no-milk`; `en:vegan`; `en:dairy-free`


<a id="intolerancia_lactose"></a>

## Intolerância à lactose

**Identificador:** `intolerancia_lactose` · **Tipo:** Intolerância · **Rigor:** MEDIO

**Substância ou regra:** lactose.

### Termos de conflito

`leite`; `lacteo`; `lactea`; `queijo`; `queijos`; `parmesao`; `mussarela`; `mucarela`; `muzarela`; `requeijao`; `manteiga`; `creme de leite`; `nata`; `iogurte`; `coalhada`; `soro de leite`; `whey`; `lactose`; `ricota`; `burrata`; `mascarpone`; `cream cheese`; `catupiry`; `cheddar`; `gorgonzola`; `provolone`; `brie`; `gouda`; `pecorino`; `grana padano`; `molho branco`; `bechamel`; `alfredo`; `quatro queijos`; `chantilly`; `leite condensado`; `doce de leite`; `pudim`; `brigadeiro`; `ghee`; `gratinado`; `gratinada`; `fondue`; `tiramisu`; `sorvete`; `milkshake`; `cappuccino`

### Termos centrais efetivamente usados

`lactose`

### Termos de atenção

`cremoso`; `cremosa`; `creme`; `molho da casa`; `molho especial`; `chocolate`; `margarina`

### Expressões ignoradas

`leite de coco`; `leite de amendoa`; `leite de aveia`; `leite de arroz`; `leite de soja`; `leite vegetal`; `creme de leite de coco`; `manteiga de cacau`; `manteiga de amendoim`; `queijo vegano`; `queijo vegetal`; `requeijao vegano`; `manteiga vegana`; `creme vegetal`; `iogurte vegetal`; `iogurte de coco`; `zero lactose`; `sem lactose`

### Declarações de ausência reconhecidas

`sem lactose`; `zero lactose`; `lactose free`; `sem leite`; `vegano`; `vegana`; `100% vegetal`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

`LAC_FREE`

### Tags de presença no rótulo

`en:contains-lactose`

### Tags de ausência no rótulo

`en:no-lactose`; `en:lactose-free`; `en:no-milk`; `en:vegan`


<a id="alergia_ovo"></a>

## Alergia a ovo

**Identificador:** `alergia_ovo` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** ovo.

### Termos de conflito

`ovo`; `gema`; `clara`; `maionese`; `merengue`; `suspiro`; `omelete`; `fritada`; `carbonara`; `quiche`; `pao de lo`; `gemada`; `fios de ovos`; `ovomaltine`

### Termos centrais efetivamente usados

`ovo`; `gema`; `clara`; `albumina`

### Termos de atenção

`massa fresca`; `empanado`; `empanada`; `milanesa`; `molho da casa`; `bolo`; `panqueca`

### Expressões ignoradas

`maionese vegana`; `maionese vegetal`; `ovo vegano`

### Declarações de ausência reconhecidas

`sem ovo`; `sem ovos`; `vegano`; `vegana`; `100% vegetal`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

`VEGAN`

### Tags de presença no rótulo

`en:eggs`

### Tags de ausência no rótulo

`en:no-eggs`; `en:vegan`


<a id="alergia_amendoim"></a>

## Alergia a amendoim

**Identificador:** `alergia_amendoim` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** amendoim.

### Termos de conflito

`amendoim`; `pacoca`; `pe de moleque`; `pasta de amendoim`; `manteiga de amendoim`; `satay`; `mendorato`

### Termos centrais efetivamente usados

`amendoim`; `pacoca`; `pe de moleque`; `pasta de amendoim`; `manteiga de amendoim`; `satay`; `mendorato`

### Termos de atenção

`granola`; `crocante`; `praline`; `chocolate`; `molho thai`; `molho asiatico`; `xerem`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem amendoim`; `livre de amendoim`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

`en:peanuts`

### Tags de ausência no rótulo

`en:no-peanuts`


<a id="alergia_castanhas"></a>

## Alergia a castanhas e nozes

**Identificador:** `alergia_castanhas` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** castanhas/nozes.

### Termos de conflito

`castanha`; `castanha de caju`; `castanha do para`; `noz`; `nozes`; `amendoa`; `avela`; `pistache`; `macadamia`; `peca`; `pinoli`; `nutella`; `marzipan`; `praline`; `gianduia`; `leite de amendoa`

### Termos centrais efetivamente usados

`castanha`; `castanha de caju`; `castanha do para`; `noz`; `nozes`; `amendoa`; `avela`; `pistache`; `macadamia`; `peca`; `pinoli`; `nutella`; `marzipan`; `praline`; `gianduia`; `leite de amendoa`

### Termos de atenção

`pesto`; `granola`; `crocante`; `chocolate`; `farofa doce`; `mix de graos`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem castanhas`; `sem nozes`; `livre de castanhas`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

`en:nuts`

### Tags de ausência no rótulo

`en:no-nuts`


<a id="alergia_soja"></a>

## Alergia a soja

**Identificador:** `alergia_soja` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** soja.

### Termos de conflito

`soja`; `shoyu`; `molho de soja`; `tofu`; `misso`; `missoshiru`; `edamame`; `lecitina de soja`; `proteina de soja`; `tempeh`; `teriyaki`

### Termos centrais efetivamente usados

`soja`; `shoyu`; `molho de soja`; `tofu`; `misso`; `missoshiru`; `edamame`; `lecitina de soja`; `proteina de soja`; `tempeh`; `teriyaki`

### Termos de atenção

`proteina vegetal`; `molho oriental`; `tempero pronto`; `chocolate`; `margarina`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem soja`; `livre de soja`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

`en:soybeans`

### Tags de ausência no rótulo

`en:no-soy`


<a id="alergia_peixe"></a>

## Alergia a peixe

**Identificador:** `alergia_peixe` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** peixe.

### Termos de conflito

`peixe`; `salmao`; `atum`; `bacalhau`; `tilapia`; `sardinha`; `anchova`; `aliche`; `pescada`; `merluza`; `robalo`; `sushi`; `sashimi`; `molho de peixe`; `dashi`; `katsuobushi`

### Termos centrais efetivamente usados

`peixe`; `salmao`; `atum`; `bacalhau`; `tilapia`; `sardinha`; `anchova`; `aliche`; `pescada`; `merluza`; `robalo`; `sushi`; `sashimi`; `molho de peixe`; `dashi`; `katsuobushi`

### Termos de atenção

`molho ingles`; `worcestershire`; `caesar`; `temaki`; `poke`; `frutos do mar`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem peixe`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

`en:fish`

### Tags de ausência no rótulo

Nenhum cadastrado.


<a id="alergia_frutos_mar"></a>

## Alergia a frutos do mar

**Identificador:** `alergia_frutos_mar` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** crustáceos e moluscos.

### Termos de conflito

`camarao`; `lagosta`; `caranguejo`; `siri`; `lula`; `polvo`; `mexilhao`; `marisco`; `ostra`; `vieira`; `frutos do mar`; `paella`; `kani`

### Termos centrais efetivamente usados

`camarao`; `lagosta`; `caranguejo`; `siri`; `lula`; `polvo`; `mexilhao`; `marisco`; `ostra`; `vieira`; `frutos do mar`; `paella`; `kani`

### Termos de atenção

`molho de peixe`; `tempura`; `yakisoba`; `moqueca`; `bobo`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem frutos do mar`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

`en:crustaceans`; `en:molluscs`

### Tags de ausência no rótulo

Nenhum cadastrado.


<a id="alergia_gergelim"></a>

## Alergia a gergelim

**Identificador:** `alergia_gergelim` · **Tipo:** Alergia · **Rigor:** ALTO

**Substância ou regra:** gergelim.

### Termos de conflito

`gergelim`; `tahine`; `tahini`; `homus`; `hommus`; `oleo de gergelim`; `gomasio`

### Termos centrais efetivamente usados

`gergelim`; `tahine`; `tahini`; `homus`; `hommus`; `oleo de gergelim`; `gomasio`

### Termos de atenção

`molho oriental`; `pao sirio`; `zaatar`; `furikake`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem gergelim`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

`en:sesame-seeds`

### Tags de ausência no rótulo

`en:no-sesame`


<a id="intolerancia_frutose"></a>

## Intolerância à frutose

**Identificador:** `intolerancia_frutose` · **Tipo:** Intolerância · **Rigor:** MEDIO

**Substância ou regra:** frutose.

### Termos de conflito

`frutose`; `mel`; `xarope de milho`; `xarope de agave`; `agave`; `sorbitol`; `acucar invertido`; `melado`

### Termos centrais efetivamente usados

`frutose`; `mel`; `xarope de milho`; `xarope de agave`; `agave`; `sorbitol`; `acucar invertido`; `melado`

### Termos de atenção

`fruta`; `frutas`; `suco`; `geleia`; `calda`; `adocado`

### Expressões ignoradas

Nenhum cadastrado.

### Declarações de ausência reconhecidas

`sem frutose`; `sem acucar`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

Nenhum cadastrado.

### Tags de ausência no rótulo

Nenhum cadastrado.


<a id="religiao_sem_porco"></a>

## Sem carne de porco (islamismo, judaísmo, adventismo)

**Identificador:** `religiao_sem_porco` · **Tipo:** Religiosa · **Rigor:** MEDIO

**Substância ou regra:** carne de porco e derivados.

**Observação:** Banha, gelatina e caldos podem ser de origem suína mesmo sem aparecer no nome do prato.

### Termos de conflito

`porco`; `suino`; `suina`; `bacon`; `presunto`; `pancetta`; `toucinho`; `torresmo`; `banha`; `lombo`; `pernil`; `costelinha de porco`; `leitao`; `pururuca`; `linguica`; `calabresa`; `salame`; `mortadela`; `copa`; `parma`; `pepperoni`; `chourico`; `salsicha`; `feijoada`

### Termos centrais efetivamente usados

`porco`; `suino`; `suina`; `bacon`; `presunto`; `pancetta`; `toucinho`; `torresmo`; `banha`; `lombo`; `pernil`; `costelinha de porco`; `leitao`; `pururuca`; `linguica`; `calabresa`; `salame`; `mortadela`; `copa`; `parma`; `pepperoni`; `chourico`; `salsicha`; `feijoada`

### Termos de atenção

`gelatina`; `embutido`; `frios`; `hamburguer`; `almondega`; `caldo de carne`; `toucinho defumado`

### Expressões ignoradas

`linguica de frango`; `salsicha de frango`; `presunto de peru`; `bacon vegano`; `linguica vegana`; `calabresa vegana`

### Declarações de ausência reconhecidas

`sem porco`; `sem carne suina`; `halal`; `kosher`; `casher`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

Nenhum cadastrado.

### Tags de ausência no rótulo

`en:halal`; `en:kosher`; `en:vegetarian`; `en:vegan`


<a id="halal"></a>

## Halal (islamismo)

**Identificador:** `halal` · **Tipo:** Religiosa · **Rigor:** MEDIO

**Substância ou regra:** porco, álcool e carnes sem abate halal.

**Observação:** Carnes só são compatíveis com abate e certificação halal; peça a confirmação do estabelecimento.

### Termos de conflito

`porco`; `suino`; `suina`; `bacon`; `presunto`; `pancetta`; `toucinho`; `torresmo`; `banha`; `lombo`; `pernil`; `costelinha de porco`; `leitao`; `pururuca`; `linguica`; `calabresa`; `salame`; `mortadela`; `copa`; `parma`; `pepperoni`; `chourico`; `salsicha`; `feijoada`; `vinho`; `cerveja`; `chope`; `cachaca`; `rum`; `vodka`; `whisky`; `conhaque`; `licor`; `saque`; `marsala`; `flambado`

### Termos centrais efetivamente usados

`porco`; `suino`; `suina`; `bacon`; `presunto`; `pancetta`; `toucinho`; `torresmo`; `banha`; `lombo`; `pernil`; `costelinha de porco`; `leitao`; `pururuca`; `linguica`; `calabresa`; `salame`; `mortadela`; `copa`; `parma`; `pepperoni`; `chourico`; `salsicha`; `feijoada`; `vinho`; `cerveja`; `chope`; `cachaca`; `rum`; `vodka`; `whisky`; `conhaque`; `licor`; `saque`; `marsala`; `flambado`

### Termos de atenção

`gelatina`; `embutido`; `frios`; `hamburguer`; `almondega`; `caldo de carne`; `toucinho defumado`; `carne`; `frango`; `cordeiro`; `peru`; `file`; `linguica de frango`

### Expressões ignoradas

`linguica de frango`; `salsicha de frango`; `presunto de peru`; `bacon vegano`; `linguica vegana`; `calabresa vegana`; `carne vegetal`; `carne de jaca`; `frango vegano`; `hamburguer vegano`

### Declarações de ausência reconhecidas

`halal`; `certificado halal`; `abate halal`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

Nenhum cadastrado.

### Tags de ausência no rótulo

`en:halal`


<a id="kosher"></a>

## Kosher / casher (judaísmo)

**Identificador:** `kosher` · **Tipo:** Religiosa · **Rigor:** MEDIO

**Substância ou regra:** porco, frutos do mar e carnes não kosher.

**Observação:** Kosher também proíbe misturar carne e leite; só a certificação do estabelecimento confirma.

### Termos de conflito

`porco`; `suino`; `suina`; `bacon`; `presunto`; `pancetta`; `toucinho`; `torresmo`; `banha`; `lombo`; `pernil`; `costelinha de porco`; `leitao`; `pururuca`; `linguica`; `calabresa`; `salame`; `mortadela`; `copa`; `parma`; `pepperoni`; `chourico`; `salsicha`; `feijoada`; `camarao`; `lagosta`; `caranguejo`; `siri`; `lula`; `polvo`; `mexilhao`; `marisco`; `ostra`; `vieira`; `frutos do mar`; `kani`

### Termos centrais efetivamente usados

`porco`; `suino`; `suina`; `bacon`; `presunto`; `pancetta`; `toucinho`; `torresmo`; `banha`; `lombo`; `pernil`; `costelinha de porco`; `leitao`; `pururuca`; `linguica`; `calabresa`; `salame`; `mortadela`; `copa`; `parma`; `pepperoni`; `chourico`; `salsicha`; `feijoada`; `camarao`; `lagosta`; `caranguejo`; `siri`; `lula`; `polvo`; `mexilhao`; `marisco`; `ostra`; `vieira`; `frutos do mar`; `kani`

### Termos de atenção

`gelatina`; `embutido`; `frios`; `hamburguer`; `almondega`; `caldo de carne`; `toucinho defumado`; `carne`; `frango`; `cordeiro`; `queijo`; `molho branco`; `gelatina`

### Expressões ignoradas

`linguica de frango`; `salsicha de frango`; `presunto de peru`; `bacon vegano`; `linguica vegana`; `calabresa vegana`; `carne vegetal`; `carne de jaca`; `frango vegano`; `queijo vegano`

### Declarações de ausência reconhecidas

`kosher`; `casher`; `certificado kosher`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

Nenhum cadastrado.

### Tags de ausência no rótulo

`en:kosher`


<a id="sem_carne_bovina"></a>

## Sem carne bovina (hinduísmo)

**Identificador:** `sem_carne_bovina` · **Tipo:** Religiosa · **Rigor:** MEDIO

**Substância ou regra:** carne bovina.

### Termos de conflito

`carne bovina`; `bovina`; `bovino`; `boi`; `vaca`; `picanha`; `alcatra`; `patinho`; `file mignon`; `contra file`; `acem`; `cupim`; `maminha`; `fraldinha`; `costela bovina`; `ossobuco`; `vitelo`; `carne moida`; `carne seca`; `charque`; `rosbife`; `cheeseburger`

### Termos centrais efetivamente usados

`carne bovina`; `bovina`; `bovino`; `boi`; `vaca`; `picanha`; `alcatra`; `patinho`; `file mignon`; `contra file`; `acem`; `cupim`; `maminha`; `fraldinha`; `costela bovina`; `ossobuco`; `vitelo`; `carne moida`; `carne seca`; `charque`; `rosbife`; `cheeseburger`

### Termos de atenção

`carne`; `hamburguer`; `bolonhesa`; `ragu`; `almondega`; `caldo de carne`; `estrogonofe`; `file`; `gelatina`

### Expressões ignoradas

`carne vegetal`; `carne de jaca`; `hamburguer vegano`; `hamburguer de frango`; `file de frango`; `file de peixe`

### Declarações de ausência reconhecidas

`sem carne bovina`; `vegetariano`; `vegetariana`; `vegano`; `vegana`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

Nenhum cadastrado.

### Tags de presença no rótulo

Nenhum cadastrado.

### Tags de ausência no rótulo

`en:vegetarian`; `en:vegan`


<a id="vegano"></a>

## Vegano

**Identificador:** `vegano` · **Tipo:** Preferência · **Rigor:** BAIXO

**Substância ou regra:** ingredientes de origem animal.

### Termos de conflito

`carne`; `bovina`; `bovino`; `frango`; `galinha`; `porco`; `suino`; `suina`; `bacon`; `presunto`; `linguica`; `calabresa`; `salame`; `mortadela`; `peru`; `pernil`; `costela`; `file`; `file mignon`; `picanha`; `alcatra`; `patinho`; `acem`; `cupim`; `ossobuco`; `ragu`; `bolonhesa`; `hamburguer`; `almondega`; `vitelo`; `cordeiro`; `pato`; `parma`; `copa`; `pepperoni`; `peixe`; `salmao`; `atum`; `bacalhau`; `camarao`; `frutos do mar`; `lula`; `polvo`; `anchova`; `aliche`; `tilapia`; `sardinha`; `caldo de carne`; `caldo de galinha`; `banha`; `torresmo`; `gelatina`; `leite`; `lacteo`; `lactea`; `queijo`; `queijos`; `parmesao`; `mussarela`; `mucarela`; `muzarela`; `requeijao`; `manteiga`; `creme de leite`; `nata`; `iogurte`; `coalhada`; `soro de leite`; `whey`; `caseina`; `caseinato`; `lactose`; `ricota`; `burrata`; `mascarpone`; `cream cheese`; `catupiry`; `cheddar`; `gorgonzola`; `provolone`; `brie`; `gouda`; `pecorino`; `grana padano`; `molho branco`; `bechamel`; `alfredo`; `quatro queijos`; `chantilly`; `leite condensado`; `doce de leite`; `pudim`; `brigadeiro`; `ghee`; `gratinado`; `gratinada`; `fondue`; `tiramisu`; `sorvete`; `milkshake`; `cappuccino`; `ovo`; `gema`; `clara`; `maionese`; `merengue`; `suspiro`; `omelete`; `fritada`; `carbonara`; `quiche`; `pao de lo`; `gemada`; `fios de ovos`; `ovomaltine`; `mel`

### Termos centrais efetivamente usados

`carne`; `frango`; `porco`; `bacon`; `presunto`; `peixe`; `camarao`; `gelatina`; `banha`; `caldo de carne`; `caldo de galinha`; `leite`; `lacteo`; `lactea`; `queijo`; `manteiga`; `creme de leite`; `nata`; `iogurte`; `soro de leite`; `whey`; `caseina`; `caseinato`; `lactose`; `requeijao`; `leite condensado`; `leite em po`; `ovo`; `gema`; `clara`; `albumina`; `mel`

### Termos de atenção

`molho da casa`; `caldo`; `massa fresca`; `chocolate`

### Expressões ignoradas

`carne vegetal`; `carne de jaca`; `hamburguer vegetal`; `hamburguer vegano`; `hamburguer de grao de bico`; `frango vegano`; `carne vegana`; `proteina vegetal`; `hamburguer de cogumelo`; `leite de coco`; `leite de amendoa`; `leite de aveia`; `leite de arroz`; `leite de soja`; `leite vegetal`; `creme de leite de coco`; `manteiga de cacau`; `manteiga de amendoim`; `queijo vegano`; `queijo vegetal`; `requeijao vegano`; `manteiga vegana`; `creme vegetal`; `iogurte vegetal`; `iogurte de coco`; `maionese vegana`

### Declarações de ausência reconhecidas

`vegano`; `vegana`; `100% vegetal`; `plant based`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

`VEGAN`

### Tags de presença no rótulo

`en:milk`; `en:eggs`; `en:fish`; `en:crustaceans`; `en:molluscs`

### Tags de ausência no rótulo

`en:vegan`


<a id="vegetariano"></a>

## Vegetariano

**Identificador:** `vegetariano` · **Tipo:** Preferência · **Rigor:** BAIXO

**Substância ou regra:** carnes.

### Termos de conflito

`carne`; `bovina`; `bovino`; `frango`; `galinha`; `porco`; `suino`; `suina`; `bacon`; `presunto`; `linguica`; `calabresa`; `salame`; `mortadela`; `peru`; `pernil`; `costela`; `file`; `file mignon`; `picanha`; `alcatra`; `patinho`; `acem`; `cupim`; `ossobuco`; `ragu`; `bolonhesa`; `hamburguer`; `almondega`; `vitelo`; `cordeiro`; `pato`; `parma`; `copa`; `pepperoni`; `peixe`; `salmao`; `atum`; `bacalhau`; `camarao`; `frutos do mar`; `lula`; `polvo`; `anchova`; `aliche`; `tilapia`; `sardinha`; `caldo de carne`; `caldo de galinha`; `banha`; `torresmo`; `gelatina`

### Termos centrais efetivamente usados

`carne`; `frango`; `porco`; `bacon`; `presunto`; `peixe`; `camarao`; `gelatina`; `banha`; `caldo de carne`; `caldo de galinha`

### Termos de atenção

`caldo`; `molho da casa`

### Expressões ignoradas

`carne vegetal`; `carne de jaca`; `hamburguer vegetal`; `hamburguer vegano`; `hamburguer de grao de bico`; `frango vegano`; `carne vegana`; `proteina vegetal`; `hamburguer de cogumelo`

### Declarações de ausência reconhecidas

`vegetariano`; `vegetariana`; `vegano`; `vegana`

### Declarações insuficientes

Nenhum cadastrado.

### Filtros do iFood

`VEGETARIAN`

### Tags de presença no rótulo

`en:fish`; `en:crustaceans`; `en:molluscs`

### Tags de ausência no rótulo

`en:vegetarian`; `en:vegan`

## Restrições personalizadas

Além do catálogo, o agente aceita restrições informadas durante a conversa. A entrada usa `id: personalizada`, `nome`, `tipo` e uma lista de `termos` não vazia. Os termos informados também são usados como termos centrais. Não há filtros do iFood ou tags de rótulo específicos cadastrados automaticamente para elas.

Os tipos são: `ALERGIA`, `INTOLERANCIA`, `DOENCA_CELIACA`, `RELIGIOSA`, `PREFERENCIA`.

## Atualização

Execute na raiz do repositório:

```sh
npm run docs:restricoes
```

Para conferir se o documento corresponde ao catálogo, sem alterar arquivos:

```sh
npm run docs:restricoes -- --check
```
