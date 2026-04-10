"""Fluxo principal de scraping do portal do FIES."""

import os
import re
from typing import Callable, Dict, List, Optional, Set, Tuple
import unicodedata

import pandas as pd
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.config.settings as settings
from src.actions import (
    curso_existe,
    listar_opcoes_select2,
    listar_opcoes_select2_multi,
    selecionar_radio_fies_social,
    select2,
    select2_exact,
    select2_exact_multi,
    select2_pick_first,
    esperar_select2_habilitado,
)
from src.config import CSV_COLUMNS, ESTADOS
from src.core import BrowserContext, human_delay, normalizar_decimal_pt, com_retry_timeout
from src.navigation import abrir_nova_consulta, aplicar_filtros, preparar_primeira_pagina
from src.scraping.extract import extrair_nota_enem_de_linha
from src.scraping.table import (
    expandir_todos_candidatos,
    obter_ultima_linha_pre_selecionado,
    selecionar_categoria,
)


_IES_CODIGO_RE = re.compile(r"\((\d{4,})\)\s*$")


def _filtrar_celulas_concorrencia(cells):
    filtradas = []
    for td in cells:
        try:
            txt = (td.text or "").lower().strip()
        except Exception:
            txt = ""
        if "tipo" in txt and "concorr" in txt:
            continue
        filtradas.append(td)
    return filtradas


def _extrair_codigo_ies(txt: str) -> Optional[str]:
    try:
        m = _IES_CODIGO_RE.search(txt or "")
        return m.group(1) if m else None
    except Exception:
        return None


def _nome_sem_codigo_ies(txt: str) -> str:
    return _IES_CODIGO_RE.sub("", txt or "").strip()


def _norm_label(txt: str) -> str:
    norm = unicodedata.normalize("NFD", txt or "")
    ascii_txt = norm.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_txt.lower().split())


def _caminho_csv_modalidade(modalidade: str | None = None) -> str:
    atual = (modalidade or settings.FIES_MODALIDADE or "social").lower()
    if atual == "regular":
        return getattr(settings, "REGULAR_CSV_PATH", "notas_fies_medicina_fiesregular.csv")
    return getattr(settings, "SOCIAL_CSV_PATH", "notas_fies_medicina.csv")


def _caminho_faltantes_modalidade(modalidade: str | None = None) -> str:
    atual = (modalidade or settings.FIES_MODALIDADE or "social").lower()
    if atual == "regular":
        return "notas_fies_medicina_faltantes_regular.txt"
    return "notas_fies_medicina_faltantes.txt"


def _ies_selecionado(ctx: BrowserContext, container_id: str, esperado: str) -> bool:
    try:
        el = ctx.driver.find_element(By.ID, container_id)
        titulo = (el.get_attribute("title") or el.text or "").strip()
        if not titulo:
            return False

        cod_esperado = _extrair_codigo_ies(esperado)
        cod_titulo = _extrair_codigo_ies(titulo)
        if cod_esperado and cod_titulo:
            return cod_esperado == cod_titulo

        nome_esperado = _norm_label(_nome_sem_codigo_ies(esperado))
        nome_titulo = _norm_label(_nome_sem_codigo_ies(titulo))
        if not nome_esperado or not nome_titulo:
            return False
        return nome_esperado in nome_titulo or nome_titulo in nome_esperado
    except Exception:
        return False


def _limpar_marcas_concorrencia(df: pd.DataFrame) -> pd.DataFrame:
    """Remove resíduos de 'TIPOS DE CONCORRÊNCIA' gravados em conceito_curso."""

    if "conceito_curso" not in df.columns:
        return df

    try:
        serie = df["conceito_curso"].astype("string")
        serie = serie.str.replace("TIPOS DE CONCORRÊNCIA", "", case=False, regex=False)
        serie = serie.str.replace("\n", " ", regex=False).str.replace("\r", " ", regex=False)
        serie = serie.str.strip()
        serie = serie.where(serie.str.len() > 0, None)
        serie = serie.where(~serie.str.lower().isin({"ampla", "ppiq", "pcd"}), None)
        df["conceito_curso"] = serie
    except Exception:
        pass

    return df


def salvar_incremental(rows: List[Dict], caminho: str = "notas_fies_medicina.csv") -> None:
    if not rows:
        return

    modo = "a" if os.path.exists(caminho) and os.path.getsize(caminho) > 0 else "w"
    df = pd.DataFrame(rows)
    df.to_csv(caminho, mode=modo, header=(modo == "w"), index=False, encoding="utf-8-sig")


def salvar_csv_completo(registros: List[Dict], caminho: str = "notas_fies_medicina.csv") -> None:
    df = pd.DataFrame(registros)
    df.to_csv(caminho, index=False, encoding="utf-8-sig")


FALHAS_COLUMNS = ["estado", "municipio", "curso", "ies", "ies_codigo", "motivo"]


def _normalizar_csv_falhas(caminho: str) -> None:
    try:
        df_existente = pd.read_csv(caminho)
        df_existente = df_existente.reindex(columns=FALHAS_COLUMNS)
        df_existente.to_csv(caminho, index=False, encoding="utf-8-sig")
    except Exception as exc:
        print(f"⚠️ Não foi possível normalizar CSV de falhas: {exc}")


def salvar_falha_ies(row: Dict, caminho: str = "notas_fies_medicina_falhas.csv") -> None:
    if not row:
        return
    if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
        try:
            header_df = pd.read_csv(caminho, nrows=0)
            if list(header_df.columns) != FALHAS_COLUMNS:
                _normalizar_csv_falhas(caminho)
        except Exception:
            pass
        modo = "a"
    else:
        modo = "w"

    df = pd.DataFrame([row]).reindex(columns=FALHAS_COLUMNS)
    df.to_csv(caminho, mode=modo, header=(modo == "w"), index=False, encoding="utf-8-sig")


