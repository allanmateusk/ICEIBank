"""Contrato provisório de sincronização offline; estado dura a sessão da agência."""
from typing import Literal
from uuid import UUID
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from .. import estado
from ..esquemas import TransferenciaIn
from ..services import versao_conta
from . import transferencias_controller


class SincronizacaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operacaoId: UUID
    contaId: int = Field(ge=0)
    tipo: Literal["DEPOSITO", "SAQUE", "TRANSFERENCIA"]
    valor: float = Field(gt=0, allow_inf_nan=False, multiple_of=0.01)
    destinoId: int | None = Field(default=None, ge=0)
    vetorBase: list[StrictInt] = Field(min_length=3, max_length=3)
    sessaoServidor: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_campos(self):
        if any(n < 0 for n in self.vetorBase):
            raise ValueError("Vetor deve conter inteiros nao negativos.")
        if self.tipo == "TRANSFERENCIA":
            if self.destinoId is None or self.destinoId == self.contaId:
                raise ValueError("Destino distinto da origem e obrigatorio.")
        elif self.destinoId is not None:
            raise ValueError("Destino so e permitido para transferencia.")
        return self


async def sincronizar(dados: SincronizacaoIn, request: Request) -> dict:
    chave = str(dados.operacaoId)
    pedido = dados.model_dump(mode="json")
    with estado.lock:
        anterior = estado.sincronizacoes.get(chave)
        if anterior:
            if anterior["pedido"] != pedido:
                raise HTTPException(409, {"codigo": "CHAVE_REUTILIZADA", "mensagem": "UUID ja utilizado para outro pedido."})
            if anterior.get("resposta") is not None:
                return anterior["resposta"]
        conta = estado.contas.get(dados.contaId)
        if conta is None:
            raise HTTPException(404, "Conta nao encontrada nesta agencia.")
        if anterior is None and chave in estado.transferencias:
            raise HTTPException(409, {"codigo": "CHAVE_REUTILIZADA", "mensagem": "UUID ja utilizado em uma transferencia."})
        if dados.tipo != "TRANSFERENCIA":
            versao_conta.validar(conta, dados.vetorBase, dados.sessaoServidor)
            if dados.tipo == "SAQUE" and conta["saldo"] < dados.valor:
                raise HTTPException(400, "Saldo insuficiente.")
            sinal = 1 if dados.tipo == "DEPOSITO" else -1
            novo_saldo = round(conta["saldo"] + sinal * dados.valor, 2)
            # Uma falha ao gravar o evento não pode alterar o saldo sem
            # registrar a chave de idempotência: a repetição aplicaria duas
            # vezes a mesma operação.
            estado.registro.registrar("SINCRONIZACAO_" + dados.tipo, estado.relogio.evento_local(),
                                     {"operacaoId": chave, "id": dados.contaId, "valor": dados.valor,
                                      "novoSaldo": novo_saldo})
            conta["saldo"] = novo_saldo
            versao_conta.atualizar(dados.contaId)
            resposta = {"operacaoId": chave, "status": "SINCRONIZADA", "conta": versao_conta.snapshot(conta)}
            estado.sincronizacoes[chave] = {"pedido": pedido, "resposta": resposta}
            return resposta
        # Guarda o pedido antes de publicar para impedir reutilização do UUID
        # com outro contexto mesmo se a resposta da publicação for perdida.
        if anterior is None:
            versao_conta.validar(conta, dados.vetorBase, dados.sessaoServidor)
            estado.sincronizacoes[chave] = {"pedido": pedido, "resposta": None}

    request.state.sincronizacao = dados
    transferencia = await transferencias_controller.transferir(
        TransferenciaIn(idOrigem=dados.contaId, idDestino=dados.destinoId, valor=dados.valor), request, chave)
    with estado.lock:
        conta = estado.contas[dados.contaId]
        status = "SINCRONIZADA" if transferencia["status"] == "CONFIRMADA" else "PENDENTE"
        resposta = {"operacaoId": chave, "status": status, "conta": versao_conta.snapshot(conta),
                    "transferencia": transferencia}
        # A transferência pode mudar de PENDENTE para CONFIRMADA em segundo
        # plano; em reenvios consultamos sempre o registro de transferências.
        return resposta
