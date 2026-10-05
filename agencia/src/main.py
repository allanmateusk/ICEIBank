"""Entrypoint da agência do ICEIBank (FastAPI).

Rodar cada agência com um AGENCIA_ID diferente:

    AGENCIA_ID=0 uv run uvicorn src.main:app --port 4000
    AGENCIA_ID=1 uv run uvicorn src.main:app --port 4001
    AGENCIA_ID=2 uv run uvicorn src.main:app --port 4002

Docs interativas: http://localhost:400X/docs
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import estado
from .banco import fechar as fechar_banco
from .banco import iniciar as iniciar_banco
from .rotas import router
from .controllers import transferencias_controller
from .services.mensageria import Mensageria


@asynccontextmanager
async def lifespan(app):
    iniciar_banco()
    broker = Mensageria(estado.ID_AGENCIA, transferencias_controller.consumir)
    app.state.mensageria = broker
    transferencias_controller.broker_ativo = broker
    await broker.iniciar()
    try:
        yield
    finally:
        await broker.fechar()
        fechar_banco()

app = FastAPI(
    title=f"ICEIBank - Agencia {estado.ID_AGENCIA}",
    description="Sprint 2 - RabbitMQ, relogio vetorial e confirmacao de credito",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: o frontend (Vite) roda em http://localhost:5173 e chama esta API em
# outra porta. Config permissiva de desenvolvimento - restringir em producao.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["meta"])
def raiz() -> dict:
    return {"servico": "ICEIBank - agencia", "idAgencia": estado.ID_AGENCIA}
