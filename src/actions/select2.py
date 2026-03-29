"""Ações de interação com Select2 (listas e seleções)."""

import time
from typing import Iterable, List, Optional
import unicodedata
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait

from src.core import BrowserContext, human_delay
from src.config import MAX_RETRIES, RETRY_DELAY


def _get_logger():
    """Importação lazy do logger para evitar imports circulares."""
    from src.core.timeout_log import get_logger
    return get_logger()


def esperar_select2_habilitado(
    ctx: BrowserContext,
    container_id: str,
    timeout: Optional[int] = None,
    check_network: bool = False,
):
    """
    Aguarda um Select2 ficar habilitado (interagível).
    
    ATENÇÃO: Esta função espera APENAS que o elemento esteja presente e não-desabilitado.
    NÃO verifica conteúdo interno ou opções.
    
    Args:
        ctx: Contexto do navegador
        container_id: ID do container Select2
        timeout: Timeout customizado (usa config padrão se None)
        check_network: Se True, monitora erros HTTP e faz retry automático
    
    Returns:
        WebElement do container habilitado
    
    Raises:
        TimeoutException: Se elemento não ficar habilitado dentro do timeout
    """
    from src.core import wait_interactable_only, execute_with_network_check
    
    # Otimizado: Reduzido de 45/60 para 5/10 segundos
    limite = timeout or (5 if ctx.fast_mode else 10)
    driver = ctx.driver

    def _esperar():
        # Verifica se está habilitado (não-disabled)
        element = driver.find_element(By.ID, container_id)
        classe = element.get_attribute("class") or ""
        aria_disabled = (element.get_attribute("aria-disabled") or "").lower()
        
        if "select2-container--disabled" in classe or aria_disabled == "true":
            raise Exception(f"Select2 {container_id} está desabilitado")
        
        # Espera estar clicável
        return wait_interactable_only(driver, (By.ID, container_id), timeout=limite)
    
    if check_network:
        # Com monitoramento de rede
        return execute_with_network_check(
            ctx,
            _esperar,
            operation_name=f"esperar_select2_habilitado({container_id})",
            max_retries=3,
            retry_delay=2.0
        )
    else:
        # Sem monitoramento de rede (comportamento padrão por compatibilidade)
        return _esperar()


def select2_interagivel(ctx: BrowserContext, container_id: str, timeout: Optional[int] = None) -> bool:
    """
    Verifica se um Select2 está pronto para interação (habilitado e clicável).
    
    Use esta função para verificar interatividade ANTES de tentar buscar opções.
    Evita timeouts desnecessários quando o select está bloqueado/desabilitado.
    
    Args:
        ctx: Contexto do navegador
        container_id: ID do container Select2
        timeout: Timeout em segundos (default: 3s fast, 5s normal)
        
    Returns:
        True se interagível, False caso contrário (sem lançar exceção)
    """
    driver = ctx.driver
    limite = timeout or (3 if ctx.fast_mode else 5)
    
    try:
        # Verificar se existe e está habilitado
        el = driver.find_element(By.ID, container_id)
        classe = el.get_attribute("class") or ""
        aria_disabled = (el.get_attribute("aria-disabled") or "").lower()
        
        if "select2-container--disabled" in classe or aria_disabled == "true":
            return False
        
        # Verificar se está clicável
        WebDriverWait(driver, limite, poll_frequency=0.1).until(
            EC.element_to_be_clickable((By.ID, container_id))
        )
        return True
        
    except Exception:
        return False


def select2(ctx: BrowserContext, container_id: str, texto: str, check_network: bool = False) -> None:
    """
    Seleciona opção em Select2 digitando texto e pressionando ENTER.
    
    Args:
        ctx: Contexto do navegador
        container_id: ID do container Select2
        texto: Texto a digitar (não precisa ser match exato)
        check_network: Se True, monitora erros HTTP e faz retry automático
    """
    from src.core import wait_interactable_only, execute_with_network_check
    
    driver = ctx.driver
    
    def _selecionar():
        # 1. Clica para abrir
        container = wait_interactable_only(driver, (By.ID, container_id), timeout=5)
        container.click()

        # 2. Busca campo de pesquisa
        time.sleep(0.1)  # Mínimo para dropdown renderizar
        campo = wait_interactable_only(
            driver, 
            (By.XPATH, "//input[contains(@class,'select2-search__field')]"),
            timeout=3
        )

        # 3. Limpa e digita
        campo.send_keys(Keys.CONTROL + "a")
        campo.send_keys(Keys.BACKSPACE)

        if ctx.fast_mode:
            campo.send_keys(texto)
        else:
            for letra in texto:
                campo.send_keys(letra)
                human_delay(ctx.fast_mode, 0.02, 0.02)

        # 4. Aguarda e pressiona ENTER
        human_delay(ctx.fast_mode, 0.04, 0.08 if ctx.fast_mode else 0.7)
        campo.send_keys(Keys.ENTER)
        
        return True
    
    if check_network:
        # Com monitoramento de rede e retry automático
        return execute_with_network_check(
            ctx,
            _selecionar,
            operation_name=f"select2({container_id}, {texto})",
            max_retries=3,
            retry_delay=2.0
        )
    else:
        # Sem monitoramento de rede (comportamento padrão)
        try:
            return _selecionar()
        except Exception:
            # Tenta fechar dropdown se aberto
            try:
                driver.find_element(By.TAG_NAME, "body").click()
            except:
                pass
            raise


