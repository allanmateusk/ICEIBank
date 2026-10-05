"""Controller de autenticação (Parte F).

POST /auth/login: recebe usuário + senha; se válidos, devolve um JWT.
"""
from fastapi import HTTPException

from ..banco import ativo, inserir_usuario
from ..esquemas import CadastroIn, LoginIn
from ..seguranca import JWT_EXPIRACAO_MIN, autenticar, criar_token


def cadastro(dados: CadastroIn) -> dict:
    if not ativo():
        raise HTTPException(
            503,
            "Banco de dados indisponivel. Suba o Postgres antes de criar usuarios.",
        )
    if not inserir_usuario(dados.usuario, dados.senha):
        raise HTTPException(409, "Usuario ja existe.")
    return {"usuario": dados.usuario}


def login(dados: LoginIn) -> dict:
    if not autenticar(dados.usuario, dados.senha):
        raise HTTPException(401, "Usuario ou senha invalidos.")
    token = criar_token(sub=dados.usuario)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expira_em_min": JWT_EXPIRACAO_MIN,
    }
