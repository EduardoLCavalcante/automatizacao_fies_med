import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.app import main
import src.config.settings as settings
from src.config import BASE_URL
from src.core.captcha import (
    CaptchaMonitor,
    CaptchaState,
    CaptchaTimeoutError,
    aguardar_captcha,
)
from src.core.browser import PortalCheckpoint
from src.navigation.flow import abrir_nova_consulta, preparar_primeira_pagina
from src.scraping import runner


class FakeLink:
    def __init__(self):
        self.clicked = False

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self, captcha_snapshot=None):
        self.urls = []
        self.captcha_snapshot = captcha_snapshot

    def get(self, url):
        self.urls.append(url)

    def execute_script(self, _script):
        return self.captcha_snapshot


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class NavigationCaptchaTests(unittest.TestCase):
    def make_context(self):
        return SimpleNamespace(
            driver=FakeDriver(),
            wait=Mock(),
            captcha=CaptchaMonitor(),
            captcha_timeout_seconds=300,
            fast_mode=True,
            server_pause_seconds=300,
            checkpoint=PortalCheckpoint(),
            cloudflare_checkpoint_completed=False,
        )

    def test_initial_page_resets_and_waits_for_captcha(self):
        ctx = self.make_context()
        with (
            patch("src.navigation.flow.remove_loading_overlay"),
            patch("src.navigation.flow.aguardar_cloudflare_inicial") as wait_cloudflare,
            patch("src.navigation.flow.aguardar_captcha") as wait_captcha,
            patch("src.navigation.flow._aguardar_formulario"),
        ):
            preparar_primeira_pagina(ctx)

        self.assertEqual([BASE_URL], ctx.driver.urls)
        self.assertEqual(1, ctx.captcha.generation)
        wait_cloudflare.assert_called_once_with(ctx)
        wait_captcha.assert_called_once_with(ctx)

    def test_new_query_resets_and_waits_for_new_captcha(self):
        ctx = self.make_context()
        link = FakeLink()
        ctx.wait.until.return_value = link
        ctx.captcha.seen_solved = True

        with (
            patch("src.navigation.flow.remove_loading_overlay"),
            patch("src.navigation.flow.aguardar_captcha") as wait_captcha,
            patch("src.navigation.flow._aguardar_formulario"),
        ):
            self.assertTrue(abrir_nova_consulta(ctx))

        self.assertTrue(link.clicked)
        self.assertEqual(1, ctx.captcha.generation)
        self.assertFalse(ctx.captcha.seen_solved)
        wait_captcha.assert_called_once_with(ctx)

    def test_search_checks_captcha_before_clicking(self):
        events = []
        button = Mock()
        button.click.side_effect = lambda: events.append("click")
        ctx = SimpleNamespace(wait=Mock())
        ctx.wait.until.return_value = button

        with patch(
            "src.scraping.runner.aguardar_captcha",
            side_effect=lambda _ctx: events.append("captcha"),
        ):
            runner._pesquisar_e_aguardar(ctx)

        self.assertEqual("captcha", events[0])
        self.assertEqual("click", events[1])

    def test_runner_does_not_swallow_captcha_error_or_print_finalized(self):
        ctx = SimpleNamespace(
            driver=Mock(),
            fast_mode=True,
            server_pause_seconds=300,
            checkpoint=PortalCheckpoint(),
        )
        output = io.StringIO()
        with (
            patch.object(runner, "carregar_progresso", return_value=([], set(), None, {})),
            patch.object(runner, "preparar_primeira_pagina"),
            patch.object(runner, "ESTADOS", {"AC": "Acre"}),
            patch.object(runner, "aplicar_filtros", return_value=True),
            patch.object(runner, "listar_opcoes_select2", return_value=["Cidade"]),
            patch.object(
                runner,
                "buscar_notas_por_municipio",
                side_effect=CaptchaTimeoutError("limite"),
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(CaptchaTimeoutError):
                runner.run_scraper(ctx)

        self.assertNotIn("FINALIZADO", output.getvalue())


class AppCaptchaTests(unittest.TestCase):
    def test_timeout_returns_two_and_always_closes_browser(self):
        ctx = SimpleNamespace(checkpoint=PortalCheckpoint())
        output = io.StringIO()
        with (
            patch("src.app.build_browser", return_value=ctx),
            patch("src.app.run_scraper", side_effect=CaptchaTimeoutError("300s")),
            patch("src.app.shutdown_browser") as shutdown,
            redirect_stdout(output),
        ):
            code = main([])

        self.assertEqual(2, code)
        shutdown.assert_called_once_with(ctx)
        self.assertIn("CAPTCHA_TIMEOUT", output.getvalue())
        self.assertNotIn("FINALIZADO", output.getvalue())

    def test_timeout_option_is_forwarded_to_browser(self):
        ctx = SimpleNamespace(checkpoint=PortalCheckpoint())
        with (
            patch("src.app.build_browser", return_value=ctx) as build,
            patch("src.app.run_scraper"),
            patch("src.app.shutdown_browser"),
        ):
            self.assertEqual(0, main(["--captcha-timeout", "17"]))

        build.assert_called_once_with(
            captcha_timeout_seconds=17,
            server_pause_seconds=300,
        )

    def test_all_modes_and_modalities_use_the_captcha_enabled_context(self):
        modes = [
            ([], "run_scraper"),
            (["--check"], "run_checker"),
            (["--review"], "run_review"),
            (["--faltantes-txt"], "run_faltantes_txt"),
        ]
        solved_snapshot = {
            "readyState": "complete",
            "widgetPresent": True,
            "apiAvailable": True,
            "apiResponseLength": 20,
            "textareaResponseLength": 0,
            "formReady": True,
            "resultsReady": False,
            "errorKind": None,
        }

        with patch.object(settings, "FIES_MODALIDADE", "social"):
            for modalidade in ("social", "regular"):
                for mode_argv, expected in modes:
                    argv = ["--modalidade", modalidade, *mode_argv]
                    with self.subTest(argv=argv):
                        ctx = SimpleNamespace(
                            driver=FakeDriver(solved_snapshot),
                            wait=Mock(),
                            captcha=CaptchaMonitor(),
                            captcha_timeout_seconds=300,
                            fast_mode=True,
                            server_pause_seconds=300,
                            checkpoint=PortalCheckpoint(),
                            cloudflare_checkpoint_completed=False,
                        )
                        clock = FakeClock()

                        def verify_captcha(received_ctx, **_kwargs):
                            self.assertIs(ctx, received_ctx)
                            state = aguardar_captcha(
                                received_ctx,
                                _monotonic=clock.monotonic,
                                _sleep=clock.sleep,
                            )
                            self.assertEqual(CaptchaState.SOLVED, state)

                        with (
                            patch("src.app.build_browser", return_value=ctx),
                            patch("src.app.shutdown_browser"),
                            patch("src.app.run_scraper", side_effect=verify_captcha) as scraper,
                            patch("src.app.run_checker", side_effect=verify_captcha) as checker,
                            patch("src.app.run_review", side_effect=verify_captcha) as review,
                            patch(
                                "src.app.run_faltantes_txt",
                                side_effect=verify_captcha,
                            ) as faltantes,
                        ):
                            self.assertEqual(0, main(argv))

                        selected = {
                            "run_scraper": scraper,
                            "run_checker": checker,
                            "run_review": review,
                            "run_faltantes_txt": faltantes,
                        }[expected]
                        self.assertTrue(selected.called)

    def test_timeout_must_be_positive(self):
        with patch("src.app.build_browser") as build:
            with self.assertRaises(SystemExit) as exc:
                main(["--captcha-timeout", "0"])
        self.assertEqual(2, exc.exception.code)
        build.assert_not_called()

    def test_server_pause_option_is_forwarded_and_must_be_positive(self):
        ctx = SimpleNamespace(checkpoint=PortalCheckpoint())
        with (
            patch("src.app.build_browser", return_value=ctx) as build,
            patch("src.app.run_scraper"),
            patch("src.app.shutdown_browser"),
        ):
            self.assertEqual(0, main(["--server-pause", "41"]))

        build.assert_called_once_with(
            captcha_timeout_seconds=300,
            server_pause_seconds=41,
        )

        with patch("src.app.build_browser") as invalid_build:
            with self.assertRaises(SystemExit) as exc:
                main(["--server-pause", "0"])
        self.assertEqual(2, exc.exception.code)
        invalid_build.assert_not_called()

    def test_keyboard_interrupt_closes_browser_without_finalized_message(self):
        ctx = SimpleNamespace(checkpoint=PortalCheckpoint())
        output = io.StringIO()
        with (
            patch("src.app.build_browser", return_value=ctx),
            patch("src.app.run_scraper", side_effect=KeyboardInterrupt),
            patch("src.app.shutdown_browser") as shutdown,
            redirect_stdout(output),
        ):
            with self.assertRaises(KeyboardInterrupt):
                main([])

        shutdown.assert_called_once_with(ctx)
        self.assertNotIn("FINALIZADO", output.getvalue())


if __name__ == "__main__":
    unittest.main()
