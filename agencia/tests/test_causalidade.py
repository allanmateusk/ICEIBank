import unittest
from mesclar_logs import analisar


class CausalidadeTest(unittest.TestCase):
    def evento(self, agencia, vetor, sessao="unica"):
        return {"agencia": agencia, "timestampVetorial": vetor, "sessaoProcesso": sessao}

    def test_causal_nao_e_concorrente(self):
        debito = self.evento("agencia-0", [2, 0, 0])
        credito = self.evento("agencia-1", [3, 1, 0])
        self.assertEqual(analisar([debito, credito]), [])

    def test_independentes_concorrentes(self):
        a, b = self.evento("agencia-0", [1, 0, 0]), self.evento("agencia-1", [0, 1, 0])
        self.assertEqual(analisar([a, b]), [(a, b)])

    def test_reinicio_nao_gera_inferencia_falsa(self):
        with self.assertRaises(ValueError):
            analisar([self.evento("agencia-0", [2, 0, 0], "antes"),
                      self.evento("agencia-0", [1, 0, 0], "depois")])

    def test_log_legado_preservado(self):
        self.assertEqual(analisar([{"agencia": "agencia-0", "timestampLamport": 5}]), [])
