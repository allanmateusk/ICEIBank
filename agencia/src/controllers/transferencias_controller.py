"""Transferências locais e remotas; a publicação não confirma o crédito."""
from uuid import UUID, uuid4
from fastapi import Header, HTTPException, Request
from .. import banco, config, estado
from ..esquemas import EventoCredito, EventoResultado, TransferenciaIn
from ..services.mensageria import BrokerIndisponivel, PublicacaoRecusada
from ..services import versao_conta


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
    sync = getattr(getattr(request, "state", None), "sincronizacao", None)
    with estado.transacao():
        # Os dois endpoints compartilham o namespace de idempotência. Caso
        # contrário, um UUID já aplicado como saque ou depósito offline pode
        # ser reaproveitado para debitar uma transferência distinta.
        if tid in estado.sincronizacoes and sync is None:
            raise HTTPException(409, "Chave ja utilizada em sincronizacao.")
        anterior = estado.transferencias.get(tid)
        if anterior:
            if anterior["pedido"] != dados.model_dump():
                raise HTTPException(409, "Chave ja utilizada com outra transferencia.")
            return _resposta(anterior)
        origem = estado.contas.get(dados.idOrigem)
        if origem is None:
            raise HTTPException(404, "Conta de origem nao encontrada nesta agencia.")
        if sync is not None:
            versao_conta.validar(origem, sync.vetorBase, sync.sessaoServidor)
        if origem["saldo"] < dados.valor:
            raise HTTPException(400, "Saldo insuficiente.")
        conta_destino = estado.contas.get(dados.idDestino) if destino == estado.ID_AGENCIA else None
        if destino == estado.ID_AGENCIA and conta_destino is None:
            raise HTTPException(404, "Conta de destino nao encontrada.")
        if destino != estado.ID_AGENCIA and not broker.disponivel:
            raise HTTPException(503, "Broker indisponivel. Nenhum debito foi aplicado.")
        operacao = {"transferenciaId": tid, **dados.model_dump(), "pedido": dados.model_dump(),
                    "status": "PUBLICANDO", "destinoAgencia": destino}
        saldo_origem = round(origem["saldo"] - dados.valor, 2)
        operacao["saldoOrigem"] = saldo_origem
        detalhes = {"transferenciaId": tid, **dados.model_dump()}
        debito = estado.relogio.evento_local()
        if conta_destino is not None:
            credito = estado.relogio.evento_local()
            estado.registro.registrar_lote([("TRANSFERENCIA_DEBITO", debito, detalhes),
                                          ("TRANSFERENCIA_CREDITO", credito, detalhes)])
            origem["saldo"] = saldo_origem
            conta_destino["saldo"] = round(conta_destino["saldo"] + dados.valor, 2)
            estado.versoes_contas[dados.idOrigem] = debito
            estado.versoes_contas[dados.idDestino] = credito
            operacao.update(status="CONFIRMADA", saldoDestino=conta_destino["saldo"])
            estado.transferencias[tid] = operacao
            return _resposta(operacao)
        evento = {"tipo": "CREDITAR", "versao": 1, **detalhes,
                  "origemAgencia": estado.ID_AGENCIA, "destinoAgencia": destino,
                  "vetorEnvio": estado.relogio.ao_enviar()}
        estado.registro.registrar_lote([("TRANSFERENCIA_DEBITO", debito, detalhes),
                                      ("TRANSFERENCIA_ENVIADA", evento["vetorEnvio"], detalhes)])
        origem["saldo"] = saldo_origem
        estado.versoes_contas[dados.idOrigem] = debito
        estado.transferencias[tid] = operacao
        if banco.ativo():
            # Incluído no mesmo commit que o débito e o acompanhamento.
            operacao["status"] = "PENDENTE"
            estado.outbox[tid] = {"routing_key": f"agencia.{destino}.creditar", "evento": evento}
    if banco.ativo():
        # O publicador em segundo plano entrega mesmo após reinício.
        with estado.lock:
            estado.verificar_disponibilidade()
            return _resposta(estado.transferencias[tid])
    # Nenhum lock de thread atravessa o await de rede.
    try:
        await broker.publicar(f"agencia.{destino}.creditar", evento)
    except Exception as erro:
        status = "FALHA_PUBLICACAO" if isinstance(erro, (BrokerIndisponivel, PublicacaoRecusada)) else "PUBLICACAO_INCERTA"
        with estado.transacao():
            # Outro pedido pode ter falhado enquanto aguardávamos o broker e
            # restaurado cópias do estado. A referência anterior não é segura.
            operacao = estado.transferencias[tid]
            if operacao["status"] in ("CONFIRMADA", "FALHOU"):
                # O resultado do destino prova que o pedido foi processado,
                # mesmo se a confirmação de publicação se perdeu.
                return _resposta(operacao)
            operacao.update(status=status, motivo="Debito aplicado; publicacao nao confirmada. Consulte o acompanhamento.")
            estado.registro.registrar(status, estado.relogio.evento_local(), detalhes)
            resposta = _resposta(operacao)
        raise HTTPException(502, resposta) from None
    with estado.transacao():
        operacao = estado.transferencias[tid]
        if operacao["status"] == "PUBLICANDO":
            operacao["status"] = "PENDENTE"
        return _resposta(operacao)


