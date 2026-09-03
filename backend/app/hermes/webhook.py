"""Recebe do Telegram: o opt-in por código e os cliques nos botões.

Esta é a única rota do serviço que aceita chamada sem JWT — quem chama é o
Telegram, não um navegador. O que a protege é o cabeçalho
`X-Telegram-Bot-Api-Secret-Token`, comparado em tempo constante. Sem ele,
qualquer um que descubra a URL fala pelo bot.

O opt-in é por código, e o código nasce no painel: a pessoa entra no sistema
com a senha dela, pede o código, e envia ao bot de dentro do Telegram dela.
São dois fatores independentes — ninguém cadastra ninguém.
"""

from __future__ import annotations

import datetime
import secrets
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import agora, settings
from app.core.db import get_session
from app.core.seguranca import (
    PODE_GERIR_USUARIOS,
    registrar,
    requer_papel,
    usuario_atual,
)
from app.hermes.telegram import ClienteTelegram, TelegramErro
from app.models import Publicacao, StatusTriagem, Triagem, Usuario, VinculoTelegram

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/hermes", tags=["hermes"])

VALIDADE_CODIGO = datetime.timedelta(minutes=15)

AJUDA = (
    "👋 Sou o <b>Hermes</b>, o mensageiro do Departamento Jurídico de Pradópolis.\n\n"
    "Aviso sobre prazos críticos — não confirmo intimação e não mostro o inteiro "
    "teor das publicações. Isso se faz no painel, com login.\n\n"
    "Para receber os avisos, peça seu código no painel e me envie:\n"
    "<code>/vincular SEUCODIGO</code>"
)


# ── Rotas do painel (com JWT) ─────────────────────────────────────────────

