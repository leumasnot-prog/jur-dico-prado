"""Decide QUANDO avisar e QUEM avisar. Junta o formatador ao transporte.

Duas rotinas, com cadências diferentes de propósito:

  resumo_diario   08:00, dias úteis do calendário forense, no grupo.
  varrer_alertas  de 30 em 30 minutos, fora da janela de silêncio, no privado
                  do procurador responsável.

O que impede o bot de virar ruído:
  - No máximo UM alerta por publicação e por destinatário. A garantia é do
    banco (índice parcial único em `hermes_envios.chave`), não deste código:
    código com bug repete, índice único não.
  - Silêncio entre 20h e 07h. O que acontecer nessa janela entra no resumo da
    manhã, que é o lugar certo para uma notícia que já não é urgente.
  - Nada em fim de semana e feriado forense — o calendário vem do MCP, que já
    sabe o que é dia útil, recesso e feriado estadual.
"""

from __future__ import annotations

import datetime
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import FUSO_FORO, agora, hoje, settings
from app.core.db import get_sessionmaker
from app.hermes.formatador import (
    ItemPrazo,
    botoes_alerta,
    montar_alerta_critico,
    montar_resumo_diario,
)
from app.hermes.telegram import ClienteTelegram, TelegramErro
from app.models import EnvioHermes, Processo, Publicacao, Triagem, Usuario, VinculoTelegram

logger = structlog.get_logger(__name__)

# Palavras que tornam uma publicação urgente independentemente do prazo.
# Curta de propósito: cada termo a mais é uma chance a mais de alarme falso, e
# alarme falso é o que faz a equipe parar de ler o bot.
PALAVRAS_URGENTES: tuple[str, ...] = (
    "liminar", "tutela de urgencia", "tutela de urgência",
    "penhora", "bloqueio", "sequestro", "busca e apreensao", "busca e apreensão",
)

TRIAGEM_ENCERRADA = ("concluido", "sem_providencia")


def _dias_uteis_ate(destino: datetime.date, partida: datetime.date | None = None) -> int:
    """Dias úteis entre hoje e o vencimento. Negativo quando já venceu."""
    from mcp_juridico_brasil.prazo.calendario import eh_dia_util

    partida = partida or hoje()
    if destino == partida:
        return 0
    passo = 1 if destino > partida else -1
    dias, cursor = 0, partida
    while cursor != destino:
        cursor += datetime.timedelta(days=passo)
        if eh_dia_util(cursor, settings.juridico_uf):
            dias += passo
    return dias


def _e_dia_util(data: datetime.date | None = None) -> bool:
    from mcp_juridico_brasil.prazo.calendario import eh_dia_util

    return bool(eh_dia_util(data or hoje(), settings.juridico_uf))


def _urgencia_no_texto(texto: str | None) -> str | None:
    baixo = (texto or "").lower()
    for palavra in PALAVRAS_URGENTES:
        if palavra in baixo:
            return palavra
    return None


async def _reservar(
    sessao: AsyncSession, *, chave: str, tipo: str, destino: str,
    usuario_id: int | None = None, publicacao_id: str | None = None,
) -> int | None:
    """Marca a intenção de enviar ANTES de enviar. Devolve o id, ou None se já foi.

    Reservar antes é o que fecha a janela entre "decidi mandar" e "mandei": se
    duas execuções coincidirem, a segunda encontra a chave tomada e desiste.
    """
    stmt = insert(EnvioHermes).values(
        chave=chave, tipo=tipo, destino=destino, usuario_id=usuario_id,
        publicacao_id=publicacao_id, sucesso=None, criado_em=agora(),
    ).on_conflict_do_nothing(
        index_elements=["chave"], index_where=text("sucesso IS NOT FALSE")
    ).returning(EnvioHermes.id)
    reservado = await sessao.scalar(stmt)
    return int(reservado) if reservado is not None else None


async def _concluir(sessao: AsyncSession, envio_id: int, *, erro: str | None = None) -> None:
    """Fecha a reserva. `sucesso=False` LIBERA a chave para nova tentativa."""
    await sessao.execute(
        update(EnvioHermes).where(EnvioHermes.id == envio_id)
        .values(sucesso=erro is None, erro=(erro[:400] if erro else None))
    )


async def _enviar(
    sessao: AsyncSession, cliente: ClienteTelegram, *, chave: str, tipo: str,
    chat_id: str, texto: str, botoes: Any = None,
    usuario_id: int | None = None, publicacao_id: str | None = None,
) -> bool:
    """Reserva, envia, registra. É por aqui que passa TODO envio do Hermes."""
    envio_id = await _reservar(sessao, chave=chave, tipo=tipo, destino=chat_id,
                               usuario_id=usuario_id, publicacao_id=publicacao_id)
    await sessao.commit()
    if envio_id is None:
        logger.debug("hermes_ja_enviado", chave=chave)
        return False
    try:
        await cliente.enviar(chat_id, texto, botoes)
    except TelegramErro as exc:
        await _concluir(sessao, envio_id, erro=str(exc))
        await sessao.commit()
        logger.warning("hermes_envio_falhou", chave=chave, erro=str(exc)[:200])
        return False
    await _concluir(sessao, envio_id)
    await sessao.commit()
    logger.info("hermes_enviado", chave=chave, tipo=tipo)
    return True


