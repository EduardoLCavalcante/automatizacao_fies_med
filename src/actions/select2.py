"""Ações de interação com Select2 (listas e seleções)."""

from typing import Iterable, List
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from src.core import BrowserContext, human_delay


def select2(ctx: BrowserContext, container_id: str, texto: str) -> None:
    driver, wait = ctx.driver, ctx.wait
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    campo = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//input[contains(@class,'select2-search__field')]")
        )
    )

    campo.send_keys(Keys.CONTROL + "a")
    campo.send_keys(Keys.BACKSPACE)

    per_char = 0.02 if ctx.fast_mode else 0.06
    for letra in texto:
        campo.send_keys(letra)
        human_delay(ctx.fast_mode, per_char, per_char)

    if ctx.fast_mode:
        human_delay(ctx.fast_mode, 0.08, 0.18)
    else:
        human_delay(ctx.fast_mode, 1.0, 1.0)
    campo.send_keys(Keys.ENTER)


def select2_exact(ctx: BrowserContext, container_id: str, texto: str) -> None:
    driver, wait = ctx.driver, ctx.wait
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    campo = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//input[contains(@class,'select2-search__field')]")
        )
    )

    campo.send_keys(Keys.CONTROL + "a")
    campo.send_keys(Keys.BACKSPACE)
    per_char = 0.02 if ctx.fast_mode else 0.06
    for letra in texto:
        campo.send_keys(letra)
        human_delay(ctx.fast_mode, per_char, per_char)

    human_delay(ctx.fast_mode, 0.08, 0.18 if ctx.fast_mode else 0.8)

    results = wait.until(
        EC.presence_of_element_located(
            (By.CLASS_NAME, "select2-results__options")
        )
    )

    match = None
    last_count = -1
    while True:
        itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
        for item in itens:
            txt = item.text.strip()
            if txt and txt.upper() == texto.upper():
                match = item
                break
        if match:
            break
        if len(itens) == last_count:
            break
        last_count = len(itens)
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", results
        )
        if ctx.fast_mode:
            human_delay(ctx.fast_mode, 0.06, 0.14)
        else:
            human_delay(ctx.fast_mode, 0.6, 0.6)

    if match:
        match.click()
        human_delay(ctx.fast_mode, 0.4, 0.9)
    else:
        driver.find_element(By.TAG_NAME, "body").click()
        raise TimeoutException(f"Opção exata não encontrada para: {texto}")

    driver.find_element(By.TAG_NAME, "body").click()


def curso_existe(ctx: BrowserContext, nome_curso: str) -> bool:
    driver, wait = ctx.driver, ctx.wait
    try:
        container = wait.until(
            EC.element_to_be_clickable((By.ID, "select2-noCursosPublico-container"))
        )
        container.click()

        campo = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//input[contains(@class,'select2-search__field')]")
            )
        )

        campo.send_keys(nome_curso)
        human_delay(ctx.fast_mode, 0.1, 0.2)

        WebDriverWait(driver, 3 if ctx.fast_mode else 5).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "select2-results__option")
            )
        )

        opcoes = driver.find_elements(By.CLASS_NAME, "select2-results__option")
        existe = any(nome_curso.upper() in o.text.upper() for o in opcoes)

        driver.find_element(By.TAG_NAME, "body").click()
        return existe
    except TimeoutException:
        driver.find_element(By.TAG_NAME, "body").click()
        return False


def listar_opcoes_select2(ctx: BrowserContext, container_id: str) -> List[str]:
    driver, wait = ctx.driver, ctx.wait
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    results = wait.until(
        EC.presence_of_element_located(
            (By.CLASS_NAME, "select2-results__options")
        )
    )

    opcoes = set()
    last_count = 0

    while True:
        itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
        for item in itens:
            txt = item.text.strip()
            if txt and "Selecione" not in txt:
                opcoes.add(txt)

        if len(opcoes) == last_count:
            break

        last_count = len(opcoes)
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", results
        )
        human_delay(ctx.fast_mode, 0.8, 0.8)

    driver.find_element(By.TAG_NAME, "body").click()
    return sorted(opcoes)


def listar_opcoes_select2_rapido(ctx: BrowserContext, container_id: str) -> List[str]:
    driver, wait = ctx.driver, ctx.wait
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    results = wait.until(
        EC.presence_of_element_located(
            (By.CLASS_NAME, "select2-results__options")
        )
    )

    itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
    opcoes: List[str] = []
    for item in itens[:10]:
        txt = item.text.strip()
        if txt and "Selecione" not in txt:
            opcoes.append(txt)

    driver.find_element(By.TAG_NAME, "body").click()
    return opcoes


def select2_pick_first(ctx: BrowserContext, container_id: str) -> bool:
    driver, wait = ctx.driver, ctx.wait
    try:
        container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
        container.click()
        results = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "select2-results__options")))
        itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
        alvo = None
        for item in itens:
            txt = item.text.strip()
            if txt and "Selecione" not in txt and "No results" not in txt:
                alvo = item
                break
        if not alvo and itens:
            alvo = itens[0]
        if alvo:
            alvo.click()
            driver.find_element(By.TAG_NAME, "body").click()
            return True
    except Exception:
        pass
    try:
        driver.find_element(By.TAG_NAME, "body").click()
    except Exception:
        pass
    return False


def _verify_select2_selected(ctx: BrowserContext, container_id: str, expected_text: str, timeout: int = 6) -> bool:
    driver = ctx.driver
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: (d.find_element(By.ID, container_id).get_attribute("title") or d.find_element(By.ID, container_id).text).strip().upper() == expected_text.strip().upper()
        )
        return True
    except Exception:
        return False


def select2_exact_multi(ctx: BrowserContext, container_ids: Iterable[str], texto: str) -> bool:
    for cid in container_ids:
        try:
            select2_exact(ctx, cid, texto)
            if _verify_select2_selected(ctx, cid, texto):
                return True
        except Exception:
            continue
    return False


def listar_opcoes_select2_multi(ctx: BrowserContext, container_ids: Iterable[str]) -> List[str]:
    for cid in container_ids:
        try:
            op = listar_opcoes_select2(ctx, cid)
            if op:
                return op
            human_delay(ctx.fast_mode, 0.1, 0.2)
            op2 = listar_opcoes_select2(ctx, cid)
            if op2:
                return op2
        except Exception:
            continue
    return []
