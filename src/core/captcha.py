"""Detecção e espera human-in-the-loop do reCAPTCHA do portal FIES."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchWindowException,
    WebDriverException,
)

if TYPE_CHECKING:
    from src.core.browser import BrowserContext


CAPTCHA_POLL_INTERVAL_SECONDS = 0.5


class CaptchaState(str, Enum):
    """Estados observáveis do desafio na página atual."""

    LOADING = "loading"
    PENDING = "pending"
    SOLVED = "solved"
    EXPIRED = "expired"
    ABSENT = "absent"


class CaptchaError(RuntimeError):
    """Erro fatal relacionado ao estado do CAPTCHA ou do portal."""


class CaptchaTimeoutError(CaptchaError):
    """O operador não concluiu um CAPTCHA dentro do limite configurado."""


class PortalStateError(CaptchaError):
    """A página carregada não é um formulário ou resultado funcional do portal."""


class CloudflareChallengeError(PortalStateError):
    """O Cloudflare assumiu temporariamente a página do portal."""


class _PortalReloadingError(PortalStateError):
    """O documento está temporariamente indisponível durante uma recarga."""


@dataclass
class CaptchaMonitor:
    """Memória do CAPTCHA associada a uma geração da página de consulta."""

    generation: int = 0
    seen_solved: bool = False
    last_state: CaptchaState | None = None

    def reset(self) -> None:
        self.generation += 1
        self.seen_solved = False
        self.last_state = None


@dataclass(frozen=True)
class CaptchaSnapshot:
    ready_state: str
    widget_present: bool
    api_available: bool
    api_response_length: int
    textarea_response_length: int
    form_ready: bool
    results_ready: bool
    error_kind: str | None

    @property
    def response_length(self) -> int:
        return max(self.api_response_length, self.textarea_response_length)

    @property
    def page_ready(self) -> bool:
        return self.ready_state == "complete" and (
            self.form_ready or self.results_ready or self.widget_present
        )


_CAPTCHA_PROBE_SCRIPT = r"""
const readyState = document.readyState || "";
const widgets = document.querySelectorAll(".g-recaptcha");
const frames = [...document.querySelectorAll("iframe")];
const widgetPresent = widgets.length > 0 || frames.some((frame) => {
  const src = (frame.getAttribute("src") || "").toLowerCase();
  return src.includes("recaptcha");
});
const cloudflareChallengePresent = frames.some((frame) => {
  const src = (frame.getAttribute("src") || "").toLowerCase();
  return src.includes("challenges.cloudflare.com") || src.includes("turnstile");
});

let apiAvailable = false;
let apiResponseLength = 0;
try {
  apiAvailable = typeof window.grecaptcha !== "undefined"
    && typeof window.grecaptcha.getResponse === "function";
  if (apiAvailable) {
    apiResponseLength = (window.grecaptcha.getResponse() || "").length;
  }
} catch (_) {
  apiAvailable = false;
  apiResponseLength = 0;
}

let textareaResponseLength = 0;
for (const element of document.querySelectorAll(
  'textarea[name="g-recaptcha-response"]'
)) {
  textareaResponseLength = Math.max(
    textareaResponseLength,
    (element.value || "").length,
  );
}

const formReady = Boolean(
  document.getElementById("select2-noEstado-container")
  || document.getElementById("btnBuscarCursos")
);
const resultsReady = Boolean(
  document.querySelector("table tbody tr")
  || document.querySelector("a[href='/consulta']")
);
const bodyText = (document.body?.innerText || "").trim().toLowerCase();
const title = (document.title || "").trim().toLowerCase();

let errorKind = null;
if (
  bodyText.includes("504 gateway")
  || bodyText.includes("gateway time-out")
  || bodyText.includes("gateway timeout")
) {
  errorKind = "504";
} else if (
  bodyText.includes("cloudflare")
  || bodyText.includes("checking your browser")
  || bodyText.includes("verify you are human")
  || bodyText.includes("performing security verification")
  || bodyText.includes("enable javascript and cookies")
  || title.includes("just a moment")
  || title.includes("attention required")
  || cloudflareChallengePresent
) {
  errorKind = "cloudflare";
} else if (readyState === "complete" && bodyText.length === 0) {
  errorKind = "blank";
}

