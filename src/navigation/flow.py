"""Navegação, recarga e reaplicação de filtros na página principal."""

import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException

from src.core import BrowserContext, human_delay, remove_loading_overlay
from src.core.timeout_log import get_logger
from src.config import (
    BASE_URL, MAX_RETRIES, RETRY_DELAY, USE_EXPONENTIAL_BACKOFF, MAX_RETRY_DELAY, 
    FIES_MODALIDADE, ENABLE_INTELLIGENT_STATE_CHANGE, STATE_CHANGE_TIMEOUT, 
    FALLBACK_TO_DIRECT_SELECT
)
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
            
            # Verificação rápida sem timeout longo - elemento já deve estar pronto
            try:
                driver.find_element(By.ID, "select2-noEstado-container")
            except Exception:
                pass  # Continua mesmo se não encontrar
            
            if attempt > 1:
                logger.log_success_after_retry(
                    operation="preparar_primeira_pagina",
                    attempt=attempt,
                    total_time=attempt * RETRY_DELAY,
                )
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
            
            # Verificação rápida sem timeout - elemento pode ou não estar presente
            time.sleep(0.3)  # Pausa mínima para página carregar
            
            print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
            input()
            remove_loading_overlay(ctx)
            
            # Verificação rápida sem timeout
            time.sleep(0.2)
            
            if attempt > 1:
                logger.log_success_after_retry(
                    operation="abrir_nova_consulta",
                    attempt=attempt,
                    total_time=attempt * RETRY_DELAY,
                )
            return True
            
        except StaleElementReferenceException as e:
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

    # Selecionar Estado (com network check)
    try:
        select2(ctx, "select2-noEstado-container", estado, check_network=True)
    except Exception as e:
        print(f"⚠️ Erro ao selecionar estado {estado}: {e}")
        return False

    if municipio:
        # Selecionar Município (com network check)
        try:
            select2(ctx, "select2-noMunicipio-container", municipio, check_network=True)
        except Exception as e:
            print(f"⚠️ Erro ao selecionar município {municipio}: {e}")
            return False
        
        if curso:
            # Selecionar Curso (com network check)
            try:
                esperar_select2_habilitado(ctx, "select2-noCursosPublico-container", check_network=True)
                select2_exact(ctx, "select2-noCursosPublico-container", curso, check_network=True)
            except Exception as e:
                print(f"⚠️ Erro ao selecionar curso {curso}: {e}")
                return False
    
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


def nova_consulta_disponivel(ctx: BrowserContext, timeout: Optional[float] = None) -> bool:
    """
    Verifica se o botão "Nova Consulta" está disponível na página.
    
    Usa um timeout curto para evitar esperas longas quando o botão não existe.
    
    Args:
        ctx: Contexto do browser
        timeout: Tempo máximo de espera (usa STATE_CHANGE_TIMEOUT se não especificado)
    
    Returns:
        True se o botão está disponível e clicável, False caso contrário
    """
    driver = ctx.driver
    timeout_efetivo = timeout if timeout is not None else STATE_CHANGE_TIMEOUT
    
    WebDriverWait(driver, timeout_efetivo).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/consulta']"))
    )
    return True


def preparar_para_mudanca_estado(
    ctx: BrowserContext,
    pesquisa_foi_executada: bool,
    max_attempts: int = MAX_RETRIES,
) -> bool:
    """
    Prepara a página para mudança de estado de forma inteligente.
    
    Decide automaticamente qual estratégia usar:
    - Se pesquisa foi executada E botão "Nova Consulta" existe: usa "Nova Consulta"
    - Se não houve pesquisa OU botão não existe: prepara para mudança direta no select
    
    Args:
        ctx: Contexto do browser
        pesquisa_foi_executada: Flag indicando se uma pesquisa foi feita
        max_attempts: Número máximo de tentativas para operações
    
    Returns:
        True se a página está pronta para mudança de estado, False caso contrário
    """
    logger = get_logger()
    
    if not ENABLE_INTELLIGENT_STATE_CHANGE:
        # Comportamento legado: sempre tenta "Nova Consulta"
        if pesquisa_foi_executada:
            return abrir_nova_consulta(ctx, max_attempts)
        return True
    
    # Fluxo inteligente
    if pesquisa_foi_executada:
        # Verificar se "Nova Consulta" está disponível
        if nova_consulta_disponivel(ctx):
            print("🔄 Usando 'Nova Consulta' para preparar mudança de estado...")
            return abrir_nova_consulta(ctx, max_attempts)
        else:
            # Pesquisa foi executada mas botão não existe (cenário inesperado)
            print("⚠️ Botão 'Nova Consulta' não encontrado após pesquisa - preparando para mudança direta")
            if FALLBACK_TO_DIRECT_SELECT:
                return _preparar_mudanca_direta(ctx)
            return False
    else:
        # Sem pesquisa prévia: mudança direta é o caminho correto
        print("➡️ Sem pesquisa prévia - mudança de estado será feita diretamente no select")
        return _preparar_mudanca_direta(ctx)


def _preparar_mudanca_direta(ctx: BrowserContext) -> bool:
    """
    Prepara a página para mudança direta no select (sem "Nova Consulta").
    
    Garante que overlays de loading estejam removidos e que o select
    de estado esteja acessível.
    
    Returns:
        True se pronto para mudança direta, False caso contrário
    """
    try:
        remove_loading_overlay(ctx)
        
        # Verificação rápida sem timeout longo
        try:
            ctx.driver.find_element(By.ID, "select2-noEstado-container")
            return True
        except Exception:
            # Select não encontrado, tentar refresh como último recurso
            print("⚠️ Select de estado não encontrado - tentando refresh...")
            return reiniciar_navegacao(ctx)
    except Exception as e:
        print(f"⚠️ Erro ao preparar mudança direta: {e}")
        return False


def trocar_estado_inteligente(
    ctx: BrowserContext,
    novo_estado: str,
    pesquisa_foi_executada: bool,
    modalidade: Optional[str] = None,
    max_attempts: int = MAX_RETRIES,
) -> bool:
    """
    Função principal para mudança de estado inteligente.
    
    Gerencia todo o fluxo de mudança de estado:
    1. Prepara a página (com ou sem "Nova Consulta" baseado no contexto)
    2. Aplica o novo estado
    
    Args:
        ctx: Contexto do browser
        novo_estado: Nome do novo estado (UF)
        pesquisa_foi_executada: Flag indicando se uma pesquisa foi feita no estado anterior
        modalidade: Modalidade FIES (opcional, usa padrão se não especificada)
        max_attempts: Número máximo de tentativas
    
    Returns:
        True se a mudança foi bem sucedida, False caso contrário
    """
    logger = get_logger()
    
    # Passo 1: Preparar página para mudança
    if not preparar_para_mudanca_estado(ctx, pesquisa_foi_executada, max_attempts):
        # Tentar estratégia de fallback: refresh e começar do zero
        print("🔄 Tentando recuperação via refresh...")
        if reiniciar_navegacao(ctx):
            print("✅ Navegação reiniciada com sucesso")
        else:
            print("❌ Não foi possível preparar para mudança de estado")
            return False
    
    # Passo 2: Aplicar novo estado
    return aplicar_filtros(ctx, estado=novo_estado, modalidade=modalidade, max_attempts=max_attempts)
