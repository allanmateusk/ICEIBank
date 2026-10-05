import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException
from src import estado
from src.esquemas import TransferenciaIn
from src.controllers.transferencias_controller import transferir, receber_credito
from src.services.registro_eventos import RegistroEventos
from src.services.relogio_vetorial import RelogioVetorial
from src.services.mensageria import PublicacaoRecusada


class BrokerFake:
    disponivel = True
    def __init__(self, erro=None):
        self.erro = erro
        self.mensagens = []

    async def publicar(self, rota, evento):
        self.mensagens.append((rota, evento))
        if self.erro:
            raise self.erro


class TransferenciasTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = (estado.ID_AGENCIA, estado.registro, estado.relogio)
        self.env = os.environ.get("PASTA_DADOS")
        os.environ["PASTA_DADOS"] = self.tmp.name
        estado.ID_AGENCIA = 0
        estado.registro = RegistroEventos("agencia-0")
        estado.relogio = RelogioVetorial(0)
        estado.contas.clear()
        estado.transferencias.clear()
        estado.creditos_processados.clear()
        estado.contas.update({300: {"id": 300, "saldo": 100}, 303: {"id": 303, "saldo": 10}})

    def tearDown(self):
        estado.ID_AGENCIA, estado.registro, estado.relogio = self.original
        estado.contas.clear()
        estado.transferencias.clear()
        estado.creditos_processados.clear()
        if self.env is None:
            os.environ.pop("PASTA_DADOS", None)
        else:
            os.environ["PASTA_DADOS"] = self.env
        self.tmp.cleanup()

    def request(self, broker=None):
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(mensageria=broker or BrokerFake())))

    async def test_local_e_repeticao(self):
        dados = TransferenciaIn(idOrigem=300, idDestino=303, valor=25)
        chave = str(uuid4())
        r = await transferir(dados, self.request(), chave)
        self.assertEqual(r["status"], "CONFIRMADA")
        await transferir(dados, self.request(), chave)
        self.assertEqual(estado.contas[300]["saldo"], 75)
        self.assertEqual(estado.contas[303]["saldo"], 35)
        with self.assertRaises(HTTPException) as erro:
            await transferir(TransferenciaIn(idOrigem=300, idDestino=303, valor=26), self.request(), chave)
        self.assertEqual(erro.exception.status_code, 409)

    async def test_saldo_concorrente(self):
        async def operar():
            try:
                return await transferir(TransferenciaIn(idOrigem=300, idDestino=303, valor=70), self.request(), None)
            except HTTPException as e:
                return e.status_code
        resultados = await asyncio.gather(operar(), operar())
        self.assertEqual(sum(isinstance(r, dict) for r in resultados), 1)
        self.assertEqual(estado.contas[300]["saldo"], 30)

    async def test_remota_pendente_e_idempotente(self):
        broker = BrokerFake()
        chave = str(uuid4())
        dados = TransferenciaIn(idOrigem=300, idDestino=301, valor=25)
        r = await transferir(dados, self.request(broker), chave)
        self.assertEqual(r["status"], "PENDENTE")
        await transferir(dados, self.request(broker), chave)
        self.assertEqual(len(broker.mensagens), 1)
        self.assertEqual(estado.contas[300]["saldo"], 75)

    async def test_broker_fora_sem_debito(self):
        b = BrokerFake()
        b.disponivel = False
        with self.assertRaises(HTTPException) as erro:
            await transferir(TransferenciaIn(idOrigem=300, idDestino=301, valor=25), self.request(b), None)
        self.assertEqual(erro.exception.status_code, 503)
        self.assertEqual(estado.contas[300]["saldo"], 100)

    async def test_rejeicao_diferente_de_timeout(self):
        for erro, esperado in [(PublicacaoRecusada(), "FALHA_PUBLICACAO"), (TimeoutError(), "PUBLICACAO_INCERTA")]:
            with self.assertRaises(HTTPException) as falha:
                await transferir(TransferenciaIn(idOrigem=300, idDestino=301, valor=10), self.request(BrokerFake(erro)), None)
            self.assertEqual(falha.exception.detail["status"], esperado)

    async def test_credito_reentregue_uma_vez(self):
        estado.ID_AGENCIA = 1
        estado.relogio = RelogioVetorial(1)
        estado.contas[301] = {"id": 301, "saldo": 10}
        mensagem = {"tipo": "CREDITAR", "versao": 1, "transferenciaId": str(uuid4()),
                    "idOrigem": 300, "idDestino": 301, "valor": 25,
                    "origemAgencia": 0, "destinoAgencia": 1, "vetorEnvio": [2, 0, 0]}
        receber_credito(mensagem)
        receber_credito(mensagem)
        self.assertEqual(estado.contas[301]["saldo"], 35)
        mensagem["valor"] = 30
        with self.assertRaises(ValueError):
            receber_credito(mensagem)

    async def test_destino_ausente(self):
        estado.ID_AGENCIA = 1
        estado.relogio = RelogioVetorial(1)
        mensagem = {"tipo": "CREDITAR", "versao": 1, "transferenciaId": str(uuid4()),
                    "idOrigem": 300, "idDestino": 301, "valor": 25,
                    "origemAgencia": 0, "destinoAgencia": 1, "vetorEnvio": [2, 0, 0]}
        self.assertEqual(receber_credito(mensagem)["resultado"], "CREDITO_FALHOU")
