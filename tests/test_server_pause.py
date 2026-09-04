import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)

from src.core.browser import PortalCheckpoint
from src.core.captcha import CaptchaTimeoutError
from src.core.retry import com_retry_timeout, eh_timeout_recuperavel
from src.navigation.flow import restaurar_checkpoint


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_context(pause=300):
    return SimpleNamespace(server_pause_seconds=pause)


class ServerPauseControllerTests(unittest.TestCase):
    def test_three_timeouts_use_two_short_waits_then_pause_and_restore(self):
        ctx = make_context()
        clock = FakeClock()
        operation = Mock(
            side_effect=[
                TimeoutException("1"),
                TimeoutException("2"),
                TimeoutException("3"),
                "ok",
            ]
        )
        restore = Mock()

        result = com_retry_timeout(
            ctx,
            operation,
            recuperar=restore,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual("ok", result)
        self.assertEqual([15, 15, 300], clock.sleeps)
        self.assertEqual(4, operation.call_count)
        restore.assert_called_once_with()

    def test_success_before_third_attempt_does_not_pause_or_restore(self):
        ctx = make_context()
        clock = FakeClock()
        operation = Mock(side_effect=[TimeoutException("1"), "ok"])
        restore = Mock()

        result = com_retry_timeout(
            ctx,
            operation,
            recuperar=restore,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual("ok", result)
        self.assertEqual([15], clock.sleeps)
        restore.assert_not_called()

    def test_multiple_complete_cycles_repeat_the_same_operation(self):
        ctx = make_context()
        clock = FakeClock()
        operation = Mock(
            side_effect=[TimeoutException(str(i)) for i in range(6)] + ["ok"]
        )
        restore = Mock()

        result = com_retry_timeout(
            ctx,
            operation,
            recuperar=restore,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual("ok", result)
        self.assertEqual([15, 15, 300, 15, 15, 300], clock.sleeps)
        self.assertEqual(7, operation.call_count)
        self.assertEqual(2, restore.call_count)

    def test_late_response_is_accepted_before_pause_without_replaying(self):
        ctx = make_context()
        clock = FakeClock()
        operation = Mock(side_effect=TimeoutException("late"))
        completed = Mock(side_effect=[False, False, False, True])

        result = com_retry_timeout(
            ctx,
            operation,
            concluida=completed,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertIsNone(result)
        self.assertEqual(3, operation.call_count)
        self.assertEqual([15, 15], clock.sleeps)

    def test_timeout_during_restore_starts_another_long_pause(self):
        ctx = make_context()
        clock = FakeClock()
        operation = Mock(
            side_effect=[
                TimeoutException("1"),
                TimeoutException("2"),
                TimeoutException("3"),
                "ok",
            ]
        )
        restore = Mock(side_effect=[TimeoutException("restore"), None])

        result = com_retry_timeout(
            ctx,
            operation,
            recuperar=restore,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

        self.assertEqual("ok", result)
        self.assertEqual([15, 15, 300, 300], clock.sleeps)
        self.assertEqual(2, restore.call_count)

    def test_fatal_and_captcha_errors_are_not_captured(self):
        ctx = make_context()
        clock = FakeClock()
        for error in (
            NoSuchWindowException("closed"),
            CaptchaTimeoutError("captcha"),
            KeyboardInterrupt(),
        ):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    com_retry_timeout(
                        ctx,
                        Mock(side_effect=error),
                        _monotonic=clock.monotonic,
                        _sleep=clock.sleep,
                    )

        self.assertEqual([], clock.sleeps)

    def test_only_timeout_like_webdriver_errors_are_recoverable(self):
        self.assertTrue(eh_timeout_recuperavel(WebDriverException("504 Gateway Timeout")))
        self.assertTrue(eh_timeout_recuperavel(TimeoutException("element")))
        self.assertFalse(eh_timeout_recuperavel(WebDriverException("invalid selector")))
        self.assertFalse(eh_timeout_recuperavel(NoSuchWindowException("closed")))


class CheckpointRestoreTests(unittest.TestCase):
    def test_restore_reapplies_filters_ies_and_concept_in_order(self):
        checkpoint = PortalCheckpoint(
            modalidade="regular",
            fase="pesquisa",
            estado="São Paulo",
            municipio="Campinas",
            curso="MEDICINA",
            ies_nome="Universidade Exemplo",
            ies_codigo="12345",
            conceito="5",
        )
        driver = Mock()
        ctx = SimpleNamespace(
            checkpoint=checkpoint,
            captcha=Mock(),
            driver=driver,
            wait=Mock(),
        )
        events = []

        with (
            patch("src.navigation.flow.remove_loading_overlay"),
            patch("src.navigation.flow.aguardar_captcha"),
            patch("src.navigation.flow._aguardar_formulario"),
            patch(
                "src.navigation.flow.aplicar_filtros",
                side_effect=lambda *_args, **kwargs: events.append(
                    (
                        "filtros",
                        kwargs["estado"],
                        kwargs["municipio"],
                        kwargs["curso"],
                    )
                )
                or True,
            ),
            patch("src.navigation.flow.esperar_select2_habilitado"),
            patch(
                "src.navigation.flow.select2_exact_multi",
                side_effect=lambda *_args: events.append("ies") or True,
            ),
            patch(
                "src.navigation.flow.select2_exact",
                side_effect=lambda *_args: events.append("conceito"),
            ),
        ):
            restaurar_checkpoint(ctx)

        self.assertEqual(
            [
                ("filtros", "São Paulo", "Campinas", "MEDICINA"),
                "ies",
                "conceito",
            ],
            events,
        )
        ctx.captcha.reset.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
