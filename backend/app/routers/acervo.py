"""Rotas do acervo: publicações, triagem, carteira, prazos e varredura."""

from __future__ import annotations

import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import hoje
from app.core.db import get_session
from app.core.seguranca import (
    PODE_ATRIBUIR,
    PODE_VARRER,
    PODE_VER_SIGILOSO,
    registrar,
    requer_papel,
    usuario_atual,
)
from app.models import Processo, Publicacao, StatusTriagem, Triagem, Usuario
from app.services import acervo as servico
from app.services.prazo_cache import prazo_completo

router = APIRouter(prefix="/acervo", tags=["acervo"])


class TriagemIn(BaseModel):
    status: StatusTriagem
    responsavel_id: int | None = None
    anotacao: str | None = Field(default=None, max_length=2000)


def _restringe_sigilo(consulta, usuario: Usuario):
    """Segredo de justiça só para quem tem atribuição (chefe e procurador)."""
    if usuario.papel in {str(p) for p in PODE_VER_SIGILOSO}:
        return consulta
    return consulta.where(Processo.segredo_justica.is_(False))


@router.post("/varredura", summary="Varre o DJEN e atualiza o acervo")
async def varredura(
    usuario: Annotated[Usuario, Depends(requer_papel(*PODE_VARRER))],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
    dias: int = Query(default=30, ge=1, le=400),
) -> dict[str, Any]:
    resultado = await servico.varrer_e_persistir(sessao, dias=dias)
    await registrar(sessao, acao="varredura_manual", usuario_id=usuario.id,
                    detalhe=resultado, request=request)
    await sessao.commit()
    return resultado


