"""Garante que o .env.example e o Settings não saiam de sincronia.

Regressão de um bug real: três variáveis documentadas no .env.example
(DJE_CERT_PATH, DJE_CERT_SENHA, DJE_PERMITIR_CONFIRMACAO_LEITURA) não existiam
em Settings, e como o pydantic-settings proíbe extras por padrão, seguir o
passo documentado `cp .env.example .env` derrubava a aplicação no import.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_juridico_brasil._core.config import Settings

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = RAIZ / ".env.example"


def _variaveis_do_exemplo() -> list[str]:
    texto = EXEMPLO.read_text(encoding="utf-8")
    return [m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", texto, re.M)]


def test_env_example_existe():
    assert EXEMPLO.is_file()


def test_env_example_carrega_sem_quebrar(tmp_path, monkeypatch):
    """O passo documentado `cp .env.example .env` não pode derrubar a aplicação."""
    destino = tmp_path / ".env"
    destino.write_text(EXEMPLO.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    Settings(_env_file=str(destino))  # não deve levantar


@pytest.mark.parametrize("variavel", _variaveis_do_exemplo())
def test_cada_variavel_documentada_e_aceita(variavel, tmp_path):
    """Uma a uma, para o relatório apontar exatamente qual variável quebrou.

    O valor "1" é aceito como str, int e float — assim o teste checa apenas se a
    variável EXISTE no Settings, sem esbarrar no tipo de cada campo.
    """
    destino = tmp_path / ".env"
    destino.write_text(f"{variavel}=1\n", encoding="utf-8")
    Settings(_env_file=str(destino))


def test_segredos_nao_aparecem_em_repr():
    """repr(settings) é o que vaza num traceback — não pode conter segredo."""
    s = Settings(
        dje_client_secret="SECRET-QUE-NAO-PODE-VAZAR",
        dje_cert_senha="SENHA-QUE-NAO-PODE-VAZAR",
        juridico_provider_api_key="",
    )
    texto = repr(s)
    assert "SECRET-QUE-NAO-PODE-VAZAR" not in texto
    assert "SENHA-QUE-NAO-PODE-VAZAR" not in texto


def test_variavel_desconhecida_no_env_nao_derruba(tmp_path):
    """extra='ignore': documentação desatualizada não pode virar falha total."""
    destino = tmp_path / ".env"
    destino.write_text("VARIAVEL_QUE_NAO_EXISTE_NO_CODIGO=x\n", encoding="utf-8")
    Settings(_env_file=str(destino))
