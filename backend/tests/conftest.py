"""Fixtures: banco real por teste, em schema isolado.

Testa contra Postgres de verdade, não SQLite: o schema usa JSONB e ON CONFLICT,
que SQLite não tem. Testar num banco diferente do de produção é testar outra coisa.
"""

from __future__ import annotations

import os

import pytest_asyncio

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:devlocal@localhost:55432/pradopolis_test"
)
os.environ.setdefault("JWT_SECRET", "segredo-de-teste-nao-usar-em-producao")
os.environ.setdefault("VARREDURA_ATIVA", "false")


@pytest_asyncio.fixture
async def sessao():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models  # noqa: F401
    from app.core.config import settings
    from app.core.db import Base

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def cliente(sessao):
    from httpx import ASGITransport, AsyncClient

    from app.core.db import get_session
    from app.main import app

    async def _sessao_de_teste():
        yield sessao

    app.dependency_overrides[get_session] = _sessao_de_teste
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def usuarios(sessao):
    """Um usuário de cada papel, com senha conhecida."""
    from app.core.seguranca import hash_senha
    from app.models import Papel, Procurador, Usuario

    senha = hash_senha("senha-de-teste-longa")
    feitos = {}
    for papel in (Papel.CHEFE, Papel.PROCURADOR, Papel.ASSESSOR, Papel.ESTAGIARIO):
        u = Usuario(nome=f"Teste {papel}", email=f"{papel}@t.gov.br",
                    senha_hash=senha, papel=papel)
        sessao.add(u)
        feitos[str(papel)] = u
    await sessao.flush()
    sessao.add(Procurador(usuario_id=feitos["procurador"].id, oab_uf="SP", oab_numero="274238"))
    await sessao.commit()
    return feitos


@pytest_asyncio.fixture
async def token(cliente, usuarios):
    async def _obter(papel: str) -> str:
        r = await cliente.post("/auth/login",
                               data={"username": f"{papel}@t.gov.br",
                                     "password": "senha-de-teste-longa"})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    return _obter
