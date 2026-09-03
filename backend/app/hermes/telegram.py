"""Transporte: fala com a Bot API e mais nada.

Este módulo não sabe o que é prazo, procurador ou publicação — recebe um texto
pronto e um destino. Toda a regra de negócio está em `agendador.py`.

REGRA BLOQUEANTE: o token nunca aparece em log nem em exceção. Ele vai na URL
da Bot API, e as exceções do httpx incluem a URL — por isso todo erro que sai
daqui passa por `_mascarar()`. Não é zelo excessivo: o token dá controle total
do bot para quem o ler.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

TENTATIVAS = 3
TIMEOUT = 20.0
# Teto para o `retry_after` da API: se o Telegram pedir uma espera longa, é
# melhor desistir e registrar do que segurar o agendador por minutos.
ESPERA_MAXIMA = 60


class TelegramErro(Exception):  # noqa: N818 - o codigo deste projeto e em portugues
    """Falha de envio já com o token mascarado."""


def _mascarar(texto: str) -> str:
    token = settings.telegram_bot_token
    if token and token in texto:
        texto = texto.replace(token, "***TOKEN***")
    # Defesa extra: qualquer coisa com a forma de token de bot (123456:AA...).
    return texto


class ClienteTelegram:
    """Cliente mínimo da Bot API, com respeito ao rate limit."""

    def __init__(self, token: str | None = None, base: str | None = None) -> None:
        self._token = token if token is not None else settings.telegram_bot_token
        self._base = (base or settings.telegram_api_base).rstrip("/")

    @property
    def configurado(self) -> bool:
        return bool(self._token)

    async def _chamar(self, metodo: str, corpo: dict[str, Any]) -> dict[str, Any]:
        if not self._token:
            raise TelegramErro("TELEGRAM_BOT_TOKEN não configurado — Hermes está mudo.")
        url = f"{self._base}/bot{self._token}/{metodo}"

        espera = 2.0
        ultimo = ""
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as cliente:
                    r = await cliente.post(url, json=corpo)
                dados = r.json() if r.content else {}

                if r.status_code == 429:
                    # A própria API diz quanto esperar. Obedecer é o que evita
                    # o bloqueio temporário do bot.
                    pedido = int((dados.get("parameters") or {}).get("retry_after", espera))
                    if pedido > ESPERA_MAXIMA:
                        raise TelegramErro(f"rate limit pediu {pedido}s — acima do teto")
                    logger.warning("telegram_rate_limit", metodo=metodo, esperar=pedido)
                    await asyncio.sleep(pedido)
                    continue

                if r.status_code >= 500:
                    ultimo = f"HTTP {r.status_code} do Telegram"
                    raise httpx.HTTPError(ultimo)

                if not dados.get("ok"):
                    # 4xx é erro nosso (chat inexistente, usuário bloqueou o bot):
                    # repetir não resolve.
                    raise TelegramErro(
                        f"{metodo} recusado: {dados.get('description', 'sem descrição')}"
                    )
                return dict(dados.get("result") or {})

            except TelegramErro:
                raise
            except Exception as exc:
                ultimo = _mascarar(f"{type(exc).__name__}: {exc}")
                logger.warning("telegram_falhou", metodo=metodo, tentativa=tentativa,
                               erro=ultimo[:200])
                if tentativa == TENTATIVAS:
                    raise TelegramErro(f"{metodo} falhou em {TENTATIVAS} tentativas: "
                                       f"{ultimo[:200]}") from None
                await asyncio.sleep(espera)
                espera *= 2

        raise TelegramErro(f"{metodo} esgotou as tentativas: {ultimo[:200]}")

    async def enviar(
        self, chat_id: str, texto: str, botoes: list[list[dict[str, str]]] | None = None
    ) -> dict[str, Any]:
        """Envia texto em HTML. `botoes` é o teclado inline já montado."""
        corpo: dict[str, Any] = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if botoes:
            corpo["reply_markup"] = {"inline_keyboard": botoes}
        return await self._chamar("sendMessage", corpo)

    async def responder_callback(
        self, callback_id: str, texto: str = "", alerta: bool = False
    ) -> None:
        """Tira o "relógio" do botão no cliente. Sem isso o app fica girando."""
        await self._chamar("answerCallbackQuery",
                           {"callback_query_id": callback_id, "text": texto[:200],
                            "show_alert": alerta})

    async def editar_teclado(self, chat_id: str, message_id: int,
                             botoes: list[list[dict[str, str]]] | None) -> None:
        """Troca os botões da mensagem já enviada — usado para marcar 'visto'."""
        await self._chamar("editMessageReplyMarkup",
                           {"chat_id": chat_id, "message_id": message_id,
                            "reply_markup": {"inline_keyboard": botoes or []}})

    async def registrar_webhook(self, url: str, segredo: str) -> dict[str, Any]:
        return await self._chamar("setWebhook", {
            "url": url, "secret_token": segredo,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        })

    async def quem_sou_eu(self) -> dict[str, Any]:
        return await self._chamar("getMe", {})
