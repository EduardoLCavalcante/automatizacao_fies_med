"""Navegação, recarga e reaplicação de filtros na página principal."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.core import BrowserContext, human_delay
from src.config import BASE_URL
from src.actions import select2, select2_exact


def preparar_primeira_pagina(ctx: BrowserContext) -> None:
    driver, wait = ctx.driver, ctx.wait
    driver.get(BASE_URL)
    print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
    input()
    try:
        wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
    except TimeoutException:
        pass


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
        return False

    try:
        wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
    except TimeoutException:
        pass

    print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
    input()
    try:
        wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
    except TimeoutException:
        pass
    return True


def aplicar_filtros(ctx: BrowserContext, estado: str, municipio: str | None = None, curso: str | None = "MEDICINA") -> bool:
    """Aplica estado e, opcionalmente, município e curso na página principal."""
    try:
        select2(ctx, "select2-noEstado-container", estado)
        human_delay(ctx.fast_mode, 0.2, 0.5)
    except Exception:
        return False

    if municipio:
        try:
            select2(ctx, "select2-noMunicipio-container", municipio)
            human_delay(ctx.fast_mode, 0.2, 0.5)
        except Exception:
            return False
        if curso:
            try:
                select2_exact(ctx, "select2-noCursosPublico-container", curso)
                human_delay(ctx.fast_mode, 0.2, 0.5)
            except TimeoutException:
                print(f"⚠️ Não foi possível selecionar {curso} após recarregar")
                return False
    return True
