"""Falhas de escrita não devem deixar uma operação bancária pela metade."""
import os
import tempfile
import unittest
import builtins
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from src import estado
from src.controllers import contas_controller as contas
from src.controllers import transferencias_controller as transferencias
from src.esquemas import CriarContaIn, TransferenciaIn, ValorIn
from src.services.registro_eventos import RegistroEventos
from src.services.relogio_vetorial import RelogioVetorial


class FalhaRegistroTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = os.environ.get('PASTA_DADOS')
        os.environ['PASTA_DADOS'] = self.temp.name
        self.original = estado.ID_AGENCIA, estado.registro, estado.relogio
        estado.ID_AGENCIA = 0
        estado.registro = RegistroEventos('agencia-0')
        estado.relogio = RelogioVetorial(0)
        for m in (estado.contas, estado.versoes_contas, estado.transferencias,
                  estado.creditos_processados, estado.sincronizacoes):
            m.clear()
        estado.contas.update({300: {'id': 300, 'saldo': 100}, 303: {'id': 303, 'saldo': 10}})
        estado.versoes_contas.update({300: [1, 0, 0], 303: [2, 0, 0]})

    def tearDown(self):
        estado.ID_AGENCIA, estado.registro, estado.relogio = self.original
        for m in (estado.contas, estado.versoes_contas, estado.transferencias,
                  estado.creditos_processados, estado.sincronizacoes):
            m.clear()
        if self.old_path is None:
            os.environ.pop('PASTA_DADOS', None)
        else:
            os.environ['PASTA_DADOS'] = self.old_path
        self.temp.cleanup()

    def test_contas_sem_mutacao_quando_log_falha(self):
        with patch.object(estado.registro, 'registrar', side_effect=OSError('disco')):
            for operacao in (lambda: contas.depositar(300, ValorIn(valor=10)),
                             lambda: contas.sacar(300, ValorIn(valor=10)),
                             lambda: contas.criar_conta(CriarContaIn(id=306, nomeAluno='A', saldoInicial=10))):
                with self.assertRaises(OSError):
                    operacao()
        self.assertEqual(estado.contas[300]['saldo'], 100)
        self.assertEqual(estado.versoes_contas[300], [1, 0, 0])
        self.assertNotIn(306, estado.contas)

    def test_falha_de_commit_nao_deixa_saldo_alterado(self):
        with patch('src.banco.salvar_estado', side_effect=OSError('banco indisponivel')):
            with self.assertRaises(OSError):
                contas.depositar(300, ValorIn(valor=10))
        self.assertEqual(estado.contas[300]['saldo'], 100)
        self.assertEqual(estado.versoes_contas[300], [1, 0, 0])
        try:
            with self.assertRaises(Exception) as erro:
                contas.depositar(300, ValorIn(valor=5))
            self.assertEqual(erro.exception.status_code, 503)
            with self.assertRaises(Exception) as erro:
                contas.consultar_saldo(300)
            self.assertEqual(erro.exception.status_code, 503)
        finally:
            estado.reconciliacao_necessaria = False

    def test_registro_remove_escrita_parcial_do_lote(self):
        registro = estado.registro
        registro.registrar('ANTES', [1, 0, 0], {})
        abertura_real = builtins.open

        class ArquivoComFalha:
            def __init__(self, arquivo):
                self.arquivo = arquivo
            def __enter__(self):
                self.arquivo.__enter__()
                return self
            def __exit__(self, *args):
                return self.arquivo.__exit__(*args)
            def __getattr__(self, nome):
                return getattr(self.arquivo, nome)
            def write(self, linhas):
                self.arquivo.write(linhas[:len(linhas) // 2])
                self.arquivo.flush()
                raise OSError('escrita parcial')

        def abrir_com_falha(*args, **kwargs):
            return ArquivoComFalha(abertura_real(*args, **kwargs))

        with patch('builtins.open', side_effect=abrir_com_falha):
            with self.assertRaises(OSError):
                registro.registrar_lote([('DEBITO', [2, 0, 0], {}), ('CREDITO', [3, 0, 0], {})])
        self.assertEqual([e['tipo'] for e in registro.ler()], ['ANTES'])
        self.assertEqual(registro.registrar('DEPOIS', [4, 0, 0], {})['sequencia'], 2)

    async def test_transferencia_nao_debita_nem_publica_apos_falha(self):
        class Broker:
            disponivel = True
            mensagens = []
            async def publicar(self, rota, evento):
                self.mensagens.append(evento)
        broker = Broker()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(mensageria=broker)))
        for destino in (303, 301):
            chave = str(uuid4())
            pedido = TransferenciaIn(idOrigem=300, idDestino=destino, valor=10)
            versao_antes = estado.versoes_contas[300].copy()
            with patch.object(estado.registro, 'registrar_lote', side_effect=OSError('disco')):
                with self.assertRaises(OSError):
                    await transferencias.transferir(pedido, request, chave)
            self.assertEqual(estado.contas[300]['saldo'], 100)
            self.assertEqual(estado.contas[303]['saldo'], 10)
            self.assertEqual(estado.versoes_contas[300], versao_antes)
            self.assertNotIn(chave, estado.transferencias)
            self.assertEqual(broker.mensagens, [])
            resultado = await transferencias.transferir(pedido, request, chave)
            self.assertIn(resultado['status'], ('CONFIRMADA', 'PENDENTE'))
            await transferencias.transferir(pedido, request, chave)
            self.assertEqual(estado.contas[300]['saldo'], 90)
            estado.contas[300]['saldo'] = 100
            estado.contas[303]['saldo'] = 10
            broker.mensagens.clear()

    def test_credito_remoto_retentavel_apos_falha(self):
        estado.ID_AGENCIA = 1
        estado.relogio = RelogioVetorial(1)
        estado.contas[301] = {'id': 301, 'saldo': 10}
        mensagem = {'tipo': 'CREDITAR', 'versao': 1, 'transferenciaId': str(uuid4()),
                    'idOrigem': 300, 'idDestino': 301, 'valor': 25,
                    'origemAgencia': 0, 'destinoAgencia': 1, 'vetorEnvio': [2, 0, 0]}
        with patch.object(estado.registro, 'registrar', side_effect=OSError('disco')):
            with self.assertRaises(OSError):
                transferencias.receber_credito(mensagem)
        self.assertEqual(estado.contas[301]['saldo'], 10)
        self.assertNotIn(mensagem['transferenciaId'], estado.creditos_processados)
        transferencias.receber_credito(mensagem)
        transferencias.receber_credito(mensagem)
        self.assertEqual(estado.contas[301]['saldo'], 35)
