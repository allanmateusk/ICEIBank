"""Exercita autenticação e conflitos pelo roteamento HTTP real do FastAPI."""
import os
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from src import estado
from src.main import app
from src.seguranca import criar_token
from src.services.registro_eventos import RegistroEventos
from src.services.relogio_vetorial import RelogioVetorial


class Sprint3ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = os.environ.get('PASTA_DADOS')
        os.environ['PASTA_DADOS'] = self.temp.name
        self.original = estado.registro, estado.relogio
        estado.registro = RegistroEventos('agencia-0')
        estado.relogio = RelogioVetorial(0)
        for mapping in (estado.contas, estado.versoes_contas, estado.transferencias,
                        estado.creditos_processados, estado.sincronizacoes):
            mapping.clear()
        estado.contas[300] = {'id': 300, 'nomeAluno': 'Ana', 'saldo': 100.0}
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer ' + criar_token('allan')}

    def tearDown(self):
        self.client.close()
        for mapping in (estado.contas, estado.versoes_contas, estado.transferencias,
                        estado.creditos_processados, estado.sincronizacoes):
            mapping.clear()
        estado.registro, estado.relogio = self.original
        if self.old_path is None:
            os.environ.pop('PASTA_DADOS', None)
        else:
            os.environ['PASTA_DADOS'] = self.old_path
        self.temp.cleanup()

    def test_jwt_replay_and_conflict(self):
        self.assertEqual(self.client.get('/contas/300').status_code, 401)
        conta = self.client.get('/contas/300', headers=self.headers).json()
        operacao = {'operacaoId': str(uuid4()), 'contaId': 300, 'tipo': 'DEPOSITO',
                    'valor': 10, 'vetorBase': conta['vetorVersao'],
                    'sessaoServidor': conta['sessaoServidor']}
        self.assertEqual(self.client.post('/sincronizacao', json=operacao).status_code, 401)
        first = self.client.post('/sincronizacao', json=operacao, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        replay = self.client.post('/sincronizacao', json=operacao, headers=self.headers)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(replay.json()['conta']['saldo'], 110)
        operacao['operacaoId'] = str(uuid4())
        conflito = self.client.post('/sincronizacao', json=operacao, headers=self.headers)
        self.assertEqual(conflito.status_code, 409)
        self.assertEqual(conflito.json()['detail']['relacao'], 'ANTES')


if __name__ == '__main__':
    unittest.main()
