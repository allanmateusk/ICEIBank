"""Integração Sprint 3 com RabbitMQ e PostgreSQL isolados pelo teste.

Requer os serviços locais documentados em test_integracao.py. Os processos,
vhost e schema são criados e encerrados pela fixture da Sprint 2.
"""
import time
import unittest
from uuid import uuid4

from tests import test_integracao


class Sprint3IntegracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_integracao.IntegracaoTest.setUpClass()
        cls.base = test_integracao.IntegracaoTest()

    @classmethod
    def tearDownClass(cls):
        test_integracao.IntegracaoTest.tearDownClass()

    def esperar_lider(self, agencias, lider):
        base = test_integracao.IntegracaoTest
        observado = None
        for _ in range(120):
            try:
                observado = [base.cliente.get(base.url(i) + '/bully/lider', timeout=1)
                             .json()['liderId'] for i in agencias]
                if observado == [lider] * len(agencias):
                    return
            except Exception:
                pass
            time.sleep(0.2)
        self.fail(f'Líder esperada: {lider}; observado: {observado}')

    def test_eleicao_failover_sincronizacao_e_transferencia(self):
        base = test_integracao.IntegracaoTest
        self.esperar_lider([0, 1, 2], 2)
        self.base.criar(300, 100)
        self.base.criar(301, 10)
        snapshot = self.base.chamada(0, 'GET', '/contas/300').json()
        deposito = {'operacaoId': str(uuid4()), 'contaId': 300, 'tipo': 'DEPOSITO',
                    'valor': 10, 'vetorBase': snapshot['vetorVersao'],
                    'sessaoServidor': snapshot['sessaoServidor']}
        resposta = self.base.chamada(0, 'POST', '/sincronizacao', json=deposito)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json()['conta']['saldo'], 110)
        repetida = self.base.chamada(0, 'POST', '/sincronizacao', json=deposito)
        self.assertEqual(repetida.status_code, 200, repetida.text)
        self.assertEqual(repetida.json()['conta']['saldo'], 110)
        antiga = {**deposito, 'operacaoId': str(uuid4())}
        conflito = self.base.chamada(0, 'POST', '/sincronizacao', json=antiga)
        self.assertEqual(conflito.status_code, 409, conflito.text)

        snapshot = self.base.chamada(0, 'GET', '/contas/300').json()
        transferencia = {'operacaoId': str(uuid4()), 'contaId': 300,
                         'tipo': 'TRANSFERENCIA', 'valor': 5, 'destinoId': 301,
                         'vetorBase': snapshot['vetorVersao'],
                         'sessaoServidor': snapshot['sessaoServidor']}
        resposta = self.base.chamada(0, 'POST', '/sincronizacao', json=transferencia)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.base.esperar_saldo(301, 15)
        self.base.esperar_status(transferencia['operacaoId'], 'CONFIRMADA')

        base.parar(2)
        self.esperar_lider([0, 1], 1)
        base.iniciar(2)
        self.esperar_lider([0, 1, 2], 2)
