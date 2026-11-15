"""Eventos JSONL: vetor, sessão do processo e hora de parede para exibição."""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

log = logging.getLogger(__name__)


class RegistroEventos:
    def __init__(self, nome_agencia: str):
        self.nome_agencia = nome_agencia
        pasta = Path(os.environ.get("PASTA_DADOS", Path(__file__).resolve().parents[2] / "data"))
        pasta.mkdir(parents=True, exist_ok=True)
        self.caminho_arquivo = str(pasta / f"eventos-{nome_agencia}.jsonl")
        self.sessao = str(uuid4())
        self._sequencia = 0
        self._lock = threading.RLock()
        # O lote local é usado somente por transações bancárias na thread
        # atual; os eventos de eleição continuam no JSONL imediatamente.
        self._local = threading.local()

    def iniciar_lote(self):
        if getattr(self._local, "lote", None) is not None:
            raise RuntimeError("Lote de eventos já iniciado nesta thread.")
        self._local.lote = []
        return self._local.lote

    def encerrar_lote(self):
        self._local.lote = None

    def registrar(self, tipo: str, timestamp: list[int], detalhes: dict) -> dict:
        return self.registrar_lote([(tipo, timestamp, detalhes)])[0]

    def registrar_lote(self, entradas: list[tuple[str, list[int], dict]]) -> list[dict]:
        """Grava os eventos de uma operação juntos antes de alterar os saldos.

        Se a escrita falhar, remove a parte gravada sempre que o arquivo ainda
        estiver acessível. Não oferece garantia de recuperação após queda do SO.
        """
        with self._lock:
            eventos = [{
                "agencia": self.nome_agencia, "sessaoProcesso": self.sessao,
                "sequencia": self._sequencia + indice + 1, "tipo": tipo,
                "timestampVetorial": list(timestamp),
                "horaParede": datetime.now(timezone.utc).isoformat(), "detalhes": detalhes,
            } for indice, (tipo, timestamp, detalhes) in enumerate(entradas)]
            # Validar serialização antes de alterar saldo ou confirmar banco.
            linhas = "".join(json.dumps(e, ensure_ascii=False, allow_nan=False) + "\n" for e in eventos)
            self._sequencia += len(eventos)
            lote = getattr(self._local, "lote", None)
            if lote is not None:
                lote.extend(eventos)
                return eventos
            try:
                self._escrever(linhas)
            except Exception:
                self._sequencia -= len(eventos)
                raise
            for evento in eventos:
                try:
                    print(f"[Vetor {evento['timestampVetorial']}] {evento['tipo']} {evento['detalhes']}", flush=True)
                except OSError:
                    pass
            return eventos

    def _escrever(self, linhas: str) -> None:
        with open(self.caminho_arquivo, "a+", encoding="utf-8") as arquivo:
            arquivo.seek(0, os.SEEK_END)
            posicao = arquivo.tell()
            try:
                arquivo.write(linhas)
                arquivo.flush()
            except OSError:
                try:
                    arquivo.seek(posicao)
                    arquivo.truncate()
                except OSError:
                    pass
                raise

    def exportar_confirmados(self, eventos: list[dict]) -> None:
        """Reparar o JSONL a partir de eventos já confirmados no Postgres.

        Uma queda entre commit e escrita no arquivo não perde o evento. A
        identificação por sessão e sequência evita duplicar após reinício.
        """
        with self._lock:
            existentes = {(e.get("sessaoProcesso"), e.get("sequencia")) for e in self.ler()}
            faltantes = [e for e in eventos if (e.get("sessaoProcesso"), e.get("sequencia")) not in existentes]
            if faltantes:
                self._escrever("".join(json.dumps(e, ensure_ascii=False, allow_nan=False) + "\n" for e in faltantes))
                for evento in faltantes:
                    try:
                        print(f"[Vetor {evento['timestampVetorial']}] {evento['tipo']} {evento['detalhes']}", flush=True)
                    except OSError:
                        pass

    def ler(self) -> list[dict]:
        with self._lock:
            try:
                with open(self.caminho_arquivo, "rb") as arquivo:
                    conteudo = arquivo.read()
            except FileNotFoundError:
                return []
            linhas = conteudo.splitlines(keepends=True)
            eventos = []
            for indice, linha in enumerate(linhas):
                if not linha.strip():
                    continue
                try:
                    eventos.append(json.loads(linha.decode("utf-8")))
                except (UnicodeDecodeError, json.JSONDecodeError) as erro:
                    # Só a última linha sem terminador pode ser um append
                    # interrompido. Corrupção interna exige intervenção.
                    if indice != len(linhas) - 1 or linha.endswith((b"\n", b"\r")):
                        raise ValueError(f"JSONL corrompido na linha {indice + 1} de {self.caminho_arquivo}") from erro
                    copia = self.caminho_arquivo + f".corrompido-{uuid4().hex}.bak"
                    temporario = self.caminho_arquivo + f".reparo-{uuid4().hex}.tmp"
                    # Primeiro salva o arquivo inteiro, incluindo o fragmento;
                    # só então troca o original por seu prefixo válido.
                    with open(copia, "xb") as backup:
                        backup.write(conteudo)
                        backup.flush()
                        os.fsync(backup.fileno())
                    try:
                        with open(temporario, "xb") as reparado:
                            reparado.write(b"".join(linhas[:indice]))
                            reparado.flush()
                            os.fsync(reparado.fileno())
                        os.replace(temporario, self.caminho_arquivo)
                    finally:
                        if os.path.exists(temporario):
                            os.unlink(temporario)
                    log.warning("Fragmento final incompleto preservado em %s; JSONL restaurado até a linha %s.", copia, indice)
                    return eventos
            # Uma última linha JSON válida sem quebra deve ser separada do
            # próximo append, sem mudar seu conteúdo.
            if conteudo and not conteudo.endswith((b"\n", b"\r")):
                with open(self.caminho_arquivo, "ab") as arquivo:
                    arquivo.write(b"\n")
            return eventos
