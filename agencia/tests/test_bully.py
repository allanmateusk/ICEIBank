import asyncio
import unittest
from urllib.parse import urlparse

import httpx

from src.services.bully import Bully
from src.services.relogio_vetorial import RelogioVetorial


class Registro:
    def __init__(self):
        self.eventos = []

    def registrar(self, tipo, vetor, detalhes):
        self.eventos.append((tipo, vetor, detalhes))


class Rede:
    def __init__(self):
        self.agencias = {}

    async def post(self, url, json):
        destino, rota = self._destino(url)
        if rota == '/bully/eleicao':
            await destino.receber_eleicao(json['origemId'], json['vetorEnvio'])
        else:
            await destino.receber_coordenador(json['liderId'], json['vetorEnvio'])
        return httpx.Response(200, json={'resposta': 'OK'}, request=httpx.Request('POST', url))

    async def get(self, url):
        destino, _ = self._destino(url)
        return httpx.Response(200, json={'liderId': destino.lider}, request=httpx.Request('GET', url))

    def _destino(self, url):
        parsed = urlparse(url)
        destino = self.agencias.get(int(parsed.hostname))
        if destino is None:
            raise httpx.ConnectError('indisponível')
        return destino, parsed.path

    async def aclose(self):
        pass


class BullyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.rede = Rede()
        self.nodos = []
        for i in range(3):
            no = Bully(i, RelogioVetorial(i), Registro(),
                       urls={j: f'http://{j}' for j in range(3)}, intervalo=0.03)
            no.espera = 0.12
            no.cliente = self.rede
            self.nodos.append(no)
            self.rede.agencias[i] = no

    async def asyncTearDown(self):
        await asyncio.gather(*(n.fechar() for n in self.nodos))

    async def aguardar_lider(self, ids, esperado):
        async def esperar():
            while not all(self.nodos[i].lider == esperado for i in ids):
                await asyncio.sleep(0.01)
        await asyncio.wait_for(esperar(), timeout=2)

    async def test_convergencia_queda_e_retorno(self):
        for no in self.nodos:
            no.loop = no.criar_tarefa(no.monitorar())
        await asyncio.gather(*(n.iniciar_eleicao('teste') for n in self.nodos))
        await self.aguardar_lider([0, 1, 2], 2)
        del self.rede.agencias[2]
        await self.nodos[2].fechar()
        await self.aguardar_lider([0, 1], 1)
        self.rede.agencias[2] = self.nodos[2]
        self.nodos[2].loop = self.nodos[2].criar_tarefa(self.nodos[2].monitorar())
        await self.nodos[2].iniciar_eleicao('retorno')
        await self.aguardar_lider([0, 1, 2], 2)
        self.assertTrue(any(e[0] == 'BULLY_LIDER_INDISPONIVEL' for e in self.nodos[0].registro.eventos))

    async def test_vetor_invalido_rejeitado(self):
        with self.assertRaises(ValueError):
            await self.nodos[0].receber_coordenador(2, [1, 2])

    async def test_reconverge_apos_rede_restaurada_sem_reiniciar_processos(self):
        self.rede.agencias.clear()
        await asyncio.gather(*(n.iniciar_eleicao('rede_fora') for n in self.nodos))
        await asyncio.gather(*(n.eleicao for n in self.nodos))
        self.assertEqual([n.lider for n in self.nodos], [0, 1, 2])
        self.rede.agencias.update({n.id: n for n in self.nodos})
        for no in self.nodos:
            no.criar_tarefa(no.monitorar())
        await self.aguardar_lider([0, 1, 2], 2)
        await asyncio.sleep(.15)
        self.assertEqual([n.lider for n in self.nodos], [2, 2, 2])

    async def test_coordenador_libera_tarefa_antiga_para_nova_eleicao(self):
        no = self.nodos[0]
        no.espera = 10
        antigo = no.criar_tarefa(asyncio.sleep(10))
        no.eleicao = antigo
        await no.receber_coordenador(2, [0, 0, 1])
        self.assertEqual(no.lider, 2)
        self.assertIsNone(no.eleicao)
        await asyncio.sleep(0)
        self.assertTrue(antigo.cancelled())
        await no.iniciar_eleicao('nova_falha')
        self.assertIsNotNone(no.eleicao)
