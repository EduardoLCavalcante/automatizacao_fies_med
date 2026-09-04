"""Operações sobre a tabela de resultados."""

import time
from typing import List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from src.core import (
    BrowserContext,
    PortalRequestTimeout,
    emitir_aviso_tracker_indisponivel,
    human_delay,
    propagar_timeout,
)


_RESULT_ROWS_XPATH = "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr"


def _assinatura_tabela(driver) -> tuple[str, ...]:
    """Assinatura textual para detectar atualização mesmo com a mesma contagem."""

    linhas = driver.find_elements(By.XPATH, _RESULT_ROWS_XPATH)
    return tuple((linha.text or "").strip() for linha in linhas)


def _categoria_ativa(botao) -> bool:
    try:
        classe = (botao.get_attribute("class") or "").lower()
        aria = (botao.get_attribute("aria-pressed") or "").lower()
        estado = (botao.get_attribute("data-active") or "").lower()
        return (
            aria == "true"
            or estado in {"true", "1", "active", "selected"}
            or any(token in classe.split() for token in ("active", "selected"))
        )
    except Exception as exc:
        propagar_timeout(exc)
        return False


def expandir_todos_candidatos(ctx: BrowserContext) -> None:
    driver, wait = ctx.driver, ctx.wait
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
            )
        )
    except TimeoutException:
        raise

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
                except Exception as exc:
                    propagar_timeout(exc)
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
        except Exception as exc:
            propagar_timeout(exc)
            pass
        clicked = False
        try:
            ver_mais_el.click()
            clicked = True
        except Exception as exc:
            propagar_timeout(exc)
            try:
                driver.execute_script("arguments[0].click();", ver_mais_el)
                clicked = True
            except Exception as fallback_exc:
                propagar_timeout(fallback_exc)
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
                except Exception as exc:
                    propagar_timeout(exc)
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
        raise

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
    except Exception as exc:
        propagar_timeout(exc)
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
        raise

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
        assinatura_antes = _assinatura_tabela(driver)
    except Exception as exc:
        propagar_timeout(exc)
        assinatura_antes = ()

    btn = None
    ultimo_timeout = None
    for by, sel in alvos:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel)))
            if el and el.is_displayed():
                btn = el
                break
        except TimeoutException as exc:
            ultimo_timeout = exc
            continue

    if not btn:
        if ultimo_timeout is not None:
            raise ultimo_timeout
        return False

    # Alguns portais deixam a categoria inicial marcada. Clicar de novo nesse
    # botão não produz uma nova resposta e fazia o código confundir uma tabela
    # válida com timeout.
    if _categoria_ativa(btn):
        return True

    tracker = getattr(ctx, "network", None)
    operacao_rede = tracker.begin(driver) if tracker is not None else None

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    except Exception as exc:
        propagar_timeout(exc)
        pass
    try:
        btn.click()
    except Exception as exc:
        propagar_timeout(exc)
        try:
            driver.execute_script("arguments[0].click();", btn)
        except Exception as fallback_exc:
            propagar_timeout(fallback_exc)
            return False

    ultimo_snapshot = None

    def tabela_atualizada(_driver) -> bool:
        nonlocal ultimo_snapshot
        if tracker is not None and operacao_rede is not None:
            ultimo_snapshot = tracker.snapshot(driver, operacao_rede)
            if ultimo_snapshot.has_busy:
                raise PortalRequestTimeout(
                    f"requisição da categoria falhou: {ultimo_snapshot.description}"
                )
            # Não considerar o DOM pronto enquanto a requisição ainda está em
            # andamento: uma resposta antiga pode continuar visível.
            if ultimo_snapshot.pending:
                return False

        assinatura_atual = _assinatura_tabela(driver)
        if _categoria_ativa(btn):
            return True
        return bool(assinatura_atual) and assinatura_atual != assinatura_antes

    try:
        WebDriverWait(driver, 8).until(tabela_atualizada)
        return True
    except PortalRequestTimeout:
        raise
    except TimeoutException:
        if tracker is not None and operacao_rede is not None:
            ultimo_snapshot = tracker.snapshot(driver, operacao_rede)
            if ultimo_snapshot.has_busy:
                raise PortalRequestTimeout(
                    f"requisição da categoria falhou: {ultimo_snapshot.description}"
                )
            if ultimo_snapshot.pending:
                raise PortalRequestTimeout(
                    f"requisição da categoria não terminou: {ultimo_snapshot.description}"
                )
            if not ultimo_snapshot.available:
                emitir_aviso_tracker_indisponivel(ctx)
            # HTTP 2xx sem atualização do resultado é uma falha local de
            # validação; o chamador pode tentar novamente sem iniciar pausa de
            # servidor. O mesmo vale para ausência de categoria ativa quando
            # há uma tabela antiga, já que não houve erro de rede confirmado.
            if ultimo_snapshot.has_success and _assinatura_tabela(driver):
                return False

        # Sem rede e sem tabela não há pós-condição válida para a operação;
        # propaga o timeout para o controlador central.
        if not _assinatura_tabela(driver):
            raise
        return False
