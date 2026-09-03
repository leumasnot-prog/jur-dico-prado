"""Serviço do Painel Jurídico de Pradópolis.

Consome o MCP (`mcp_juridico_brasil`) para o domínio processual e acrescenta o
que ele não faz: acervo permanente, usuários com papéis, triagem compartilhada,
varredura automática e trilha de auditoria.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.db import reset_engine
from app.hermes.webhook import router as hermes_router
from app.routers.acervo import router as acervo_router
from app.routers.auth import router as auth_router
from app.routers.relatorios import router as relatorios_router
from app.services import agendador

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    agendador.iniciar()
    yield
    agendador.parar()
    await reset_engine()


app = FastAPI(
    title="Painel Jurídico Pradópolis",
    description=("Acervo processual do Departamento Jurídico: DJEN, cálculo de prazo "
                 "do ente público, triagem compartilhada e auditoria."),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health", tags=["infra"], summary="Healthcheck")
async def health() -> dict[str, object]:
    return {"status": "ok", "varredura_ativa": settings.varredura_ativa,
            "banco_configurado": bool(settings.database_url),
            "hermes_configurado": settings.hermes_configurado}


app.include_router(auth_router)
app.include_router(acervo_router)
app.include_router(relatorios_router)
app.include_router(hermes_router)

# O painel é servido pelo próprio serviço: um processo só para publicar, e a
# API na mesma origem — sem CORS e sem token atravessando domínio.
_PAINEL = Path(__file__).parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
async def painel() -> FileResponse:
    return FileResponse(_PAINEL, media_type="text/html")
