"""Consistência entre saldo, histórico confirmado e exportação JSONL."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from src import estado
from src.controllers import contas_controller, historico_controller
from src.esquemas import CriarContaIn, ValorIn
from src.services.registro_eventos import RegistroEventos
from src.services.relogio_vetorial import RelogioVetorial


class HistoricoTransacionalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_anterior = os.environ.get("PASTA_DADOS")
        os.environ["PASTA_DADOS"] = self.temp.name
        self.original = (estado.registro, estado.relogio, estado.ID_AGENCIA,
                         estado._snapshot(), estado.reconciliacao_necessaria)
        estado.ID_AGENCIA = 0
        estado.registro = RegistroEventos("agencia-0")
        estado.relogio = RelogioVetorial(0)
        estado._restaurar({"contas": {300: {"id": 300, "nomeAluno": "Teste", "saldo": 100}},
                           "versoes_contas": {300: [0, 0, 0]}})
        estado.reconciliacao_necessaria = False
        self.db = copy.deepcopy(estado._snapshot())
        self.patches = [patch("src.banco.ativo", return_value=True),
                        patch("src.banco.carregar_estado", side_effect=lambda _: copy.deepcopy(self.db))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        estado.registro, estado.relogio, estado.ID_AGENCIA, dados, estado.reconciliacao_necessaria = self.original
        estado._restaurar(dados)
        if self.path_anterior is None:
            os.environ.pop("PASTA_DADOS", None)
        else:
            os.environ["PASTA_DADOS"] = self.path_anterior
        self.temp.cleanup()

    def salvar(self, _, dados):
        self.db = copy.deepcopy(dados)

    def reiniciar(self):
        estado.registro = RegistroEventos("agencia-0")
        estado.relogio = RelogioVetorial(0)
        estado.reconciliacao_necessaria = False
        estado.carregar()

    def test_commit_falhou_sem_aplicar_nem_criar_evento_fantasma(self):
        with patch("src.banco.salvar_estado", side_effect=OSError("sem commit")):
            with self.assertRaises(OSError):
                contas_controller.depositar(300, ValorIn(valor=10))
        self.assertEqual(estado.registro.ler(), [])
        with self.assertRaises(HTTPException) as falha:
            historico_controller.historico(300)
        self.assertEqual(falha.exception.status_code, 503)
        self.reiniciar()
        self.assertEqual(estado.contas[300]["saldo"], 100)
        self.assertEqual(historico_controller.historico(300)["eventos"], [])
        self.assertEqual(estado.registro.ler(), [])

    def test_commit_ambiguo_confirmado_recupera_saldo_e_evento_uma_vez(self):
        def gravar_depois_falhar(agencia, dados):
            self.salvar(agencia, dados)
            raise OSError("resposta do commit perdida")
        with patch("src.banco.salvar_estado", side_effect=gravar_depois_falhar):
            with self.assertRaises(OSError):
                contas_controller.depositar(300, ValorIn(valor=10))
        self.assertEqual(estado.registro.ler(), [])
        self.reiniciar()
        self.assertEqual(estado.contas[300]["saldo"], 110)
        self.assertEqual([e["tipo"] for e in historico_controller.historico(300)["eventos"]], ["DEPOSITO"])
        self.assertEqual([e["tipo"] for e in estado.registro.ler()], ["DEPOSITO"])
        self.reiniciar()
        self.assertEqual(len(estado.registro.ler()), 1)

    def test_falha_de_exportacao_nao_apaga_operacao_e_reconcilia(self):
        with patch("src.banco.salvar_estado", side_effect=self.salvar), \
             patch.object(estado.registro, "exportar_confirmados", side_effect=OSError("disco")):
            resposta = contas_controller.depositar(300, ValorIn(valor=10))
        self.assertEqual(resposta["saldo"], 110)
        self.assertEqual(estado.registro.ler(), [])
        self.assertEqual(len(historico_controller.historico(300)["eventos"]), 1)
        self.reiniciar()
        self.assertEqual(len(estado.registro.ler()), 1)
        self.assertEqual(estado.contas[300]["saldo"], 110)

    def test_migracao_preserva_eventos_legados_sem_duplicar(self):
        # Um banco da versão anterior não tinha histórico no snapshot.
        # Os arquivos existentes são preservados na primeira atualização.
        self.db.pop("historico_bancario")
        estado.registro.registrar("CRIAR_CONTA", [1, 0, 0], {"id": 300})
        estado.registro.registrar("BULLY_LIDER_ELEITA", [2, 0, 0], {"liderId": 0})
        self.reiniciar()
        self.assertEqual([e["tipo"] for e in historico_controller.historico(300)["eventos"]], ["CRIAR_CONTA"])
        with patch("src.banco.salvar_estado", side_effect=self.salvar):
            contas_controller.depositar(300, ValorIn(valor=10))
        self.reiniciar()
        tipos = [e["tipo"] for e in estado.registro.ler()]
        self.assertEqual(tipos.count("CRIAR_CONTA"), 1)
        self.assertEqual(tipos.count("DEPOSITO"), 1)
        self.assertEqual(tipos.count("BULLY_LIDER_ELEITA"), 1)
        self.assertEqual([e["tipo"] for e in historico_controller.historico(300)["eventos"]], ["CRIAR_CONTA", "DEPOSITO"])

    def test_banco_novo_nao_importa_eventos_de_outra_execucao(self):
        estado.registro.registrar("DEPOSITO", [1, 0, 0], {"id": 300, "valor": 50})
        # O arquivo é preservado, mas não pertence ao banco vazio.
        with patch("src.banco.carregar_estado", return_value=None):
            estado._restaurar({})
            estado.carregar()
        self.assertEqual(estado.historico_bancario, [])
        self.assertEqual([e["tipo"] for e in estado.registro.ler()], ["DEPOSITO"])
        with patch("src.banco.salvar_estado", side_effect=self.salvar):
            contas_controller.criar_conta(CriarContaIn(id=300, nomeAluno="Nova conta", saldoInicial=10))
        self.assertEqual([e["tipo"] for e in historico_controller.historico(300)["eventos"]], ["CRIAR_CONTA"])
        self.reiniciar()
        self.assertEqual([e["tipo"] for e in historico_controller.historico(300)["eventos"]], ["CRIAR_CONTA"])
        self.assertEqual([e["tipo"] for e in estado.registro.ler()], ["DEPOSITO", "CRIAR_CONTA"])

    def test_linha_final_truncada_e_preservada_e_evento_confirmado_recuperado(self):
        with patch("src.banco.salvar_estado", side_effect=self.salvar), \
             patch.object(estado.registro, "exportar_confirmados", side_effect=OSError("antes da escrita")):
            contas_controller.depositar(300, ValorIn(valor=10))
        arquivo = Path(estado.registro.caminho_arquivo)
        fragmento = b'{"agencia":"agencia-0","tipo":"DEPOS'
        arquivo.write_bytes(fragmento)
        self.reiniciar()
        self.assertEqual(estado.contas[300]["saldo"], 110)
        self.assertEqual([e["tipo"] for e in estado.registro.ler()], ["DEPOSITO"])
        copias = list(arquivo.parent.glob(arquivo.name + ".corrompido-*.bak"))
        self.assertEqual(len(copias), 1)
        self.assertEqual(copias[0].read_bytes(), fragmento)
        self.reiniciar()
        self.assertEqual(len(estado.registro.ler()), 1)

    def test_corrompimento_interno_nao_e_reparado_automaticamente(self):
        arquivo = Path(estado.registro.caminho_arquivo)
        valido = json.dumps({"tipo": "LEGADO"}).encode("utf-8")
        conteudo = valido + b'\n{"invalido":\n' + valido + b'\n'
        arquivo.write_bytes(conteudo)
        with self.assertRaisesRegex(ValueError, "linha 2"):
            self.reiniciar()
        self.assertEqual(arquivo.read_bytes(), conteudo)
        self.assertEqual(list(arquivo.parent.glob(arquivo.name + ".corrompido-*.bak")), [])

    def test_ultima_linha_valida_sem_quebra_nao_e_colada_ao_proximo_evento(self):
        arquivo = Path(estado.registro.caminho_arquivo)
        primeiro = {"tipo": "LEGADO"}
        arquivo.write_bytes(json.dumps(primeiro).encode("utf-8"))
        self.assertEqual(estado.registro.ler(), [primeiro])
        estado.registro.registrar("NOVO", [1, 0, 0], {})
        self.assertEqual([e["tipo"] for e in estado.registro.ler()], ["LEGADO", "NOVO"])
