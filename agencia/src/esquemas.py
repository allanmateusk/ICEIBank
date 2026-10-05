"""Modelos Pydantic dos corpos de requisição (a camada de entrada da API).

Os nomes dos campos seguem o roteiro (camelCase) para casar com o JSON usado
nos exemplos de teste. As restrições (`Field(...)`, validadores) rejeitam
entradas inválidas com HTTP 422 antes de chegar ao controller.
"""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, StrictInt, ConfigDict, model_validator


class CriarContaIn(BaseModel):
    id: int = Field(ge=0, description="Número da conta (inteiro >= 0).")
    nomeAluno: str = Field(min_length=1)
    saldoInicial: float = Field(default=0, ge=0, allow_inf_nan=False, multiple_of=0.01)


class ValorIn(BaseModel):
    valor: float = Field(gt=0, allow_inf_nan=False, multiple_of=0.01)


class TransferenciaIn(BaseModel):
    idOrigem: int = Field(ge=0)
    idDestino: int = Field(ge=0)
    valor: float = Field(gt=0, allow_inf_nan=False, multiple_of=0.01)

    @model_validator(mode="after")
    def _contas_diferentes(self):
        if self.idOrigem == self.idDestino:
            raise ValueError("idOrigem e idDestino devem ser contas diferentes")
        return self


class EventoCredito(TransferenciaIn):
    model_config = ConfigDict(extra="forbid")
    tipo: Literal["CREDITAR"] = "CREDITAR"
    versao: Literal[1] = 1
    transferenciaId: UUID
    origemAgencia: int = Field(ge=0, le=2)
    destinoAgencia: int = Field(ge=0, le=2)
    vetorEnvio: list[StrictInt] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _particao(self):
        if self.idOrigem % 3 != self.origemAgencia or self.idDestino % 3 != self.destinoAgencia:
            raise ValueError("Particao da mensagem invalida.")
        if self.origemAgencia == self.destinoAgencia or any(n < 0 for n in self.vetorEnvio):
            raise ValueError("Agencias ou vetor invalidos.")
        return self


class LoginIn(BaseModel):
    usuario: str = Field(min_length=1)
    senha: str = Field(min_length=1)


class CadastroIn(BaseModel):
    usuario: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    senha: str = Field(min_length=6, max_length=72)


class EventoResultado(EventoCredito):
    tipo: Literal["CONFIRMAR"] = "CONFIRMAR"
    resultado: Literal["CREDITO_APLICADO", "CREDITO_FALHOU"]
    motivo: str | None = Field(default=None, max_length=300)