def _sanear_arquivo_falhas(caminho: str) -> None:
    """Corrige casos comuns de concatenação de linhas no CSV de falhas."""
    if not os.path.exists(caminho):
        return
    try:
        with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
            texto = f.read()
    except Exception:
        return

    # Ex.: "...,nao_selecionadaMA,..." -> "...,nao_selecionada\nMA,..."
    corrigido = re.sub(r"(nao_selecionada)([A-Z]{2},)", r"\1\n\2", texto)

    if corrigido != texto:
        try:
            with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
                f.write(corrigido)
        except Exception:
            pass


def _resolver_uf_estado(valor_estado: str) -> Tuple[Optional[str], Optional[str]]:
    estado = str(valor_estado or "").strip()
    if not estado:
        return None, None

    if estado in ESTADOS:
        return estado, ESTADOS[estado]

    alvo_norm = _norm_label(estado)
    for uf, nome in ESTADOS.items():
        if _norm_label(nome) == alvo_norm:
            return uf, nome

    return None, None


def _selecionar_ies_para_review(
    ctx: BrowserContext,
    ies_desejada: str,
    codigo_ies: Optional[str] = None,
) -> Tuple[bool, str]:
    """Seleciona IES no mesmo fluxo do principal: lista opção e seleciona com select2_exact_multi."""
    container_ids = ["select2-iesPublico-container"]
    selecionado_nome = ies_desejada
    nome_busca = _nome_sem_codigo_ies(ies_desejada)
    if not nome_busca:
        nome_busca = ies_desejada

    # Mesmo padrão do fluxo principal: primeiro lista as opções disponíveis no município.
    try:
        opcoes = listar_opcoes_select2_multi(ctx, container_ids)
    except Exception:
        opcoes = []

    nome_norm = _norm_label(nome_busca)
    candidato = None

    # tenta casar por código sem digitar código na busca
    if codigo_ies:
        for opcao in opcoes:
            if _extrair_codigo_ies(opcao) == codigo_ies:
                candidato = opcao
                break

    # fallback textual usando apenas nome
    if not candidato:
        for opcao in opcoes:
            opcao_norm = _norm_label(_nome_sem_codigo_ies(opcao))
            if nome_norm and nome_norm in opcao_norm:
                candidato = opcao
                break

    if not candidato:
        return False, selecionado_nome

    ok_ies = False
    candidato_busca = _nome_sem_codigo_ies(candidato)
    for _ in range(5):
        ok_ies = select2_exact_multi(ctx, container_ids, candidato_busca)
        if ok_ies and _ies_selecionado(ctx, container_ids[0], candidato):
            break
        human_delay(ctx.fast_mode, 0.2, 0.4)

    if ok_ies:
        try:
            el = ctx.driver.find_element(By.ID, container_ids[0])
            selecionado_nome = (el.get_attribute("title") or el.text or "").strip() or candidato
        except Exception:
            selecionado_nome = candidato
        return True, selecionado_nome

    return False, selecionado_nome


def _coletar_notas_ies_review(
    ctx: BrowserContext,
    uf: str,
    municipio: str,
    curso: str,
    ies_nome: str,
) -> Optional[Dict]:
    """Coleta conceito e notas da IES atualmente selecionada."""

    conceito_valor: Optional[str] = None
    try:
        if select2_pick_first(ctx, "select2-conceitoCurso-container"):
            elc = ctx.driver.find_element(By.ID, "select2-conceitoCurso-container")
            conceito_valor = (elc.get_attribute("title") or elc.text or "").strip() or None
    except Exception:
        conceito_valor = None

    try:
        ctx.wait.until(EC.element_to_be_clickable((By.ID, "btnBuscarCursos"))).click()
    except TimeoutException:
        try:
            ctx.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[@id='btnBuscarCursos' or (@type='button' and @value='Pesquisar')]")
                )
            ).click()
        except TimeoutException:
            return None

    categorias = [
        ("Ampla", 1, "nota_enem_ultimo_ampla"),
        ("PPIQ", 3, "nota_enem_ultimo_ppiq"),
        ("PCD", 2, "nota_enem_ultimo_pcd"),
    ]
    enem_por_categoria: Dict[str, Optional[str]] = {}
    for label, codigo, chave in categorias:
        nota_cat = None
        for _ in range(2):
            ok = selecionar_categoria(ctx, tipo_label=label, tipo_codigo=codigo)
            if not ok:
                continue
            ultima_cat = obter_ultima_linha_pre_selecionado(ctx)
            if not ultima_cat:
                continue
            try:
                nota_enem = extrair_nota_enem_de_linha(ctx, ultima_cat)
                nota_cat = normalizar_decimal_pt(nota_enem) if nota_enem else None
            except Exception:
                nota_cat = None
            if nota_cat is not None:
                break
        enem_por_categoria[chave] = nota_cat

    tem_dado = any(
        [
            conceito_valor,
            enem_por_categoria.get("nota_enem_ultimo_ampla"),
            enem_por_categoria.get("nota_enem_ultimo_ppiq"),
            enem_por_categoria.get("nota_enem_ultimo_pcd"),
        ]
    )
    if not tem_dado:
        return None

    return {
        "estado": uf,
        "municipio": municipio,
        "curso": curso,
        "ies": ies_nome,
        "conceito_curso": conceito_valor,
        "nota_enem_ultimo_ampla": enem_por_categoria.get("nota_enem_ultimo_ampla"),
        "nota_enem_ultimo_ppiq": enem_por_categoria.get("nota_enem_ultimo_ppiq"),
        "nota_enem_ultimo_pcd": enem_por_categoria.get("nota_enem_ultimo_pcd"),
    }


