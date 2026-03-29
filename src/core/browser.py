"""Criação e gerenciamento do navegador (Selenium)."""

import time
from dataclasses import dataclass
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager

from src.config import (
    FAST_MODE,
    MAX_RETRIES,
    RETRY_DELAY,
    MAX_RETRY_DELAY,
    USE_EXPONENTIAL_BACKOFF,
    TIMEOUT_LOG_FILE,
    TIMEOUT_METRICS_FILE,
    FAILED_ITEMS_FILE,
    TIMEOUT_LOGGING_ENABLED,
)


@dataclass
class BrowserContext:
    driver: webdriver.Chrome
    wait: WebDriverWait
    fast_mode: bool = FAST_MODE


def build_browser() -> BrowserContext:
    """Inicializa o Chrome com as opções adequadas ao modo escolhido."""
    from src.core.timeout_log import configure_logger
    
    # Configura o logger global de timeout
    configure_logger(
        log_file=TIMEOUT_LOG_FILE,
        metrics_file=TIMEOUT_METRICS_FILE,
        failed_items_file=FAILED_ITEMS_FILE,
        enabled=TIMEOUT_LOGGING_ENABLED,
    )
    
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.page_load_strategy = "none" if FAST_MODE else "normal"
    
    # Habilitar log de performance para monitoramento de rede via CDP
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    # Otimizado: Reduzido de 25/60 para 10/30 segundos
    wait = WebDriverWait(driver, 10 if FAST_MODE else 30)
    return BrowserContext(driver=driver, wait=wait, fast_mode=FAST_MODE)


def remove_loading_overlay(ctx: BrowserContext, max_attempts: int = 3) -> bool:
    """
    Remove overlay de loading quando presente para evitar bloqueios de clique.
    
    Agora com retry automático caso o script falhe.
    
    Returns:
        True se conseguiu executar, False caso contrário
    """
    for attempt in range(1, max_attempts + 1):
        try:
            ctx.driver.execute_script(
                "const el = document.getElementById('loadingDiv'); if (el) el.remove();"
            )
            return True
        except Exception as e:
            if attempt < max_attempts:
                time.sleep(0.5)
            continue
    return False


def wait_page_ready(ctx: BrowserContext, timeout: int = 30) -> bool:
    """
    Aguarda a página estar pronta (document.readyState == 'complete').
    
    Args:
        ctx: Contexto do browser
        timeout: Tempo máximo de espera em segundos
    
    Returns:
        True se página está pronta, False se timeout
    """
    try:
        WebDriverWait(ctx.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        return True
    except TimeoutException:
        return False


def refresh_page_with_retry(
    ctx: BrowserContext,
    max_attempts: int = MAX_RETRIES,
    base_delay: float = RETRY_DELAY,
) -> bool:
    """
    Recarrega a página com retry em caso de falha.
    
    Args:
        ctx: Contexto do browser
        max_attempts: Número máximo de tentativas
        base_delay: Delay base entre tentativas
    
    Returns:
        True se recarregou com sucesso, False caso contrário
    """
    from src.core.timeout_log import get_logger
    
    logger = get_logger()
    
    for attempt in range(1, max_attempts + 1):
        try:
            ctx.driver.refresh()
            if wait_page_ready(ctx):
                if attempt > 1:
                    logger.log_success_after_retry(
                        operation="refresh_page",
                        attempt=attempt,
                        total_time=attempt * base_delay,
                    )
                return True
        except (TimeoutException, WebDriverException) as e:
            logger.log_timeout(
                operation="refresh_page",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=e,
            )
            
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1)) if USE_EXPONENTIAL_BACKOFF else base_delay
                time.sleep(min(delay, MAX_RETRY_DELAY))
    
    return False


def navigate_with_retry(
    ctx: BrowserContext,
    url: str,
    max_attempts: int = MAX_RETRIES,
    base_delay: float = RETRY_DELAY,
) -> bool:
    """
    Navega para uma URL com retry em caso de timeout.
    
    Args:
        ctx: Contexto do browser
        url: URL de destino
        max_attempts: Número máximo de tentativas
        base_delay: Delay base entre tentativas
    
    Returns:
        True se navegou com sucesso, False caso contrário
    """
    from src.core.timeout_log import get_logger
    
    logger = get_logger()
    
    for attempt in range(1, max_attempts + 1):
        try:
            ctx.driver.get(url)
            # Em FAST_MODE com page_load_strategy="none", não esperamos carregamento completo
            if ctx.fast_mode or wait_page_ready(ctx, timeout=60):
                if attempt > 1:
                    logger.log_success_after_retry(
                        operation="navigate",
                        attempt=attempt,
                        total_time=attempt * base_delay,
                    )
                return True
        except (TimeoutException, WebDriverException) as e:
            logger.log_timeout(
                operation="navigate",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=e,
                context={"url": url},
            )
            
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1)) if USE_EXPONENTIAL_BACKOFF else base_delay
                time.sleep(min(delay, MAX_RETRY_DELAY))
    
    return False


def shutdown_browser(ctx: BrowserContext) -> None:
    """Encerra o navegador e salva métricas de timeout."""
    from src.core.timeout_log import get_logger
    
    # Salva métricas e itens falhados antes de encerrar
    try:
        logger = get_logger()
        logger.save_all()
        logger.print_summary()
    except Exception:
        pass
    
    try:
        ctx.driver.quit()
    except Exception:
        pass
