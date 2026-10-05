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
from uuid import uuid4
import httpx

RAIZ = Path(__file__).resolve().parents[1]
GESTOR = "http://127.0.0.1:15678/api"
AUTH = ("iceibank", "iceibank-dev")


class IntegracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vhost = "teste-" + str(uuid4())
        cls.pasta = RAIZ / "data" / cls.vhost
        cls.pasta.mkdir(parents=True)
        cls.processos = {}
        cls.arquivos = []
        cls.cliente = httpx.Client(timeout=10)
        try:
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
