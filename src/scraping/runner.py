"""Fluxo principal de scraping do portal do FIES."""

from typing import Dict, List, Optional

import pandas as pd
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from src.actions import (
    curso_existe,
    listar_opcoes_select2,
    listar_opcoes_select2_multi,
    selecionar_radio_fies_social,
    select2,
    select2_exact,
    select2_exact_multi,
    select2_pick_first,
)
from src.config import CSV_COLUMNS, ESTADOS
from src.core import BrowserContext, human_delay, normalizar_decimal_pt
from src.navigation import abrir_nova_consulta, aplicar_filtros, preparar_primeira_pagina
from src.scraping.extract import extrair_nota_enem_de_linha
from src.scraping.table import (
    expandir_todos_candidatos,
    obter_ultima_linha_pre_selecionado,
    selecionar_categoria,
)


def buscar_notas_por_municipio(ctx: BrowserContext, municipio: str, estado: str) -> List[Dict]:
    resultados: List[Dict] = []

    select2(ctx, "select2-noMunicipio-container", municipio)
    human_delay(ctx.fast_mode, 0.2, 0.5)

    if not curso_existe(ctx, "MEDICINA"):
        print("⏭️ Sem Medicina — pulando")
        return resultados

    try:
        select2_exact(ctx, "select2-noCursosPublico-container", "MEDICINA")
    except TimeoutException:
        print("⚠️ Não foi possível selecionar MEDICINA (exato)")
        return resultados
    human_delay(ctx.fast_mode, 0.2, 0.5)

    ies_container_ids = ["select2-iesPublico-container"]
    ies_lista = listar_opcoes_select2_multi(ctx, ies_container_ids)
    if not ies_lista:
        return resultados

    for idx, ies in enumerate(ies_lista):
        print(f"🏫 IES ({idx+1}/{len(ies_lista)}): {ies}")
        ok_ies = select2_exact_multi(ctx, ies_container_ids, ies)
        if not ok_ies:
            print(f"⚠️ IES não selecionada: {ies} — registrando com notas ausentes")
            resultados.append({
                "municipio": municipio,
                "curso": "MEDICINA",
                "ies": ies,
                "conceito_curso": None,
                "nota_ultimo_aprovado": None,
                "nota_enem_ultimo_ampla": None,
                "nota_enem_ultimo_ppiq": None,
                "nota_enem_ultimo_pcd": None,
            })
            continue
        human_delay(ctx.fast_mode, 0.2, 0.5)

        conceito_container_ids = ["select2-conceitoCurso-container"]
        conceito_container_presente = None
        for cid in conceito_container_ids:
            try:
                ctx.wait.until(EC.presence_of_element_located((By.ID, cid)))
                conceito_container_presente = cid
                break
            except TimeoutException:
                continue

        if not conceito_container_presente:
            print("⚠️ Select2 de conceito não disponível após IES")
            continue

        conceito_valor: Optional[str] = None
        if not select2_pick_first(ctx, conceito_container_presente):
            print("⚠️ Não foi possível selecionar o conceito")
            continue
        else:
            try:
                elc = ctx.driver.find_element(By.ID, conceito_container_presente)
                conceito_valor = (elc.get_attribute("title") or elc.text or "").strip()
            except Exception:
                conceito_valor = None

        if not selecionar_radio_fies_social(ctx):
            print("⚠️ Radio 'Fies Social' não encontrado/selecionável")

        try:
            ctx.wait.until(EC.element_to_be_clickable((By.ID, "btnBuscarCursos"))).click()
        except TimeoutException:
            try:
                ctx.wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='btnBuscarCursos' or (@type='button' and @value='Pesquisar')]"))).click()
            except TimeoutException:
                print("⚠️ Botão 'Pesquisar' não clicável")

        try:
            ctx.wait.until(EC.presence_of_element_located((By.XPATH, "//table/tbody/tr")))
        except TimeoutException:
            continue

        expandir_todos_candidatos(ctx)

        ultima = obter_ultima_linha_pre_selecionado(ctx)
        nota = None
        if ultima:
            try:
                tds = ultima.find_elements(By.TAG_NAME, "td")
                if len(tds) >= 5:
                    nota = tds[4].text.replace(",", ".")
            except Exception:
                nota = None

        categorias = [
            ("Ampla", 1, "nota_enem_ultimo_ampla"),
            ("PPIQ", 3, "nota_enem_ultimo_ppiq"),
            ("PCD", 2, "nota_enem_ultimo_pcd"),
        ]
        enem_por_categoria: Dict[str, Optional[str]] = {}
        for label, codigo, chave in categorias:
            ok = selecionar_categoria(ctx, tipo_label=label, tipo_codigo=codigo)
            if not ok:
                enem_por_categoria[chave] = None
                continue
            ultima_cat = obter_ultima_linha_pre_selecionado(ctx)
            if not ultima_cat:
                enem_por_categoria[chave] = None
                continue
            try:
                nota_enem = extrair_nota_enem_de_linha(ctx, ultima_cat)
            except Exception:
                nota_enem = None
            enem_por_categoria[chave] = normalizar_decimal_pt(nota_enem) if nota_enem else None

        resultados.append({
            "municipio": municipio,
            "curso": "MEDICINA",
            "ies": ies,
            "conceito_curso": conceito_valor,
            "nota_ultimo_aprovado": nota,
            "nota_enem_ultimo_ampla": enem_por_categoria.get("nota_enem_ultimo_ampla"),
            "nota_enem_ultimo_ppiq": enem_por_categoria.get("nota_enem_ultimo_ppiq"),
            "nota_enem_ultimo_pcd": enem_por_categoria.get("nota_enem_ultimo_pcd"),
        })

        if idx < len(ies_lista) - 1:
            if not abrir_nova_consulta(ctx):
                print("⚠️ Não foi possível acionar 'Nova Consulta' para próxima IES")
                break
            if not aplicar_filtros(ctx, estado=estado, municipio=municipio, curso="MEDICINA"):
                print("⚠️ Não foi possível reconfigurar filtros após 'Nova Consulta'")
                break

    return resultados


