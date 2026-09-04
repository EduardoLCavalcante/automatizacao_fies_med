"""Criação e gerenciamento do navegador (Selenium)."""

from dataclasses import dataclass, field
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from src.config import CAPTCHA_WAIT_TIMEOUT_SECONDS, FAST_MODE, SERVER_BUSY_PAUSE_SECONDS
from src.core.captcha import CaptchaMonitor
from src.core.network import NetworkTracker


@dataclass
class PortalCheckpoint:
    """Estado lógico mínimo necessário para reconstruir a consulta atual."""

    mode: str = "normal"
    modalidade: str = "social"
    fase: str = "inicio"
    estado: str | None = None
    municipio: str | None = None
    curso: str | None = None
    ies_nome: str | None = None
    ies_codigo: str | None = None
    conceito: str | None = None

    def limpar_apos_estado(self) -> None:
        self.municipio = None
        self.curso = None
        self.ies_nome = None
        self.ies_codigo = None
        self.conceito = None

    def limpar_apos_municipio(self) -> None:
        self.ies_nome = None
        self.ies_codigo = None
        self.conceito = None


@dataclass
class BrowserContext:
    driver: webdriver.Chrome
    wait: WebDriverWait
    fast_mode: bool = FAST_MODE
    captcha_timeout_seconds: float = CAPTCHA_WAIT_TIMEOUT_SECONDS
    captcha: CaptchaMonitor = field(default_factory=CaptchaMonitor)
    cloudflare_checkpoint_completed: bool = False
    server_pause_seconds: float = SERVER_BUSY_PAUSE_SECONDS
    checkpoint: PortalCheckpoint = field(default_factory=PortalCheckpoint)
    network: NetworkTracker = field(default_factory=NetworkTracker)


def build_browser(
    captcha_timeout_seconds: float = CAPTCHA_WAIT_TIMEOUT_SECONDS,
    server_pause_seconds: float = SERVER_BUSY_PAUSE_SECONDS,
) -> BrowserContext:
    """Inicializa o Chrome com as opções adequadas ao modo escolhido."""
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    options.page_load_strategy = "none" if FAST_MODE else "normal"

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    wait = WebDriverWait(driver, 25 if FAST_MODE else 60)
    network = NetworkTracker()
    network.enable(driver)
    return BrowserContext(
        driver=driver,
        wait=wait,
        fast_mode=FAST_MODE,
        captcha_timeout_seconds=captcha_timeout_seconds,
        server_pause_seconds=server_pause_seconds,
        network=network,
    )


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