def _pesquisar_e_aguardar(ctx: BrowserContext) -> None:
    """Clica em Pesquisar e aguarda a tabela de resultados aparecer."""
    try:
        ctx.wait.until(EC.element_to_be_clickable((By.ID, "btnBuscarCursos"))).click()
    except TimeoutException:
        ctx.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@id='btnBuscarCursos' or (@type='button' and @value='Pesquisar')]")
            )
        ).click()
    ctx.wait.until(EC.presence_of_element_located((By.XPATH, "//table/tbody/tr")))


def buscar_notas_por_municipio(
    ctx: BrowserContext,
    municipio: str,
    estado: str,
    uf: str,
    ies_ja_salvos: Optional[Set[str]] = None,
    salvar_automatico: bool = True,
    registrar_falha: bool = True,
    ies_alvo_nome_norm: Optional[Set[str]] = None,
    ies_alvo_codigo: Optional[Set[str]] = None,
    caminho_csv: Optional[str] = None,
) -> Tuple[List[Dict], bool]:
    resultados: List[Dict] = []
    pesquisa_executada = False
    ies_ja_salvos = ies_ja_salvos or set()
    caminho_csv = caminho_csv or _caminho_csv_modalidade()

    select2(ctx, "select2-noMunicipio-container", municipio)
    human_delay(ctx.fast_mode, 0.2, 0.5)

    if not curso_existe(ctx, "MEDICINA"):
        print("⏭️ Sem Medicina — pulando")
        return resultados, pesquisa_executada

    try:
        select2_exact(ctx, "select2-noCursosPublico-container", "MEDICINA")
    except TimeoutException:
        print("⚠️ Não foi possível selecionar MEDICINA (exato)")
        return resultados, pesquisa_executada
    human_delay(ctx.fast_mode, 0.2, 0.5)

    ies_container_ids = ["select2-iesPublico-container"]
    try:
        esperar_select2_habilitado(ctx, ies_container_ids[0])
    except TimeoutException:
        print("⚠️ IES ainda desabilitado após aguardar")
        return resultados, pesquisa_executada
    ies_lista = listar_opcoes_select2_multi(ctx, ies_container_ids)
    if not ies_lista:
        print("⚠️ Nenhuma IES listada para este município")
        return resultados, pesquisa_executada
    print(f"📑 IES encontradas ({len(ies_lista)}): {ies_lista}")

    alvos_nome = ies_alvo_nome_norm or set()
    alvos_nome_sem_codigo = {_norm_label(_nome_sem_codigo_ies(n)) for n in alvos_nome}
    alvos_codigo = ies_alvo_codigo or set()

    for idx, ies in enumerate(ies_lista):
        codigo_lista = _extrair_codigo_ies(ies)
        ies_nome_busca = _nome_sem_codigo_ies(ies)
        if ies_alvo_nome_norm or ies_alvo_codigo:
            if not (
                (_norm_label(ies) in alvos_nome)
                or (_norm_label(ies_nome_busca) in alvos_nome_sem_codigo)
                or (codigo_lista and codigo_lista in alvos_codigo)
            ):
                continue

        if _norm_label(ies) in ies_ja_salvos:
            print(f"⏭️ IES já presente no CSV, pulando: {ies}")
            continue
        print(f"🏫 IES ({idx+1}/{len(ies_lista)}): {ies}")
        ok_ies = False
        codigo_selecionado: Optional[str] = None
        ies_nome_registro = ies
        for tent in range(5):
            # Busca da IES sempre pelo nome (sem código) para evitar quebrar o Select2.
            ok_ies = select2_exact_multi(ctx, ies_container_ids, ies_nome_busca)
            if not ok_ies and _ies_selecionado(ctx, ies_container_ids[0], ies):
                ok_ies = True

            if ok_ies and _ies_selecionado(ctx, ies_container_ids[0], ies):
                try:
                    selecionado = ctx.driver.find_element(By.ID, ies_container_ids[0]).get_attribute("title") or ctx.driver.find_element(By.ID, ies_container_ids[0]).text
                    ies_nome_registro = selecionado or ies
                    codigo_selecionado = _extrair_codigo_ies(selecionado)
                    if codigo_lista and codigo_selecionado and codigo_lista != codigo_selecionado:
                        print(f"⚠️ Código divergente entre opção ({codigo_lista}) e selecionado ({codigo_selecionado}) — armazenando o selecionado")
                    print(f"✅ Selecionado: {selecionado}")
                except Exception:
                    pass
                break
            print(f"🔁 Retentando seleção da IES ({tent+1}/5): {ies}")
            human_delay(ctx.fast_mode, 0.25, 0.5)
        if not ok_ies:
            print(f"⚠️ IES não selecionada após retentativas: {ies} — descartando sem salvar")
            if registrar_falha:
                salvar_falha_ies(
                    {
                        "estado": uf,
                        "municipio": municipio,
                        "curso": "MEDICINA",
                        "ies": ies,
                        "ies_codigo": codigo_lista,
                        "motivo": "nao_selecionada",
                    }
                )
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
        conceito_ok = False
        for tent in range(2):
            if select2_pick_first(ctx, conceito_container_presente):
                conceito_ok = True
                break
            print(f"🔁 Retentando conceito ({tent+1}/2)")
            human_delay(ctx.fast_mode, 0.2, 0.4)
        if not conceito_ok:
            print("⚠️ Não foi possível selecionar o conceito após retentativas")
            continue
        try:
            elc = ctx.driver.find_element(By.ID, conceito_container_presente)
            conceito_valor = (elc.get_attribute("title") or elc.text or "").strip()
        except Exception:
            conceito_valor = None

        try:
            com_retry_timeout(
                ctx,
                operacao=lambda: _pesquisar_e_aguardar(ctx),
                descricao=f"pesquisa IES '{ies}' em {municipio}/{uf}",
            )
            pesquisa_executada = True
        except (TimeoutException, WebDriverException):
            print(f"⚠️ Falha persistente ao pesquisar IES '{ies}' em {municipio} após retentativas — registrando falha")
            if registrar_falha:
                salvar_falha_ies({
                    "estado": uf,
                    "municipio": municipio,
                    "curso": "MEDICINA",
                    "ies": ies,
                    "ies_codigo": codigo_lista,
                    "motivo": "timeout_pesquisa",
                })
            continue

        categorias = [
            ("Ampla", 1, "nota_enem_ultimo_ampla"),
            ("PPIQ", 3, "nota_enem_ultimo_ppiq"),
            ("PCD", 2, "nota_enem_ultimo_pcd"),
        ]
        enem_por_categoria: Dict[str, Optional[str]] = {}
        for label, codigo, chave in categorias:
            nota_cat = None
            for tent in range(2):
                ok = selecionar_categoria(ctx, tipo_label=label, tipo_codigo=codigo)
                if not ok:
                    print(f"🔁 Categoria {label} não selecionada, tentando novamente ({tent+1}/2)")
                    human_delay(ctx.fast_mode, 0.2, 0.4)
                    continue
                ultima_cat = obter_ultima_linha_pre_selecionado(ctx)
                if not ultima_cat:
                    print(f"🔁 Linha não encontrada em {label}, retentando ({tent+1}/2)")
                    human_delay(ctx.fast_mode, 0.2, 0.4)
                    continue
                try:
                    nota_enem = extrair_nota_enem_de_linha(ctx, ultima_cat)
                except Exception:
                    nota_enem = None
                nota_cat = normalizar_decimal_pt(nota_enem) if nota_enem else None
                if nota_cat is not None:
                    break
                print(f"🔁 Nota ENEM não lida em {label}, retentando ({tent+1}/2)")
            enem_por_categoria[chave] = nota_cat

        registro = {
            "estado": uf,
            "municipio": municipio,
            "curso": "MEDICINA",
            "ies": ies_nome_registro,
            "conceito_curso": conceito_valor,
            
            "nota_enem_ultimo_ampla": enem_por_categoria.get("nota_enem_ultimo_ampla"),
            "nota_enem_ultimo_ppiq": enem_por_categoria.get("nota_enem_ultimo_ppiq"),
            "nota_enem_ultimo_pcd": enem_por_categoria.get("nota_enem_ultimo_pcd"),
        }

        tem_nota = any([
            
            registro["nota_enem_ultimo_ampla"],
            registro["nota_enem_ultimo_ppiq"],
            registro["nota_enem_ultimo_pcd"],
        ])

        if tem_nota:
            resultados.append(registro)
            if salvar_automatico:
                salvar_incremental([registro], caminho=caminho_csv)
            ies_ja_salvos.add(_norm_label(ies_nome_registro))
        else:
            print("⚠️ Nenhuma nota obtida após retentativas — seguindo para próxima IES")

        if idx < len(ies_lista) - 1:
            if not abrir_nova_consulta(ctx):
                print("⚠️ Não foi possível acionar 'Nova Consulta' para próxima IES")
                break
            if not aplicar_filtros(ctx, estado=estado, municipio=municipio, curso="MEDICINA"):
                print("⚠️ Não foi possível reconfigurar filtros após 'Nova Consulta'")
                break

    return resultados, pesquisa_executada