def run_scraper(ctx: BrowserContext) -> None:
    driver = ctx.driver
    dados_finais: List[Dict] = []

    preparar_primeira_pagina(ctx)

    primeiro_estado = True

    for uf, estado in ESTADOS.items():
        print(f"\n🟦 Estado: {estado}")

        if not primeiro_estado:
            if not abrir_nova_consulta(ctx):
                print("⚠️ Não foi possível abrir 'Nova Consulta' para novo estado; avançando")
                continue
        primeiro_estado = False

        if not aplicar_filtros(ctx, estado=estado):
            print("⚠️ Não foi possível selecionar Estado; avançando")
            continue
        human_delay(ctx.fast_mode, 0.2, 0.5)

        municipios = listar_opcoes_select2(ctx, "select2-noMunicipio-container")
        print(f"➡️ {len(municipios)} municípios")

        for i, municipio in enumerate(municipios):
            print(f"📍 {municipio}")

            if not aplicar_filtros(ctx, estado=estado, municipio=municipio, curso="MEDICINA"):
                print("⚠️ Não foi possível aplicar filtros para o município; seguindo para o próximo")
                continue

            try:
                res = buscar_notas_por_municipio(ctx, municipio, estado)
                for r in res:
                    dados_finais.append({"estado": uf, **r})
            except Exception:
                pass

            pd.DataFrame(dados_finais).reindex(columns=CSV_COLUMNS).to_csv(
                "notas_fies_medicina.csv",
                index=False,
                encoding="utf-8-sig"
            )

            human_delay(ctx.fast_mode, 0.3, 0.7)

            if i < len(municipios) - 1:
                if not abrir_nova_consulta(ctx):
                    print("⚠️ Não foi possível acionar 'Nova Consulta' para o próximo município; seguindo mesmo assim")
                else:
                    if not aplicar_filtros(ctx, estado=estado):
                        print("⚠️ Não foi possível reaplicar estado após 'Nova Consulta'")
    print("\n✅ FINALIZADO")
