"""Relógio vetorial: causalidade parcial entre as três agências."""
import threading


def validar_vetor(vetor: list[int], tamanho: int) -> None:
    if len(vetor) != tamanho or any(type(n) is not int or n < 0 for n in vetor):
        raise ValueError(f"O vetor deve conter {tamanho} inteiros nao negativos.")


def comparar_vetores(a: list[int], b: list[int]) -> str:
    validar_vetor(a, len(b))
    validar_vetor(b, len(a))
    if a == b:
        return "IGUAIS"
    if all(x <= y for x, y in zip(a, b)):
        return "ANTES"
    if all(y <= x for x, y in zip(a, b)):
        return "DEPOIS"
    return "CONCORRENTES"


class RelogioVetorial:
    def __init__(self, id_agencia: int, numero_agencias: int = 3):
        if not 0 <= id_agencia < numero_agencias:
            raise ValueError("Agencia fora do vetor.")
        self.id_agencia = id_agencia
        self.vetor = [0] * numero_agencias
        self._lock = threading.Lock()

    def evento_local(self) -> list[int]:
        with self._lock:
            self.vetor[self.id_agencia] += 1
            return self.vetor.copy()

    def ao_enviar(self) -> list[int]:
        return self.evento_local()

    def ao_receber(self, recebido: list[int]) -> list[int]:
        validar_vetor(recebido, len(self.vetor))
        with self._lock:
            self.vetor = [max(a, b) for a, b in zip(self.vetor, recebido)]
            self.vetor[self.id_agencia] += 1
            return self.vetor.copy()
