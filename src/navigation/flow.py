"""Navegação, recarga e reaplicação de filtros na página principal."""

import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

from src.core import BrowserContext, human_delay, remove_loading_overlay
from src.core.timeout_log import get_logger
from src.config import BASE_URL, MAX_RETRIES, RETRY_DELAY, USE_EXPONENTIAL_BACKOFF, MAX_RETRY_DELAY, FIES_MODALIDADE
from src.actions import (
    select2,
    select2_exact,
    esperar_select2_habilitado,
    selecionar_radio_fies,
)


def _calculate_delay(attempt: int, base_delay: float) -> float:
    """Calcula delay para próxima tentativa."""
    if USE_EXPONENTIAL_BACKOFF:
        delay = base_delay * (2 ** (attempt - 1))
    else:
        delay = base_delay
    return min(delay, MAX_RETRY_DELAY)


def preparar_primeira_pagina(ctx: BrowserContext, max_attempts: int = MAX_RETRIES) -> bool:
    """
    Carrega a página inicial com retry.
    
    Returns:
        True se carregou com sucesso, False caso contrário
    """
    from src.core.browser import navigate_with_retry
    
    driver, wait = ctx.driver, ctx.wait
    logger = get_logger()
    
    for attempt in range(1, max_attempts + 1):
        try:
            if not navigate_with_retry(ctx, BASE_URL):
                if attempt < max_attempts:
                    time.sleep(_calculate_delay(attempt, RETRY_DELAY))
                    continue
                return False
            
            remove_loading_overlay(ctx)
            print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
            input()
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
                if attempt > 1:
                    logger.log_success_after_retry(
                        operation="preparar_primeira_pagina",
                        attempt=attempt,
                        total_time=attempt * RETRY_DELAY,
                    )
                return True
            except TimeoutException:
                # Página carregou mas elemento não apareceu, ainda pode funcionar
                return True
                
        except Exception as e:
            logger.log_timeout(
                operation="preparar_primeira_pagina",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=e,
            )
            
            if attempt < max_attempts:
                time.sleep(_calculate_delay(attempt, RETRY_DELAY))
    
    return False


def abrir_nova_consulta(ctx: BrowserContext, max_attempts: int = MAX_RETRIES) -> bool:
    """
    Clica em "Nova Consulta" e aguarda a página principal (CAPTCHA incluído).
    
    Agora com retry automático em caso de timeout.
    """
    driver, wait = ctx.driver, ctx.wait
    logger = get_logger()
    
    for attempt in range(1, max_attempts + 1):
        try:
            link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='/consulta']")))
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
            except Exception:
                pass
            link.click()
            
            remove_loading_overlay(ctx)
            try:
                wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
            except TimeoutException:
                pass

            print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
            input()
            remove_loading_overlay(ctx)
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
            except TimeoutException:
                pass
            
            if attempt > 1:
                logger.log_success_after_retry(
                    operation="abrir_nova_consulta",
                    attempt=attempt,
                    total_time=attempt * RETRY_DELAY,
                )
            return True
            
        except (TimeoutException, StaleElementReferenceException) as e:
            logger.log_timeout(
                operation="abrir_nova_consulta",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=e,
            )
            
            if attempt < max_attempts:
                # Tenta refresh antes de retry
                try:
                    driver.refresh()
                    time.sleep(_calculate_delay(attempt, RETRY_DELAY))
                except Exception:
                    pass
    
    return False


def aplicar_filtros(
    ctx: BrowserContext,
    estado: str,
    municipio: Optional[str] = None,
    curso: Optional[str] = "MEDICINA",
    modalidade: Optional[str] = None,
    max_attempts: int = MAX_RETRIES,
) -> bool:
    """
    Aplica estado e, opcionalmente, município e curso na página principal.
    
    Args:
        ctx: Contexto do browser
        estado: UF do estado
        municipio: Nome do município (opcional)
        curso: Nome do curso (default: MEDICINA)
        modalidade: Modalidade FIES ("social" ou "regular"). Se None, usa FIES_MODALIDADE do settings.
        max_attempts: Número máximo de tentativas por filtro
    
    Cada filtro é aplicado com retry individual.
    """
    logger = get_logger()
    
    # Usar modalidade passada ou pegar do settings
    modalidade_efetiva = modalidade or str(FIES_MODALIDADE.value)
    
    logger.set_context(estado=estado, municipio=municipio, curso=curso, modalidade_fies=modalidade_efetiva)
    
    remove_loading_overlay(ctx)
    
    # Selecionar rádio FIES com a modalidade especificada
    if not selecionar_radio_fies(ctx, modalidade_efetiva):
        print(f"⚠️ Não foi possível selecionar modalidade FIES: {modalidade_efetiva}")
        return False
    
    human_delay(ctx.fast_mode, 0.1, 0.3)

    # Selecionar Estado com retry
    for attempt in range(1, max_attempts + 1):
        try:
            select2(ctx, "select2-noEstado-container", estado)
            human_delay(ctx.fast_mode, 0.2, 0.5)
            if attempt > 1:
                logger.log_success_after_retry(
                    operation="aplicar_filtros_estado",
                    attempt=attempt,
                    total_time=attempt * RETRY_DELAY,
                )
            break
        except Exception as e:
            logger.log_timeout(
                operation="aplicar_filtros_estado",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=e,
                context={"estado": estado},
            )
            if attempt >= max_attempts:
                return False
            time.sleep(_calculate_delay(attempt, RETRY_DELAY))

    if municipio:
        # Selecionar Município com retry
        for attempt in range(1, max_attempts + 1):
            try:
                select2(ctx, "select2-noMunicipio-container", municipio)
                human_delay(ctx.fast_mode, 0.2, 0.5)
                if attempt > 1:
                    logger.log_success_after_retry(
                        operation="aplicar_filtros_municipio",
                        attempt=attempt,
                        total_time=attempt * RETRY_DELAY,
                    )
                break
            except Exception as e:
                logger.log_timeout(
                    operation="aplicar_filtros_municipio",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    exception=e,
                    context={"estado": estado, "municipio": municipio},
                )
                if attempt >= max_attempts:
                    return False
                time.sleep(_calculate_delay(attempt, RETRY_DELAY))
        
        if curso:
            # Selecionar Curso com retry
            for attempt in range(1, max_attempts + 1):
                try:
                    esperar_select2_habilitado(ctx, "select2-noCursosPublico-container")
                    select2_exact(ctx, "select2-noCursosPublico-container", curso)
                    human_delay(ctx.fast_mode, 0.2, 0.5)
                    if attempt > 1:
                        logger.log_success_after_retry(
                            operation="aplicar_filtros_curso",
                            attempt=attempt,
                            total_time=attempt * RETRY_DELAY,
                        )
                    break
                except TimeoutException as e:
                    logger.log_timeout(
                        operation="aplicar_filtros_curso",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        exception=e,
                        context={"estado": estado, "municipio": municipio, "curso": curso},
                    )
                    if attempt >= max_attempts:
                        print(f"⚠️ Não foi possível selecionar {curso} após {max_attempts} tentativas")
                        return False
                    time.sleep(_calculate_delay(attempt, RETRY_DELAY))
    
    return True


def reiniciar_navegacao(ctx: BrowserContext) -> bool:
    """
    Estratégia de recuperação: reinicia navegação completa.
    
    Útil quando há muitos timeouts consecutivos.
    """
    from src.core.browser import navigate_with_retry
    
    logger = get_logger()
    print("🔄 Reiniciando navegação...")
    
    if navigate_with_retry(ctx, BASE_URL):
        remove_loading_overlay(ctx)
        print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
        input()
        return True
    
    return False