return {
  readyState,
  widgetPresent,
  apiAvailable,
  apiResponseLength,
  textareaResponseLength,
  formReady,
  resultsReady,
  errorKind,
};
"""


def inspecionar_pagina(ctx: BrowserContext) -> CaptchaSnapshot:
    """Lê sinais do portal sem entrar nos iframes cross-origin do reCAPTCHA."""

    try:
        raw = ctx.driver.execute_script(_CAPTCHA_PROBE_SCRIPT) or {}
    except (InvalidSessionIdException, NoSuchWindowException) as exc:
        raise PortalStateError(f"a janela do navegador não está mais disponível: {exc}") from exc
    except WebDriverException as exc:
        raise _PortalReloadingError(
            f"página temporariamente indisponível durante atualização: {exc}"
        ) from exc
    except Exception as exc:
        raise PortalStateError(f"não foi possível inspecionar a página: {exc}") from exc

    return CaptchaSnapshot(
        ready_state=str(raw.get("readyState") or ""),
        widget_present=bool(raw.get("widgetPresent")),
        api_available=bool(raw.get("apiAvailable")),
        api_response_length=int(raw.get("apiResponseLength") or 0),
        textarea_response_length=int(raw.get("textareaResponseLength") or 0),
        form_ready=bool(raw.get("formReady")),
        results_ready=bool(raw.get("resultsReady")),
        error_kind=str(raw["errorKind"]) if raw.get("errorKind") else None,
    )


def pagina_esta_funcional(ctx: BrowserContext) -> bool:
    """Retorna True apenas para formulário, CAPTCHA ou resultados funcionais."""

    try:
        snapshot = inspecionar_pagina(ctx)
    except PortalStateError:
        return False
    return snapshot.error_kind is None and snapshot.page_ready


def aguardar_cloudflare_inicial(
    ctx: BrowserContext,
    *,
    _cloudflare_detectado: bool = False,
    _input: Callable[[str], str] | None = None,
    _monotonic: Callable[[], float] | None = None,
    _sleep: Callable[[float], None] | None = None,
) -> bool:
    """Cria um único checkpoint manual quando o primeiro desafio é Cloudflare."""

    input_func = _input or input
    monotonic = _monotonic or time.monotonic
    sleep = _sleep or time.sleep
    deadline = monotonic() + ctx.captcha_timeout_seconds
    intervencao_solicitada = False

    if _cloudflare_detectado:
        print("\nCloudflare: conclua a verificação inicial no navegador.")
        input_func(
            "Depois que o Cloudflare liberar a página, pressione ENTER para continuar... "
        )
        intervencao_solicitada = True
        deadline = monotonic() + ctx.captcha_timeout_seconds
        ctx.captcha.last_state = None

    while True:
        try:
            snapshot = inspecionar_pagina(ctx)
        except _PortalReloadingError:
            snapshot = None

        if snapshot is not None:
            if snapshot.error_kind == "cloudflare":
                if not intervencao_solicitada:
                    print("\nCloudflare: conclua a verificação inicial no navegador.")
                    input_func(
                        "Depois que o Cloudflare liberar a página, pressione ENTER para continuar... "
                    )
                    intervencao_solicitada = True
                    deadline = monotonic() + ctx.captcha_timeout_seconds
                    ctx.captcha.last_state = None
            elif snapshot.error_kind == "blank":
                pass
            elif snapshot.error_kind:
                raise PortalStateError(
                    f"portal em estado inválido durante verificação inicial: {snapshot.error_kind}"
                )
            elif snapshot.page_ready:
                if intervencao_solicitada:
                    ctx.cloudflare_checkpoint_completed = True
                    print("Cloudflare concluído; iniciando monitoramento automático do CAPTCHA.")
                return intervencao_solicitada

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CaptchaTimeoutError(
                "a página não ficou disponível após a verificação inicial do Cloudflare"
            )
        sleep(min(CAPTCHA_POLL_INTERVAL_SECONDS, remaining))


def detectar_estado_captcha(ctx: BrowserContext) -> CaptchaState:
    """Classifica o CAPTCHA e atualiza a memória da geração atual."""

    snapshot = inspecionar_pagina(ctx)
    if snapshot.error_kind == "cloudflare":
        raise CloudflareChallengeError("Cloudflare aguardando verificação humana")
    if snapshot.error_kind:
        raise PortalStateError(f"portal em estado inválido: {snapshot.error_kind}")

    if snapshot.response_length > 0:
        ctx.captcha.seen_solved = True
        return CaptchaState.SOLVED

    if snapshot.ready_state != "complete":
        return CaptchaState.LOADING

    if ctx.captcha.seen_solved and snapshot.form_ready:
        return CaptchaState.EXPIRED

    if snapshot.widget_present:
        return CaptchaState.PENDING

    if snapshot.form_ready:
        return CaptchaState.ABSENT
    raise PortalStateError("portal carregado sem CAPTCHA e sem formulário de consulta válido")


_STATE_MESSAGES = {
    CaptchaState.LOADING: "CAPTCHA: aguardando o widget carregar...",
    CaptchaState.PENDING: "CAPTCHA: aguardando resolução humana no navegador...",
    CaptchaState.SOLVED: "CAPTCHA: resolvido; continuando automaticamente.",
    CaptchaState.EXPIRED: "CAPTCHA: o token expirou; resolva o novo desafio no navegador...",
    CaptchaState.ABSENT: "CAPTCHA: não exigido nesta página; continuando.",
}


def _registrar_transicao(ctx: BrowserContext, state: CaptchaState) -> None:
    if ctx.captcha.last_state == state:
        return
    ctx.captcha.last_state = state
    print(_STATE_MESSAGES[state])


def aguardar_captcha(
    ctx: BrowserContext,
    timeout_seconds: float | None = None,
    *,
    _input: Callable[[str], str] | None = None,
    _monotonic: Callable[[], float] | None = None,
    _sleep: Callable[[float], None] | None = None,
) -> CaptchaState:
    """Aguarda resolução humana e prossegue sem confirmação pelo terminal."""

    timeout = ctx.captcha_timeout_seconds if timeout_seconds is None else timeout_seconds
    if timeout <= 0:
        raise ValueError("captcha timeout deve ser positivo")

    monotonic = _monotonic or time.monotonic
    sleep = _sleep or time.sleep
    deadline = monotonic() + timeout

    while True:
        try:
            state = detectar_estado_captcha(ctx)
        except CloudflareChallengeError:
            if not getattr(ctx, "cloudflare_checkpoint_completed", False):
                aguardar_cloudflare_inicial(
                    ctx,
                    _cloudflare_detectado=True,
                    _input=_input,
                    _monotonic=monotonic,
                    _sleep=sleep,
                )
                deadline = monotonic() + timeout
                continue
            state = CaptchaState.LOADING
        except _PortalReloadingError:
            state = CaptchaState.LOADING
        _registrar_transicao(ctx, state)
        if state in (CaptchaState.SOLVED, CaptchaState.ABSENT):
            ctx.cloudflare_checkpoint_completed = True
            return state

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CaptchaTimeoutError(
                f"CAPTCHA não concluído em {timeout:g}s (estado final: {state.value})"
            )
        sleep(min(CAPTCHA_POLL_INTERVAL_SECONDS, remaining))
