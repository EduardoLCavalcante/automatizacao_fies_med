"""Extração de notas ENEM a partir do modal/linhas."""

from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from src.core import BrowserContext


def extrair_nota_enem_de_modal(ctx: BrowserContext) -> Optional[str]:
    wait, driver = ctx.wait, ctx.driver
    try:
        wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//span[contains(normalize-space(.), 'NOTA ENEM')]")
            )
        )
    except TimeoutException:
        return None

    valor_span = None
    candidatos = [
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[contains(@style,'font-weight')][1]",
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[contains(@style,'font-size')][1]",
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[1]",
    ]
    for xp in candidatos:
        try:
            valor_span = wait.until(
                EC.visibility_of_element_located((By.XPATH, xp))
            )
            if valor_span and valor_span.text.strip():
                break
        except TimeoutException:
            continue
    nota_texto = valor_span.text.strip() if valor_span else None

    try:
        btn_voltar = wait.until(EC.element_to_be_clickable((By.ID, "btnModalFechar")))
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_voltar)
        except Exception:
            pass
        try:
            btn_voltar.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn_voltar)
        try:
            WebDriverWait(driver, 5).until(
                EC.invisibility_of_element_located((By.ID, "btnModalFechar"))
            )
        except TimeoutException:
            pass
    except TimeoutException:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            try:
                fechar = driver.find_element(By.XPATH, "//div[contains(@class,'modal')]//button[contains(@class,'close') or contains(.,'Fechar')]")
                driver.execute_script("arguments[0].click();", fechar)
            except Exception:
                pass
    return nota_texto


def extrair_nota_enem_de_linha(ctx: BrowserContext, linha) -> Optional[str]:
    driver = ctx.driver
    try:
        btn = linha.find_element(By.XPATH, ".//button[contains(., 'Ver Detalhes')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        btn.click()
        return extrair_nota_enem_de_modal(ctx)
    except Exception:
        return None
