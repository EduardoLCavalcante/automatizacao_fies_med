"""Operações sobre a tabela de resultados."""

import time
from typing import List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from src.core import BrowserContext, human_delay


def expandir_todos_candidatos(ctx: BrowserContext) -> None:
    driver, wait = ctx.driver, ctx.wait
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
            )
        )
    except TimeoutException:
        return

    max_clicks = 500
    sem_crescimento = 0
    localizadores = [
        (By.ID, "linkPaginacaoPublico"),
        (By.XPATH, "//span[contains(@class,'link-ver-mais-consulta') and contains(., 'Ver mais')]")
    ]

    def _get_ver_mais():
        for by, sel in localizadores:
            els = driver.find_elements(by, sel)
            for el in els:
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        return None

    def _rows_count():
        return len(driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr"))

    while max_clicks > 0:
        max_clicks -= 1
        qtd_antes = _rows_count()

        ver_mais_el = _get_ver_mais()
        if not ver_mais_el:
            break

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ver_mais_el)
        except Exception:
            pass
        clicked = False
        try:
            ver_mais_el.click()
            clicked = True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", ver_mais_el)
                clicked = True
            except Exception:
                clicked = False

        if not clicked:
            break

        timeout = 2.0 if ctx.fast_mode else 5.0
        end = time.time() + timeout
        cresceu = False
        while time.time() < end:
            qtd_atual = _rows_count()
            if qtd_atual > qtd_antes:
                cresceu = True
                break
            if _get_ver_mais() is None:
                break
            human_delay(ctx.fast_mode, 0.05 if ctx.fast_mode else 0.15, 0.05 if ctx.fast_mode else 0.15)

        if not cresceu:
            sem_crescimento += 1
            if sem_crescimento >= 2:
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                except Exception:
                    pass
                break
        else:
            sem_crescimento = 0

        if ctx.fast_mode:
            human_delay(ctx.fast_mode, 0.05, 0.05)
        else:
            human_delay(ctx.fast_mode, 0.1, 0.2)


def obter_ultima_linha(ctx: BrowserContext):
    wait = ctx.wait
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
            )
        )
    except TimeoutException:
        return None

    expandir_todos_candidatos(ctx)

    linhas = ctx.driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
    if not linhas:
        return None
    return linhas[-1]


def _linha_e_pre_selecionado(linha) -> bool:
    try:
        spans = linha.find_elements(By.CSS_SELECTOR, "span.situacao-selecionado")
        if any("pré-selecionado" in (s.text or "").lower() for s in spans):
            return True
        if "pré-selecionado" in (linha.text or "").lower():
            return True
    except Exception:
        return False
    return False


def obter_ultima_linha_pre_selecionado(ctx: BrowserContext):
    wait = ctx.wait
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
            )
        )
    except TimeoutException:
        return None

    expandir_todos_candidatos(ctx)

    linhas = ctx.driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
    for linha in reversed(linhas):
        if _linha_e_pre_selecionado(linha):
            return linha
    return None


def selecionar_categoria(ctx: BrowserContext, tipo_label: Optional[str] = None, tipo_codigo: Optional[int] = None) -> bool:
    driver, wait = ctx.driver, ctx.wait
    alvos: List[Tuple[str, str]] = []
    if tipo_codigo is not None:
        alvos.append((By.XPATH, f"//button[contains(@onclick,'selecaoClassificaoTipoVaga({tipo_codigo})')]") )
    if tipo_label:
        alvos.append((By.XPATH, f"//button[contains(normalize-space(.), '{tipo_label}')]") )

    try:
        linhas_antes = driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
        qtd_antes = len(linhas_antes)
    except Exception:
        qtd_antes = 0

    btn = None
    for by, sel in alvos:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel)))
            if el and el.is_displayed():
                btn = el
                break
        except TimeoutException:
            continue

    if not btn:
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    except Exception:
        pass
    try:
        btn.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", btn)
        except Exception:
            return False

    try:
        WebDriverWait(driver, 8).until(
            lambda d: len(d.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")) != qtd_antes
        )
    except TimeoutException:
        pass
    return True