def carregar_progresso(caminho_csv: str) -> Tuple[List[Dict], Set[Tuple[str, str]], Optional[Tuple[str, str]], Dict[Tuple[str, str], Set[str]]]:
    if not os.path.exists(caminho_csv):
        return [], set(), None, {}

    try:
        df = pd.read_csv(caminho_csv)
    except Exception:
        return [], set(), None, {}

    if df.empty:
        return [], set(), None, {}

    df = df.fillna("")
    registros = df.to_dict("records")

    ies_por_mun: Dict[Tuple[str, str], Set[str]] = {}
    for r in registros:
        uf = str(r.get("estado", "")).strip()
        mun = str(r.get("municipio", "")).strip()
        ies_nome = str(r.get("ies", "")).strip()
        if uf and mun and ies_nome:
            chave = (uf, mun)
            ies_por_mun.setdefault(chave, set()).add(_norm_label(ies_nome))

    ja_processados = {
        (str(r.get("estado", "")).strip(), str(r.get("municipio", "")).strip())
        for r in registros
        if str(r.get("estado", "")).strip() and str(r.get("municipio", "")).strip()
    }

    ultima_linha = None
    try:
        ultima = df.iloc[-1]
        uf_ultima = str(ultima.get("estado", "")).strip()
        mun_ultima = str(ultima.get("municipio", "")).strip()
        if uf_ultima and mun_ultima:
            ultima_linha = (uf_ultima, mun_ultima)
    except Exception:
        ultima_linha = None

    return registros, ja_processados, ultima_linha, ies_por_mun


def _carregar_alvos_review(caminho_falhas: str) -> Dict[Tuple[str, str], Tuple[Set[str], Set[str]]]:
    alvos: Dict[Tuple[str, str], Tuple[Set[str], Set[str]]] = {}
    if not os.path.exists(caminho_falhas):
        return alvos

    _sanear_arquivo_falhas(caminho_falhas)
    try:
        falhas_df = pd.read_csv(caminho_falhas)
    except Exception:
        try:
            falhas_df = pd.read_csv(caminho_falhas, engine="python", on_bad_lines="skip")
        except Exception:
            return alvos

    if falhas_df.empty:
        return alvos

    falhas_df = falhas_df.reindex(columns=FALHAS_COLUMNS).fillna("")
    for _, row in falhas_df.iterrows():
        uf, _estado_nome = _resolver_uf_estado(str(row.get("estado", "")))
        municipio = str(row.get("municipio", "")).strip()
        ies_nome = str(row.get("ies", "")).strip()
        ies_codigo = str(row.get("ies_codigo", "")).strip()
        if not uf or not municipio:
            continue

        chave = (uf, municipio)
        nomes, codigos = alvos.get(chave, (set(), set()))
        if ies_nome:
            nomes.add(_norm_label(ies_nome))
        if ies_codigo:
            codigos.add(ies_codigo)
        alvos[chave] = (nomes, codigos)

    return alvos


