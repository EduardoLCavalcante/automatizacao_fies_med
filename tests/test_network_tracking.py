import json
import unittest

from selenium.common.exceptions import TimeoutException
from src.core.network import NetworkTracker, PortalRequestTimeout


def _log(method, **params):
    return {"message": json.dumps({"message": {"method": method, "params": params}})}


class FakeDriver:
    current_url = "https://fiesselecaoaluno.mec.gov.br/consulta"

    def __init__(self):
        self.logs = []
        self.cdp_commands = []

    def execute_cdp_cmd(self, command, params):
        self.cdp_commands.append((command, params))

    def get_log(self, kind):
        self.assert_log_kind = kind
        logs, self.logs = self.logs, []
        return logs


def _request(request_id="1", url="https://fiesselecaoaluno.mec.gov.br/api/consulta"):
    return _log(
        "Network.requestWillBeSent",
        requestId=request_id,
        type="XHR",
        request={"url": url, "method": "POST"},
    )


class NetworkTrackerTests(unittest.TestCase):
    def test_http_504_is_classified_as_busy_without_exposing_payload(self):
        driver = FakeDriver()
        tracker = NetworkTracker()
        self.assertTrue(tracker.enable(driver))
        operation = tracker.begin(driver)
        driver.logs = [
            _request(),
            _log(
                "Network.responseReceived",
                requestId="1",
                response={"status": 504, "url": "https://fiesselecaoaluno.mec.gov.br/api/consulta?token=secret"},
            ),
            _log("Network.loadingFinished", requestId="1"),
        ]

        snapshot = tracker.snapshot(driver, operation)

        self.assertTrue(snapshot.available)
        self.assertTrue(snapshot.has_busy)
        self.assertFalse(snapshot.has_success)
        self.assertNotIn("token", snapshot.description)
        self.assertEqual("POST https://fiesselecaoaluno.mec.gov.br/api/consulta HTTP 504", snapshot.description)
        self.assertTrue(issubclass(PortalRequestTimeout, TimeoutException))

    def test_pending_request_is_not_success_and_external_events_are_ignored(self):
        driver = FakeDriver()
        tracker = NetworkTracker()
        tracker.enable(driver)
        operation = tracker.begin(driver)
        driver.logs = [
            _request(),
            _request("external", "https://www.google-analytics.com/collect"),
        ]

        snapshot = tracker.snapshot(driver, operation)

        self.assertTrue(snapshot.pending)
        self.assertFalse(snapshot.has_success)
        self.assertEqual(1, len(snapshot.requests))

    def test_successful_request_is_available_after_finished(self):
        driver = FakeDriver()
        tracker = NetworkTracker()
        tracker.enable(driver)
        operation = tracker.begin(driver)
        driver.logs = [
            _request(),
            _log("Network.responseReceived", requestId="1", response={"status": 200}),
            _log("Network.loadingFinished", requestId="1"),
        ]

        snapshot = tracker.snapshot(driver, operation)

        self.assertTrue(snapshot.has_success)
        self.assertFalse(snapshot.pending)
        self.assertFalse(snapshot.has_busy)

    def test_unavailable_performance_log_uses_dom_fallback(self):
        class NoLogDriver:
            current_url = "https://fiesselecaoaluno.mec.gov.br/consulta"

            def execute_cdp_cmd(self, *_args):
                raise AttributeError("performance log unavailable")

        driver = NoLogDriver()
        tracker = NetworkTracker()
        self.assertFalse(tracker.enable(driver))
        snapshot = tracker.snapshot(driver, tracker.begin(driver))
        self.assertFalse(snapshot.available)


if __name__ == "__main__":
    unittest.main()
