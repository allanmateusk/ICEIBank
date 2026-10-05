"""Histórico por conta, na ordem local de registro (compatível com sprint1)."""
from fastapi import HTTPException
from .. import estado


def historico(id_conta: int, limite: int = 20) -> dict:
    if not 1 <= limite <= 500:
        raise HTTPException(422, "limite deve estar entre 1 e 500.")
    with estado.lock:
        if id_conta not in estado.contas:
            raise HTTPException(404, "Conta nao encontrada nesta agencia.")
    def pertence(evento):
        detalhes = evento.get("detalhes", {})
        tipo = evento.get("tipo", "")
        if tipo == "TRANSFERENCIA_DEBITO":
            return detalhes.get("idOrigem") == id_conta
        if tipo in ("TRANSFERENCIA_CREDITO", "TRANSFERENCIA_CREDITO_REMOTO"):
            return detalhes.get("idDestino", detalhes.get("idConta")) == id_conta
        return any(detalhes.get(c) == id_conta for c in ("id", "idConta", "idOrigem", "idDestino"))
    eventos = [e for e in estado.registro.ler()
               if pertence(e)]
    return {"agencia": estado.ID_AGENCIA, "conta": id_conta, "total": len(eventos),
            "limite": limite, "eventos": eventos[-limite:]}
