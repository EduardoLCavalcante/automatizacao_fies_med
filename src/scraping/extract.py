"""Extração de notas ENEM a partir do modal/linhas."""

from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.core import BrowserContext


def extrair_nota_enem_de_modal(ctx: BrowserContext) -> Optional[str]:
    wait, driver = ctx.wait, ctx.driver
    wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//span[contains(normalize-space(.), 'NOTA ENEM')]")
        )
    )

    valor_span = None
    candidatos = [
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[contains(@style,'font-weight')][1]",
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[contains(@style,'font-size')][1]",
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[1]",
    ]
    for xp in candidatos:
        valor_span = wait.until(
            EC.visibility_of_element_located((By.XPATH, xp))
        )
        if valor_span and valor_span.text.strip():
            break
    nota_texto = valor_span.text.strip() if valor_span else None

    btn_voltar = wait.until(EC.element_to_be_clickable((By.ID, "btnModalFechar")))
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_voltar)
    except Exception:
        pass
    try:
        btn_voltar.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn_voltar)
    WebDriverWait(driver, 5).until(
        EC.invisibility_of_element_located((By.ID, "btnModalFechar"))
    )
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
