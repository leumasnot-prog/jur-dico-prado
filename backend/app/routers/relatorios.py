"""Exportação da pauta semanal."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import hoje
from app.core.db import get_session
from app.core.seguranca import registrar, usuario_atual
from app.models import Usuario
from app.services import relatorios as servico

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


@router.get("/pauta-semanal", summary="Pauta da semana em PDF ou Excel")
async def pauta(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
    formato: Literal["pdf", "xlsx"] = "pdf",
    dias: int = Query(default=7, ge=1, le=60),
) -> Response:
    dados = await servico.coletar(sessao, dias=dias)
    total = sum(len(v) for v in dados.values())
    await registrar(sessao, acao="relatorio_pauta", usuario_id=usuario.id,
                    detalhe={"formato": formato, "dias": dias, "prazos": total},
                    request=request)
    await sessao.commit()

    nome = f"pauta-{hoje().isoformat()}.{formato}"
    if formato == "xlsx":
        return Response(
            servico.para_excel(dados),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    return Response(servico.para_pdf(dados, dias), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})
