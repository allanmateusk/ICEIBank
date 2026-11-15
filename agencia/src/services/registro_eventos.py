"""Eventos JSONL: vetor, sessão do processo e hora de parede para exibição."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class RegistroEventos:
    def __init__(self, nome_agencia: str):
        self.nome_agencia = nome_agencia
        pasta = Path(os.environ.get("PASTA_DADOS", Path(__file__).resolve().parents[2] / "data"))
        pasta.mkdir(parents=True, exist_ok=True)
        self.caminho_arquivo = str(pasta / f"eventos-{nome_agencia}.jsonl")
        self.sessao = str(uuid4())
        self._sequencia = 0
        self._lock = threading.RLock()

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
            linhas = "".join(json.dumps(e, ensure_ascii=False, allow_nan=False) + "\n" for e in eventos)
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
            self._sequencia += len(eventos)
            for evento in eventos:
                try:
                    print(f"[Vetor {evento['timestampVetorial']}] {evento['tipo']} {evento['detalhes']}", flush=True)
                except OSError:
                    pass
            return eventos

    def ler(self) -> list[dict]:
        with self._lock:
            try:
                with open(self.caminho_arquivo, encoding="utf-8") as arquivo:
                    return [json.loads(linha) for linha in arquivo if linha.strip()]
            except FileNotFoundError:
                return []