def _resposta(operacao: dict) -> dict:
    retorno = {k: v for k, v in operacao.items() if k != "pedido"}
    retorno["mensagem"] = {"CONFIRMADA": "Credito confirmado.", "PENDENTE": "Aguardando envio ou confirmacao do credito.",
                            "PUBLICANDO": "Publicacao em andamento.", "FALHOU": "Credito nao aplicado no destino."}.get(operacao["status"], operacao.get("motivo", "Consulte o acompanhamento."))
    return retorno


def receber_credito(corpo: dict) -> dict:
    evento = EventoCredito.model_validate(corpo)
    if evento.destinoAgencia != estado.ID_AGENCIA:
        raise ValueError("Mensagem entregue a agencia incorreta.")
    tid = str(evento.transferenciaId)
    with estado.transacao():
        anterior = estado.creditos_processados.get(tid)
        if anterior:
            if anterior["pedido"] != evento.model_dump(mode="json", exclude={"vetorEnvio"}):
                raise ValueError("UUID de credito reutilizado com outro pedido.")
            estado.registro.registrar("CREDITO_DUPLICADO", estado.relogio.ao_receber(evento.vetorEnvio),
                                     {"transferenciaId": tid, "idOrigem": evento.idOrigem, "idDestino": evento.idDestino})
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
            tipo = "TRANSFERENCIA_CREDITO_REMOTO"
        else:
            resultado["motivo"] = "Conta nao encontrada no destino."
            tipo = "CREDITO_REMOTO_FALHOU"
        estado.registro.registrar(tipo, vetor, detalhes)
        if conta:
            conta["saldo"] = round(conta["saldo"] + evento.valor, 2)
            estado.versoes_contas[evento.idDestino] = vetor
        estado.creditos_processados[tid] = resultado
        return resultado.copy()


def consultar(transferencia_id: str) -> dict:
    tid = _id(transferencia_id)
    with estado.lock:
        estado.verificar_disponibilidade()
        operacao = estado.transferencias.get(tid)
        if not operacao:
            raise HTTPException(404, "Acompanhamento nao encontrado nesta agencia. Pode ter sido perdido em um reinicio.")
        return _resposta(operacao)


def receber_confirmacao(corpo: dict):
    evento = EventoResultado.model_validate(corpo)
    if evento.origemAgencia != estado.ID_AGENCIA:
        raise ValueError("Confirmacao entregue a agencia incorreta.")
    tid = str(evento.transferenciaId)
    with estado.transacao():
        operacao = estado.transferencias.get(tid)
        if operacao and any(operacao[c] != getattr(evento, c) for c in ("idOrigem", "idDestino", "valor", "destinoAgencia")):
            raise ValueError("Confirmacao nao corresponde a transferencia.")
        if operacao and operacao["status"] in ("CONFIRMADA", "FALHOU"):
            esperado = "CONFIRMADA" if evento.resultado == "CREDITO_APLICADO" else "FALHOU"
            if operacao["status"] != esperado:
                raise ValueError("Confirmacao conflitante.")
            estado.registro.registrar("CONFIRMACAO_DUPLICADA", estado.relogio.ao_receber(evento.vetorEnvio),
                                     {"transferenciaId": tid, "idOrigem": evento.idOrigem, "idDestino": evento.idDestino})
            return
        vetor = estado.relogio.ao_receber(evento.vetorEnvio)
        detalhes = {"transferenciaId": tid, "idOrigem": evento.idOrigem,
                    "idDestino": evento.idDestino, "valor": evento.valor, "resultado": evento.resultado}
        if operacao:
            tipo = "CONFIRMACAO_RECEBIDA"
        else:
            tipo = "CONFIRMACAO_SEM_REGISTRO"
        estado.registro.registrar(tipo, vetor, detalhes)
        if operacao:
            operacao["status"] = "CONFIRMADA" if evento.resultado == "CREDITO_APLICADO" else "FALHOU"
            if evento.resultado == "CREDITO_FALHOU":
                origem = estado.contas.get(operacao["idOrigem"])
                if origem is None:
                    raise RuntimeError("Nao foi possivel estornar: conta de origem ausente.")
                novo_saldo = round(origem["saldo"] + operacao["valor"], 2)
                estorno = estado.relogio.evento_local()
                estado.registro.registrar("TRANSFERENCIA_ESTORNO", estorno,
                    {**detalhes, "novoSaldo": novo_saldo})
                origem["saldo"] = novo_saldo
                estado.versoes_contas[operacao["idOrigem"]] = estorno
                operacao["estornada"] = True
            if evento.motivo:
                operacao["motivo"] = evento.motivo


async def consumir(corpo: dict):
    if corpo.get("tipo") == "CONFIRMAR":
        receber_confirmacao(corpo)
        return
    resultado = receber_credito(corpo)
    with estado.transacao():
        evento = {k: v for k, v in resultado.items() if k != "pedido"}
        evento.update(tipo="CONFIRMAR", versao=1, vetorEnvio=estado.relogio.ao_enviar())
        estado.registro.registrar("CONFIRMACAO_ENVIADA", evento["vetorEnvio"],
                                 {k: v for k, v in evento.items() if k != "vetorEnvio"})
    # Se esta publicação falhar, o crédito já está no cache. A reentrega
    # repete somente a confirmação, sem reaplicar o crédito.
    await broker_ativo.publicar(f"agencia.{evento['origemAgencia']}.confirmar", evento)


broker_ativo = None
