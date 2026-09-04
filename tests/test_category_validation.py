import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from src.scraping import runner
from src.core.network import NetworkTracker, PortalRequestTimeout
from src.scraping.table import selecionar_categoria


class FakeButton:
    def __init__(self, driver, active=False):
        self.driver = driver
        self.active = active
        self.clicked = False

    def is_displayed(self):
        return True

    def get_attribute(self, name):
        if name == "class":
            return "btn active" if self.active else "btn"
        if name == "aria-pressed":
            return "true" if self.active else "false"
        return ""

    def click(self):
        self.clicked = True
        self.driver.changed = True


class FakeRow:
    def __init__(self, text):
        self.text = text


class FakeDriver:
    current_url = "https://fiesselecaoaluno.mec.gov.br/consulta"

    def __init__(self, before, after=None, active=False):
        self.before = before
        self.after = after if after is not None else before
        self.changed = False
        self.button = FakeButton(self, active=active)
        self.logs = []

    def find_elements(self, by, selector):
        if by == By.XPATH and selector.startswith("//button"):
            return [self.button]
        rows = self.after if self.changed else self.before
        return [FakeRow(text) for text in rows]

    def execute_script(self, *_args):
        return None

    def execute_cdp_cmd(self, *_args):
        return None

    def get_log(self, _kind):
        logs, self.logs = self.logs, []
        return logs


class ImmediateWebDriverWait:
    def __init__(self, driver, _timeout):
        self.driver = driver

    def until(self, predicate):
        for _ in range(2):
            if predicate(self.driver):
                return True
        raise TimeoutException("resultado não atualizado")


class CategoryValidationTests(unittest.TestCase):
    def make_context(self, driver):
        return SimpleNamespace(driver=driver, wait=Mock(), network=None)

    def test_same_row_count_with_changed_text_is_success(self):
        driver = FakeDriver(["Ampla 700", "Ampla 650"], ["PPIQ 710", "PPIQ 660"])
        ctx = self.make_context(driver)
        ctx.wait.until.return_value = driver.button

        with patch("src.scraping.table.WebDriverWait", ImmediateWebDriverWait):
            self.assertTrue(selecionar_categoria(ctx, tipo_label="PPIQ", tipo_codigo=3))
        self.assertTrue(driver.button.clicked)

    def test_already_active_category_does_not_click_again(self):
        driver = FakeDriver(["Ampla 700"], active=True)
        ctx = self.make_context(driver)
        ctx.wait.until.return_value = driver.button

        self.assertTrue(selecionar_categoria(ctx, tipo_label="Ampla", tipo_codigo=1))
        self.assertFalse(driver.button.clicked)

    def test_valid_unchanged_table_is_local_failure_without_timeout(self):
        driver = FakeDriver(["Ampla 700"])
        ctx = self.make_context(driver)
        ctx.wait.until.return_value = driver.button

        with patch("src.scraping.table.WebDriverWait", ImmediateWebDriverWait):
            self.assertFalse(selecionar_categoria(ctx, tipo_label="PPIQ", tipo_codigo=3))
        self.assertTrue(driver.button.clicked)

    def test_http_504_from_category_request_reaches_timeout_controller(self):
        driver = FakeDriver(["Ampla 700"])
        ctx = self.make_context(driver)
        tracker = NetworkTracker()
        tracker.enable(driver)
        ctx.network = tracker
        ctx.wait.until.return_value = driver.button

        original_click = driver.button.click

        def click_with_504():
            original_click()
            driver.logs = [
                {"message": json.dumps({"message": {
                    "method": "Network.requestWillBeSent",
                    "params": {
                        "requestId": "cat",
                        "type": "XHR",
                        "request": {"url": "https://fiesselecaoaluno.mec.gov.br/api/categoria", "method": "POST"},
                    },
                }})},
                {"message": json.dumps({"message": {
                    "method": "Network.responseReceived",
                    "params": {"requestId": "cat", "response": {"status": 504}},
                }})},
            ]

        driver.button.click = click_with_504
        with patch("src.scraping.table.WebDriverWait", ImmediateWebDriverWait):
            with self.assertRaises(PortalRequestTimeout):
                selecionar_categoria(ctx, tipo_label="PPIQ", tipo_codigo=3)

    def test_search_requires_network_success_and_new_result_dom(self):
        driver = FakeDriver([], ["resultado da pesquisa"])
        tracker = NetworkTracker()
        tracker.enable(driver)
        ctx = self.make_context(driver)
        ctx.network = tracker
        ctx.fast_mode = True
        ctx.wait.until.return_value = driver.button

        original_click = driver.button.click

        def click_with_success():
            original_click()
            events = [
                {"message": json.dumps({"message": {
                    "method": "Network.requestWillBeSent",
                    "params": {
                        "requestId": "search",
                        "type": "XHR",
                        "request": {"url": "https://fiesselecaoaluno.mec.gov.br/api/consulta", "method": "POST"},
                    },
                }})},
                {"message": json.dumps({"message": {
                    "method": "Network.responseReceived",
                    "params": {"requestId": "search", "response": {"status": 200}},
                }})},
                {"message": json.dumps({"message": {
                    "method": "Network.loadingFinished",
                    "params": {"requestId": "search"},
                }})},
            ]
            driver.logs = events

        driver.button.click = click_with_success
        with (
            patch("src.scraping.runner.aguardar_captcha"),
            patch("src.scraping.runner.WebDriverWait", ImmediateWebDriverWait),
        ):
            runner._pesquisar_e_aguardar(ctx)

        self.assertTrue(driver.button.clicked)

    def test_ampla_reads_initial_table_without_selecting_category(self):
        ctx = SimpleNamespace()
        with (
            patch.object(runner, "selecionar_categoria") as select_category,
            patch.object(runner, "obter_ultima_linha_pre_selecionado", return_value=object()),
            patch.object(runner, "extrair_nota_enem_de_linha", return_value="700,00"),
        ):
            self.assertEqual("700,00", runner._ler_nota_categoria(ctx, "Ampla", 1))
        select_category.assert_not_called()


if __name__ == "__main__":
    unittest.main()