def _carregar_alvos_faltantes_txt(
    caminho_txt: str,
) -> Tuple[
    Dict[Tuple[str, str], Tuple[Set[str], Set[str]]],
    List[str],
    Dict[Tuple[str, str, str], Set[int]],
    Dict[Tuple[str, str, str], Set[int]],
    int,
]:
    alvos: Dict[Tuple[str, str], Tuple[Set[str], Set[str]]] = {}
    try:
        with open(caminho_txt, "r", encoding="utf-8") as f:
            linhas = [linha.rstrip("\n\r") for linha in f]
    except Exception:
        return {}, [], {}, {}, 0

    indices_nome: Dict[Tuple[str, str, str], Set[int]] = {}
    indices_codigo: Dict[Tuple[str, str, str], Set[int]] = {}
    invalidas = 0
    vistos: Set[Tuple[str, str, str, str]] = set()

    for idx, linha in enumerate(linhas):
        texto = linha.strip()
        if not texto:
            continue
        partes = [p.strip() for p in texto.split("|")]
        if len(partes) < 4:
            invalidas += 1
            continue
        uf_raw, municipio, ies_nome, ies_codigo = partes[0], partes[1], partes[2], partes[3]
        if not uf_raw or not municipio or not ies_nome:
            invalidas += 1
            continue

        uf, _estado = _resolver_uf_estado(uf_raw)
        if not uf:
            invalidas += 1
            continue

        ies_nome_norm = _norm_label(ies_nome)
        dedup_key = (uf, municipio, ies_nome_norm, ies_codigo or "")
        if dedup_key in vistos:
            continue
        vistos.add(dedup_key)

        chave_mun = (uf, municipio)
        nomes, codigos = alvos.get(chave_mun, (set(), set()))
        if ies_nome_norm:
            nomes.add(ies_nome_norm)
            key_nome = (uf, municipio, ies_nome_norm)
            indices_nome.setdefault(key_nome, set()).add(idx)
        if ies_codigo:
            codigos.add(ies_codigo)
            key_cod = (uf, municipio, ies_codigo)
            indices_codigo.setdefault(key_cod, set()).add(idx)
        alvos[chave_mun] = (nomes, codigos)

    return alvos, linhas, indices_nome, indices_codigo, invalidas


def _persistir_faltantes_restantes(caminho_txt: str, linhas: List[str], removidos: Set[int]) -> None:
    restantes = [linha for idx, linha in enumerate(linhas) if idx not in removidos and linha.strip()]
    with open(caminho_txt, "w", encoding="utf-8") as f:
        if restantes:
            f.write("\n".join(restantes) + "\n")


def run_scraper(
    ctx: BrowserContext,
    alvos_review: Optional[Dict[Tuple[str, str], Tuple[Set[str], Set[str]]]] = None,
    on_registro_salvo: Optional[Callable[[Dict], None]] = None,
) -> None:
    driver = ctx.driver
    caminho_csv = _caminho_csv_modalidade()
    existentes, ja_processados, ultimo_par, ies_por_mun = carregar_progresso(caminho_csv)
    dados_finais: List[Dict] = list(existentes)

    modo_alvos = bool(alvos_review)
    ufs_alvo: Set[str] = set()
    if modo_alvos:
        ufs_alvo = {uf for uf, _ in (alvos_review or {}).keys()}

    if ultimo_par and not modo_alvos:
        count_ultimo = sum(1 for r in existentes if str(r.get("estado")) == ultimo_par[0] and str(r.get("municipio")) == ultimo_par[1])
        print(f"▶️ Retomando após: {ultimo_par[0]} - {ultimo_par[1]} (registros salvos: {count_ultimo})")
    elif ja_processados and not modo_alvos:
        print("▶️ Registros existentes encontrados, iniciando do começo ignorando duplicados")
    elif modo_alvos:
        print(f"▶️ Modo alvo: {len(alvos_review or {})} município(s) com IES do CSV de falhas")

    preparar_primeira_pagina(ctx)

    primeiro_estado = True
    estado_teve_pesquisa = False
    iniciar_processamento = True if modo_alvos else (ultimo_par is None)
    iniciar_estado = True if modo_alvos else (ultimo_par is None)

    for uf, estado in ESTADOS.items():
        print(f"\n🟦 Estado: {estado}")

        if modo_alvos and uf not in ufs_alvo:
            print("⏭️ Estado sem alvos no review — pulando")
            continue

        # retoma diretamente a partir do último UF registrado no CSV
        if not iniciar_estado:
            if uf == (ultimo_par or (None, None))[0]:
                iniciar_estado = True
            else:
                print("⏭️ Estado já percorrido — pulando")
                continue

        if not primeiro_estado:
            if estado_teve_pesquisa:
                if not abrir_nova_consulta(ctx):
                    print("⚠️ 'Nova Consulta' não disponível — prosseguindo apenas alterando filtros")
            else:
                # Não houve pesquisa no estado anterior: o botão não existe; apenas siga alterando filtros
                print("ℹ️ Sem pesquisa no estado anterior — pulando 'Nova Consulta' e apenas alterando filtros")
        primeiro_estado = False
        estado_teve_pesquisa = False

        if not aplicar_filtros(ctx, estado=estado):
            print("⚠️ Não foi possível selecionar Estado; avançando")
            continue
        human_delay(ctx.fast_mode, 0.2, 0.5)

        municipios = listar_opcoes_select2(ctx, "select2-noMunicipio-container")
        print(f"➡️ {len(municipios)} municípios")

        for i, municipio in enumerate(municipios):
            print(f"📍 {municipio}")

            if not iniciar_processamento:
                if ultimo_par and uf == ultimo_par[0] and municipio == ultimo_par[1]:
                    iniciar_processamento = True
                else:
                    continue

            if modo_alvos and (uf, municipio) not in (alvos_review or {}):
                print("⏭️ Município sem IES alvo — pulando")
                continue

            if (not modo_alvos) and (uf, municipio) in ja_processados and not (ultimo_par and uf == ultimo_par[0] and municipio == ultimo_par[1]):
                print("⏭️ Já processado — pulando")
                continue

            if not aplicar_filtros(ctx, estado=estado, municipio=municipio, curso="MEDICINA"):
                print("⚠️ Não foi possível aplicar filtros para o município; seguindo para o próximo")
                continue

            try:
                res, pesquisou = buscar_notas_por_municipio(
                    ctx,
                    municipio,
                    estado,
                    uf,
                    ies_ja_salvos=ies_por_mun.get((uf, municipio), set()),
                    ies_alvo_nome_norm=(alvos_review or {}).get((uf, municipio), (set(), set()))[0] if modo_alvos else None,
                    ies_alvo_codigo=(alvos_review or {}).get((uf, municipio), (set(), set()))[1] if modo_alvos else None,
                    caminho_csv=caminho_csv,
                )
                if pesquisou:
                    estado_teve_pesquisa = True
                for r in res:
                    dados_finais.append(r)
                    ies_por_mun.setdefault((uf, municipio), set()).add(_norm_label(r.get("ies", "")))
                    if on_registro_salvo:
                        on_registro_salvo(r)
            except Exception:
                pesquisou = False

            # evita clicar em Nova Consulta quando não houve pesquisa (curso inexistente)
            pesquisou = locals().get("pesquisou", False)

            human_delay(ctx.fast_mode, 0.3, 0.7)

            if i < len(municipios) - 1:
                if pesquisou:
                    if not abrir_nova_consulta(ctx):
                        print("⚠️ Não foi possível acionar 'Nova Consulta' para o próximo município; seguindo apenas alterando filtros")
                    else:
                        if not aplicar_filtros(ctx, estado=estado):
                            print("⚠️ Não foi possível reaplicar estado após 'Nova Consulta'")
                else:
                    # sem pesquisa no município atual: botão não existe; apenas siga para o próximo aplicando filtros no próximo loop
                    pass
    print("\n✅ FINALIZADO")


