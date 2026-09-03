"""Acionamento externo por cron — para hosts de plano gratuito.

O Render (e equivalentes) hibernam o serviço sem uso, e sem uso é exatamente
o estado em que a varredura das 06h e os alertas do Hermes precisam disparar
sozinhos. Em vez de manter uma instância paga só para o agendador interno
ficar vivo, um workflow do GitHub Actions acorda o serviço com uma chamada
HTTP — e essa própria chamada JÁ É o disparo da tarefa.

Protegido por segredo estático, não por login: quem chama aqui é uma Action,
não uma pessoa. `CRON_SECRET` vazio fecha as duas rotas para sempre — não as
deixa abertas.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.seguranca import registrar

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/cron", tags=["cron"])


def _verificar(segredo: Annotated[str | None, Header(alias="X-Cron-Secret")] = None) -> None:
    esperado = settings.cron_secret
    if not esperado or not secrets.compare_digest(segredo or "", esperado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Segredo de cron ausente ou inválido.")


async def _relatar(sessao: AsyncSession, acao: str, exc: Exception) -> HTTPException:
    """Registra a falha e devolve um erro QUE DIZ O QUE ACONTECEU.

    Um 500 pelado num endpoint de cron é inútil: quem lê é o log de uma
    GitHub Action, sem acesso ao dashboard do host. A causa precisa vir na
    resposta, ou a falha vira mistério — foi exatamente o que aconteceu com o
    primeiro disparo em produção.

    A trilha guarda o mesmo, para haver registro mesmo se ninguém ler a Action.
    """
    detalhe = f"{type(exc).__name__}: {exc}"[:400]
    logger.error("cron_falhou", acao=acao, erro=type(exc).__name__, detalhe=detalhe)
    try:
        await sessao.rollback()
        await registrar(sessao, acao=f"{acao}_falhou", detalhe={"erro": detalhe})
        await sessao.commit()
    except Exception:  # banco fora do ar não pode engolir a causa original
        logger.error("cron_auditoria_falhou", acao=acao)
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detalhe)


@router.post("/varredura", dependencies=[Depends(_verificar)],
            summary="Aciona a varredura do DJEN (chamado pelo GitHub Actions)")
async def varredura(sessao: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    from app.services.acervo import varrer_e_persistir

    try:
        resultado = await varrer_e_persistir(sessao)
        await registrar(sessao, acao="varredura_cron", detalhe=resultado)
        await sessao.commit()
    except Exception as exc:
        raise await _relatar(sessao, "varredura_cron", exc) from exc
    return resultado


@router.post("/hermes", dependencies=[Depends(_verificar)],
            summary="Aciona resumo diário e alertas do Hermes (chamado pelo GitHub Actions)")
async def hermes(sessao: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    """Chamado a cada 30 min, todo dia — a lógica de dia útil, horário e
    não-repetição já mora em `resumo_diario`/`varrer_alertas`. Chamar fora de
    hora não tem efeito, por isso o agendamento externo pode ser generoso."""
    from app.hermes.agendador import resumo_diario, varrer_alertas

    try:
        enviou_resumo = await resumo_diario(sessao)
        alertas_enviados = await varrer_alertas(sessao)
    except Exception as exc:
        raise await _relatar(sessao, "hermes_cron", exc) from exc
    return {"resumo_diario_enviado": enviou_resumo, "alertas_enviados": alertas_enviados}


@router.get("/diagnostico", dependencies=[Depends(_verificar)],
            summary="Confere se o serviço alcança o que precisa alcançar")
async def diagnostico(sessao: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    """Testa banco, DJEN e Telegram um a um, e diz qual falhou.

    Existe porque num host gerenciado não há shell para depurar: sem isto, a
    unica pista de uma falha e o codigo HTTP.
    """
    from sqlalchemy import text as sql

    saida: dict[str, Any] = {}

    try:
        await sessao.execute(sql("select 1"))
        saida["banco"] = "ok"
    except Exception as exc:
        saida["banco"] = f"{type(exc).__name__}: {exc}"[:200]

    # O DJEN e sondado DUAS VEZES, com cabecalhos diferentes. Um 403 sozinho
    # nao diz se o bloqueio e do IP (datacenter) ou do User-Agent (WAF barrando
    # cliente de script), e a diferenca decide a correcao: cabecalho se resolve
    # numa linha, IP exige varrer de outro lugar.
    import httpx

    ua_navegador = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
    sondas = {
        "djen": None,  # cabecalho padrao do httpx
        "djen_com_user_agent": {"User-Agent": ua_navegador, "Accept": "application/json",
                                "Accept-Language": "pt-BR,pt;q=0.9"},
    }
    for rotulo, cabecalhos in sondas.items():
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.get("https://comunicaapi.pje.jus.br/api/v1/comunicacao",
                                params={"numeroOab": "274238", "ufOab": "SP",
                                        "itensPorPagina": 1},
                                headers=cabecalhos)
            nota = f"HTTP {r.status_code}"
            if r.status_code != 200:
                servidor = r.headers.get("server", "?")
                corpo = r.text[:120].replace("\n", " ")
                nota += f" · server={servidor} · {corpo}"
            saida[rotulo] = nota
        except Exception as exc:
            saida[rotulo] = f"{type(exc).__name__}: {exc}"[:200]

    if settings.telegram_bot_token:
        from app.hermes.telegram import ClienteTelegram, TelegramErro

        try:
            me = await ClienteTelegram().quem_sou_eu()
            saida["telegram"] = f"ok — @{me.get('username')}"
        except TelegramErro as exc:
            saida["telegram"] = str(exc)[:200]
    else:
        saida["telegram"] = "sem token configurado"

    return saida
