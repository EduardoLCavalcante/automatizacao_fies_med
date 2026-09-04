"""Smoke test humano opcional contra o portal FIES real."""

import hashlib
import os
import unittest
from pathlib import Path

from src.core import build_browser, shutdown_browser
from src.navigation import preparar_primeira_pagina


ROOT = Path(__file__).resolve().parents[1]
ARTEFATOS_OFICIAIS = (
    "notas_fies_medicina.csv",
    "notas_fies_medicina_fiesregular.csv",
    "notas_fies_medicina_falhas.csv",
    "notas_fies_medicina_faltantes.txt",
    "notas_fies_medicina_faltantes_regular.txt",
)


def _hashes_artefatos() -> dict[str, str]:
    hashes = {}
    for nome in ARTEFATOS_OFICIAIS:
        caminho = ROOT / nome
        if caminho.exists():
            hashes[nome] = hashlib.sha256(caminho.read_bytes()).hexdigest()
    return hashes


@unittest.skipUnless(
    os.environ.get("FIES_CAPTCHA_SMOKE") == "1",
    "defina FIES_CAPTCHA_SMOKE=1 para executar o smoke test humano",
)
class CaptchaPortalSmokeTest(unittest.TestCase):
    def test_operator_completes_initial_gate_and_automatic_captcha_flow(self):
        before = _hashes_artefatos()
        timeout = int(os.environ.get("FIES_CAPTCHA_SMOKE_TIMEOUT", "300"))
        ctx = build_browser(captcha_timeout_seconds=timeout)
        try:
            preparar_primeira_pagina(ctx)
        finally:
            shutdown_browser(ctx)

        self.assertEqual(before, _hashes_artefatos())


if __name__ == "__main__":
    unittest.main()
