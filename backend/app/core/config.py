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

    @property
    def termos_confirmacao(self) -> list[str]:
        return [t.strip() for t in self.juridico_termos_confirmacao.split(",") if t.strip()]


settings = Settings()
