"""Operações locais protegidas pelo lock compartilhado da agência."""
from fastapi import HTTPException
from .. import config, estado
from ..esquemas import CriarContaIn, ValorIn


def _conta(id_conta: int) -> dict:
    conta = estado.contas.get(id_conta)
    if conta is None:
        raise HTTPException(404, "Conta nao encontrada nesta agencia.")
    return conta


def criar_conta(dados: CriarContaIn) -> dict:
    responsavel = config.agencia_responsavel(dados.id)
    if responsavel != estado.ID_AGENCIA:
        raise HTTPException(400, f"Conta {dados.id} pertence a agencia {responsavel}.")
    with estado.lock:
        if dados.id in estado.contas:
            raise HTTPException(409, "Conta ja existe.")
        conta = dados.model_dump()
        conta["saldo"] = conta.pop("saldoInicial")
        estado.contas[dados.id] = conta
        estado.registro.registrar("CRIAR_CONTA", estado.relogio.evento_local(), dados.model_dump())
        return conta.copy()


def consultar_saldo(id_conta: int) -> dict:
    with estado.lock:
        return _conta(id_conta).copy()


def depositar(id_conta: int, dados: ValorIn) -> dict:
    with estado.lock:
        conta = _conta(id_conta)
        conta["saldo"] = round(conta["saldo"] + dados.valor, 2)
        estado.registro.registrar("DEPOSITO", estado.relogio.evento_local(),
                                 {"id": id_conta, "valor": dados.valor, "novoSaldo": conta["saldo"]})
        return conta.copy()


def sacar(id_conta: int, dados: ValorIn) -> dict:
    with estado.lock:
        conta = _conta(id_conta)
        if conta["saldo"] < dados.valor:
            raise HTTPException(400, "Saldo insuficiente.")
        conta["saldo"] = round(conta["saldo"] - dados.valor, 2)
        estado.registro.registrar("SAQUE", estado.relogio.evento_local(),
                                 {"id": id_conta, "valor": dados.valor, "novoSaldo": conta["saldo"]})
        return conta.copy()
