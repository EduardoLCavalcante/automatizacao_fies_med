"""Opt-in: Select2 real em Chrome, sem consultar o portal ou escrever CSVs.

FIES_SELECT2_SMOKE=1 habilita; FIES_SELECT2_EVIDENCE aponta para pasta externa.
Requer Chrome e acesso ao CDN das versões fixadas de jQuery e Select2.
"""

import importlib
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
import unittest
from unittest.mock import patch, mock_open
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

from src.core.browser import BrowserContext
from src.scraping import runner
from src.scraping.table import selecionar_categoria
from src.navigation.flow import aplicar_filtros, aplicar_filtros_detalhado
import src.config.settings as settings

s2 = importlib.import_module('src.actions.select2')


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        scenario = query.get('scenario', [''])[0]
        if url.path == '/':
            body = (Path(__file__).parent / 'fixtures' / 'select2.html').read_bytes()
            content_type = 'text/html; charset=utf-8'
        elif url.path == '/ies':
            if scenario in ('slow', 'stale-results'):
                time.sleep(1.2)
            rows = [{'id': '1001', 'text': 'UNIVERSIDADE TESTE (1001)'},
                    {'id': '1002', 'text': 'UNIVERSIDADE TESTE (1002)'}]
            term = query.get('q', [''])[0].upper()
            if scenario == 'stale-results' and term:
                rows = [rows[0]]  # a opção antiga 1002 desapareceu na resposta atual
            if scenario == 'first-page':
                rows = [{'id': str(code), 'text': f'UNIVERSIDADE TESTE ({code})'}
                        for code in range(1001, 1041)]
            rows = [r for r in rows if term in r['text']]
            page = int(query.get('page', ['1'])[0])
            if scenario == 'pages':
                more = page == 1 and len(rows) > 1
                rows = rows[page-1:page]
            elif scenario == 'first-page':
                more = page == 1
                if not more:
                    rows = [{'id': '2001', 'text': 'UNIVERSIDADE TESTE (2001)'}]
            else:
                more = False
            body = json.dumps({'results': rows, 'pagination': {'more': more}}).encode()
            content_type = 'application/json'
        elif url.path == '/background':
            time.sleep(8)
            body = b'{}'
            content_type = 'application/json'
        elif url.path == '/options':
            time.sleep(0.15 if scenario != 'slow' else 0.8)
            rows = {
                'noMunicipio': [('Manaus', 'MANAUS'), ('Parintins', 'PARINTINS')],
                'noCursosPublico': [('1', 'MEDICINA'), ('2', 'MEDICINA VETERINÁRIA')],
                'iesPublico': [],
                'conceitoCurso': [('5', '5'), ('3', '3')],
            }.get(query.get('field', [''])[0], [])
            if scenario == 'missing' and query.get('field') == ['noCursosPublico']:
                rows = [('2', 'MEDICINA VETERINÁRIA')]
            body = json.dumps([{'id': key, 'text': value} for key, value in rows]).encode()
            content_type = 'application/json'
        else:
            self.send_error(404)
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


