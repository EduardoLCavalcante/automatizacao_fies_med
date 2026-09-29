import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.scraping import runner
from src.scraping import table


class ResultRow:
    def __init__(self, status="", label=""):
        self.status = status
        self.text = label

    def find_elements(self, _by, selector):
        return [SimpleNamespace(text=self.text)] if self.status and selector.endswith(self.status) else []


class MissingNotesTests(unittest.TestCase):
    def test_preselected_has_priority_over_later_vencido(self):
        rows = [ResultRow("situacao-selecionado", "Pré-Selecionado"), ResultRow("situacao-vencido", "Vencido")]
        ctx = SimpleNamespace(wait=Mock(), driver=Mock())
        ctx.driver.find_elements.return_value = rows
        with patch.object(table, "expandir_todos_candidatos"):
            self.assertIs(rows[0], table.obter_ultima_linha_pre_selecionado(ctx))

    def test_last_vencido_is_fallback_when_no_preselected_exists(self):
        rows = [ResultRow("situacao-vencido", "Vencido"), ResultRow("situacao-vencido", "Vencido")]
        ctx = SimpleNamespace(wait=Mock(), driver=Mock())
        ctx.driver.find_elements.return_value = rows
        with patch.object(table, "expandir_todos_candidatos"):
            self.assertIs(rows[-1], table.obter_ultima_linha_pre_selecionado(ctx))

    def test_missing_status_returns_no_row(self):
        ctx = SimpleNamespace(wait=Mock(), driver=Mock())
        ctx.driver.find_elements.return_value = [ResultRow()]
        with patch.object(table, "expandir_todos_candidatos"):
            self.assertIsNone(table.obter_ultima_linha_pre_selecionado(ctx))

    def test_fill_merges_only_empty_notes(self):
        row = {"nota_enem_ultimo_ampla": "700,00", "nota_enem_ultimo_ppiq": "", "nota_enem_ultimo_pcd": None}
        collected = {
            "nota_enem_ultimo_ampla": "710,00",
            "nota_enem_ultimo_ppiq": "650,00",
            "nota_enem_ultimo_pcd": None,
        }
        self.assertTrue(runner._mesclar_notas_vazias(row, collected))
        self.assertEqual("700,00", row["nota_enem_ultimo_ampla"])
        self.assertEqual("650,00", row["nota_enem_ultimo_ppiq"])

    def test_targets_only_incomplete_ies_and_merges_by_code(self):
        rows = [
            {"estado": "SP", "municipio": "SANTOS", "ies": "COMPLETA (1234)",
             "nota_enem_ultimo_ampla": "700", "nota_enem_ultimo_ppiq": "650", "nota_enem_ultimo_pcd": "600"},
            {"estado": "SP", "municipio": "SANTOS", "ies": "ALVO (5678)",
             "nota_enem_ultimo_ampla": "", "nota_enem_ultimo_ppiq": "", "nota_enem_ultimo_pcd": ""},
        ]
        self.assertEqual({("SP", "SANTOS"): (set(), {"5678"})}, runner._alvos_com_notas_vazias(rows))
        self.assertTrue(runner._mesclar_nota_na_ies(rows, {
            "estado": "SP", "municipio": "SANTOS", "ies": "NOME ATUALIZADO (5678)",
            "nota_enem_ultimo_ampla": "720", "nota_enem_ultimo_ppiq": None, "nota_enem_ultimo_pcd": None,
        }))
        self.assertEqual("720", rows[1]["nota_enem_ultimo_ampla"])
        self.assertEqual("700", rows[0]["nota_enem_ultimo_ampla"])


if __name__ == "__main__":
    unittest.main()
