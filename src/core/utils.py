"""Funções utilitárias compartilhadas."""

import random
import time
from typing import Optional, Callable, Any, Tuple
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement


def human_delay(fast_mode: bool, a: Optional[float] = None, b: Optional[float] = None) -> None:
    """Simula digitação/click humano com pequenas variações."""
    # Em modo rápido, eliminamos quase todo o delay para máxima performance
    if a is None or b is None:
        a, b = (0.01, 0.02) if fast_mode else (1.5, 3.5)

    fator = 0.05 if fast_mode else 1.0  # Reduzido de 0.25 para 0.05
    time.sleep(random.uniform(a * fator, b * fator))


def normalizar_decimal_pt(texto: Optional[str]) -> Optional[str]:
    """Converte separadores PT-BR para formato de ponto, quando aplicável."""
    if not texto:
        return None
    try:
        return texto.replace(".", "").replace(",", ".")
    except Exception:
        return texto


def wait_interactable_only(driver, locator: Tuple, timeout: int = 10) -> WebElement:
    """
    Espera APENAS que o elemento esteja presente e interagível (clicável).
    
    NÃO verifica conteúdo interno, opções, ou qualquer dado dentro do elemento.
    Use esta função quando você só precisa garantir que o elemento está pronto
    para interação (click, send_keys, etc).
    
    Args:
        driver: WebDriver instance
        locator: Tupla (By.ID, "element-id") ou similar
        timeout: Tempo máximo de espera (padrão: 10s)
    
    Returns:
        WebElement quando estiver clicável
    
    Raises:
        TimeoutException: Se elemento não ficar clicável dentro do timeout
    
    Exemplo:
        select = wait_interactable_only(driver, (By.ID, "select2-noEstado-container"))
        select.click()  # Garantido estar clicável
    """
    element = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable(locator)
    )
    return element


def execute_with_network_check(
    ctx,
    operation: Callable[[], Any],
    operation_name: str = "operacao",
    max_retries: int = 3,
    retry_delay: float = 2.0,
    check_network: bool = True
) -> Any:
    """
    Executa uma operação monitorando requisições HTTP.
    
    Faz retry APENAS se houver erro HTTP (502, 503, 504, 5xx).
    NÃO faz retry por timeouts de UI ou elementos ausentes.
    
    Args:
        ctx: BrowserContext com driver e logger
        operation: Função a executar (sem argumentos)
        operation_name: Nome da operação para logs
        max_retries: Número máximo de tentativas
        retry_delay: Delay base entre tentativas (aumenta exponencialmente)
        check_network: Se True, verifica erros HTTP e faz retry
    
    Returns:
        Resultado da operação
    
    Raises:
        Exception: Se operação falhar após todas as tentativas
    
    Exemplo:
        def minha_operacao():
            select = driver.find_element(By.ID, "select")
            select.click()
            return True
        
        resultado = execute_with_network_check(
            ctx, 
            minha_operacao,
            operation_name="selecionar_estado",
            max_retries=3
        )
    """
    from src.core.network_monitor import NetworkMonitor
    from src.core.timeout_log import get_logger
    
    logger = get_logger()
    driver = ctx.driver
    
    for attempt in range(1, max_retries + 1):
        monitor = None
        
        try:
            # Inicia monitoramento de rede se habilitado
            if check_network:
                monitor = NetworkMonitor(driver)
                monitor.start()
            
            # Executa a operação
            result = operation()
            
            # Verifica se houve erros HTTP
            if check_network and monitor:
                time.sleep(0.2)  # Aguarda requisições finalizarem
                
                if monitor.has_gateway_error():
                    errors = monitor.get_errors()
                    error_details = [f"{e.method} {e.url} -> {e.status}" for e in errors[:3]]
                    
                    logger.log_timeout(
                        operation=operation_name,
                        attempt=attempt,
                        max_attempts=max_retries,
                        exception=Exception(f"Gateway error: {error_details}")
                    )
                    
                    if attempt < max_retries:
                        delay = retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                        print(f"⚠️ Erro HTTP detectado - tentativa {attempt}/{max_retries}. Aguardando {delay:.1f}s...")
                        time.sleep(delay)
                        continue
                    else:
                        raise Exception(f"Erro HTTP após {max_retries} tentativas: {error_details}")
            
            # Sucesso
            if attempt > 1:
                logger.log_success_after_retry(
                    operation=operation_name,
                    attempt=attempt,
                    total_time=sum(retry_delay * (2 ** i) for i in range(attempt - 1))
                )
            
            return result
            
        except Exception as e:
            # Se não tem network check OU não é erro HTTP, propaga exceção
            if not check_network or attempt >= max_retries:
                logger.log_timeout(
                    operation=operation_name,
                    attempt=attempt,
                    max_attempts=max_retries,
                    exception=e
                )
                raise
            
            # Retry apenas se habilitado
            delay = retry_delay * (2 ** (attempt - 1))
            print(f"⚠️ Erro na operação - tentativa {attempt}/{max_retries}. Aguardando {delay:.1f}s...")
            time.sleep(delay)
        
        finally:
            if monitor:
                monitor.stop()
    
    raise Exception(f"Operação {operation_name} falhou após {max_retries} tentativas")
