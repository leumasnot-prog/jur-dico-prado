"""Varredura automática em dias úteis.

Roda às 06:00 America/Sao_Paulo, ANTES do expediente, para que o painel já esteja
atualizado quando a equipe chegar.

Duas regras que evitam problemas conhecidos:
1. Não roda em fim de semana nem feriado forense — reaproveita o calendário do
   MCP, que já sabe o que é dia útil (inclusive recesso e feriado estadual).
2. Timeout de 90s com retry: o DJEN responde em 10-16s sob concorrência e o
   timeout padrão de 45s já estourou em teste real.
"""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import FUSO_FORO, hoje, settings
from app.core.db import get_sessionmaker
from app.core.seguranca import registrar

logger = structlog.get_logger(__name__)
_scheduler: AsyncIOScheduler | None = None

TENTATIVAS = 3
ESPERA_INICIAL = 20  # segundos; dobra a cada tentativa


def _e_dia_util() -> bool:
    from mcp_juridico_brasil.prazo.calendario import eh_dia_util

    return eh_dia_util(hoje(), settings.juridico_uf)


async def executar_varredura_automatica() -> None:
    """Uma varredura, com retry. Falha registrada é falha tratável; silêncio não."""
    if not _e_dia_util():
        logger.info("varredura_pulada_sem_expediente", data=hoje().isoformat())
        return

    from app.services.acervo import varrer_e_persistir

    espera = ESPERA_INICIAL
    for tentativa in range(1, TENTATIVAS + 1):
        async with get_sessionmaker()() as sessao:
            try:
                resultado = await varrer_e_persistir(sessao)
                await registrar(sessao, acao="varredura_automatica",
                                detalhe={**resultado, "tentativa": tentativa})
                await sessao.commit()
                # Publicacao nova com prazo curto nao espera o proximo intervalo
                # do Hermes: a varredura das 06:00 e justamente quando ela chega.
                await _avisar_hermes(sessao)
                return
            except Exception as exc:
                logger.warning("varredura_automatica_falhou", tentativa=tentativa,
                               erro=type(exc).__name__, detalhe=str(exc)[:200])
                await registrar(sessao, acao="varredura_automatica_falhou",
                                detalhe={"tentativa": tentativa, "erro": type(exc).__name__,
                                         "detalhe": str(exc)[:300]})
                await sessao.commit()
        if tentativa < TENTATIVAS:
            await asyncio.sleep(espera)
            espera *= 2
    logger.error("varredura_automatica_desistiu", tentativas=TENTATIVAS)


async def _avisar_hermes(sessao) -> None:
    """Dispara os alertas logo apos a varredura. Falha aqui nao invalida a varredura."""
    if not (settings.hermes_ativo and settings.hermes_configurado):
        return
    from app.hermes.agendador import varrer_alertas

    try:
        enviados = await varrer_alertas(sessao)
        logger.info("hermes_apos_varredura", enviados=enviados)
    except Exception as exc:
        logger.error("hermes_apos_varredura_falhou", erro=type(exc).__name__)


def iniciar() -> AsyncIOScheduler | None:
    """Monta o agendador com o que estiver ligado.

    VARREDURA_ATIVA e HERMES_ATIVO sao chaves INDEPENDENTES. Desligar a varredura
    numa segunda instancia (para nao varrer o DJEN duas vezes) nao pode matar os
    alertas junto — o Hermes so le o banco, e rodar os dois e legitimo.
    """
    global _scheduler
    from app.hermes import agendador as hermes

    _scheduler = AsyncIOScheduler(timezone=FUSO_FORO)

    if settings.varredura_ativa:
        hora, _, minuto = settings.varredura_hora.partition(":")
        _scheduler.add_job(
            executar_varredura_automatica,
            CronTrigger(day_of_week="mon-fri", hour=int(hora), minute=int(minuto or 0),
                        timezone=FUSO_FORO),
            id="varredura_djen", replace_existing=True, misfire_grace_time=3600,
        )
    else:
        logger.info("varredura_desativada")

    hermes.registrar(_scheduler)

    if not _scheduler.get_jobs():
        logger.info("agendador_sem_tarefas")
        _scheduler = None
        return None

    _scheduler.start()
    logger.info("agendador_iniciado", tarefas=[j.id for j in _scheduler.get_jobs()],
                fuso="America/Sao_Paulo")
    return _scheduler


def parar() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