# ── Coleta ────────────────────────────────────────────────────────────────

async def coletar_criticos(sessao: AsyncSession) -> list[ItemPrazo]:
    """Publicações que merecem alerta: prazo curto OU palavra de urgência.

    Vencidas entram também, limitadas a uma semana para trás: prazo perdido é
    exatamente o que não pode passar em silêncio, mas o acervo antigo inteiro
    não pode ressurgir num dia.
    """
    limite = settings.hermes_dias_criticos
    h = hoje()
    janela_inicio = h - datetime.timedelta(days=7)
    # A folga em dias corridos cobre feriados: 3 dias úteis podem levar 6 de
    # calendário. O corte exato vem depois, em dias úteis.
    janela_fim = h + datetime.timedelta(days=limite * 2 + 4)

    # A palavra de urgência vale INDEPENDENTEMENTE do prazo — uma penhora com
    # vencimento em 40 dias continua sendo uma penhora. Por isso ela entra no
    # SQL, e não só no filtro em Python: o que a consulta não traz, o filtro
    # nunca vê. O piso `janela_inicio` continua valendo para as duas pontas,
    # senão o acervo antigo inteiro ressurgiria num dia.
    urgencia = or_(*[Publicacao.texto.ilike(f"%{p}%") for p in PALAVRAS_URGENTES])
    q = (select(Publicacao, Triagem, Processo.numero_formatado)
         .join(Processo, Processo.numero_processo == Publicacao.numero_processo)
         .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
         .where(Publicacao.vencimento.is_not(None),
                Publicacao.vencimento >= janela_inicio,
                or_(Publicacao.vencimento <= janela_fim, urgencia),
                func.coalesce(Triagem.status, "novo").not_in(TRIAGEM_ENCERRADA))
         .order_by(Publicacao.vencimento))

    itens: list[ItemPrazo] = []
    for pub, tri, formatado in await sessao.execute(q):
        assert pub.vencimento is not None
        restantes = _dias_uteis_ate(pub.vencimento)
        urgente = _urgencia_no_texto(pub.texto)
        if restantes > limite and not urgente:
            continue
        itens.append(ItemPrazo(
            publicacao_id=pub.id,
            numero=formatado or pub.numero_processo,
            tribunal=pub.tribunal,
            ato=pub.ato_inferido or "Manifestação",
            rito=pub.rito_inferido or "comum",
            vencimento=pub.vencimento,
            dias_restantes=restantes,
            partes=tuple(str(p.get("nome", "")) for p in (pub.partes or [])),
            responsavel_id=(tri.responsavel_id if tri else None),
            motivo=("prazo" if restantes <= limite else str(urgente)),
        ))
    return itens


async def coletar_resumo(sessao: AsyncSession) -> dict[str, Any]:
    # Duas listas, não uma: o que vence logo e o que é urgente por natureza.
    # Um item entra em exatamente uma delas.
    todos = [i for i in await coletar_criticos(sessao) if i.dias_restantes >= 0]
    criticos = [i for i in todos if i.motivo == "prazo"]
    urgentes = [i for i in todos if i.motivo != "prazo"]
    sem_triagem = await sessao.scalar(
        select(func.count()).select_from(Publicacao)
        .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
        .where(func.coalesce(Triagem.status, "novo") == "novo")) or 0
    por_tribunal = await sessao.execute(
        select(Publicacao.tribunal, func.count())
        .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
        .where(func.coalesce(Triagem.status, "novo") == "novo")
        .group_by(Publicacao.tribunal))
    total = await sessao.scalar(select(func.count()).select_from(Processo)) or 0
    return {"criticos": criticos, "urgentes": urgentes, "sem_triagem": int(sem_triagem),
            "novas_por_tribunal": {t: int(q) for t, q in por_tribunal},
            "total_processos": int(total)}


# ── Rotinas agendadas ─────────────────────────────────────────────────────

