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
        with self._lock:
            self._sequencia += 1
            evento = {
                "agencia": self.nome_agencia, "sessaoProcesso": self.sessao,
                "sequencia": self._sequencia, "tipo": tipo,
                "timestampVetorial": list(timestamp),
                "horaParede": datetime.now(timezone.utc).isoformat(), "detalhes": detalhes,
            }
            with open(self.caminho_arquivo, "a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(evento, ensure_ascii=False, allow_nan=False) + "\n")
            print(f"[Vetor {timestamp}] {tipo} {detalhes}", flush=True)
            return evento

    def ler(self) -> list[dict]:
        with self._lock:
            try:
                with open(self.caminho_arquivo, encoding="utf-8") as arquivo:
                    return [json.loads(linha) for linha in arquivo if linha.strip()]
            except FileNotFoundError:
                return []
