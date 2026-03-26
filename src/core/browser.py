"""Criação e gerenciamento do navegador (Selenium)."""

from dataclasses import dataclass
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from src.config import FAST_MODE


@dataclass
class BrowserContext:
    driver: webdriver.Chrome
    wait: WebDriverWait
    fast_mode: bool = FAST_MODE


def build_browser() -> BrowserContext:
    """Inicializa o Chrome com as opções adequadas ao modo escolhido."""
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.page_load_strategy = "none" if FAST_MODE else "normal"

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    wait = WebDriverWait(driver, 25 if FAST_MODE else 60)
    return BrowserContext(driver=driver, wait=wait, fast_mode=FAST_MODE)


def remove_loading_overlay(ctx: BrowserContext) -> None:
    """Remove overlay de loading quando presente para evitar bloqueios de clique."""
    try:
        ctx.driver.execute_script(
            "const el = document.getElementById('loadingDiv'); if (el) el.remove();"
        )
    except Exception:
        pass


def shutdown_browser(ctx: BrowserContext) -> None:
    try:
        ctx.driver.quit()
    except Exception:
        pass
