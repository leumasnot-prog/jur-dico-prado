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

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.seguranca import registrar

router = APIRouter(prefix="/cron", tags=["cron"])


def _verificar(segredo: Annotated[str | None, Header(alias="X-Cron-Secret")] = None) -> None:
    esperado = settings.cron_secret
    if not esperado or not secrets.compare_digest(segredo or "", esperado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Segredo de cron ausente ou inválido.")


@router.post("/varredura", dependencies=[Depends(_verificar)],
            summary="Aciona a varredura do DJEN (chamado pelo GitHub Actions)")
async def varredura(sessao: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    from app.services.acervo import varrer_e_persistir

    resultado = await varrer_e_persistir(sessao)
    await registrar(sessao, acao="varredura_cron", detalhe=resultado)
    await sessao.commit()
    return resultado


@router.post("/hermes", dependencies=[Depends(_verificar)],
            summary="Aciona resumo diário e alertas do Hermes (chamado pelo GitHub Actions)")
async def hermes(sessao: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    """Chamado a cada 30 min, todo dia — a lógica de dia útil, horário e
    não-repetição já mora em `resumo_diario`/`varrer_alertas`. Chamar fora de
    hora não tem efeito, por isso o agendamento externo pode ser generoso."""
    from app.hermes.agendador import resumo_diario, varrer_alertas

    enviou_resumo = await resumo_diario(sessao)
    alertas_enviados = await varrer_alertas(sessao)
    return {"resumo_diario_enviado": enviou_resumo, "alertas_enviados": alertas_enviados}