def run_faltantes_txt(
    ctx: BrowserContext,
    caminho_txt: Optional[str] = None,
    caminho_csv: Optional[str] = None,
) -> None:
    caminho_txt = caminho_txt or _caminho_faltantes_modalidade()
    caminho_csv = caminho_csv or _caminho_csv_modalidade()

    if not os.path.exists(caminho_txt):
        print(f"⚠️ Arquivo de faltantes não encontrado: {caminho_txt}")
        return

    alvos, linhas, indices_nome, indices_codigo, invalidas = _carregar_alvos_faltantes_txt(caminho_txt)
    total_linhas = len([l for l in linhas if l.strip()])
    total_alvos = sum(len(nomes) + len(codigos) for nomes, codigos in alvos.values())
    print(
        f"📄 Faltantes TXT: arquivo={caminho_txt} | linhas={total_linhas} | "
        f"invalidas={invalidas} | alvos={total_alvos}"
    )
    if not alvos:
        print("⚠️ Sem alvos válidos no TXT de faltantes")
        return

    removidos: Set[int] = set()
    removidos_sucesso = 0

    def _marcar_sucesso_e_persistir(registro: Dict) -> None:
        nonlocal removidos_sucesso
        uf = str(registro.get("estado", "")).strip()
        municipio = str(registro.get("municipio", "")).strip()
        ies = str(registro.get("ies", "")).strip()
        ies_norm = _norm_label(ies)
        codigo = _extrair_codigo_ies(ies)

        idxs: Set[int] = set()
        if codigo:
            idxs |= indices_codigo.get((uf, municipio, codigo), set())
        if ies_norm:
            idxs |= indices_nome.get((uf, municipio, ies_norm), set())

        novos_idxs = idxs - removidos
        if not novos_idxs:
            return
        removidos |= novos_idxs
        removidos_sucesso += len(novos_idxs)
        try:
            _persistir_faltantes_restantes(caminho_txt, linhas, removidos)
        except Exception as exc:
            print(f"⚠️ Falha ao atualizar TXT de faltantes: {exc}")

    run_scraper(ctx, alvos_review=alvos, on_registro_salvo=_marcar_sucesso_e_persistir)

    restantes = len([l for idx, l in enumerate(linhas) if idx not in removidos and l.strip()])
    print(
        f"📊 Faltantes processados: removidos_txt={removidos_sucesso} | "
        f"restantes_txt={restantes} | csv={caminho_csv}"
    )


def _carregar_faltantes_conceito(caminho_csv: str) -> Tuple[Set[Tuple[str, str, str]], Set[Tuple[str, str, str]]]:
    faltantes_nome: Set[Tuple[str, str, str]] = set()
    faltantes_codigo: Set[Tuple[str, str, str]] = set()
    if not os.path.exists(caminho_csv):
        return faltantes_nome, faltantes_codigo
    try:
        df = pd.read_csv(caminho_csv)
        for _, row in df.iterrows():
            conceito = str(row.get("conceito_curso", "")).strip()
            if conceito:
                continue
            uf = str(row.get("estado", "")).strip()
            mun = str(row.get("municipio", "")).strip()
            ies_raw = str(row.get("ies", ""))
            ies_norm = _norm_label(ies_raw)
            if uf and mun and ies_norm:
                faltantes_nome.add((uf, mun, ies_norm))
            cod = _extrair_codigo_ies(ies_raw)
            if uf and mun and cod:
                faltantes_codigo.add((uf, mun, cod))
    except Exception:
        pass
    return faltantes_nome, faltantes_codigo