@unittest.skipUnless(os.environ.get('FIES_SELECT2_SMOKE') == '1', 'smoke Select2 opt-in')
class Select2BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        Thread(target=cls.server.serve_forever, daemon=True).start()
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1440,1400')
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        cls.driver = webdriver.Chrome(options=options)
        cls.driver.set_page_load_timeout(30)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        cls.server.shutdown()
        cls.server.server_close()

    def load(self, scenario=''):
        self.driver.get(f'http://127.0.0.1:{self.server.server_port}/?scenario={scenario}')
        WebDriverWait(self.driver, 15).until(lambda d: d.execute_script('return window.ready === true'))
        self.ctx = BrowserContext(self.driver, WebDriverWait(self.driver, 5), fast_mode=True)
        self.assertEqual('FIES — teste local de Select2', self.driver.title)
        self.assertIn('validação local', self.driver.find_element('tag name', 'body').text)

    def setUp(self):
        timeout_patch = patch.object(s2, '_limite', return_value=8)
        timeout_patch.start()
        self.addCleanup(timeout_patch.stop)

    def counts(self):
        return self.driver.execute_script('return window.opens')

    def select_ies(self):
        return s2.select2_exact_multi(self.ctx, ['select2-iesPublico-container'], 'UNIVERSIDADE TESTE (1002)')

    def screenshot(self, name):
        directory = os.environ.get('FIES_SELECT2_EVIDENCE')
        if directory:
            self.driver.save_screenshot(str(Path(directory) / name))

    def test_pipeline_single_open_and_reset_both_modalities(self):
        for modalidade in ('social', 'regular'):
            with self.subTest(modalidade=modalidade), patch.object(settings, 'FIES_MODALIDADE', modalidade):
                self.load()
                self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
                radio_id = 'stCadunicoS' if modalidade == 'social' else 'stCadunicoN'
                self.assertTrue(self.driver.find_element('id', radio_id).is_selected())
                self.assertTrue(self.select_ies())
                self.assertTrue(s2.select2_pick_first(self.ctx, 'select2-conceitoCurso-container'))
                self.assertEqual('5', self.driver.find_element('id', 'select2-conceitoCurso-container').text)
                expected = {key: 1 for key in ('noEstado','noMunicipio','noCursosPublico','iesPublico','conceitoCurso')}
                self.assertEqual(expected, self.counts())
                self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
                self.assertTrue(self.select_ies())
                self.assertTrue(s2.select2_pick_first(self.ctx, 'select2-conceitoCurso-container'))
                self.assertEqual(expected, self.counts())
                self.screenshot(f'select2-{modalidade}-single-open.png')
                self.driver.find_element('id', 'reset').click()
                self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Parintins'))
                self.assertEqual(2, self.counts()['noEstado'])
                self.assertEqual(2, self.counts()['noMunicipio'])
                self.assertEqual(2, self.counts()['noCursosPublico'])
                errors = [entry for entry in self.driver.get_log('browser')
                          if entry['level'] == 'SEVERE' and 'favicon.ico' not in entry['message']]
                self.assertEqual([], errors)

    def test_slow_response_does_not_reopen(self):
        self.load('slow')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        self.assertTrue(self.select_ies())
        self.assertEqual(1, self.counts()['iesPublico'])
        self.assertEqual(0, self.ctx.select2_retries)

    def test_missing_course_is_confirmed_without_retry(self):
        self.load('missing')
        result = aplicar_filtros_detalhado(self.ctx, 'Amazonas', 'Manaus')
        self.assertFalse(result.ok)
        self.assertEqual('indisponivel_confirmado', result.motivo)
        self.assertEqual(1, self.counts()['noCursosPublico'])
        self.assertEqual(0, self.ctx.select2_retries)

    def test_failure_retries_only_failed_field(self):
        self.load('retry')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        with patch.object(s2, '_limite', return_value=1.6):
            self.assertTrue(self.select_ies())
        self.assertEqual(2, self.counts()['iesPublico'])
        self.assertEqual(1, self.counts()['noMunicipio'])
        self.assertEqual(1, self.ctx.select2_retries)

    def test_late_selection_is_not_clicked_again(self):
        self.load('late')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        with patch.object(s2, '_limite', return_value=1.6), patch.object(
            s2, 'aguardar_pagina_responsiva', side_effect=lambda *_a, **_kw: (time.sleep(1.8) or True)
        ):
            self.assertTrue(self.select_ies())
        self.assertEqual(1, self.counts()['iesPublico'])

    def test_permanent_failure_has_three_attempts_total(self):
        self.load('fail')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        with patch.object(s2, '_limite', return_value=1.6):
            self.assertFalse(self.select_ies())
        self.assertEqual(3, self.counts()['iesPublico'])
        self.assertEqual(1, self.counts()['noMunicipio'])

    def test_enumeration_paginates_without_reopening(self):
        self.load('pages')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        options = s2.listar_opcoes_select2_multi(self.ctx, ['select2-iesPublico-container'])
        self.assertEqual(['UNIVERSIDADE TESTE (1001)', 'UNIVERSIDADE TESTE (1002)'], options)
        self.assertEqual(1, self.counts()['iesPublico'])

    def test_dom_recreated_during_poll_does_not_reopen(self):
        self.load()
        original = s2._resultados
        replaced = False

        def recreate(ctx, cid):
            nonlocal replaced
            result = original(ctx, cid)
            if cid == 'select2-noMunicipio-container' and not replaced:
                replaced = True
                option = result.find_element('css selector', '.select2-results__option')
                self.driver.execute_script('$(arguments[0]).replaceWith($(arguments[0]).clone(true,true))', option)
                # Simula o consumidor que leu uma referência removida entre polls.
                option.get_attribute('id')
            return result

        with patch.object(s2, '_resultados', side_effect=recreate):
            self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        self.assertTrue(replaced)
        self.assertEqual(1, self.counts()['noMunicipio'])
        self.assertEqual(0, self.ctx.select2_retries)

    def test_collection_does_not_reapply_municipality_or_course(self):
        self.load()
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        with (
            patch.object(runner, 'com_retry_timeout'),
            patch.object(runner, 'selecionar_categoria', return_value=False),
            patch.object(runner, 'human_delay'),
            patch.object(runner, 'salvar_incremental') as save,
            patch.object(runner, 'salvar_falha_ies') as failure,
        ):
            runner.buscar_notas_por_municipio(
                self.ctx, 'Manaus', 'Amazonas', 'AM', salvar_automatico=False,
                registrar_falha=False, ies_alvo_codigo={'1002'},
            )
        save.assert_not_called()
        failure.assert_not_called()
        self.assertEqual(1, self.counts()['noEstado'])
        self.assertEqual(1, self.counts()['noMunicipio'])
        self.assertEqual(1, self.counts()['noCursosPublico'])
        self.assertEqual(2, self.counts()['iesPublico'])  # enumeração + seleção

    def test_checker_keeps_filters_between_institutions(self):
        self.load()
        rows = [{'estado': 'AM', 'municipio': 'Manaus', 'ies': f'UNIVERSIDADE TESTE ({code})',
                 'conceito_curso': ''} for code in ('1001', '1002')]
        with (
            patch.object(runner, 'carregar_progresso', return_value=(rows, set(), None, {})),
            patch.object(runner, '_carregar_faltantes_conceito', return_value=(
                set(), {('AM', 'Manaus', '1001'), ('AM', 'Manaus', '1002')}, [('AM', 'Manaus')]
            )),
            patch.object(runner, 'preparar_primeira_pagina'),
            patch.object(runner, 'ESTADOS', {'AM': 'Amazonas'}),
            patch.object(runner, 'human_delay'),
            patch.object(runner, 'salvar_csv_completo') as save,
            patch('src.scraping.runner.open', mock_open(read_data=''), create=True),
        ):
            runner.run_checker(self.ctx, caminho_csv='fixture-only.csv')
        self.assertEqual(['5', '5'], [row['conceito_curso'] for row in rows])
        self.assertEqual(1, self.counts()['noEstado'])
        self.assertEqual(1, self.counts()['noMunicipio'])
        self.assertEqual(1, self.counts()['noCursosPublico'])
        self.assertEqual(3, self.counts()['iesPublico'])  # enumeração + duas IES
        self.assertEqual(2, self.counts()['conceitoCurso'])
        save.assert_called_once()

    def test_unrelated_request_does_not_block_select(self):
        self.load()
        self.driver.execute_script("$.getJSON('/background')")
        s2.select2(self.ctx, 'select2-noEstado-container', 'Amazonas')
        self.assertGreater(self.driver.execute_script('return $.active'), 0)
        self.assertEqual(1, self.counts()['noEstado'])

    def test_selection_finds_target_on_later_page(self):
        self.load('pages')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        self.assertTrue(self.select_ies())
        self.assertEqual(1, self.counts()['iesPublico'])

    def test_identified_target_does_not_enumerate_later_pages(self):
        self.load('first-page')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        self.assertTrue(self.select_ies())
        self.assertNotIn('2', self.driver.execute_script('return window.iesPages'))

    def test_search_does_not_select_stale_results(self):
        self.load('stale-results')
        self.assertTrue(aplicar_filtros(self.ctx, 'Amazonas', 'Manaus'))
        cid = 'select2-iesPublico-container'
        s2.esperar_select2_habilitado(self.ctx, cid)
        self.driver.find_element('id', cid).click()
        WebDriverWait(self.driver, 5).until(lambda _: not s2._opcoes_visiveis(self.ctx, cid)['loading'])
        self.assertFalse(self.select_ies())
        self.assertFalse(s2._confirmado(self.ctx, cid, 'UNIVERSIDADE TESTE (1002)'))
        self.assertEqual(0, self.ctx.select2_retries)

    def test_category_with_same_row_count_returns_after_update(self):
        for scenario in ('', 'category-inplace'):
            with self.subTest(scenario=scenario):
                self.load(scenario)
                started = time.monotonic()
                self.assertTrue(selecionar_categoria(self.ctx, 'PPIQ', 3))
                self.assertLess(time.monotonic() - started, 3)
                self.assertIn('Categoria 3', self.driver.find_element('id', 'listaResultadoConsulta').text)

    def test_category_without_update_does_not_authorize_reading_old_table(self):
        self.load('category-fail')
        self.assertFalse(selecionar_categoria(self.ctx, 'PPIQ', 3))


if __name__ == '__main__':
    unittest.main()
