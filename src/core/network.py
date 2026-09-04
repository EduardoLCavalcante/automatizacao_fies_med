"""Rastreamento mínimo de requisições do portal via Chrome DevTools Protocol."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable
from urllib.parse import urlsplit, urlunsplit

from selenium.common.exceptions import TimeoutException, WebDriverException


_RESOURCE_TYPES = {"Document", "XHR", "Fetch"}
_BUSY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_TIMEOUT_ERRORS = (
    "timed_out",
    "timed out",
    "timeout",
    "connection reset",
    "connection closed",
    "empty response",
    "err_connection_reset",
    "err_connection_closed",
    "err_timed_out",
)
_IGNORED_MARKERS = (
    "recaptcha",
    "challenges.cloudflare.com",
    "cloudflare.com/cdn-cgi",
    "googletagmanager",
    "google-analytics",
)


class PortalRequestTimeout(TimeoutException):
    """Falha de requisição confirmada pelo rastreador de rede."""


@dataclass
class TrackedRequest:
    request_id: str
    url: str
    method: str
    resource_type: str
    status: int | None = None
    finished: bool = False
    failed: bool = False
    error_text: str | None = None

    @property
    def endpoint(self) -> str:
        partes = urlsplit(self.url)
        return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))

    @property
    def busy(self) -> bool:
        if self.status in _BUSY_STATUSES:
            return True
        erro = (self.error_text or "").lower()
        return any(marcador in erro for marcador in _TIMEOUT_ERRORS)

    @property
    def terminal(self) -> bool:
        return self.finished or self.failed or self.status is not None

    @property
    def successful(self) -> bool:
        return self.terminal and not self.busy and (
            self.status is None or 200 <= self.status < 400
        )


@dataclass
class NetworkOperation:
    """Janela de correlação iniciada imediatamente antes de uma ação UI."""

    started_at: float
    origin_host: str | None = None
    requests: Dict[str, TrackedRequest] = field(default_factory=dict)


@dataclass(frozen=True)
class NetworkSnapshot:
    available: bool
    requests: tuple[TrackedRequest, ...] = ()
    error: str | None = None

    @property
    def pending(self) -> bool:
        return any(not request.terminal for request in self.requests)

    @property
    def has_busy(self) -> bool:
        return any(request.busy for request in self.requests)

    @property
    def has_success(self) -> bool:
        return any(request.successful for request in self.requests)

    @property
    def has_requests(self) -> bool:
        return bool(self.requests)

    @property
    def description(self) -> str:
        if self.error:
            return self.error
        if not self.requests:
            return "nenhuma requisição do portal identificada"
        request = self.requests[-1]
        status = f" HTTP {request.status}" if request.status is not None else ""
        return f"{request.method} {request.endpoint}{status}"


class NetworkTracker:
    """Coleta eventos de performance sem persistir conteúdo sensível."""

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.monotonic = monotonic or time.monotonic
        self.enabled = False
        self._readable = False
        self._warning_emitted = False

    def enable(self, driver: Any) -> bool:
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            self.enabled = True
            self._readable = True
            return True
        except (AttributeError, WebDriverException):
            self.enabled = False
            self._readable = False
            return False

    def begin(self, driver: Any) -> NetworkOperation:
        self._drain(driver)
        try:
            origin_host = urlsplit(str(driver.current_url or "")).hostname
        except Exception:
            origin_host = None
        return NetworkOperation(started_at=self.monotonic(), origin_host=origin_host)

    def snapshot(self, driver: Any, operation: NetworkOperation) -> NetworkSnapshot:
        if not self.enabled or not self._readable:
            return NetworkSnapshot(available=False)
        self._read_events(driver, operation)
        return NetworkSnapshot(
            available=self._readable,
            requests=tuple(operation.requests.values()),
            error=None if self._readable else "leitura do log de performance indisponível",
        )

    def _drain(self, driver: Any) -> None:
        if not self.enabled or not self._readable:
            return
        try:
            driver.get_log("performance")
        except (AttributeError, WebDriverException):
            self._readable = False

    def _read_events(self, driver: Any, operation: NetworkOperation) -> None:
        try:
            entries: Iterable[Dict[str, Any]] = driver.get_log("performance") or []
        except (AttributeError, WebDriverException):
            self._readable = False
            return

        for entry in entries:
            try:
                envelope = json.loads(entry.get("message", "{}"))
                message = envelope.get("message", {})
                self._apply_event(operation, message.get("method"), message.get("params", {}))
            except (TypeError, ValueError, AttributeError):
                continue

    def _apply_event(
        self,
        operation: NetworkOperation,
        method: str | None,
        params: Dict[str, Any],
    ) -> None:
        if method == "Network.requestWillBeSent":
            request = params.get("request") or {}
            url = str(request.get("url") or "")
            resource_type = str(params.get("type") or "")
            if not self._is_relevant(url, resource_type, operation.origin_host):
                return
            request_id = str(params.get("requestId") or "")
            if not request_id:
                return
            operation.requests[request_id] = TrackedRequest(
                request_id=request_id,
                url=url,
                method=str(request.get("method") or "GET"),
                resource_type=resource_type,
            )
            return

        request_id = str(params.get("requestId") or "")
        request = operation.requests.get(request_id)
        if request is None:
            return
        if method == "Network.responseReceived":
            response = params.get("response") or {}
            try:
                request.status = int(response.get("status"))
            except (TypeError, ValueError):
                request.status = None
        elif method == "Network.loadingFinished":
            request.finished = True
        elif method == "Network.loadingFailed":
            request.failed = True
            request.error_text = str(params.get("errorText") or "")

    @staticmethod
    def _is_relevant(url: str, resource_type: str, origin_host: str | None = None) -> bool:
        if resource_type not in _RESOURCE_TYPES:
            return False
        url_lower = url.lower()
        if not url or any(marker in url_lower for marker in _IGNORED_MARKERS):
            return False
        if origin_host is None:
            return True
        host = urlsplit(url).hostname
        if not host:
            return False
        # O portal pode distribuir APIs em subdomínios do MEC, mas eventos de
        # terceiros (analytics, captcha e assets externos) não representam a
        # operação protegida.
        return host == origin_host or host.endswith(".mec.gov.br")


def emitir_aviso_tracker_indisponivel(ctx: Any) -> None:
    tracker = getattr(ctx, "network", None)
    if tracker is None or getattr(tracker, "enabled", False) or getattr(tracker, "_warning_emitted", False):
        return
    print("⚠️ Rastreamento de rede indisponível; usando validação do DOM.")
    try:
        tracker._warning_emitted = True
    except Exception:
        pass
