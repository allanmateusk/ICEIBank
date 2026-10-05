"""Transferências locais e remotas; a publicação não confirma o crédito."""
from uuid import UUID, uuid4
from fastapi import Header, HTTPException, Request
from .. import config, estado
from ..esquemas import EventoCredito, TransferenciaIn
from ..services.mensageria import BrokerIndisponivel, PublicacaoRecusada


def _id(chave):
    try:
        return str(UUID(chave)) if chave else str(uuid4())
    except ValueError:
        raise HTTPException(422, "Idempotency-Key deve ser um UUID.") from None


async def transferir(dados: TransferenciaIn, request: Request,
                     chave: str | None = Header(default=None, alias="Idempotency-Key")) -> dict:
    tid = _id(chave)
    destino = config.agencia_responsavel(dados.idDestino)
    broker = request.app.state.mensageria
    with estado.lock:
        anterior = estado.transferencias.get(tid)
        if anterior:
            if anterior["pedido"] != dados.model_dump():
                raise HTTPException(409, "Chave ja utilizada com outra transferencia.")
            return _resposta(anterior)
        origem = estado.contas.get(dados.idOrigem)
        if origem is None:
            raise HTTPException(404, "Conta de origem nao encontrada nesta agencia.")
        if origem["saldo"] < dados.valor:
            raise HTTPException(400, "Saldo insuficiente.")
        conta_destino = estado.contas.get(dados.idDestino) if destino == estado.ID_AGENCIA else None
        if destino == estado.ID_AGENCIA and conta_destino is None:
            raise HTTPException(404, "Conta de destino nao encontrada.")
        if destino != estado.ID_AGENCIA and not broker.disponivel:
            raise HTTPException(503, "Broker indisponivel. Nenhum debito foi aplicado.")
        operacao = {"transferenciaId": tid, **dados.model_dump(), "pedido": dados.model_dump(),
                    "status": "PUBLICANDO", "destinoAgencia": destino}
        estado.transferencias[tid] = operacao
        origem["saldo"] = round(origem["saldo"] - dados.valor, 2)
        operacao["saldoOrigem"] = origem["saldo"]
        detalhes = {"transferenciaId": tid, **dados.model_dump()}
        estado.registro.registrar("TRANSFERENCIA_DEBITO", estado.relogio.evento_local(), detalhes)
        if conta_destino is not None:
            conta_destino["saldo"] = round(conta_destino["saldo"] + dados.valor, 2)
            estado.registro.registrar("TRANSFERENCIA_CREDITO", estado.relogio.evento_local(), detalhes)
            operacao.update(status="CONFIRMADA", saldoDestino=conta_destino["saldo"])
            return _resposta(operacao)
        evento = {"tipo": "CREDITAR", "versao": 1, **detalhes,
                  "origemAgencia": estado.ID_AGENCIA, "destinoAgencia": destino,
                  "vetorEnvio": estado.relogio.ao_enviar()}
        estado.registro.registrar("TRANSFERENCIA_ENVIADA", evento["vetorEnvio"], detalhes)
    # Nenhum lock de thread atravessa o await de rede.
    try:
        await broker.publicar(f"agencia.{destino}.creditar", evento)
    except Exception as erro:
        status = "FALHA_PUBLICACAO" if isinstance(erro, (BrokerIndisponivel, PublicacaoRecusada)) else "PUBLICACAO_INCERTA"
        with estado.lock:
            if operacao["status"] not in ("CONFIRMADA", "FALHOU"):
                operacao.update(status=status, motivo="Debito aplicado; publicacao nao confirmada. Consulte o acompanhamento.")
                estado.registro.registrar(status, estado.relogio.evento_local(), detalhes)
            resposta = _resposta(operacao)
        raise HTTPException(502, resposta) from None
    with estado.lock:
        if operacao["status"] == "PUBLICANDO":
            operacao["status"] = "PENDENTE"
        return _resposta(operacao)


def _resposta(operacao: dict) -> dict:
    retorno = {k: v for k, v in operacao.items() if k != "pedido"}
    retorno["mensagem"] = {"CONFIRMADA": "Credito confirmado.", "PENDENTE": "Mensagem publicada. Aguardando confirmacao do credito.",
                            "PUBLICANDO": "Publicacao em andamento.", "FALHOU": "Credito nao aplicado no destino."}.get(operacao["status"], operacao.get("motivo", "Consulte o acompanhamento."))
    return retorno


def receber_credito(corpo: dict) -> dict:
    evento = EventoCredito.model_validate(corpo)
    if evento.destinoAgencia != estado.ID_AGENCIA:
        raise ValueError("Mensagem entregue a agencia incorreta.")
    tid = str(evento.transferenciaId)
    with estado.lock:
        anterior = estado.creditos_processados.get(tid)
        if anterior:
            if anterior["pedido"] != evento.model_dump(mode="json", exclude={"vetorEnvio"}):
                raise ValueError("UUID de credito reutilizado com outro pedido.")
            return anterior.copy()
        vetor = estado.relogio.ao_receber(evento.vetorEnvio)
        conta = estado.contas.get(evento.idDestino)
        detalhes = {"transferenciaId": tid, "idOrigem": evento.idOrigem,
                    "idDestino": evento.idDestino, "valor": evento.valor}
        resultado = {**detalhes, "origemAgencia": evento.origemAgencia,
                     "destinoAgencia": evento.destinoAgencia,
                     "resultado": "CREDITO_APLICADO" if conta else "CREDITO_FALHOU",
                     "pedido": evento.model_dump(mode="json", exclude={"vetorEnvio"})}
        if conta:
            conta["saldo"] = round(conta["saldo"] + evento.valor, 2)
            tipo = "TRANSFERENCIA_CREDITO_REMOTO"
        else:
            resultado["motivo"] = "Conta nao encontrada no destino (estado em memoria perdido no reinicio)."
            tipo = "CREDITO_REMOTO_FALHOU"
        estado.creditos_processados[tid] = resultado
        estado.registro.registrar(tipo, vetor, detalhes)
        return resultado.copy()


async def consumir(corpo: dict):
    receber_credito(corpo)
