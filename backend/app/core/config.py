"""Configuração do serviço, lida exclusivamente de variáveis de ambiente.

REGRA BLOQUEANTE: nenhum segredo tem valor padrão utilizável, e nenhum aparece
em `repr()` — que é o que vaza num traceback.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Fuso do foro. NUNCA usar date.today(): servidor em UTC faz "hoje" virar o dia
# seguinte a partir das 21h de Brasília, e toda a agenda de prazos desloca.
FUSO_FORO = ZoneInfo("America/Sao_Paulo")


def hoje() -> datetime.date:
    return datetime.datetime.now(tz=FUSO_FORO).date()


def agora() -> datetime.datetime:
    return datetime.datetime.now(tz=FUSO_FORO)


def _hora(texto: str) -> datetime.time:
    """"HH:MM" -> time. Configuracao malformada nao pode derrubar o agendador."""
    hora, _, minuto = texto.partition(":")
    try:
        return datetime.time(int(hora), int(minuto or 0))
    except ValueError:
        return datetime.time(0, 0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(default="", repr=False)
    jwt_secret: str = Field(default="", repr=False)
    jwt_algoritmo: str = "HS256"
    access_token_minutos: int = 15
    refresh_token_dias: int = 7

    juridico_nome_parte: str = "PRADOPOLIS"
    juridico_termos_confirmacao: str = "MUNICIPIO,PREFEITURA"
    juridico_uf: str = "SP"

    varredura_hora: str = "06:00"
    varredura_janela_dias: int = 30
    varredura_ativa: bool = True

    frontend_origin: str = "http://localhost:5173"

    # --- Hermes: notificacao via Telegram (Task 3) --------------------------
    # O token do bot da acesso total a ele: e segredo, fica fora de repr e de log.
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_chat_id_grupo: str = ""
    telegram_hora_resumo: str = "08:00"
    telegram_silencio_inicio: str = "20:00"
    telegram_silencio_fim: str = "07:00"
    # Segredo do cabecalho X-Telegram-Bot-Api-Secret-Token: sem ele, qualquer um
    # que descubra a URL do webhook fala pelo bot.
    telegram_webhook_secret: str = Field(default="", repr=False)
    telegram_api_base: str = "https://api.telegram.org"
    painel_base_url: str = "http://127.0.0.1:8100"
    hermes_ativo: bool = True
    hermes_dias_criticos: int = 3
    hermes_intervalo_alertas_min: int = 30

    # --- Acionamento externo por cron (plano gratuito do host) --------------
    # O Render (e hosts free equivalentes) hiberna o serviço sem uso. Em vez de
    # manter uma instância paga só para o agendador interno, um workflow do
    # GitHub Actions acorda o serviço com uma chamada HTTP em POST /cron/*, e
    # essa própria chamada É o disparo da tarefa. Sem segredo configurado, as
    # rotas de cron ficam fechadas (403 sempre) — não abertas.
    cron_secret: str = Field(default="", repr=False)

    @property
    def termos_confirmacao(self) -> list[str]:
        return [t.strip() for t in self.juridico_termos_confirmacao.split(",") if t.strip()]

    @property
    def hermes_configurado(self) -> bool:
        """Sem token nao ha bot. O servico sobe do mesmo jeito, so nao notifica."""
        return bool(self.telegram_bot_token)

    def janela_de_silencio(self, momento: datetime.time) -> bool:
        """Entre 20h e 07h o bot cala. A janela cruza a meia-noite, entao o teste
        e uma UNIAO (>= inicio OU < fim), nao uma interseccao."""
        inicio = _hora(self.telegram_silencio_inicio)
        fim = _hora(self.telegram_silencio_fim)
        if inicio == fim:
            return False
        if inicio < fim:  # janela dentro do mesmo dia
            return inicio <= momento < fim
        return momento >= inicio or momento < fim


settings = Settings()
