"""Engine e sessão assíncrona.

O engine é PREGUIÇOSO de propósito: criá-lo no import derruba o módulo inteiro
quando DATABASE_URL não está configurada — inclusive ao rodar `--help`, ao coletar
testes ou ao gerar migração. Falha de configuração deve aparecer na primeira
consulta, com mensagem clara, não no import.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL não configurada. Copie .env.example para .env e preencha "
                "com a string de conexão do Postgres (Neon em produção)."
            )
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), class_=AsyncSession,
                                           expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as sessao:
        yield sessao


async def reset_engine() -> None:
    """Descarta engine e sessionmaker (uso em testes e após troca de configuração)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
