import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException, WebDriverException

from src.core.browser import BrowserContext
from src.core.captcha import (
    CaptchaState,
    CaptchaTimeoutError,
    CloudflareChallengeError,
    PortalStateError,
    aguardar_cloudflare_inicial,
    aguardar_captcha,
    detectar_estado_captcha,
    pagina_esta_funcional,
)
from src.core.retry import com_retry_timeout


def snapshot(
    *,
    token_length=0,
    textarea_length=0,
    widget=True,
    api=True,
    form=True,
    results=False,
    ready="complete",
    error=None,
):
    return {
        "readyState": ready,
        "widgetPresent": widget,
        "apiAvailable": api,
        "apiResponseLength": token_length,
        "textareaResponseLength": textarea_length,
        "formReady": form,
        "resultsReady": results,
        "errorKind": error,
    }


class FakeDriver:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.last = self.snapshots[-1]

    def execute_script(self, _script):
        if self.snapshots:
            self.last = self.snapshots.pop(0)
        if isinstance(self.last, BaseException):
            raise self.last
        return self.last


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_context(snapshots, timeout=300):
    return BrowserContext(
        driver=FakeDriver(snapshots),
        wait=Mock(),
        fast_mode=True,
        captcha_timeout_seconds=timeout,
    )


class CaptchaTests(unittest.TestCase):
    def test_pending_then_solved_resumes_within_poll_interval(self):
        ctx = make_context([snapshot(), snapshot(token_length=20)])
        clock = FakeClock()

        state = aguardar_captcha(
            ctx,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual(CaptchaState.SOLVED, state)
        self.assertEqual([0.5], clock.sleeps)
        self.assertTrue(ctx.captcha.seen_solved)

    def test_expired_token_is_reported_and_waits_for_new_solution(self):
        ctx = make_context([snapshot(), snapshot(token_length=12)])
        ctx.captcha.seen_solved = True
        clock = FakeClock()
        output = io.StringIO()

        with redirect_stdout(output):
            state = aguardar_captcha(
                ctx,
                _monotonic=clock.monotonic,
                _sleep=clock.sleep,
            )

        self.assertEqual(CaptchaState.SOLVED, state)
        self.assertIn("token expirou", output.getvalue())
        self.assertEqual([0.5], clock.sleeps)

    def test_filled_to_empty_is_expired_even_if_widget_disappears(self):
        ctx = make_context(
            [snapshot(widget=False), snapshot(token_length=12)],
        )
        ctx.captcha.seen_solved = True
        clock = FakeClock()

        state = aguardar_captcha(
            ctx,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual(CaptchaState.SOLVED, state)
        self.assertEqual([0.5], clock.sleeps)

    def test_textarea_is_fallback_when_grecaptcha_api_is_unavailable(self):
        ctx = make_context([snapshot(api=False, textarea_length=18)])
        self.assertEqual(CaptchaState.SOLVED, detectar_estado_captcha(ctx))

    def test_page_stays_loading_until_document_is_complete(self):
        ctx = make_context(
            [snapshot(widget=False, api=False, form=True, ready="interactive")]
        )
        self.assertEqual(CaptchaState.LOADING, detectar_estado_captcha(ctx))

    def test_manual_refresh_keeps_waiting_for_first_captcha(self):
        ctx = make_context(
            [
                snapshot(),
                WebDriverException("target frame detached during refresh"),
                snapshot(),
                snapshot(token_length=20),
            ]
        )
        clock = FakeClock()

        state = aguardar_captcha(
            ctx,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual(CaptchaState.SOLVED, state)
        self.assertEqual([0.5, 0.5, 0.5], clock.sleeps)

    def test_initial_cloudflare_waits_for_enter_then_returns_to_automatic_flow(self):
        cloudflare = snapshot(
            widget=False,
            api=False,
            form=False,
            error="cloudflare",
        )
        ctx = make_context(
            [cloudflare, cloudflare, snapshot()],
        )
        clock = FakeClock()
        prompts = []

        handled = aguardar_cloudflare_inicial(
            ctx,
            _input=lambda prompt: prompts.append(prompt) or "",
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertTrue(handled)
        self.assertEqual(1, len(prompts))
        self.assertIn("ENTER", prompts[0])
        self.assertEqual([0.5, 0.5], clock.sleeps)

    def test_initial_page_without_cloudflare_does_not_request_enter(self):
        ctx = make_context([snapshot()])

        handled = aguardar_cloudflare_inicial(
            ctx,
            _input=lambda _prompt: self.fail("não deveria solicitar ENTER"),
        )

        self.assertFalse(handled)

    def test_cloudflare_during_first_captcha_requests_enter_and_resumes(self):
        cloudflare = snapshot(
            widget=False,
            api=False,
            form=False,
            error="cloudflare",
        )
        ctx = make_context(
            [snapshot(), cloudflare, cloudflare, snapshot(), snapshot(token_length=20)]
        )
        clock = FakeClock()
        prompts = []

        state = aguardar_captcha(
            ctx,
            _input=lambda prompt: prompts.append(prompt) or "",
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual(CaptchaState.SOLVED, state)
        self.assertEqual(1, len(prompts))
        self.assertTrue(ctx.cloudflare_checkpoint_completed)

    def test_cloudflare_error_has_a_specific_type(self):
        ctx = make_context(
            [snapshot(widget=False, form=False, error="cloudflare")]
        )
        with self.assertRaises(CloudflareChallengeError):
            detectar_estado_captcha(ctx)

    def test_absent_widget_requires_a_functional_page(self):
        ready_ctx = make_context([snapshot(widget=False, api=False, form=True)])
        self.assertEqual(CaptchaState.ABSENT, detectar_estado_captcha(ready_ctx))

        invalid_ctx = make_context(
            [snapshot(widget=False, api=False, form=False, results=False)]
        )
        with self.assertRaises(PortalStateError):
            detectar_estado_captcha(invalid_ctx)

        results_only_ctx = make_context(
            [snapshot(widget=False, api=False, form=False, results=True)]
        )
        with self.assertRaises(PortalStateError):
            detectar_estado_captcha(results_only_ctx)

    def test_portal_errors_are_not_classified_as_captcha(self):
        for error in ("504", "cloudflare", "blank"):
            with self.subTest(error=error):
                ctx = make_context([snapshot(error=error)])
                self.assertFalse(pagina_esta_funcional(ctx))
                with self.assertRaises(PortalStateError):
                    detectar_estado_captcha(ctx)

    def test_timeout_raises_after_configured_deadline(self):
        ctx = make_context([snapshot()], timeout=300)
        clock = FakeClock()

        with self.assertRaises(CaptchaTimeoutError):
            aguardar_captcha(
                ctx,
                _monotonic=clock.monotonic,
                _sleep=clock.sleep,
            )

        self.assertEqual(300.0, clock.now)
        self.assertEqual(300, BrowserContext.__dataclass_fields__["captcha_timeout_seconds"].default)

    def test_new_generation_forgets_previous_solution(self):
        ctx = make_context([snapshot()])
        ctx.captcha.seen_solved = True
        ctx.captcha.reset()

        self.assertEqual(CaptchaState.PENDING, detectar_estado_captcha(ctx))
        self.assertFalse(ctx.captcha.seen_solved)
        self.assertEqual(1, ctx.captcha.generation)

    def test_retry_waits_for_captcha_before_repeating_operation(self):
        ctx = make_context([snapshot(widget=False, api=False, form=True)])
        operation = Mock(side_effect=[TimeoutException("timeout"), "ok"])

        with (
            patch("src.core.retry.time.sleep"),
            patch("src.core.retry.aguardar_pagina_responsiva", return_value=True),
            patch("src.core.retry.aguardar_captcha") as wait_captcha,
        ):
            result = com_retry_timeout(
                ctx,
                operation,
                max_tentativas=2,
                espera_entre_tentativas=0,
            )

        self.assertEqual("ok", result)
        wait_captcha.assert_called_once_with(ctx)
        self.assertEqual(2, operation.call_count)

    def test_retry_does_not_swallow_captcha_timeout(self):
        ctx = make_context([snapshot()])
        operation = Mock(side_effect=TimeoutException("timeout"))

        with (
            patch("src.core.retry.time.sleep"),
            patch("src.core.retry.aguardar_pagina_responsiva", return_value=True),
            patch(
                "src.core.retry.aguardar_captcha",
                side_effect=CaptchaTimeoutError("limite"),
            ),
        ):
            with self.assertRaises(CaptchaTimeoutError):
                com_retry_timeout(
                    ctx,
                    operation,
                    max_tentativas=2,
                    espera_entre_tentativas=0,
                )


if __name__ == "__main__":
    unittest.main()
