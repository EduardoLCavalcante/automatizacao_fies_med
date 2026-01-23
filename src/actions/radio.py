"""Seleção de rádios relacionados ao FIES (ex.: Fies Social)."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.core import BrowserContext, human_delay


def selecionar_radio_por_texto(ctx: BrowserContext, texto: str) -> bool:
    driver, wait = ctx.driver, ctx.wait
    alvo = texto.strip()

    radios = driver.find_elements(By.XPATH, "//input[@type='radio']")
    for r in radios:
        lbl = None
        try:
            lbl = r.find_element(By.XPATH, "following-sibling::label")
        except Exception:
            pass
        if not lbl:
            try:
                lbl = r.find_element(By.XPATH, "ancestor::label")
            except Exception:
                pass

        if lbl:
            txt = lbl.text.strip()
            if txt and alvo.upper() in txt.upper():
                try:
                    driver.execute_script("arguments[0].click()", lbl)
                except Exception:
                    lbl.click()
                try:
                    wait.until(lambda d: r.is_selected())
                except TimeoutException:
                    pass
                human_delay(ctx.fast_mode, 0.2, 0.6)
                return True

    labels = driver.find_elements(By.XPATH, "//label")
    for lbl in labels:
        txt = lbl.text.strip()
        if txt and alvo.upper() in txt.upper():
            try:
                driver.execute_script("arguments[0].click()", lbl)
            except Exception:
                lbl.click()
            human_delay(ctx.fast_mode, 0.2, 0.6)
            return True

    try:
        radio = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//input[@type='radio' and following-sibling::label[contains(normalize-space(.), '{alvo}')]]")
            )
        )
        driver.execute_script("arguments[0].click()", radio)
        human_delay(ctx.fast_mode, 0.2, 0.6)
        return True
    except TimeoutException:
        return False


def selecionar_radio_fies_social(ctx: BrowserContext) -> bool:
    driver, wait = ctx.driver, ctx.wait
    alvo = "Fies Social"
    if selecionar_radio_por_texto(ctx, alvo):
        try:
            marcado = driver.find_elements(By.XPATH, "//input[@type='radio' and (following-sibling::label[contains(normalize-space(.), 'Fies Social')] or ancestor::label[contains(normalize-space(.), 'Fies Social')]) and @checked]")
            if marcado:
                return True
        except Exception:
            pass
    try:
        lbl = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(normalize-space(.), 'Fies Social')]")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lbl)
        try:
            lbl.click()
        except Exception:
            driver.execute_script("arguments[0].click();", lbl)
        human_delay(ctx.fast_mode, 0.2, 0.6)
        return True
    except Exception:
        pass
    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[self::label or self::span or self::div or self::button][contains(normalize-space(.), 'Fies Social')]")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        human_delay(ctx.fast_mode, 0.2, 0.6)
        return True
    except Exception:
        return False