def select2_exact(ctx: BrowserContext, container_id: str, texto: str, check_network: bool = False) -> None:
    """
    Seleciona opção exata em Select2 com busca e scroll automático.
    
    Args:
        ctx: Contexto do navegador
        container_id: ID do container Select2
        texto: Texto exato a ser selecionado
        check_network: Se True, monitora erros HTTP e faz retry automático
    
    Raises:
        Exception: Se não encontrar opção após busca completa
    """
    from src.core import wait_interactable_only, execute_with_network_check
    
    driver = ctx.driver
    
    def _selecionar():
        # 1. Espera select estar interagível
        esperar_select2_habilitado(ctx, container_id, check_network=False)
        
        # 2. Clica para abrir
        container = wait_interactable_only(driver, (By.ID, container_id), timeout=5)
        container.click()

        # 3. Busca campo de pesquisa
        time.sleep(0.1)  # Mínimo para dropdown renderizar
        campo = wait_interactable_only(
            driver, 
            (By.XPATH, "//input[contains(@class,'select2-search__field')]"),
            timeout=3
        )

        # 4. Digita texto
        campo.send_keys(Keys.CONTROL + "a")
        campo.send_keys(Keys.BACKSPACE)
        if ctx.fast_mode:
            campo.send_keys(texto)
        else:
            for letra in texto:
                campo.send_keys(letra)
                human_delay(ctx.fast_mode, 0.04, 0.04)

        human_delay(ctx.fast_mode, 0.04, 0.1 if ctx.fast_mode else 0.6)

        # 5. Busca resultado sem wait longo
        try:
            results = driver.find_element(By.CLASS_NAME, "select2-results__options")
        except Exception:
            raise Exception(f"Dropdown não abriu para {container_id}")

        # 6. Procura match fazendo scroll
        match = None
        last_count = -1
        max_scrolls = 20  # Limite de segurança
        scroll_count = 0
        
        while scroll_count < max_scrolls:
            itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
            for item in itens:
                txt = item.text.strip()
                if txt and txt.upper() == texto.upper():
                    match = item
                    break
            if match:
                break
            if len(itens) == last_count:  # Não há mais itens
                break
            last_count = len(itens)
            
            # Scroll down
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight", results
            )
            human_delay(ctx.fast_mode, 0.03, 0.08 if ctx.fast_mode else 0.5)
            scroll_count += 1

        if not match:
            # Fecha dropdown
            try:
                driver.find_element(By.TAG_NAME, "body").click()
            except:
                pass
            raise Exception(f"Opção '{texto}' não encontrada em {container_id}")

        # 7. Clica no match
        match.click()
        human_delay(ctx.fast_mode, 0.2, 0.5 if ctx.fast_mode else 0.8)
        
        return True
    
    if check_network:
        # Com monitoramento de rede e retry automático
        return execute_with_network_check(
            ctx,
            _selecionar,
            operation_name=f"select2_exact({container_id}, {texto})",
            max_retries=3,
            retry_delay=2.0
        )
    else:
        # Sem monitoramento de rede (comportamento padrão)
        return _selecionar()


def curso_existe(ctx: BrowserContext, nome_curso: str) -> bool:
    """
    Verifica se um curso existe no select de cursos.
    
    REGRAS:
    ✅ Timeout APENAS para verificar interatividade do select (clicável)
    ❌ ZERO waits para buscar opções internas
    ✅ Ausência de opção = retorna False (fluxo normal, sem exceção)
    
    Args:
        ctx: Contexto do navegador
        nome_curso: Nome do curso a buscar (ex: "MEDICINA")
        
    Returns:
        True se o curso existe, False caso contrário
    """
    driver = ctx.driver
    container_id = "select2-noCursosPublico-container"
    
    # ═══════════════════════════════════════════════════════════════════════
    # FASE 1: ESPERA - Verificar se o select está INTERAGÍVEL
    # ═══════════════════════════════════════════════════════════════════════
    # ÚNICO local onde usamos timeout/wait
    esperar_select2_habilitado(ctx, container_id, timeout=5)
    
    # Verificar se está clicável
    container = WebDriverWait(driver, 3 if ctx.fast_mode else 5).until(
        EC.element_to_be_clickable((By.ID, container_id))
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # FASE 2: SEM ESPERA - Abrir dropdown e verificar opções instantaneamente
    # ═══════════════════════════════════════════════════════════════════════
    try:
        # Abrir o dropdown
        container.click()
        
        # Pequena pausa para o dropdown renderizar (NÃO é wait, é sleep fixo mínimo)
        time.sleep(0.15)
        
        # Buscar campo de busca IMEDIATAMENTE (sem wait)
        try:
            campo = driver.find_element(
                By.XPATH, "//input[contains(@class,'select2-search__field')]"
            )
        except Exception:
            # Se não encontrou campo de busca, tentar fechar e retornar False
            try:
                driver.find_element(By.TAG_NAME, "body").click()
            except:
                pass
            return False
        
        # Digitar nome do curso para filtrar
        campo.send_keys(nome_curso)
        
        # Pequena pausa para o filtro processar (NÃO é wait, é sleep fixo mínimo)
        time.sleep(0.15)
        
        # Buscar opções IMEDIATAMENTE (sem wait)
        opcoes = driver.find_elements(By.CLASS_NAME, "select2-results__option")
        
        # Verificar se alguma opção contém o curso buscado
        existe = any(nome_curso.upper() in o.text.upper() for o in opcoes if o.text.strip())
        
        # Fechar dropdown
        driver.find_element(By.TAG_NAME, "body").click()
        
        return existe
        
    except Exception:
        # Qualquer erro na busca = assumir que não existe (sem propagar exceção)
        try:
            driver.find_element(By.TAG_NAME, "body").click()
        except:
            pass
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
        # Otimizado: Reduzido de 0.8s para 0.05-0.1s
        human_delay(ctx.fast_mode, 0.05, 0.1)

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
