"""Seleção de rádios relacionados ao FIES (Social e Regular)."""

import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.core import BrowserContext, human_delay
from src.config import MAX_RETRIES, RETRY_DELAY


# Mapeamento de modalidades para IDs e textos
FIES_RADIO_CONFIG = {
    "social": {
        "id": "stCadunicoS",
        "value": "S",
        "label_text": "Fies Social",
    },
    "regular": {
        "id": "stCadunicoN",
        "value": "N",
        "label_text": "Fies",
    },
}


def _get_logger():
    """Importação lazy do logger."""
    from src.core.timeout_log import get_logger
    return get_logger()


def selecionar_radio_por_texto(ctx: BrowserContext, texto: str) -> bool:
    """Seleciona rádio por texto da label."""
    driver, wait = ctx.driver, ctx.wait
    alvo = texto.strip()

    radios = driver.find_elements(By.XPATH, "//input[@type='radio']")
    for r in radios:
        lbl = None
        try:
            lbl = r.find_element(By.XPATH, "following-sibling::label")
        except Exception:
            pass
        if not lbl:
            try:
                lbl = r.find_element(By.XPATH, "ancestor::label")
            except Exception:
                pass

        if lbl:
            txt = lbl.text.strip()
            if txt and alvo.upper() in txt.upper():
                try:
                    driver.execute_script("arguments[0].click()", lbl)
                except Exception:
                    lbl.click()
                try:
                    wait.until(lambda d: r.is_selected())
                except TimeoutException:
                    pass
                human_delay(ctx.fast_mode, 0.2, 0.6)
                return True

    labels = driver.find_elements(By.XPATH, "//label")
    for lbl in labels:
        txt = lbl.text.strip()
        if txt and alvo.upper() in txt.upper():
            try:
                driver.execute_script("arguments[0].click()", lbl)
            except Exception:
                lbl.click()
            human_delay(ctx.fast_mode, 0.2, 0.6)
            return True

    try:
        radio = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//input[@type='radio' and following-sibling::label[contains(normalize-space(.), '{alvo}')]]")
            )
        )
        driver.execute_script("arguments[0].click()", radio)
        human_delay(ctx.fast_mode, 0.2, 0.6)
        return True
    except TimeoutException:
        return False


