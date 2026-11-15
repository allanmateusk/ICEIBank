"""Estado de uma agência, persistido em Postgres quando configurado.

Um único processo por agência é necessário: o lock é local ao processo.
Sem DATABASE_URL, os dados são voláteis e outbox não está disponível.
"""
import os
import threading

from . import config
from .services.registro_eventos import RegistroEventos
from .services.relogio_vetorial import RelogioVetorial

ID_AGENCIA = int(os.environ.get("AGENCIA_ID", "0"))

if not any(a["id"] == ID_AGENCIA for a in config.AGENCIAS):
    raise SystemExit(
        f"Agencia {ID_AGENCIA} nao configurada em config.py "
        f"(validas: {[a['id'] for a in config.AGENCIAS]})"
    )

relogio = RelogioVetorial(ID_AGENCIA, config.NUMERO_AGENCIAS)
registro = RegistroEventos(f"agencia-{ID_AGENCIA}")

# id_conta -> {"id": int, "nomeAluno": str, "saldo": float}
contas: dict[int, dict] = {}
# Controllers no threadpool e consumidor AMQP compartilham a mesma memória.
lock = threading.RLock()
transferencias: dict[str, dict] = {}
creditos_processados: dict[str, dict] = {}
# Versões específicas das contas e resultados de operações offline duram a
# sessão do processo, assim como as próprias contas.
versoes_contas: dict[int, list[int]] = {}
sincronizacoes: dict[str, dict] = {}


# Intenções de publicação fazem parte do mesmo registro transacional que o
# saldo. Um processo por agência é requisito do desenho atual.
outbox: dict[str, dict] = {}
# Um commit pode ter ocorrido mesmo se o driver reportar erro. Só o reinício
# e leitura do banco podem reconciliar esta incerteza.
reconciliacao_necessaria = False


def verificar_disponibilidade():
    if reconciliacao_necessaria:
        from fastapi import HTTPException
        raise HTTPException(503, "Estado bancario indisponivel; reinicie a agencia para reconciliar o banco.")


def _snapshot():
    import copy
    with relogio._lock:
        vetor = relogio.vetor.copy()
    return copy.deepcopy({"contas": contas, "transferencias": transferencias,
        "creditos_processados": creditos_processados, "versoes_contas": versoes_contas,
        "sincronizacoes": sincronizacoes, "outbox": outbox, "vetor": vetor})


def _restaurar(dados, restaurar_vetor=True):
    for nome in ("contas", "transferencias", "creditos_processados", "versoes_contas", "sincronizacoes", "outbox"):
        alvo = globals()[nome]
        alvo.clear()
        valores = dados.get(nome, {})
        if nome in ("contas", "versoes_contas"):
            valores = {int(k): v for k, v in valores.items()}
        alvo.update(valores)
    if restaurar_vetor:
        with relogio._lock:
            relogio.vetor = dados.get("vetor", [0, 0, 0]).copy()


def carregar():
    from . import banco
    with lock:
        dados = banco.carregar_estado(ID_AGENCIA)
        if dados is not None:
            _restaurar(dados)
        # Eventos Bully também avançam o vetor entre operações bancárias.
        # Recupera o maior valor observado nos logs da própria agência.
        eventos = registro.ler()
        with relogio._lock:
            for evento in eventos:
                vetor = evento.get("timestampVetorial", [])
                if len(vetor) == len(relogio.vetor) and all(type(x) is int and x >= 0 for x in vetor):
                    relogio.vetor = [max(a, b) for a, b in zip(relogio.vetor, vetor)]


from contextlib import contextmanager
_profundidade = threading.local()

@contextmanager
def transacao():
    """Persiste uma alteração local com seu outbox em um único commit."""
    from . import banco
    with lock:
        verificar_disponibilidade()
        if getattr(_profundidade, "ativa", False):
            yield
            return
        anterior = _snapshot()
        _profundidade.ativa = True
        try:
            try:
                yield
            except BaseException:
                _restaurar(anterior, restaurar_vetor=False)
                raise
            try:
                banco.salvar_estado(ID_AGENCIA, _snapshot())
            except Exception:
                # O servidor pode ter confirmado o commit antes da queda da
                # conexão. Nunca continuar operando com estado presumido.
                global reconciliacao_necessaria
                reconciliacao_necessaria = True
                _restaurar(anterior, restaurar_vetor=False)
                raise
        finally:
            _profundidade.ativa = False
