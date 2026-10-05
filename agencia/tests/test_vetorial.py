import unittest
from concurrent.futures import ThreadPoolExecutor
from src.services.relogio_vetorial import RelogioVetorial, comparar_vetores


class VetorialTest(unittest.TestCase):
    def test_regras_e_snapshot(self):
        r = RelogioVetorial(1)
        primeiro = r.evento_local()
        self.assertEqual(primeiro, [0, 1, 0])
        self.assertEqual(r.ao_enviar(), [0, 2, 0])
        self.assertEqual(r.ao_receber([3, 1, 2]), [3, 3, 2])
        self.assertEqual(primeiro, [0, 1, 0])

    def test_comparacoes(self):
        self.assertEqual(comparar_vetores([3, 1, 0], [3, 2, 0]), "ANTES")
        self.assertEqual(comparar_vetores([3, 1, 0], [1, 3, 0]), "CONCORRENTES")
        self.assertEqual(comparar_vetores([1, 0, 0], [1, 0, 0]), "IGUAIS")
        self.assertEqual(comparar_vetores([3, 2, 0], [3, 1, 0]), "DEPOIS")

    def test_validacao(self):
        for vetor in ([1, 0], [True, 0, 0], [-1, 0, 0]):
            with self.assertRaises(ValueError):
                RelogioVetorial(0).ao_receber(vetor)

    def test_threads(self):
        r = RelogioVetorial(0)
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(pool.map(lambda _: r.evento_local()[0], range(1000)))
        self.assertEqual(sorted(resultados), list(range(1, 1001)))
