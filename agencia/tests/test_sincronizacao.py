import os
import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException

from src import estado
from src.controllers import contas_controller, sincronizacao_controller as sync
from src.esquemas import ValorIn
from src.services.registro_eventos import RegistroEventos
from src.services.relogio_vetorial import RelogioVetorial
from src.services.versao_conta import snapshot


class SincronizacaoTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = os.environ.get("PASTA_DADOS")
        os.environ["PASTA_DADOS"] = self.temp.name
        self.original = estado.registro, estado.relogio
        estado.registro = RegistroEventos("agencia-0")
        estado.relogio = RelogioVetorial(0)
        estado.contas.clear()
        estado.versoes_contas.clear()
        estado.transferencias.clear()
        estado.creditos_processados.clear()
        estado.sincronizacoes.clear()
        estado.contas.update({300: {"id": 300, "nomeAluno": "Ana", "saldo": 100},
                              303: {"id": 303, "nomeAluno": "Bia", "saldo": 10}})
        self.request = SimpleNamespace(state=SimpleNamespace(), app=SimpleNamespace(state=SimpleNamespace(mensageria=None)))

    def tearDown(self):
        estado.registro, estado.relogio = self.original
        estado.contas.clear()
        estado.versoes_contas.clear()
        estado.transferencias.clear()
        estado.creditos_processados.clear()
        estado.sincronizacoes.clear()
        if self.old_path is None:
            os.environ.pop("PASTA_DADOS", None)
        else:
            os.environ["PASTA_DADOS"] = self.old_path
        self.temp.cleanup()

    def pedido(self, tipo="DEPOSITO", **mudancas):
        conta = snapshot(estado.contas[300])
        valores = {"operacaoId": str(uuid4()), "contaId": 300, "tipo": tipo, "valor": 10,
                   "vetorBase": conta["vetorVersao"], "sessaoServidor": conta["sessaoServidor"]}
        valores.update(mudancas)
        return sync.SincronizacaoIn(**valores)

    async def test_reenvio_deposito_e_chave_reutilizada(self):
        pedido = self.pedido()
        primeira = await sync.sincronizar(pedido, self.request)
        segunda = await sync.sincronizar(pedido, self.request)
        self.assertEqual(primeira, segunda)
        self.assertEqual(estado.contas[300]["saldo"], 110)
        with self.assertRaises(HTTPException) as erro:
            await sync.sincronizar(pedido.model_copy(update={"valor": 20}), self.request)
        self.assertEqual(erro.exception.status_code, 409)

    async def test_uuid_sincronizado_nao_pode_ser_reutilizado_na_transferencia_online(self):
        from src.controllers.transferencias_controller import transferir
        from src.esquemas import TransferenciaIn

        pedido = self.pedido(tipo="DEPOSITO")
        await sync.sincronizar(pedido, self.request)
        requisicao_online = SimpleNamespace(
            state=SimpleNamespace(), app=SimpleNamespace(state=SimpleNamespace(mensageria=None))
        )
        with self.assertRaises(HTTPException) as erro:
            await transferir(TransferenciaIn(idOrigem=300, idDestino=303, valor=10),
                             requisicao_online, str(pedido.operacaoId))
        self.assertEqual(erro.exception.status_code, 409)
        self.assertEqual(estado.contas[300]["saldo"], 110)
        self.assertEqual(estado.contas[303]["saldo"], 10)

    async def test_falha_de_log_nao_aplica_deposito_duas_vezes(self):
        pedido = self.pedido()
        with patch.object(estado.registro, "registrar", side_effect=OSError("disco indisponível")):
            with self.assertRaises(OSError):
                await sync.sincronizar(pedido, self.request)
        self.assertEqual(estado.contas[300]["saldo"], 100)
        self.assertNotIn(str(pedido.operacaoId), estado.sincronizacoes)
        resposta = await sync.sincronizar(pedido, self.request)
        self.assertEqual(resposta["conta"]["saldo"], 110)
        self.assertEqual((await sync.sincronizar(pedido, self.request))["conta"]["saldo"], 110)

    async def test_versao_desatualizada_e_concorrente(self):
        pedido = self.pedido()
        contas_controller.depositar(300, ValorIn(valor=5))
        with self.assertRaises(HTTPException) as erro:
            await sync.sincronizar(pedido, self.request)
        self.assertEqual(erro.exception.detail["relacao"], "ANTES")
        concorrente = self.pedido(vetorBase=[0, 1, 0])
        with self.assertRaises(HTTPException) as erro:
            await sync.sincronizar(concorrente, self.request)
        self.assertEqual(erro.exception.detail["relacao"], "CONCORRENTES")
        self.assertEqual(estado.contas[300]["saldo"], 105)

    async def test_sessao_e_saldo_insuficiente(self):
        with self.assertRaises(HTTPException) as erro:
            await sync.sincronizar(self.pedido(sessaoServidor="sessao-antiga"), self.request)
        self.assertEqual(erro.exception.detail["codigo"], "SESSAO_ALTERADA")
        with self.assertRaises(HTTPException) as erro:
            await sync.sincronizar(self.pedido(tipo="SAQUE", valor=101), self.request)
        self.assertEqual(erro.exception.status_code, 400)
        self.assertEqual(estado.contas[300]["saldo"], 100)

    async def test_transferencia_local_replay(self):
        pedido = self.pedido(tipo="TRANSFERENCIA", destinoId=303)
        primeira = await sync.sincronizar(pedido, self.request)
        repeticao = await sync.sincronizar(pedido, self.request)
        self.assertEqual(primeira, repeticao)
        self.assertEqual(primeira["transferencia"]["status"], "CONFIRMADA")
        self.assertEqual(estado.contas[300]["saldo"], 90)
        self.assertEqual(estado.contas[303]["saldo"], 20)

    async def test_publicacao_incerta_retry_nao_duplica_debito(self):
        class Broker:
            disponivel = True
            chamadas = 0
            async def publicar(self, rota, evento):
                self.chamadas += 1
                raise TimeoutError("resposta perdida")
        broker = Broker()
        self.request.app.state.mensageria = broker
        pedido = self.pedido(tipo="TRANSFERENCIA", destinoId=301)
        with self.assertRaises(HTTPException) as erro:
            await sync.sincronizar(pedido, self.request)
        self.assertEqual(erro.exception.status_code, 502)
        resposta = await sync.sincronizar(pedido, self.request)
        self.assertEqual(resposta["transferencia"]["status"], "PUBLICACAO_INCERTA")
        self.assertEqual(estado.contas[300]["saldo"], 90)
        self.assertEqual(broker.chamadas, 1)

    async def test_concorrencia_de_mesma_versao(self):
        pedido1 = self.pedido(valor=60, tipo="SAQUE")
        pedido2 = self.pedido(valor=60, tipo="SAQUE")
        resultados = await asyncio.gather(sync.sincronizar(pedido1, self.request),
                                           sync.sincronizar(pedido2, self.request),
                                           return_exceptions=True)
        self.assertEqual(sum(isinstance(r, dict) for r in resultados), 1)
        self.assertEqual(estado.contas[300]["saldo"], 40)

    async def test_credito_remoto_altera_versao_uma_vez(self):
        from src.controllers.transferencias_controller import receber_credito
        agencia_original = estado.ID_AGENCIA
        try:
            estado.ID_AGENCIA = 1
            estado.relogio = RelogioVetorial(1)
            estado.contas[301] = {"id": 301, "nomeAluno": "Ana", "saldo": 10}
            evento = {"tipo": "CREDITAR", "versao": 1, "transferenciaId": str(uuid4()),
                      "idOrigem": 300, "idDestino": 301, "valor": 25,
                      "origemAgencia": 0, "destinoAgencia": 1, "vetorEnvio": [2, 0, 0]}
            receber_credito(evento)
            versao = snapshot(estado.contas[301])["vetorVersao"]
            self.assertEqual(versao, [2, 1, 0])
            receber_credito(evento)
            self.assertEqual(snapshot(estado.contas[301])["vetorVersao"], versao)
            self.assertEqual(estado.contas[301]["saldo"], 35)
        finally:
            estado.ID_AGENCIA = agencia_original


if __name__ == "__main__":
    unittest.main()
