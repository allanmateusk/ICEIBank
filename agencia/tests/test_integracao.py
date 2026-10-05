"""Integração REAL: broker Docker local isolado por vhost e três processos.

Executar: python -m unittest discover -s tests -p test_integracao.py -v
Requer docker compose up -d --wait na raiz. Não usa credenciais CloudAMQP.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from datetime import timedelta
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import httpx
from src.seguranca import criar_token

RAIZ = Path(__file__).resolve().parents[1]
GESTOR = "http://127.0.0.1:15678/api"
AUTH = ("iceibank", "iceibank-dev")


class IntegracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vhost = "teste-" + str(uuid4())
        cls.pasta = RAIZ / "data" / cls.vhost
        cls.pasta.mkdir(parents=True)
        cls.schema = "teste_" + uuid4().hex
        cls.banco = None
        cls.processos = {}
        cls.arquivos = []
        cls.cliente = httpx.Client(timeout=10)
        try:
            cls.banco = psycopg.connect(
                "postgresql://iceibank:iceibank-dev@127.0.0.1:5434/iceibank",
                autocommit=True,
            )
            cls.banco.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
            cls.database_url = make_conninfo(
                "postgresql://iceibank:iceibank-dev@127.0.0.1:5434/iceibank",
                options=f"-c search_path={cls.schema}"
            )
            cls.cliente.put(f"{GESTOR}/vhosts/{cls.vhost}", auth=AUTH, json={}).raise_for_status()
            cls.cliente.put(f"{GESTOR}/permissions/{cls.vhost}/iceibank", auth=AUTH,
                            json={"configure": ".*", "write": ".*", "read": ".*"}).raise_for_status()
            for agencia in range(3):
                cls.iniciar(agencia)
            cls.token = cls.cliente.post(cls.url(0) + "/auth/login",
                                         json={"usuario": "allan", "senha": "iceibank"}).json()["access_token"]
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def url(cls, agencia):
        return f"http://127.0.0.1:{14500 + agencia}"

    @classmethod
    def iniciar(cls, agencia):
        env = {**os.environ, "AGENCIA_ID": str(agencia), "OFFSET": "10500",
               "PASTA_DADOS": str(cls.pasta), "PYTHONUNBUFFERED": "1",
               "RABBITMQ_URL": f"amqp://iceibank:iceibank-dev@127.0.0.1:5678/{cls.vhost}"}
        env["DATABASE_URL"] = cls.database_url
        arquivo = open(cls.pasta / f"processo-{agencia}-{uuid4().hex[:6]}.log", "w", encoding="utf-8")
        cls.arquivos.append(arquivo)
        processo = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1",
                                      "--port", str(14500 + agencia)], cwd=RAIZ, env=env,
                                     stdout=arquivo, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        cls.processos[agencia] = processo
        for _ in range(80):
            if processo.poll() is not None:
                raise RuntimeError(f"Agencia {agencia} falhou: consulte {cls.pasta}")
            try:
                if cls.cliente.get(cls.url(agencia)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.15)
        raise TimeoutError(f"Agencia {agencia} nao iniciou.")

    @classmethod
    def parar(cls, agencia):
        processo = cls.processos.get(agencia)
        if processo and processo.poll() is None:
            processo.terminate()
            processo.wait(timeout=10)

    @classmethod
    def tearDownClass(cls):
        for agencia in list(cls.processos):
            cls.parar(agencia)
        for arquivo in cls.arquivos:
            arquivo.close()
        # Remove apenas o vhost exclusivo criado por este teste.
        cls.cliente.delete(f"{GESTOR}/vhosts/{cls.vhost}", auth=AUTH)
        cls.cliente.close()
        if cls.banco is not None:
            cls.banco.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))
            cls.banco.close()

    def chamada(self, agencia, metodo, rota, **kwargs):
        return self.cliente.request(metodo, self.url(agencia) + rota,
                                    headers={"Authorization": "Bearer " + self.token, **kwargs.pop("headers", {})}, **kwargs)

    def criar(self, id_conta, saldo=100):
        resposta = self.chamada(id_conta % 3, "POST", "/contas",
                                 json={"id": id_conta, "nomeAluno": "Allan — teste real", "saldoInicial": saldo})
        self.assertEqual(resposta.status_code, 201, resposta.text)

    def esperar_saldo(self, conta, saldo):
        for _ in range(100):
            resposta = self.chamada(conta % 3, "GET", f"/contas/{conta}")
            if resposta.status_code == 200 and resposta.json()["saldo"] == saldo:
                return
            time.sleep(0.05)
        self.fail(f"Saldo {saldo} nao observado na conta {conta}: {resposta.text}")

    def esperar_status(self, tid, esperado):
        for _ in range(100):
            resposta = self.chamada(0, "GET", f"/transferencias/{tid}")
            if resposta.status_code == 200 and resposta.json()["status"] == esperado:
                return resposta.json()
            time.sleep(0.05)
        self.fail(f"Status {esperado} nao observado: {resposta.text}")

    def test_01_transferencia_real(self):
        self.criar(300)
        self.criar(301, 10)
        resposta = self.chamada(0, "POST", "/transferencias", json={"idOrigem": 300, "idDestino": 301, "valor": 25})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.esperar_saldo(301, 35)
        self.esperar_status(resposta.json()["transferenciaId"], "CONFIRMADA")
        self.assertEqual(self.chamada(0, "GET", "/contas/300").json()["saldo"], 75)

    def test_02_jwt_e_validacao(self):
        self.assertEqual(self.cliente.get(self.url(0) + "/contas/300").status_code, 401)
        self.assertEqual(self.cliente.get(self.url(0) + "/contas/300", headers={"Authorization": "Bearer invalido"}).status_code, 401)
        self.assertEqual(self.chamada(0, "POST", "/transferencias", json={"idOrigem": 300, "idDestino": 300, "valor": 1}).status_code, 422)
        self.assertEqual(self.chamada(0, "POST", "/contas", json={"id": 304, "nomeAluno": "X", "saldoInicial": 0}).status_code, 400)
        expirado = criar_token("allan", expira_em=timedelta(seconds=-60))
        self.assertEqual(self.cliente.get(self.url(0) + "/contas/300", headers={"Authorization": "Bearer " + expirado}).status_code, 401)
        self.assertEqual(self.chamada(0, "POST", "/contas/300/depositar", json={"valor": 2}).json()["saldo"], 77)
        self.assertEqual(self.chamada(0, "POST", "/contas/300/sacar", json={"valor": 2}).json()["saldo"], 75)
        self.assertEqual(self.chamada(0, "GET", "/contas/300/historico").status_code, 200)
        self.assertEqual(self.chamada(0, "POST", "/contas/300/creditar-remoto", json={}).status_code, 404)

    def test_03_offline_e_conta_perdida(self):
        self.criar(304, 20)
        self.parar(1)
        resposta = self.chamada(0, "POST", "/transferencias", json={"idOrigem": 300, "idDestino": 304, "valor": 10})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json()["status"], "PENDENTE")
        # O painel do RabbitMQ atualiza métricas por amostragem, não imediatamente.
        for _ in range(80):
            fila = self.cliente.get(f"{GESTOR}/queues/{self.vhost}/fila-agencia-1", auth=AUTH).json()
            if fila.get("consumers") == 0 and fila.get("messages_ready", 0) >= 1:
                break
            time.sleep(0.2)
        self.assertTrue(fila["durable"])
        self.assertEqual(fila.get("consumers"), 0)
        self.assertGreaterEqual(fila.get("messages_ready", 0), 1)
        self.iniciar(1)
        resultado = self.esperar_status(resposta.json()["transferenciaId"], "FALHOU")
        self.assertIn("Conta nao encontrada", resultado["motivo"])
        self.assertEqual(self.chamada(1, "GET", "/contas/304").status_code, 404)
        self.assertEqual(self.chamada(0, "GET", "/contas/300").json()["saldo"], 65)

    def test_04_status_protegido(self):
        self.assertEqual(self.cliente.get(self.url(0) + f"/transferencias/{uuid4()}").status_code, 401)
        self.assertEqual(self.chamada(0, "GET", f"/transferencias/{uuid4()}").status_code, 404)

    def test_05_cadastro_persiste_sem_persistir_contas(self):
        dados = {"usuario": "usuario_novo", "senha": "senha-teste-123"}
        resposta = self.cliente.post(self.url(2) + "/auth/cadastro", json=dados)
        self.assertEqual(resposta.status_code, 201, resposta.text)
        self.assertEqual(resposta.json(), {"usuario": dados["usuario"]})
        self.assertEqual(self.cliente.post(self.url(2) + "/auth/cadastro", json=dados).status_code, 409)
        self.assertEqual(self.cliente.post(self.url(2) + "/auth/cadastro",
                         json={"usuario": "x", "senha": "123"}).status_code, 422)
        self.assertEqual(self.cliente.post(self.url(2) + "/auth/login",
                         json={**dados, "senha": "errada"}).status_code, 401)
        with self.banco.cursor() as cur:
            cur.execute(sql.SQL("SELECT salt, hash FROM {}.usuarios WHERE usuario = %s")
                        .format(sql.Identifier(self.schema)), (dados["usuario"],))
            salt, hash_senha = cur.fetchone()
            self.assertEqual(len(salt), 16)
            self.assertNotEqual(bytes(hash_senha), dados["senha"].encode())
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                        (self.schema,))
            self.assertEqual({row[0] for row in cur.fetchall()}, {"usuarios"})
        self.criar(602, 75)
        self.parar(2)
        self.iniciar(2)
        login = self.cliente.post(self.url(2) + "/auth/login", json=dados)
        self.assertEqual(login.status_code, 200, login.text)
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        self.assertEqual(self.cliente.get(self.url(2) + "/contas/602", headers=headers).status_code, 404)
        criada = self.cliente.post(self.url(2) + "/contas", headers=headers,
                                  json={"id": 602, "nomeAluno": "Teste", "saldoInicial": 10})
        self.assertEqual(criada.status_code, 201, criada.text)
