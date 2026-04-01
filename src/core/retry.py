"""Utilitário de retry para operações sujeitas a timeout/504 no portal FIES."""

import time
from typing import Callable, TypeVar

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from src.core.browser import BrowserContext

T = TypeVar("T")


def aguardar_pagina_responsiva(ctx: BrowserContext, timeout: int = 60) -> bool:
    """
    Aguarda a página sair do estado de loading/erro sem recarregá-la.
    Retorna True se a página voltou a responder, False se continuar travada.
    """
    try:
        WebDriverWait(ctx.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        return True
    except Exception:
        return False


def com_retry_timeout(
    ctx: BrowserContext,
    operacao: Callable[[], T],
    descricao: str = "operação",
    max_tentativas: int = 3,
    espera_entre_tentativas: int = 15,
) -> T:
    """
    Executa `operacao`. Se ocorrer TimeoutException ou erro 504/WebDriverException
    relacionado a timeout:

      1. Aguarda `espera_entre_tentativas` segundos a página se recuperar sozinha.
      2. Se não recuperar, pausa e exibe mensagem no terminal pedindo intervenção manual.
      3. Tenta novamente até `max_tentativas` vezes.

    NÃO recarrega a página automaticamente, pois isso exigiria novo CAPTCHA.
    Se todas as tentativas falharem, relança a última exceção para o chamador tratar.

    Parâmetros:
        ctx: contexto do browser (BrowserContext).
        operacao: callable sem argumentos que executa a ação desejada e retorna T.
        descricao: texto legível que identifica a operação, usado nas mensagens de log.
        max_tentativas: número máximo de tentativas antes de desistir.
        espera_entre_tentativas: segundos de espera passiva antes de cada retentativa.
    """
    ultima_exc: Exception = RuntimeError("Nenhuma tentativa executada")

    for tentativa in range(1, max_tentativas + 1):
        try:
            return operacao()

        except (TimeoutException, WebDriverException) as exc:
            ultima_exc = exc
            msg = str(exc).lower()

            is_timeout = isinstance(exc, TimeoutException)
            is_504 = "504" in msg or "timed out" in msg or "timeout" in msg

            # Outros WebDriverException (ex: elemento não encontrado) não devem ser retentados
            if not (is_timeout or is_504):
                raise

            print(f"\n⏳ Timeout/504 detectado em '{descricao}' (tentativa {tentativa}/{max_tentativas}).")
            print(f"   Aguardando {espera_entre_tentativas}s para a página se recuperar...")
            time.sleep(espera_entre_tentativas)

            pagina_ok = aguardar_pagina_responsiva(ctx, timeout=30)

            if not pagina_ok:
                print("\n🔴 Página não respondeu automaticamente.")
                print("   Verifique o navegador: pode haver erro 504, CAPTCHA ou tela em branco.")
                input("   Resolva no navegador e pressione ENTER para continuar... ")
                time.sleep(3)
            else:
                print(f"   ✅ Página respondeu. Retentando '{descricao}'...")

    raise ultima_exc
