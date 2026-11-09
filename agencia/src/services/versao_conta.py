"""Versão causal por conta, separada dos demais eventos da agência.

Todas as funções devem ser chamadas com estado.lock adquirido.
"""
from fastapi import HTTPException
from .. import estado
from .relogio_vetorial import comparar_vetores


def atualizar(id_conta: int) -> None:
    with estado.relogio._lock:
        estado.versoes_contas[id_conta] = estado.relogio.vetor.copy()


def snapshot(conta: dict) -> dict:
    return {**conta, "vetorVersao": estado.versoes_contas.get(conta["id"], [0, 0, 0]).copy(),
            "sessaoServidor": estado.registro.sessao}


def validar(conta: dict, vetor_base: list[int], sessao: str) -> None:
    atual = snapshot(conta)
    relacao = comparar_vetores(vetor_base, atual["vetorVersao"])
    if sessao != estado.registro.sessao or relacao != "IGUAIS":
        codigo = "SESSAO_ALTERADA" if sessao != estado.registro.sessao else "VERSAO_CONFLITANTE"
        raise HTTPException(409, {"codigo": codigo, "mensagem": "Atualize a conta antes de sincronizar.",
                                  "relacao": relacao, "conta": atual})