@router.get("/publicacoes", summary="Feed de publicações")
async def publicacoes(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    minhas: bool = Query(default=False, description="Só as atribuídas a mim"),
    status_triagem: str | None = None,
    tribunal: str | None = None,
    busca: str | None = None,
    dias: int = Query(default=45, ge=1, le=400),
    limite: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    desde = hoje() - datetime.timedelta(days=dias)
    q = (select(Publicacao, Triagem, Processo.numero_formatado).join(Processo)
         .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
         .where(Publicacao.data_disponibilizacao >= desde))
    q = _restringe_sigilo(q, usuario)

    if minhas:
        q = q.where(Triagem.responsavel_id == usuario.id)
    if tribunal:
        q = q.where(Publicacao.tribunal == tribunal.upper())
    if status_triagem:
        q = q.where(func.coalesce(Triagem.status, "novo") == status_triagem)
    if busca:
        alvo = f"%{busca}%"
        q = q.where(Publicacao.numero_processo.ilike(alvo) | Publicacao.texto.ilike(alvo)
                    | Publicacao.partes.cast(__import__("sqlalchemy").Text).ilike(alvo))

    q = q.order_by(Publicacao.data_disponibilizacao.desc()).limit(limite).offset(offset)
    linhas = await sessao.execute(q)

    saida = []
    for pub, tri, formatado in linhas:
        saida.append({
            "id": pub.id, "numero_processo": pub.numero_processo,
            "numero_formatado": formatado, "tribunal": pub.tribunal, "orgao": pub.orgao,
            "classe": pub.classe, "data_disponibilizacao": pub.data_disponibilizacao,
            "tipo_documento": pub.tipo_documento, "meio": pub.meio,
            "link_validacao": pub.link_validacao, "partes": pub.partes,
            "advogados": pub.advogados, "texto": pub.texto,
            "prazo_no_texto": pub.prazo_no_texto, "ato": pub.ato_inferido,
            "rito": pub.rito_inferido, "vencimento": pub.vencimento,
            # Memória de cálculo completa: é dela que a tela monta os quatro
            # marcos e os tooltips que explicam a regra aplicada.
            "prazo": await prazo_completo(pub.data_disponibilizacao, pub.ato_inferido,
                                          pub.rito_inferido),
            "status_triagem": (tri.status if tri else "novo"),
            "responsavel_id": (tri.responsavel_id if tri else None),
            "anotacao": (tri.anotacao if tri else None),
        })
    return saida


@router.patch("/publicacoes/{publicacao_id}/triagem", summary="Atualiza a triagem")
async def triagem(
    publicacao_id: str, corpo: TriagemIn,
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> dict[str, Any]:
    pub = await sessao.get(Publicacao, publicacao_id)
    if pub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publicação não encontrada.")

    # Atribuir a OUTRA pessoa é privativo do chefe. Atribuir a si mesmo, não.
    if (corpo.responsavel_id is not None and corpo.responsavel_id != usuario.id
            and usuario.papel not in {str(p) for p in PODE_ATRIBUIR}):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Só o procurador-chefe atribui publicação a outra pessoa.")

    atual = await sessao.get(Triagem, publicacao_id)
    anterior = atual.status if atual else "novo"
    if atual is None:
        atual = Triagem(publicacao_id=publicacao_id)
        sessao.add(atual)
    atual.status = corpo.status
    atual.anotacao = corpo.anotacao
    atual.atualizado_por_id = usuario.id
    if corpo.responsavel_id is not None:
        atual.responsavel_id = corpo.responsavel_id

    await registrar(sessao, acao="triagem", usuario_id=usuario.id, entidade="publicacao",
                    entidade_id=publicacao_id,
                    detalhe={"de": anterior, "para": str(corpo.status),
                             "responsavel_id": atual.responsavel_id}, request=request)
    await sessao.commit()
    return {"publicacao_id": publicacao_id, "status": str(corpo.status),
            "responsavel_id": atual.responsavel_id}


@router.get("/processos", summary="Carteira processual")
async def processos(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    limite: int = Query(default=500, ge=1, le=2000),
) -> list[dict[str, Any]]:
    q = _restringe_sigilo(select(Processo).options(selectinload(Processo.publicacoes)), usuario)
    achado = await sessao.execute(q.limit(limite))
    saida = []
    for p in achado.scalars():
        pubs = p.publicacoes
        futuros = [x.vencimento for x in pubs if x.vencimento and x.vencimento >= hoje()]
        saida.append({
            "numero_processo": p.numero_processo, "numero_formatado": p.numero_formatado,
            "tribunal": p.tribunal, "orgao": p.orgao, "classe": p.classe,
            "polo_do_ente": p.polo_do_ente, "total_publicacoes": len(pubs),
            "ultima_publicacao": max((x.data_disponibilizacao for x in pubs), default=None),
            "proximo_vencimento": min(futuros, default=None),
            "partes_contrarias": p.partes_contrarias, "advogados": p.advogados,
        })
    saida.sort(key=lambda x: (x["ultima_publicacao"] or datetime.date.min), reverse=True)
    return saida


@router.get("/prazos", summary="Agenda de vencimentos")
async def prazos(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    minhas: bool = False,
    dias_atras: int = Query(default=14, ge=0, le=90),
) -> list[dict[str, Any]]:
    corte = hoje() - datetime.timedelta(days=dias_atras)
    q = (select(Publicacao, Triagem).join(Processo)
         .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
         .where(Publicacao.vencimento.is_not(None), Publicacao.vencimento >= corte))
    q = _restringe_sigilo(q, usuario)
    if minhas:
        q = q.where(Triagem.responsavel_id == usuario.id)
    achado = await sessao.execute(q.order_by(Publicacao.vencimento))
    return [{"id": p.id, "numero_processo": p.numero_processo, "tribunal": p.tribunal,
             "classe": p.classe, "ato": p.ato_inferido, "rito": p.rito_inferido,
             "vencimento": p.vencimento, "dias_restantes": (p.vencimento - hoje()).days,
             "status_triagem": (t.status if t else "novo"),
             "responsavel_id": (t.responsavel_id if t else None)}
            for p, t in achado]


class CalculoIn(BaseModel):
    disponibilizacao: datetime.date
    ato: str
    rito: str = "comum"
    fazenda_publica: bool = True


@router.post("/calcular-prazo", summary="Calculadora avulsa de prazo")
async def calcular_prazo(
    corpo: CalculoIn,
    _: Annotated[Usuario, Depends(usuario_atual)],
) -> dict[str, Any]:
    """Mesma regra do acervo: quem calcula é o MCP, aqui só se repassa."""
    from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo

    try:
        r = await calcular_proximo_prazo(
            numero_processo="0000000-00.0000.0.00.0000", tribunal="TJSP",
            tipo_ato=corpo.ato, uf="SP",
            data_intimacao_iso=corpo.disponibilizacao.isoformat(),
            parte_fazenda_publica=corpo.fazenda_publica, rito=corpo.rito,
            data_e_disponibilizacao_djen=True,
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return {
        "ato": r["tipo_ato"], "rito": r["rito"], "dias": r["dias_uteis_prazo"],
        "simples": r["dias_uteis_prazo_simples"], "mult": r.get("multiplicador", 1),
        "publicacao": r["data_intimacao_iso"], "termo": r["termo_inicial_iso"],
        "fim": r["data_final_iso"], "fundamento": r["fundamento_prazo"],
        "obstaculos": [[o["data"], o["descricao"]]
                       for o in r.get("feriados_e_recessos_no_periodo", [])],
    }


@router.get("/estatisticas", summary="Indicadores do painel")
async def estatisticas(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    h = hoje()
    total_proc = await sessao.scalar(select(func.count()).select_from(Processo))
    total_pub = await sessao.scalar(select(func.count()).select_from(Publicacao))
    sem_triagem = await sessao.scalar(
        select(func.count()).select_from(Publicacao)
        .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
        .where(func.coalesce(Triagem.status, "novo") == "novo"))
    criticos = await sessao.scalar(
        select(func.count()).select_from(Publicacao)
        .where(Publicacao.vencimento.between(h, h + datetime.timedelta(days=3))))
    vencidos = await sessao.scalar(
        select(func.count()).select_from(Publicacao)
        .outerjoin(Triagem, Triagem.publicacao_id == Publicacao.id)
        .where(Publicacao.vencimento < h, func.coalesce(Triagem.status, "novo") != "concluido"))
    return {"processos": total_proc or 0, "publicacoes": total_pub or 0,
            "sem_triagem": sem_triagem or 0, "prazos_criticos": criticos or 0,
            "vencidos_sem_providencia": vencidos or 0}
