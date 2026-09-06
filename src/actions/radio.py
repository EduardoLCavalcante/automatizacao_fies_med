"""Seleção idempotente da modalidade, sem invalidar filtros já preenchidos."""

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from src.core import BrowserContext


def selecionar_radio_por_texto(ctx: BrowserContext, texto: str) -> bool:
    alvo = " ".join(texto.casefold().split())

    def localizar(driver):
        for radio in driver.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
            labels = radio.find_elements(By.XPATH, "following-sibling::label[1] | ancestor::label")
            radio_id = radio.get_attribute("id")
            if radio_id:
                labels += driver.find_elements(By.CSS_SELECTOR, f'label[for="{radio_id}"]')
            for label in labels:
                if label.get_attribute('for') not in (None, '', radio_id):
                    continue
                if " ".join(label.text.casefold().split()) == alvo:
                    return radio, label
        return False

    try:
        radio, label = ctx.wait.until(localizar)
        if radio.is_selected():
            return True
        label.click()
        # Reconsulta o DOM; @checked não reflete necessariamente o estado atual.
        def confirmado(driver):
            par = localizar(driver)
            return bool(par and par[0].is_selected())
        ctx.wait.until(confirmado)
        return True
    except (TimeoutException, StaleElementReferenceException):
        return False


def selecionar_radio_fies_social(ctx: BrowserContext) -> bool:
    return selecionar_radio_por_texto(ctx, "Fies Social")


def selecionar_radio_fies_regular(ctx: BrowserContext) -> bool:
    return selecionar_radio_por_texto(ctx, "Fies")