def selecionar_radio_fies(
    ctx: BrowserContext,
    modalidade: str = "social",
    max_attempts: int = MAX_RETRIES,
) -> bool:
    """
    Seleciona modalidade FIES (Social ou Regular).
    
    Args:
        ctx: Contexto do browser
        modalidade: "social" (FIES Social) ou "regular" (FIES Regular)
        max_attempts: Número máximo de tentativas
    
    Returns:
        True se selecionou com sucesso, False caso contrário
    """
    driver, wait = ctx.driver, ctx.wait
    logger = _get_logger()
    
    modalidade_lower = modalidade.lower().strip()
    if modalidade_lower not in FIES_RADIO_CONFIG:
        print(f"⚠️ Modalidade FIES inválida: {modalidade}. Use 'social' ou 'regular'.")
        return False
    
    config = FIES_RADIO_CONFIG[modalidade_lower]
    radio_id = config["id"]
    radio_value = config["value"]
    label_text = config["label_text"]
    
    logger.set_context(modalidade_fies=modalidade_lower)
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Estratégia 1: Tentar por ID do input
            try:
                radio = driver.find_element(By.ID, radio_id)
                if not radio.is_selected():
                    driver.execute_script("arguments[0].click()", radio)
                    human_delay(ctx.fast_mode, 0.2, 0.4)
                
                # Verificar se foi selecionado
                if radio.is_selected():
                    if attempt > 1:
                        logger.log_success_after_retry(
                            operation="selecionar_radio_fies",
                            attempt=attempt,
                            total_time=attempt * RETRY_DELAY,
                        )
                    print(f"✅ Modalidade FIES selecionada: {label_text}")
                    return True
            except Exception:
                pass
            
            # Estratégia 2: Tentar por valor do input
            try:
                radio = driver.find_element(
                    By.XPATH, 
                    f"//input[@type='radio' and @name='stCadunico' and @value='{radio_value}']"
                )
                if not radio.is_selected():
                    driver.execute_script("arguments[0].click()", radio)
                    human_delay(ctx.fast_mode, 0.2, 0.4)
                
                if radio.is_selected():
                    if attempt > 1:
                        logger.log_success_after_retry(
                            operation="selecionar_radio_fies",
                            attempt=attempt,
                            total_time=attempt * RETRY_DELAY,
                        )
                    print(f"✅ Modalidade FIES selecionada: {label_text}")
                    return True
            except Exception:
                pass
            
            # Estratégia 3: Tentar por texto da label
            if selecionar_radio_por_texto(ctx, label_text):
                # Verificar se realmente selecionou
                try:
                    radio = driver.find_element(By.ID, radio_id)
                    if radio.is_selected():
                        if attempt > 1:
                            logger.log_success_after_retry(
                                operation="selecionar_radio_fies",
                                attempt=attempt,
                                total_time=attempt * RETRY_DELAY,
                            )
                        print(f"✅ Modalidade FIES selecionada: {label_text}")
                        return True
                except Exception:
                    pass
            
            # Estratégia 4: Clicar na label diretamente
            try:
                lbl = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, f"//label[contains(normalize-space(.), '{label_text}')]")
                    )
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lbl)
                driver.execute_script("arguments[0].click();", lbl)
                human_delay(ctx.fast_mode, 0.2, 0.4)
                
                # Verificar seleção
                try:
                    radio = driver.find_element(By.ID, radio_id)
                    if radio.is_selected():
                        if attempt > 1:
                            logger.log_success_after_retry(
                                operation="selecionar_radio_fies",
                                attempt=attempt,
                                total_time=attempt * RETRY_DELAY,
                            )
                        print(f"✅ Modalidade FIES selecionada: {label_text}")
                        return True
                except Exception:
                    pass
            except Exception:
                pass
            
            # Se chegou aqui, não conseguiu selecionar nesta tentativa
            logger.log_timeout(
                operation="selecionar_radio_fies",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=TimeoutException(f"Não foi possível selecionar {label_text}"),
                context={"modalidade": modalidade_lower},
            )
            
            if attempt < max_attempts:
                time.sleep(RETRY_DELAY)
                
        except Exception as e:
            logger.log_timeout(
                operation="selecionar_radio_fies",
                attempt=attempt,
                max_attempts=max_attempts,
                exception=e,
                context={"modalidade": modalidade_lower},
            )
            if attempt < max_attempts:
                time.sleep(RETRY_DELAY)
    
    print(f"❌ Não foi possível selecionar modalidade FIES: {label_text}")
    return False


def selecionar_radio_fies_social(ctx: BrowserContext) -> bool:
    """
    Seleciona o rádio FIES Social.
    
    Mantida para compatibilidade com código existente.
    Internamente chama selecionar_radio_fies(ctx, "social").
    """
    return selecionar_radio_fies(ctx, "social")


def selecionar_radio_fies_regular(ctx: BrowserContext) -> bool:
    """
    Seleciona o rádio FIES Regular.
    
    Atalho para selecionar_radio_fies(ctx, "regular").
    """
    return selecionar_radio_fies(ctx, "regular")


def verificar_modalidade_selecionada(ctx: BrowserContext) -> Optional[str]:
    """
    Verifica qual modalidade FIES está atualmente selecionada.
    
    Returns:
        "social", "regular", ou None se nenhuma selecionada
    """
    driver = ctx.driver
    
    for modalidade, config in FIES_RADIO_CONFIG.items():
        try:
            radio = driver.find_element(By.ID, config["id"])
            if radio.is_selected():
                return modalidade
        except Exception:
            continue
    
    return None
