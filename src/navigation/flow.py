"""Navegação, recarga e reaplicação de filtros na página principal."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import src.config.settings as settings
from src.core import (
    BrowserContext,
    aguardar_cloudflare_inicial,
    aguardar_captcha,
    human_delay,
    propagar_timeout,
    remove_loading_overlay,
)
from src.config import BASE_URL
from src.actions import (
    select2,
    select2_exact,
    select2_exact_multi,
    select2_pick_first,
    esperar_select2_habilitado,
    selecionar_radio_fies_social,
    selecionar_radio_fies_regular,
    curso_existe,
)


def _aguardar_formulario(ctx: BrowserContext) -> None:
    ctx.wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))


def preparar_primeira_pagina(ctx: BrowserContext) -> None:
    driver = ctx.driver
    ctx.captcha.reset()
    driver.get(BASE_URL)
    remove_loading_overlay(ctx)
    aguardar_cloudflare_inicial(ctx)
    aguardar_captcha(ctx)
    remove_loading_overlay(ctx)
    _aguardar_formulario(ctx)


def restaurar_checkpoint(ctx: BrowserContext) -> None:
    """Reabre a consulta e reaplica o estado lógico salvo antes do timeout."""

    checkpoint = ctx.checkpoint
    settings.FIES_MODALIDADE = checkpoint.modalidade
    ctx.captcha.reset()
    ctx.driver.get(BASE_URL)
    remove_loading_overlay(ctx)
    aguardar_captcha(ctx)
    remove_loading_overlay(ctx)
    _aguardar_formulario(ctx)

    if not checkpoint.estado:
        return

    if not aplicar_filtros(
        ctx,
        estado=checkpoint.estado,
        municipio=checkpoint.municipio,
        curso=checkpoint.curso,
    ):
        raise TimeoutException("não foi possível restaurar os filtros do checkpoint")

    if checkpoint.ies_nome:
        esperar_select2_habilitado(ctx, "select2-iesPublico-container")
        alvo_ies = checkpoint.ies_nome
        if checkpoint.ies_codigo and checkpoint.ies_codigo not in alvo_ies:
            alvo_ies = f"{alvo_ies} ({checkpoint.ies_codigo})"
        if not select2_exact_multi(ctx, ["select2-iesPublico-container"], alvo_ies):
            raise TimeoutException("não foi possível restaurar a IES do checkpoint")

    if checkpoint.conceito:
        select2_exact(ctx, "select2-conceitoCurso-container", checkpoint.conceito)
    elif checkpoint.ies_nome and not select2_pick_first(
        ctx, "select2-conceitoCurso-container"
    ):
        raise TimeoutException("não foi possível restaurar o conceito do checkpoint")

    if checkpoint.fase.startswith("categoria_") or checkpoint.fase == "nova_consulta":
        if not ctx.driver.find_elements(By.XPATH, "//table/tbody/tr"):
            aguardar_captcha(ctx)
            botao = ctx.wait.until(
                EC.element_to_be_clickable((By.ID, "btnBuscarCursos"))
            )
            botao.click()
            ctx.wait.until(
                EC.presence_of_element_located((By.XPATH, "//table/tbody/tr"))
            )


def abrir_nova_consulta(ctx: BrowserContext) -> bool:
    """Clica em "Nova Consulta" e aguarda a página principal (CAPTCHA incluído)."""
    driver, wait = ctx.driver, ctx.wait
    try:
        link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='/consulta']")))
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
        except Exception:
            pass
        link.click()
    except TimeoutException:
        raise

    ctx.captcha.reset()
    remove_loading_overlay(ctx)
    aguardar_captcha(ctx)
    remove_loading_overlay(ctx)
    _aguardar_formulario(ctx)
    return True


def aplicar_filtros(ctx: BrowserContext, estado: str, municipio: str | None = None, curso: str | None = "MEDICINA") -> bool:
    """Aplica estado e, opcionalmente, município e curso na página principal."""
    remove_loading_overlay(ctx)
    modalidade = getattr(settings, "FIES_MODALIDADE", "social").lower()
    radio_ok = (
        selecionar_radio_fies_regular(ctx)
        if modalidade == "regular"
        else selecionar_radio_fies_social(ctx)
    )
    if not radio_ok:
        print("⚠️ Não foi possível selecionar modalidade FIES")
        return False
    human_delay(ctx.fast_mode, 0.1, 0.3)

    try:
        select2(ctx, "select2-noEstado-container", estado)
        human_delay(ctx.fast_mode, 0.2, 0.5)
    except Exception as exc:
        propagar_timeout(exc)
        return False

    if municipio:
        try:
            select2(ctx, "select2-noMunicipio-container", municipio)
            human_delay(ctx.fast_mode, 0.2, 0.5)
        except Exception as exc:
            propagar_timeout(exc)
            return False
        if curso:
            try:
                esperar_select2_habilitado(ctx, "select2-noCursosPublico-container")
                if not curso_existe(ctx, curso):
                    print(f"⏭️ {curso} não disponível — pulando município")
                    return False
                select2_exact(ctx, "select2-noCursosPublico-container", curso)
                human_delay(ctx.fast_mode, 0.2, 0.5)
            except TimeoutException:
                raise
            except RuntimeError:
                print(f"⏭️ {curso} não encontrado — pulando município")
                return False
    return True