@router.get("/vinculo", summary="Situação do meu vínculo com o Telegram")
async def meu_vinculo(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    v = await sessao.get(VinculoTelegram, usuario.id)
    if v is None:
        return {"situacao": "sem_vinculo", "hermes_disponivel": settings.hermes_configurado}
    if v.telegram_user_id:
        return {"situacao": "vinculado", "ativo": v.ativo,
                "nome_telegram": v.nome_telegram,
                "desde": v.opt_in_em, "hermes_disponivel": settings.hermes_configurado}
    expirado = v.codigo_expira_em is None or v.codigo_expira_em < agora()
    return {"situacao": "codigo_expirado" if expirado else "aguardando_codigo",
            "codigo": None if expirado else v.codigo,
            "expira_em": v.codigo_expira_em,
            "hermes_disponivel": settings.hermes_configurado}


@router.post("/vinculo/codigo", summary="Gera o código de opt-in")
async def gerar_codigo(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> dict[str, Any]:
    """Código de uso único e vida curta. Gerar de novo invalida o anterior."""
    v = await sessao.get(VinculoTelegram, usuario.id)
    if v is None:
        v = VinculoTelegram(usuario_id=usuario.id)
        sessao.add(v)
    if v.telegram_user_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Já existe um Telegram vinculado. Desvincule antes de trocar.")
    v.codigo = secrets.token_hex(4).upper()
    v.codigo_expira_em = agora() + VALIDADE_CODIGO
    await registrar(sessao, acao="hermes_codigo_gerado", usuario_id=usuario.id,
                    entidade="vinculo_telegram", entidade_id=str(usuario.id), request=request)
    await sessao.commit()
    return {"codigo": v.codigo, "expira_em": v.codigo_expira_em,
            "instrucao": f"Envie ao bot no Telegram: /vincular {v.codigo}"}


@router.delete("/vinculo", summary="Desvincula meu Telegram")
async def desvincular(
    usuario: Annotated[Usuario, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> dict[str, str]:
    """Opt-out é tão simples quanto o opt-in. A linha some inteira."""
    v = await sessao.get(VinculoTelegram, usuario.id)
    if v is not None:
        await sessao.delete(v)
    await registrar(sessao, acao="hermes_desvinculado", usuario_id=usuario.id,
                    entidade="vinculo_telegram", entidade_id=str(usuario.id), request=request)
    await sessao.commit()
    return {"situacao": "sem_vinculo"}


@router.post("/testar", summary="Envia uma mensagem de teste")
async def testar(
    usuario: Annotated[Usuario, Depends(requer_papel(*PODE_GERIR_USUARIOS))],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
    destino: str = "privado",
) -> dict[str, Any]:
    cliente = ClienteTelegram()
    if not cliente.configurado:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "TELEGRAM_BOT_TOKEN não configurado.")
    if destino == "grupo":
        chat = settings.telegram_chat_id_grupo
        if not chat:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "TELEGRAM_CHAT_ID_GRUPO não configurado.")
    else:
        v = await sessao.get(VinculoTelegram, usuario.id)
        if v is None or not v.telegram_chat_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Seu Telegram ainda não está vinculado.")
        chat = v.telegram_chat_id
    try:
        await cliente.enviar(chat, "✅ Teste do <b>Hermes</b>. O canal está funcionando.")
    except TelegramErro as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    await registrar(sessao, acao="hermes_teste", usuario_id=usuario.id,
                    detalhe={"destino": destino}, request=request)
    await sessao.commit()
    return {"enviado": True, "destino": destino}


@router.post("/webhook/registrar", summary="Aponta o webhook do bot para este serviço")
async def registrar_webhook(
    usuario: Annotated[Usuario, Depends(requer_papel(*PODE_GERIR_USUARIOS))],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> dict[str, Any]:
    if not settings.telegram_webhook_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "TELEGRAM_WEBHOOK_SECRET não configurado — o webhook ficaria aberto.")
    url = f"{settings.painel_base_url.rstrip('/')}/hermes/telegram/webhook"
    try:
        await ClienteTelegram().registrar_webhook(url, settings.telegram_webhook_secret)
    except TelegramErro as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    await registrar(sessao, acao="hermes_webhook_registrado", usuario_id=usuario.id,
                    detalhe={"url": url}, request=request)
    await sessao.commit()
    return {"webhook": url}


# ── A rota que o Telegram chama ───────────────────────────────────────────

async def _vincular(sessao: AsyncSession, codigo: str, de: dict[str, Any],
                    chat_id: str) -> str:
    v = await sessao.scalar(select(VinculoTelegram).where(VinculoTelegram.codigo == codigo))
    if v is None:
        return "❌ Código não encontrado. Peça um novo no painel."
    if v.codigo_expira_em is None or v.codigo_expira_em < agora():
        return "⌛ Código expirado. Peça um novo no painel — ele vale 15 minutos."

    v.telegram_user_id = str(de.get("id"))
    v.telegram_chat_id = chat_id
    v.nome_telegram = " ".join(
        p for p in (de.get("first_name"), de.get("last_name")) if p) or de.get("username")
    v.codigo = None
    v.codigo_expira_em = None
    v.ativo = True
    v.opt_in_em = agora()
    await registrar(sessao, acao="hermes_vinculado", usuario_id=v.usuario_id,
                    entidade="vinculo_telegram", entidade_id=str(v.usuario_id))
    try:
        await sessao.commit()
    except IntegrityError:
        await sessao.rollback()
        return "❌ Este Telegram já está vinculado a outro usuário do painel."
    return ("✅ Vinculado. A partir de agora eu aviso você dos prazos críticos "
            "das publicações sob sua responsabilidade.")


async def _marcar_visto(sessao: AsyncSession, publicacao_id: str,
                        telegram_user_id: str) -> tuple[str, bool]:
    """Grava triagem 'andamento' em nome de quem clicou. Devolve (texto, sucesso)."""
    v = await sessao.scalar(
        select(VinculoTelegram).where(VinculoTelegram.telegram_user_id == telegram_user_id,
                                      VinculoTelegram.ativo.is_(True)))
    if v is None:
        # Recusa explícita: um clique anônimo não pode mexer na triagem, e a
        # pessoa precisa saber por quê.
        return ("Seu Telegram não está vinculado ao painel. Peça o código no "
                "sistema e envie /vincular.", False)

    pub = await sessao.get(Publicacao, publicacao_id)
    if pub is None:
        return ("Publicação não encontrada.", False)

    tri = await sessao.get(Triagem, publicacao_id)
    if tri is None:
        tri = Triagem(publicacao_id=publicacao_id, responsavel_id=v.usuario_id)
        sessao.add(tri)
    anterior = tri.status
    if anterior in ("concluido", "sem_providencia"):
        return (f"Esta publicação já está como '{anterior}'. Nada alterado.", True)
    tri.status = StatusTriagem.ANDAMENTO
    tri.atualizado_por_id = v.usuario_id
    await registrar(sessao, acao="triagem", usuario_id=v.usuario_id, entidade="publicacao",
                    entidade_id=publicacao_id,
                    detalhe={"de": anterior, "para": "andamento", "origem": "telegram"})
    await sessao.commit()
    return ("👁 Marcado como em andamento. A equipe já vê isso no painel.", True)


@router.post("/telegram/webhook", include_in_schema=False)
async def receber(
    atualizacao: dict[str, Any],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    """Sempre devolve 200: erro aqui faz o Telegram reenviar em laço."""
    esperado = settings.telegram_webhook_secret
    if not esperado or not secrets.compare_digest(
            x_telegram_bot_api_secret_token or "", esperado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Segredo do webhook inválido.")

    cliente = ClienteTelegram()
    try:
        if callback := atualizacao.get("callback_query"):
            dados = str(callback.get("data") or "")
            de = callback.get("from") or {}
            if dados.startswith("visto:"):
                texto, ok = await _marcar_visto(sessao, dados[6:], str(de.get("id")))
                await cliente.responder_callback(str(callback["id"]), texto, alerta=not ok)
                if ok:
                    msg = callback.get("message") or {}
                    if msg.get("message_id"):
                        await cliente.editar_teclado(
                            str((msg.get("chat") or {}).get("id")), int(msg["message_id"]), None)
            else:
                await cliente.responder_callback(str(callback["id"]), "Ação desconhecida.")
            return {"ok": True}

        mensagem = atualizacao.get("message") or {}
        texto = str(mensagem.get("text") or "").strip()
        chat_id = str((mensagem.get("chat") or {}).get("id") or "")
        if not chat_id:
            return {"ok": True}

        if texto.startswith("/vincular"):
            partes = texto.split(maxsplit=1)
            if len(partes) < 2:
                resposta = "Use: <code>/vincular SEUCODIGO</code>"
            else:
                resposta = await _vincular(sessao, partes[1].strip().upper(),
                                           mensagem.get("from") or {}, chat_id)
        else:
            resposta = AJUDA
        await cliente.enviar(chat_id, resposta)
    except TelegramErro as exc:
        logger.warning("hermes_webhook_resposta_falhou", erro=str(exc)[:200])
    except Exception as exc:
        logger.error("hermes_webhook_erro", erro=type(exc).__name__, detalhe=str(exc)[:300])
    return {"ok": True}