def run_checker(ctx: BrowserContext, curso: str = "MEDICINA", caminho_csv: Optional[str] = None) -> None:
    """Percorre UF/Município/Curso listando IES e valida cobertura contra o CSV existente.

    Se houver registros no CSV sem "conceito_curso", restringe a coleta a eles para acelerar.
    """

    caminho_csv = caminho_csv or _caminho_csv_modalidade()
    modalidade_atual = (settings.FIES_MODALIDADE or "social").lower()
    if modalidade_atual == "regular":
        caminho_faltantes = "notas_fies_medicina_faltantes_regular.txt"
    else:
        caminho_faltantes = "notas_fies_medicina_faltantes.txt"
    existentes, _, _, ies_por_mun = carregar_progresso(caminho_csv)
    novos: List[Dict] = []  # não deve ser usado em --check; mantido por compatibilidade
    alterados: Set[Tuple[str, str, str]] = set()
    houve_mudanca = False
    faltantes_txt: List[str] = []
    faltantes_txt_set: Set[str] = set()
    municipios_verificados = 0
    municipios_indisponibilidade_confirmada = 0
    municipios_recuperados_retry = 0
    falhas_transitorias_municipio = 0

    if os.path.exists(caminho_faltantes):
        try:
            with open(caminho_faltantes, "r", encoding="utf-8") as f:
                for linha_existente in f:
                    linha_existente = linha_existente.strip()
                    if linha_existente:
                        faltantes_txt_set.add(linha_existente)
        except Exception:
            pass

    def _registrar_faltante_txt(uf_val: str, mun_val: str, ies_val: str, cod_val: Optional[str]) -> None:
        linha = f"{uf_val}|{mun_val}|{ies_val}|{cod_val or ''}"
        if linha in faltantes_txt_set:
            return
        faltantes_txt_set.add(linha)
        faltantes_txt.append(linha)
        try:
            with open(caminho_faltantes, "a", encoding="utf-8") as f:
                f.write(f"{linha}\n")
        except Exception as exc:
            print(f"⚠️ Falha ao registrar faltante imediatamente: {exc}")

    def _aplicar_filtros_check_resiliente(uf_val: str, estado_val: str, municipio_val: str, curso_val: str) -> Tuple[bool, str, int]:
        tentativas_max = 3
        for tentativa in range(1, tentativas_max + 1):
            if aplicar_filtros(ctx, estado=estado_val, municipio=municipio_val, curso=curso_val):
                return True, "ok", tentativa

            disponibilidade_confirmada = []
            for _ in range(2):
                try:
                    ok_base = aplicar_filtros(ctx, estado=estado_val, municipio=municipio_val, curso=None)
                    if not ok_base:
                        disponibilidade_confirmada.append(None)
                    else:
                        esperar_select2_habilitado(ctx, "select2-noCursosPublico-container")
                        disponibilidade_confirmada.append(curso_existe(ctx, curso_val))
                except Exception:
                    disponibilidade_confirmada.append(None)
                human_delay(ctx.fast_mode, 0.15, 0.3)

            if disponibilidade_confirmada == [False, False]:
                return False, "indisponivel_confirmado", tentativa

            print(
                f"🔁 Filtro de curso instável em {municipio_val}/{uf_val} "
                f"(tentativa {tentativa}/{tentativas_max}) — retentando"
            )
            human_delay(ctx.fast_mode, 0.3, 0.6)

        return False, "falha_transitoria", tentativas_max

    faltantes_nome, faltantes_codigo = _carregar_faltantes_conceito(caminho_csv)
    if faltantes_nome or faltantes_codigo:
        print(
            f"ℹ️ Encontrados {len(faltantes_nome)} faltantes por nome e {len(faltantes_codigo)} por código — checando apenas eles"
        )

    # índices rápidos para atualizar registros existentes (por nome normalizado e por código de IES)
    existentes_idx: Dict[Tuple[str, str, str], Dict] = {}
    existentes_idx_por_codigo: Dict[Tuple[str, str, str], Dict] = {}
    for reg in existentes:
        uf_reg = str(reg.get("estado", "")).strip()
        mun_reg = str(reg.get("municipio", "")).strip()
        ies_reg = str(reg.get("ies", ""))
        chave_nome = (
            uf_reg,
            mun_reg,
            _norm_label(ies_reg),
        )
        existentes_idx[chave_nome] = reg

        cod_reg = _extrair_codigo_ies(ies_reg)
        if cod_reg:
            existentes_idx_por_codigo[(uf_reg, mun_reg, cod_reg)] = reg

    if existentes:
        print(f"▶️ CSV existente com {len(existentes)} registros — checando cobertura")
    else:
        print("ℹ️ CSV ainda vazio — iremos preenchê-lo apenas com IES descobertas")

    preparar_primeira_pagina(ctx)

    for uf, estado in ESTADOS.items():
        print(f"\n🟦 Estado: {estado}")

        if not aplicar_filtros(ctx, estado=estado):
            print("⚠️ Não foi possível selecionar Estado; avançando")
            continue
        human_delay(ctx.fast_mode, 0.2, 0.5)

        try:
            municipios = listar_opcoes_select2(ctx, "select2-noMunicipio-container")
        except Exception:
            print("⚠️ Não foi possível listar municípios; avançando")
            continue

        for i, municipio in enumerate(municipios):
            print(f"📍 {municipio}")

            if faltantes_nome or faltantes_codigo:
                # pula municípios que não têm faltantes (por nome ou código)
                tem_faltante_mun = any(uf == f[0] and municipio == f[1] for f in faltantes_nome) or any(
                    uf == f[0] and municipio == f[1] for f in faltantes_codigo
                )
                if not tem_faltante_mun:
                    print("⏭️ Sem faltantes neste município — pulando")
                    continue

            municipios_verificados += 1
            ok_filtros, motivo_filtros, tentativas_filtros = _aplicar_filtros_check_resiliente(
                uf, estado, municipio, curso
            )
            if not ok_filtros:
                if motivo_filtros == "indisponivel_confirmado":
                    municipios_indisponibilidade_confirmada += 1
                    print(f"⏭️ {curso} indisponível após dupla checagem em {municipio}/{uf} — pulando município")
                else:
                    falhas_transitorias_municipio += 1
                    print(f"⚠️ Falha transitória ao aplicar filtros em {municipio}/{uf} — seguindo para o próximo")
                continue
            if tentativas_filtros > 1:
                municipios_recuperados_retry += 1

            try:
                esperar_select2_habilitado(ctx, "select2-iesPublico-container")
                ies_lista = listar_opcoes_select2_multi(ctx, ["select2-iesPublico-container"])
            except TimeoutException:
                print("⚠️ IES ainda desabilitado após aguardar — pulando município")
                ies_lista = []
            except Exception:
                ies_lista = []

            chave_mun = (uf, municipio)
            existentes_set = ies_por_mun.get(chave_mun, set())
            novos_para_mun = 0

            for idx_ies, ies in enumerate(ies_lista):
                norm = _norm_label(ies)
                codigo_ies = _extrair_codigo_ies(ies)

                # se há lista de faltantes, só processa quem está faltando por nome ou por código
                if (faltantes_nome or faltantes_codigo) and not (
                    (uf, municipio, norm) in faltantes_nome or (codigo_ies and (uf, municipio, codigo_ies) in faltantes_codigo)
                ):
                    continue
                reg_existente = existentes_idx.get((uf, municipio, norm))
                if not reg_existente and codigo_ies:
                    # fallback para casar pelo código de IES quando o nome diverge
                    reg_existente = existentes_idx_por_codigo.get((uf, municipio, codigo_ies))

                ok_sel = select2_exact_multi(ctx, ["select2-iesPublico-container"], ies)
                if not ok_sel:
                    print(f"⚠️ Não foi possível selecionar IES para ler conceito: {ies}")
                    continue

                conceito_valor = None
                try:
                    if select2_pick_first(ctx, "select2-conceitoCurso-container"):
                        elc = ctx.driver.find_element(By.ID, "select2-conceitoCurso-container")
                        conceito_valor = (elc.get_attribute("title") or elc.text or "").strip() or None
                except Exception:
                    conceito_valor = None

                if reg_existente:
                    if conceito_valor and not str(reg_existente.get("conceito_curso") or "").strip():
                        reg_existente["conceito_curso"] = conceito_valor
                        alterados.add((uf, municipio, norm))
                        houve_mudanca = True
                else:
                    # não cria novas linhas; apenas reporta que não encontrou correspondente no CSV
                    if codigo_ies:
                        print(f"⏭️ IES não está no CSV (uf={uf}, mun={municipio}, cod={codigo_ies}) — não adicionando linha nova")
                    else:
                        print(f"⏭️ IES não está no CSV (uf={uf}, mun={municipio}, nome='{ies}') — não adicionando linha nova")
                    _registrar_faltante_txt(uf, municipio, ies, codigo_ies)

                # fecha interações atuais; reconfigura filtros para o próximo IES sem nova consulta
                try:
                    ctx.driver.find_element(By.TAG_NAME, "body").click()
                except Exception:
                    pass

                if idx_ies < len(ies_lista) - 1:
                    ok_refiltro, motivo_refiltro, _ = _aplicar_filtros_check_resiliente(
                        uf, estado, municipio, curso
                    )
                    if not ok_refiltro:
                        if motivo_refiltro == "indisponivel_confirmado":
                            municipios_indisponibilidade_confirmada += 1
                            print(f"⏭️ {curso} indisponível após dupla checagem em {municipio}/{uf} durante refiltro")
                        else:
                            falhas_transitorias_municipio += 1
                            print("⚠️ Não foi possível reaplicar filtros após IES por falha transitória")
                        break

            # antes do próximo município, reseta seleção de IES/curso para evitar travar selects
            try:
                ctx.driver.find_element(By.TAG_NAME, "body").click()
            except Exception:
                pass

            ies_por_mun[chave_mun] = existentes_set

            print(f"📑 IES encontradas: {len(ies_lista)} | novas: {novos_para_mun}")

            # sem nova consulta: apenas segue para o próximo município aplicando filtros no próximo loop

    if houve_mudanca or novos:
        print(f"💾 Salvando CSV: novos={len(novos)} alterados={len(alterados)}")
        # preserva ordem original do CSV; "novos" não deve ser usado em --check
        salvar_csv_completo(existentes, caminho=caminho_csv)
    else:
        print("✅ Nenhuma atualização necessária — CSV já cobre todos os itens listados")

    if faltantes_txt:
        print(f"📝 TXT de faltantes atualizado em tempo real: {len(faltantes_txt)} nova(s) linha(s)")

    print(
        "📊 Auditoria --check: "
        f"municipios_verificados={municipios_verificados} | "
        f"recuperados_retry={municipios_recuperados_retry} | "
        f"indisponibilidade_confirmada={municipios_indisponibilidade_confirmada} | "
        f"falhas_transitorias={falhas_transitorias_municipio}"
    )

    print("\n✅ CHECK FINALIZADO")


def run_review(
    ctx: BrowserContext,
    caminho_csv: Optional[str] = None,
    caminho_falhas: str = "notas_fies_medicina_falhas.csv",
) -> None:
    """Executa o fluxo padrão restringindo as buscas às IES alvo do CSV de falhas."""
    caminho_csv = caminho_csv or _caminho_csv_modalidade()
    alvos = _carregar_alvos_review(caminho_falhas)
    if not alvos:
        print("⚠️ Sem alvos válidos no CSV de falhas para executar --review")
        return
    run_scraper(ctx, alvos_review=alvos)
