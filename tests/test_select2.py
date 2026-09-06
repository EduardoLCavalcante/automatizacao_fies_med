"""Contratos de identidade, classificação de falhas e propagação do CAPTCHA."""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException
from src.core import CaptchaTimeoutError
from src.navigation import flow
from src.scraping import runner

s2 = importlib.import_module('src.actions.select2')


class Select2ContractsTests(unittest.TestCase):
    def test_course_requires_exact_name(self):
        self.assertIsNone(s2._candidato(['MEDICINA VETERINÁRIA'], 'MEDICINA'))
        self.assertEqual('MEDICINA', s2._candidato(['MEDICINA VETERINÁRIA', 'MEDICINA'], 'medicina'))

    def test_ies_code_disambiguates_identical_names(self):
        options = ['UNIVERSIDADE (1001)', 'UNIVERSIDADE (1002)']
        self.assertEqual(options[1], s2._candidato(options, options[1], tolerante=True))
        self.assertIsNone(s2._candidato(options, 'UNIVERSIDADE', tolerante=True))
        self.assertIsNone(s2._candidato(options, 'UNIVERSIDADE (9999)', tolerante=True))

    def test_never_selects_unrelated_first_ies(self):
        self.assertIsNone(s2._candidato(['OUTRA IES (1001)'], 'ALVO', tolerante=True))

    def test_state_suffix_and_accent_are_supported(self):
        self.assertTrue(s2._texto_selecionado('SÃO PAULO - SP', 'São Paulo'))
        self.assertFalse(s2._texto_selecionado('SÃO PAULO DO POTENGI', 'São Paulo'))

    def test_first_concept_preserves_portal_order(self):
        self.assertEqual('5', s2._candidato(['5', '3'], None))

    def test_filter_timeout_is_not_course_absence_or_outer_retry(self):
        ctx = SimpleNamespace(select2_retries=0, fast_mode=True)
        with (
            patch.object(flow, 'remove_loading_overlay'),
            patch.object(flow, 'selecionar_radio_fies_social', return_value=True),
            patch.object(flow, 'human_delay'),
            patch.object(flow, 'select2'),
            patch.object(flow, 'select2_exact', side_effect=TimeoutException()) as select_course,
            patch.object(flow.settings, 'FIES_MODALIDADE', 'social'),
        ):
            result = flow.aplicar_filtros_detalhado(ctx, 'Amazonas', 'Manaus')
        self.assertFalse(result.ok)
        self.assertEqual('falha_transitoria', result.motivo)
        select_course.assert_called_once()

    def test_captcha_timeout_propagates_from_ies_recovery(self):
        ctx = SimpleNamespace(select2_retries=0, fast_mode=True, driver=Mock())
        with (
            patch.object(s2, '_resolver_container', return_value='ies'),
            patch.object(s2, '_esperar', side_effect=TimeoutException()),
            patch.object(s2, 'aguardar_pagina_responsiva', return_value=True),
            patch.object(s2, 'aguardar_captcha', side_effect=CaptchaTimeoutError('limite')),
        ):
            with self.assertRaises(CaptchaTimeoutError):
                s2.select2_exact_multi(ctx, ['ies'], 'ALVO')

    def test_review_concept_does_not_swallow_captcha(self):
        with patch.object(runner, 'select2_pick_first', side_effect=CaptchaTimeoutError('limite')):
            with self.assertRaises(CaptchaTimeoutError):
                runner._coletar_notas_ies_review(Mock(), 'AM', 'Manaus', 'MEDICINA', 'IES')


if __name__ == '__main__':
    unittest.main()
