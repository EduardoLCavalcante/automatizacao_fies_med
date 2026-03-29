"""Sistema de retry robusto para operações Selenium com tratamento de timeout."""

import functools
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple, Type

from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    NoSuchElementException,
    WebDriverException,
)

from src.core.timeout_log import TimeoutLogger, get_logger


# Exceções que devem disparar retry
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    NoSuchElementException,
)


@dataclass
class RetryConfig:
    """Configuração de retry para operações."""
    max_attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0
    exponential_backoff: bool = True
    retryable_exceptions: Tuple[Type[Exception], ...] = RETRYABLE_EXCEPTIONS
    on_retry_callback: Optional[Callable[["RetryContext"], None]] = None


@dataclass
class RetryContext:
    """Contexto passado para callbacks de retry."""
    operation: str
    attempt: int
    max_attempts: int
    exception: Exception
    elapsed_time: float
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetryResult:
    """Resultado de uma operação com retry."""
    success: bool
    value: Any = None
    attempts: int = 0
    total_time: float = 0.0
    last_exception: Optional[Exception] = None


def calculate_delay(attempt: int, base_delay: float, max_delay: float, exponential: bool) -> float:
    """Calcula o delay para a próxima tentativa."""
    if exponential:
        delay = base_delay * (2 ** (attempt - 1))
    else:
        delay = base_delay
    return min(delay, max_delay)


