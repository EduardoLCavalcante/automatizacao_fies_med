"""Utilitário de retry para operações sujeitas a timeout/504 no portal FIES."""

import time
from typing import Callable, TypeVar, cast

from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait

from src.core.browser import BrowserContext
from src.core.captcha import pagina_esta_funcional

T = TypeVar("T")


def eh_timeout_recuperavel(exc: BaseException) -> bool:
    """Distingue sobrecarga/timeout de falhas fatais do navegador."""

    if isinstance(exc, (InvalidSessionIdException, NoSuchWindowException)):
        return False
    if isinstance(exc, TimeoutException):
        return True
    if not isinstance(exc, WebDriverException):
        return False
    mensagem = str(exc).lower()
    return any(
        marcador in mensagem
        for marcador in ("504", "gateway timeout", "gateway time-out", "timed out", "timeout")
    )


def propagar_timeout(exc: BaseException) -> None:
    """Evita que fallbacks ocultem timeout ou encerramento da sessão/janela."""

    if isinstance(exc, (InvalidSessionIdException, NoSuchWindowException)):
        raise exc
    if eh_timeout_recuperavel(exc):
        raise exc


def _pausar_ate(
    segundos: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    prazo = monotonic() + segundos
    while True:
        restante = prazo - monotonic()
        if restante <= 0:
            return
        sleep(restante)


def aguardar_pagina_responsiva(ctx: BrowserContext, timeout: int = 60) -> bool:
    """
    Aguarda a página sair do estado de loading/erro sem recarregá-la.
    Retorna True se a página voltou a responder, False se continuar travada.
    """
    try:
        WebDriverWait(ctx.driver, timeout).until(lambda _driver: pagina_esta_funcional(ctx))
        return True
    except Exception:
        return False


def com_retry_timeout(
    ctx: BrowserContext,
    operacao: Callable[[], T],
    descricao: str = "operação",
    max_tentativas: int = 3,
    espera_entre_tentativas: int = 15,
    recuperar: Callable[[], None] | None = None,
    concluida: Callable[[], bool] | None = None,
    *,
    _monotonic: Callable[[], float] | None = None,
    _sleep: Callable[[float], None] | None = None,
) -> T:
    """
    Repete a operação em blocos. Após três timeouts, pausa pelo intervalo de
    sobrecarga configurado, restaura o checkpoint e inicia um novo bloco.
    O ciclo só termina com sucesso, erro não recuperável ou interrupção externa.
    """
    if max_tentativas <= 0:
        raise ValueError("max_tentativas deve ser positivo")
    if espera_entre_tentativas < 0:
        raise ValueError("espera_entre_tentativas não pode ser negativa")

    monotonic = _monotonic or time.monotonic
    sleep = _sleep or time.sleep
    ciclo = 1

    def terminou_atrasada() -> bool:
        if concluida is None:
            return False
        try:
            return concluida()
        except (TimeoutException, WebDriverException) as exc:
            if eh_timeout_recuperavel(exc):
                return False
            raise

    while True:
        for tentativa in range(1, max_tentativas + 1):
            if terminou_atrasada():
                print(f"Resposta tardia reconhecida em '{descricao}'; continuando.")
                return cast(T, None)
            try:
                return operacao()
            except (TimeoutException, WebDriverException) as exc:
                if not eh_timeout_recuperavel(exc):
                    raise
                print(
                    f"\nTimeout/504 em '{descricao}' "
                    f"(ciclo {ciclo}, tentativa {tentativa}/{max_tentativas})."
                )
                if tentativa < max_tentativas:
                    print(f"Aguardando {espera_entre_tentativas}s antes da nova tentativa.")
                    _pausar_ate(espera_entre_tentativas, monotonic, sleep)

        if terminou_atrasada():
            print(f"Resposta tardia reconhecida em '{descricao}'; continuando.")
            return cast(T, None)

        print(
            f"Servidor possivelmente sobrecarregado em '{descricao}'. "
            f"Pausa automática de {ctx.server_pause_seconds:g}s (ciclo {ciclo})."
        )
        _pausar_ate(ctx.server_pause_seconds, monotonic, sleep)

        if terminou_atrasada():
            print(f"Resposta tardia reconhecida em '{descricao}'; continuando.")
            return cast(T, None)

        while recuperar is not None:
            try:
                recuperar()
                break
            except (TimeoutException, WebDriverException) as exc:
                if not eh_timeout_recuperavel(exc):
                    raise
                ciclo += 1
                print(
                    f"Timeout ao restaurar '{descricao}'. "
                    f"Nova pausa automática de {ctx.server_pause_seconds:g}s (ciclo {ciclo})."
                )
                _pausar_ate(ctx.server_pause_seconds, monotonic, sleep)

        print(f"Pausa concluída; retomando '{descricao}'.")
        ciclo += 1
