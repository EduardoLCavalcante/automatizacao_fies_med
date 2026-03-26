"""Ações de interação com Select2 (listas e seleções)."""

from typing import Iterable, List
import unicodedata
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait

from src.core import BrowserContext, human_delay


def esperar_select2_habilitado(ctx: BrowserContext, container_id: str, timeout: int | None = None):
    limite = timeout or (45 if ctx.fast_mode else 60)
    driver = ctx.driver

    def _habilitado(d):
        el = d.find_element(By.ID, container_id)
        classe = el.get_attribute("class") or ""
        aria_disabled = (el.get_attribute("aria-disabled") or "").lower()
        if "select2-container--disabled" in classe or aria_disabled == "true":
            return False
        return el

    return WebDriverWait(
        driver,
        limite,
        poll_frequency=0.3,
        ignored_exceptions=(StaleElementReferenceException,),
    ).until(_habilitado)


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

    if ctx.fast_mode:
        campo.send_keys(texto)
    else:
        for letra in texto:
            campo.send_keys(letra)
            human_delay(ctx.fast_mode, 0.02, 0.02)

    if ctx.fast_mode:
        human_delay(ctx.fast_mode, 0.04, 0.08)
    else:
        human_delay(ctx.fast_mode, 0.5, 0.7)
    campo.send_keys(Keys.ENTER)


def select2_exact(ctx: BrowserContext, container_id: str, texto: str) -> None:
    driver, wait = ctx.driver, ctx.wait
    esperar_select2_habilitado(ctx, container_id)

    for tentativa in range(3):
        try:
            container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
            container.click()

            campo = wait.until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//input[contains(@class,'select2-search__field')]")
                )
            )

            campo.send_keys(Keys.CONTROL + "a")
            campo.send_keys(Keys.BACKSPACE)
            if ctx.fast_mode:
                campo.send_keys(texto)
            else:
                for letra in texto:
                    campo.send_keys(letra)
                    human_delay(ctx.fast_mode, 0.04, 0.04)

            human_delay(ctx.fast_mode, 0.04, 0.1 if ctx.fast_mode else 0.6)

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
                    human_delay(ctx.fast_mode, 0.03, 0.08)
                else:
                    human_delay(ctx.fast_mode, 0.4, 0.5)

            if match:
                match.click()
                human_delay(ctx.fast_mode, 0.2, 0.5 if ctx.fast_mode else 0.8)
            else:
                driver.find_element(By.TAG_NAME, "body").click()
                raise TimeoutException(f"Opção exata não encontrada para: {texto}")

            driver.find_element(By.TAG_NAME, "body").click()
            return
        except StaleElementReferenceException:
            if tentativa == 2:
                raise
            human_delay(ctx.fast_mode, 0.08, 0.16)
            continue


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
            lambda d: _texto_selecionado(
                (d.find_element(By.ID, container_id).get_attribute("title") or d.find_element(By.ID, container_id).text),
                expected_text,
            )
        )
        return True
    except Exception:
        return False


def _norm_text(txt: str) -> str:
    # remove acentos e colapsa espaços para comparações tolerantes
    norm = unicodedata.normalize("NFD", txt or "")
    ascii_txt = norm.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_txt.lower().split())


def _codigo_final(txt: str) -> str | None:
    m = re.search(r"\((\d{4,})\)\s*$", txt or "")
    return m.group(1) if m else None


def _nome_sem_codigo(txt: str) -> str:
    return re.sub(r"\(\d{4,}\)\s*$", "", txt or "").strip()


def _texto_selecionado(container_texto: str, esperado_texto: str) -> bool:
    selecionado_norm = _norm_text(container_texto)
    esperado_norm = _norm_text(esperado_texto)
    if not selecionado_norm or not esperado_norm:
        return False

    cod_sel = _codigo_final(container_texto)
    cod_esp = _codigo_final(esperado_texto)
    if cod_sel and cod_esp:
        return cod_sel == cod_esp

    nome_sel = _norm_text(_nome_sem_codigo(container_texto))
    nome_esp = _norm_text(_nome_sem_codigo(esperado_texto))
    if not nome_sel or not nome_esp:
        return False
    return nome_esp in nome_sel or nome_sel in nome_esp


def select2_exact_multi(ctx: BrowserContext, container_ids: Iterable[str], texto: str) -> bool:
    alvo_norm = _norm_text(texto)
    codigo_alvo = _codigo_final(texto)
    for cid in container_ids:
        try:
            select2_exact(ctx, cid, texto)
            if _verify_select2_selected(ctx, cid, texto):
                return True
        except Exception:
            pass

        # fallback: busca tolerante por aproximação contendo o texto normalizado
        try:
            container = ctx.wait.until(EC.element_to_be_clickable((By.ID, cid)))
            container.click()
            # reescreve o filtro para garantir opções visíveis
            campo = ctx.wait.until(EC.visibility_of_element_located((By.XPATH, "//input[contains(@class,'select2-search__field')]")))
            campo.send_keys(Keys.CONTROL + "a")
            campo.send_keys(Keys.BACKSPACE)
            campo.send_keys(texto)
            human_delay(ctx.fast_mode, 0.12, 0.22 if ctx.fast_mode else 0.8)

            results = ctx.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "select2-results__options")))
            itens = []
            for _ in range(20):
                itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
                textos_validos = [
                    (it.text or "").strip()
                    for it in itens
                    if (it.text or "").strip()
                    and "No results" not in (it.text or "")
                    and "Searching" not in (it.text or "")
                    and "Carregando" not in (it.text or "")
                ]
                if textos_validos:
                    break
                human_delay(ctx.fast_mode, 0.08, 0.16 if ctx.fast_mode else 0.5)

            candidato = None
            for item in itens:
                itxt = item.text
                if alvo_norm in _norm_text(itxt):
                    if codigo_alvo and _codigo_final(itxt) == codigo_alvo:
                        candidato = item
                        break
                    if not candidato:
                        candidato = item
            if not candidato:
                for item in itens:
                    itxt = (item.text or "").strip()
                    if not itxt:
                        continue
                    if "No results" in itxt or "Searching" in itxt or "Carregando" in itxt:
                        continue
                    candidato = item
                    break
            if candidato:
                candidato.click()
                ctx.driver.find_element(By.TAG_NAME, "body").click()
                return _verify_select2_selected(ctx, cid, candidato.text)
        except Exception:
            pass
        try:
            ctx.driver.find_element(By.TAG_NAME, "body").click()
        except Exception:
            pass
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