def retry_on_timeout(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    exponential_backoff: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = RETRYABLE_EXCEPTIONS,
    operation_name: Optional[str] = None,
    on_retry: Optional[Callable[[RetryContext], None]] = None,
    logger: Optional[TimeoutLogger] = None,
):
    """
    Decorator que adiciona retry automático a funções que podem sofrer timeout.
    
    Args:
        max_attempts: Número máximo de tentativas (default: 3)
        base_delay: Delay base entre tentativas em segundos (default: 2.0)
        max_delay: Delay máximo entre tentativas (default: 30.0)
        exponential_backoff: Se True, usa backoff exponencial (default: True)
        retryable_exceptions: Tuple de exceções que disparam retry
        operation_name: Nome da operação para logging (default: nome da função)
        on_retry: Callback executado antes de cada retry
        logger: Logger customizado (default: logger global)
    
    Example:
        @retry_on_timeout(max_attempts=3, base_delay=2)
        def click_element(ctx, element_id):
            # código que pode falhar com timeout
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal logger
            if logger is None:
                logger = get_logger()
            
            op_name = operation_name or func.__name__
            start_time = time.time()
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    
                    # Log sucesso após retry
                    if attempt > 1 and logger:
                        logger.log_success_after_retry(
                            operation=op_name,
                            attempt=attempt,
                            total_time=time.time() - start_time,
                        )
                    
                    return result
                    
                except retryable_exceptions as e:
                    last_exception = e
                    elapsed = time.time() - start_time
                    
                    # Log da tentativa falha
                    if logger:
                        logger.log_timeout(
                            operation=op_name,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            exception=e,
                            context=kwargs.get("_retry_context", {}),
                        )
                    
                    # Se foi a última tentativa, re-raise
                    if attempt >= max_attempts:
                        if logger:
                            logger.log_final_failure(
                                operation=op_name,
                                total_attempts=attempt,
                                total_time=elapsed,
                                exception=e,
                            )
                        raise
                    
                    # Callback antes do retry
                    if on_retry:
                        ctx = RetryContext(
                            operation=op_name,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            exception=e,
                            elapsed_time=elapsed,
                            extra=kwargs.get("_retry_context", {}),
                        )
                        on_retry(ctx)
                    
                    # Aguarda antes da próxima tentativa
                    delay = calculate_delay(attempt, base_delay, max_delay, exponential_backoff)
                    time.sleep(delay)
            
            # Não deveria chegar aqui, mas por segurança
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


def with_retry(
    func: Callable,
    config: RetryConfig,
    operation_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    logger: Optional[TimeoutLogger] = None,
) -> RetryResult:
    """
    Executa uma função com retry usando configuração explícita.
    
    Alternativa ao decorator para quando precisamos de mais controle.
    
    Args:
        func: Função a executar (callable sem argumentos ou lambda)
        config: Configuração de retry
        operation_name: Nome da operação para logging
        context: Contexto adicional para logging
        logger: Logger customizado
    
    Returns:
        RetryResult com resultado da operação
    
    Example:
        result = with_retry(
            lambda: driver.find_element(By.ID, "btn"),
            config=RetryConfig(max_attempts=5),
            operation_name="find_button",
            context={"state": "SP", "city": "São Paulo"},
        )
        if result.success:
            element = result.value
    """
    if logger is None:
        logger = get_logger()
    
    op_name = operation_name or getattr(func, "__name__", "anonymous")
    start_time = time.time()
    last_exception: Optional[Exception] = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            value = func()
            total_time = time.time() - start_time
            
            if attempt > 1 and logger:
                logger.log_success_after_retry(
                    operation=op_name,
                    attempt=attempt,
                    total_time=total_time,
                )
            
            return RetryResult(
                success=True,
                value=value,
                attempts=attempt,
                total_time=total_time,
            )
            
        except config.retryable_exceptions as e:
            last_exception = e
            elapsed = time.time() - start_time
            
            if logger:
                logger.log_timeout(
                    operation=op_name,
                    attempt=attempt,
                    max_attempts=config.max_attempts,
                    exception=e,
                    context=context or {},
                )
            
            if attempt >= config.max_attempts:
                if logger:
                    logger.log_final_failure(
                        operation=op_name,
                        total_attempts=attempt,
                        total_time=elapsed,
                        exception=e,
                    )
                break
            
            if config.on_retry_callback:
                ctx = RetryContext(
                    operation=op_name,
                    attempt=attempt,
                    max_attempts=config.max_attempts,
                    exception=e,
                    elapsed_time=elapsed,
                    extra=context or {},
                )
                config.on_retry_callback(ctx)
            
            delay = calculate_delay(
                attempt,
                config.base_delay,
                config.max_delay,
                config.exponential_backoff,
            )
            time.sleep(delay)
    
    return RetryResult(
        success=False,
        attempts=config.max_attempts,
        total_time=time.time() - start_time,
        last_exception=last_exception,
    )


class RetryableOperation:
    """
    Context manager para operações com retry e recuperação automática.
    
    Example:
        with RetryableOperation(ctx, "select_state", max_attempts=3) as op:
            op.execute(lambda: select2(ctx, "estado", "SP"))
            if not op.success:
                # fallback
                pass
    """
    
    def __init__(
        self,
        browser_ctx: Any,
        operation_name: str,
        max_attempts: int = 3,
        base_delay: float = 2.0,
        recovery_callback: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.browser_ctx = browser_ctx
        self.operation_name = operation_name
        self.config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            on_retry_callback=self._on_retry if recovery_callback else None,
        )
        self.recovery_callback = recovery_callback
        self.context = context or {}
        self.result: Optional[RetryResult] = None
        self.logger = get_logger()
    
    def _on_retry(self, ctx: RetryContext) -> None:
        """Callback interno que chama recovery se definido."""
        if self.recovery_callback:
            try:
                self.recovery_callback(self.browser_ctx, ctx)
            except Exception:
                pass  # Ignora erros no recovery
    
    def __enter__(self) -> "RetryableOperation":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False  # Não suprime exceções
    
    def execute(self, func: Callable) -> RetryResult:
        """Executa a função com retry."""
        self.result = with_retry(
            func,
            config=self.config,
            operation_name=self.operation_name,
            context=self.context,
            logger=self.logger,
        )
        return self.result
    
    @property
    def success(self) -> bool:
        return self.result.success if self.result else False
    
    @property
    def value(self) -> Any:
        return self.result.value if self.result else None
