"""Eleição Bully e monitoramento da líder para uma agência por processo."""
import asyncio
import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config
from .relogio_vetorial import validar_vetor


class Eleicao(BaseModel):
    origemId: int = Field(ge=0, lt=config.NUMERO_AGENCIAS)
    vetorEnvio: list[int]


class Coordenador(BaseModel):
    liderId: int = Field(ge=0, lt=config.NUMERO_AGENCIAS)
    vetorEnvio: list[int]


class Bully:
    def __init__(self, agencia, relogio, registro, urls=None, intervalo=None):
        self.id = agencia
        self.relogio, self.registro = relogio, registro
        self.urls = urls or {a['id']: a['url'] for a in config.AGENCIAS}
        self.intervalo = intervalo or float(os.getenv('BULLY_INTERVALO', '2'))
        self.timeout = float(os.getenv('BULLY_TIMEOUT', '1'))
        self.espera = float(os.getenv('BULLY_ESPERA_COORDENADOR', '3'))
        self.lider = None
        self.lock = asyncio.Lock()
        self.geracao = 0
        self.eleicao = None
        self.tarefas = set()
        self.cliente = None
        self.loop = None
        self.falhas = 0

    def evento(self, tipo, detalhes, recebido=None):
        vetor = self.relogio.ao_receber(recebido) if recebido is not None else self.relogio.ao_enviar()
        self.registro.registrar(tipo, vetor, detalhes)
        return vetor

    def criar_tarefa(self, coro):
        tarefa = asyncio.create_task(coro)
        self.tarefas.add(tarefa)
        tarefa.add_done_callback(self.tarefas.discard)
        return tarefa

    async def iniciar(self):
        self.cliente = httpx.AsyncClient(timeout=self.timeout, trust_env=False)
        self.loop = self.criar_tarefa(self.monitorar())
        await self.iniciar_eleicao('inicializacao')

    async def fechar(self):
        tarefas = list(self.tarefas)
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        if self.cliente:
            await self.cliente.aclose()

    async def chamar(self, destino, rota, corpo=None):
        try:
            url = self.urls[destino] + rota
            if corpo is None:
                resposta = await self.cliente.get(url)
            else:
                resposta = await self.cliente.post(url, json=corpo)
            resposta.raise_for_status()
            return resposta.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def iniciar_eleicao(self, motivo):
        async with self.lock:
            if self.eleicao and not self.eleicao.done():
                return
            self.lider = None
            self.geracao += 1
            geracao = self.geracao
            self.evento('BULLY_ELEICAO_INICIADA', {'motivo': motivo, 'origemId': self.id})
            self.eleicao = self.criar_tarefa(self.executar_eleicao(geracao))

    async def executar_eleicao(self, geracao):
        superiores = [i for i in self.urls if i > self.id]

        async def perguntar(destino):
            vetor = self.evento('BULLY_ELEICAO_ENVIADA', {'origemId': self.id, 'destinoId': destino})
            return await self.chamar(destino, '/bully/eleicao', {'origemId': self.id, 'vetorEnvio': vetor})

        respostas = await asyncio.gather(*(perguntar(i) for i in superiores))
        async with self.lock:
            if geracao != self.geracao:
                return
            if not any(resposta is not None for resposta in respostas):
                self.lider = self.id
                self.falhas = 0
                self.evento('BULLY_LIDER_ELEITA', {'liderId': self.id})
            else:
                self.evento('BULLY_AGUARDANDO_COORDENADOR', {'origemId': self.id})
        if any(resposta is not None for resposta in respostas):
            await asyncio.sleep(self.espera)
            async with self.lock:
                reiniciar = geracao == self.geracao and self.lider is None
            if reiniciar:
                # A tarefa atual deve terminar antes de uma nova eleição ser criada.
                async with self.lock:
                    self.eleicao = None
                await self.iniciar_eleicao('coordenador_nao_respondeu')
            return

        async def anunciar(destino):
            vetor = self.evento('BULLY_COORDENADOR_ENVIADO', {'liderId': self.id, 'destinoId': destino})
            await self.chamar(destino, '/bully/coordenador', {'liderId': self.id, 'vetorEnvio': vetor})

        await asyncio.gather(*(anunciar(i) for i in self.urls if i != self.id))

    async def receber_eleicao(self, origem, vetor):
        validar_vetor(vetor, len(self.urls))
        self.evento('BULLY_ELEICAO_RECEBIDA', {'origemId': origem}, vetor)
        if origem < self.id:
            await self.iniciar_eleicao('eleicao_recebida')

    async def receber_coordenador(self, lider, vetor):
        validar_vetor(vetor, len(self.urls))
        self.evento('BULLY_COORDENADOR_RECEBIDO', {'liderId': lider}, vetor)
        if lider < self.id:
            await self.iniciar_eleicao('coordenador_inferior')
            return
        async with self.lock:
            # Não aceitar mensagem atrasada de um líder menor que o já conhecido.
            if self.lider is not None and lider < self.lider:
                return
            anterior = self.lider
            self.lider = lider
            self.falhas = 0
            self.geracao += 1
            # O coordenador encerra a espera da eleição anterior; não deixe
            # uma tarefa antiga impedir uma nova eleição após outra falha.
            if self.eleicao and not self.eleicao.done():
                self.eleicao.cancel()
            self.eleicao = None
            if anterior != lider:
                self.evento('BULLY_LIDER_ATUALIZADA', {'liderId': lider, 'anteriorId': anterior})

    async def monitorar(self):
        while True:
            await asyncio.sleep(self.intervalo)
            async with self.lock:
                lider = self.lider
                elegendo = self.eleicao is not None and not self.eleicao.done()
            if lider is None:
                if not elegendo:
                    await self.iniciar_eleicao('lider_desconhecida')
                continue
            if lider == self.id:
                # Uma partição pode deixar várias líderes vivas. Ao recuperar
                # a rede, a líder inferior precisa redescobrir IDs superiores.
                superiores = [i for i in self.urls if i > self.id]
                respostas = await asyncio.gather(*(
                    self.chamar(i, '/bully/lider') for i in superiores))
                async with self.lock:
                    reconciliar = self.lider == self.id and any(
                        r is not None for r in respostas)
                if reconciliar:
                    await self.iniciar_eleicao('superior_redescoberta')
                continue
            resposta = await self.chamar(lider, '/bully/lider')
            async with self.lock:
                if self.lider != lider:
                    continue
                if resposta is not None and resposta.get('liderId') == lider:
                    self.falhas = 0
                else:
                    self.falhas += 1
                falhou = self.falhas >= 2
            if falhou:
                self.evento('BULLY_LIDER_INDISPONIVEL', {'liderId': lider})
                await self.iniciar_eleicao('heartbeat')


router = APIRouter(prefix='/bully', tags=['lideranca'])


@router.get('/lider')
async def lider(request: Request):
    bully = request.app.state.bully
    async with bully.lock:
        return {'agenciaId': bully.id, 'liderId': bully.lider,
                'emEleicao': bully.lider is None}


@router.post('/eleicao')
async def eleicao(dados: Eleicao, request: Request):
    try:
        await request.app.state.bully.receber_eleicao(dados.origemId, dados.vetorEnvio)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    return {'agenciaId': request.app.state.bully.id, 'resposta': 'OK'}


@router.post('/coordenador')
async def coordenador(dados: Coordenador, request: Request):
    try:
        await request.app.state.bully.receber_coordenador(dados.liderId, dados.vetorEnvio)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    return {'agenciaId': request.app.state.bully.id, 'resposta': 'OK'}