async def resumo_diario(sessao: AsyncSession, cliente: ClienteTelegram | None = None) -> bool:
    """Boletim das 08:00 no grupo. Devolve True se algo foi enviado."""
    if not settings.telegram_chat_id_grupo:
        logger.info("hermes_sem_grupo_configurado")
        return False
    if not _e_dia_util():
        logger.info("hermes_resumo_pulado_sem_expediente", data=hoje().isoformat())
        return False

    dados = await coletar_resumo(sessao)
    texto = montar_resumo_diario(
        data=hoje(), criticos=dados["criticos"], urgentes=dados["urgentes"],
        novas_por_tribunal=dados["novas_por_tribunal"],
        sem_triagem=dados["sem_triagem"], total_processos=dados["total_processos"],
        base_url=settings.painel_base_url, dias_criticos=settings.hermes_dias_criticos,
    )
    return await _enviar(
        sessao, cliente or ClienteTelegram(),
        chave=f"resumo:{hoje().isoformat()}", tipo="resumo_diario",
        chat_id=settings.telegram_chat_id_grupo, texto=texto,
    )


async def varrer_alertas(sessao: AsyncSession, cliente: ClienteTelegram | None = None) -> int:
    """Alertas críticos no privado. Devolve quantos foram enviados agora."""
    if settings.janela_de_silencio(agora().time()):
        logger.debug("hermes_em_silencio")
        return 0

    itens = await coletar_criticos(sessao)
    if not itens:
        return 0
    cliente = cliente or ClienteTelegram()

    # Um SELECT para todos os vínculos: o alternativo seria uma consulta por
    # item, e a lista de críticos pode passar de cem numa segunda-feira.
    vinculos = {
        v.usuario_id: v for v in (await sessao.scalars(
            select(VinculoTelegram).where(VinculoTelegram.ativo.is_(True),
                                          VinculoTelegram.telegram_chat_id.is_not(None))))
    }
    nomes: dict[int, str] = {}
    if vinculos:
        achados = await sessao.scalars(select(Usuario).where(Usuario.id.in_(list(vinculos))))
        nomes = {u.id: u.nome for u in achados}

    enviados = 0
    for item in itens:
        vinculo = vinculos.get(item.responsavel_id) if item.responsavel_id else None
        if vinculo is None:
            # Sem responsável ou sem opt-in: o aviso vai ao grupo, porque o pior
            # destino de um prazo crítico é destino nenhum. Sem nomes, o texto de
            # grupo já é seguro por construção.
            if not settings.telegram_chat_id_grupo:
                continue
            texto = montar_alerta_critico(
                item=item, nome_procurador="sem responsável atribuído",
                base_url=settings.painel_base_url)
            ok = await _enviar(
                sessao, cliente, chave=f"alerta:{item.publicacao_id}:grupo",
                tipo="alerta_sem_dono", chat_id=settings.telegram_chat_id_grupo,
                texto=texto, botoes=botoes_alerta(item.publicacao_id, settings.painel_base_url),
                publicacao_id=item.publicacao_id)
        else:
            assert vinculo.telegram_chat_id is not None
            texto = montar_alerta_critico(
                item=item, nome_procurador=nomes.get(vinculo.usuario_id, "procurador(a)"),
                base_url=settings.painel_base_url)
            ok = await _enviar(
                sessao, cliente,
                chave=f"alerta:{item.publicacao_id}:{vinculo.usuario_id}",
                tipo="alerta_critico", chat_id=vinculo.telegram_chat_id, texto=texto,
                botoes=botoes_alerta(item.publicacao_id, settings.painel_base_url),
                usuario_id=vinculo.usuario_id, publicacao_id=item.publicacao_id)
        enviados += int(ok)
    return enviados


async def _job_resumo() -> None:
    async with get_sessionmaker()() as sessao:
        try:
            await resumo_diario(sessao)
        except Exception as exc:
            logger.error("hermes_resumo_erro", erro=type(exc).__name__, detalhe=str(exc)[:300])


async def _job_alertas() -> None:
    async with get_sessionmaker()() as sessao:
        try:
            await varrer_alertas(sessao)
        except Exception as exc:
            logger.error("hermes_alertas_erro", erro=type(exc).__name__, detalhe=str(exc)[:300])


def registrar(scheduler: AsyncIOScheduler) -> None:
    """Pendura as rotinas do Hermes no agendador que já existe."""
    if not (settings.hermes_ativo and settings.hermes_configurado):
        logger.info("hermes_desativado", configurado=settings.hermes_configurado)
        return
    hora, _, minuto = settings.telegram_hora_resumo.partition(":")
    scheduler.add_job(
        _job_resumo,
        CronTrigger(day_of_week="mon-fri", hour=int(hora), minute=int(minuto or 0),
                    timezone=FUSO_FORO),
        id="hermes_resumo", replace_existing=True, misfire_grace_time=3600,
    )
    scheduler.add_job(
        _job_alertas,
        IntervalTrigger(minutes=settings.hermes_intervalo_alertas_min, timezone=FUSO_FORO),
        id="hermes_alertas", replace_existing=True, misfire_grace_time=600,
    )
    logger.info("hermes_agendado", resumo=settings.telegram_hora_resumo,
                alertas_min=settings.hermes_intervalo_alertas_min)
