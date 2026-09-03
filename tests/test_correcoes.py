"""Testes das correcoes das etapas 1, 2 e 3 e do modulo Comunica."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from mcp_juridico_brasil._core.errors import JuridicoValidationError
from mcp_juridico_brasil.comunica.client import filtrar_por_destinatario, normalizar
from mcp_juridico_brasil.monitoramento import store
from mcp_juridico_brasil.prazo.calendario import calcular_prazo
from mcp_juridico_brasil.prazo.tools import calcular_proximo_prazo
from mcp_juridico_brasil.processo.tools import buscar_processo_por_numero
from mcp_juridico_brasil.shared.schemas import Movimentacao, Processo

NUM = "0001234-56.2023.8.26.0100"
NUM_NORM = "00012345620238260100"


def _processo() -> Processo:
    return Processo(
        numero_processo=NUM_NORM,
        tribunal="TJSP",
        data_ultima_atualizacao=datetime.datetime(2026, 8, 20, tzinfo=datetime.timezone.utc),
        movimentacoes=[
            Movimentacao(
                codigo=92,
                nome="Publicacao",
                data_hora=datetime.datetime(2026, 8, 20, tzinfo=datetime.timezone.utc),
            )
        ],
    )


@pytest.fixture(autouse=True)
def _store_limpo():
    store.limpar_snapshots() if hasattr(store, "limpar_snapshots") else None
    store._snapshots.clear()
    yield
    store._snapshots.clear()


# ---------------------------------------------------------------------------
# Etapa 1 - art. 183 do CPC (prazo em dobro da Fazenda Publica)
# ---------------------------------------------------------------------------


async def test_particular_mantem_prazo_simples():
    r = await calcular_proximo_prazo(
        NUM, "TJSP", tipo_ato="Contestacao", uf="SP", data_intimacao_iso="2026-08-20"
    )
    assert r["dias_uteis_prazo"] == 15
    assert r["prazo_em_dobro_aplicado"] is False


async def test_fazenda_publica_recebe_prazo_em_dobro():
    r = await calcular_proximo_prazo(
        NUM,
        "TJSP",
        tipo_ato="Contestacao",
        uf="SP",
        data_intimacao_iso="2026-08-20",
        parte_fazenda_publica=True,
    )
    assert r["dias_uteis_prazo"] == 30
    assert r["dias_uteis_prazo_simples"] == 15
    assert r["prazo_em_dobro_aplicado"] is True
    assert "183" in str(r["base_legal"])


async def test_juizado_especial_fazenda_afasta_o_dobro():
    """Art. 7º da Lei 12.153/2009: sem prazo diferenciado no JEFP."""
    r = await calcular_proximo_prazo(
        NUM,
        "TJSP",
        tipo_ato="Contestacao",
        uf="SP",
        data_intimacao_iso="2026-08-20",
        parte_fazenda_publica=True,
        rito="juizado_especial_fazenda",
    )
    assert r["dias_uteis_prazo"] == 15
    assert r["prazo_em_dobro_aplicado"] is False
    assert "12.153" in str(r["fundamento_prazo"])


async def test_prazo_proprio_em_lei_nao_dobra():
    """Art. 183, §2º: prazo proprio afasta o dobro."""
    r = await calcular_proximo_prazo(
        NUM,
        "TJSP",
        tipo_ato="Embargos a Execucao Fiscal",
        uf="SP",
        data_intimacao_iso="2026-08-20",
        parte_fazenda_publica=True,
    )
    assert r["dias_uteis_prazo"] == 30
    assert r["prazo_em_dobro_aplicado"] is False


async def test_rito_invalido_e_rejeitado():
    with pytest.raises(JuridicoValidationError):
        await calcular_proximo_prazo(NUM, "TJSP", rito="inexistente")


async def test_feriado_municipal_adia_o_vencimento():
    sem = await calcular_proximo_prazo(
        NUM, "TJSP", tipo_ato="Embargos de Declaracao", uf="SP",
        data_intimacao_iso="2026-08-20",
    )
    com = await calcular_proximo_prazo(
        NUM, "TJSP", tipo_ato="Embargos de Declaracao", uf="SP",
        data_intimacao_iso="2026-08-20",
        feriados_municipais={"2026-08-25": "Aniversario de Pradopolis"},
    )
    assert com["data_final_iso"] > sem["data_final_iso"]


async def test_feriado_municipal_com_data_invalida_e_rejeitado():
    with pytest.raises(JuridicoValidationError):
        await calcular_proximo_prazo(
            NUM, "TJSP", data_intimacao_iso="2026-08-20",
            feriados_municipais={"25/08/2026": "formato errado"},
        )


def test_nomes_de_feriado_em_portugues():
    r = calcular_prazo(datetime.date(2026, 9, 4), 5, "SP")
    nomes = [n for _, n in r.feriados_no_periodo]
    assert any("Independencia" in n for n in nomes)


# ---------------------------------------------------------------------------
# Etapa 2 - snapshot gravado pelas tools
# ---------------------------------------------------------------------------


async def test_buscar_processo_grava_snapshot():
    with patch(
        "mcp_juridico_brasil.datajud.provider.DataJudProvider.buscar_processo",
        new=AsyncMock(return_value=_processo()),
    ):
        await buscar_processo_por_numero(NUM, "TJSP")

    assert NUM_NORM in store.listar_processos_monitorados()
    snap = store.obter_snapshot(NUM_NORM)
    assert snap is not None
    assert snap["dados"]["numero_processo"] == NUM_NORM


async def test_monitorar_processo_grava_snapshot_e_detecta_novas():
    from mcp_juridico_brasil.monitoramento.tools import monitorar_processo

    with patch(
        "mcp_juridico_brasil.datajud.provider.DataJudProvider.buscar_processo",
        new=AsyncMock(return_value=_processo()),
    ):
        r = await monitorar_processo(NUM, "TJSP", "2026-01-01T00:00:00")

    assert r["houve_atualizacao"] is True
    assert r["total_movimentacoes_novas"] == 1
    assert NUM_NORM in store.listar_processos_monitorados()


# ---------------------------------------------------------------------------
# Etapa 3 - selecao de provider
# ---------------------------------------------------------------------------


def test_get_provider_usa_datajud_por_padrao(monkeypatch):
    from mcp_juridico_brasil.datajud.provider import DataJudProvider
    from mcp_juridico_brasil.shared.provider import get_provider, reset_provider

    monkeypatch.delenv("JURIDICO_PROVIDER", raising=False)
    monkeypatch.delenv("JURIDICO_PROVIDER_COMERCIAL", raising=False)
    reset_provider()
    assert isinstance(get_provider(), DataJudProvider)


def test_alias_provider_comercial_e_aceito(monkeypatch):
    """O .env.example documenta JURIDICO_PROVIDER_COMERCIAL; o registry lia so
    JURIDICO_PROVIDER. Os dois nomes passam a valer."""
    from mcp_juridico_brasil.comercial.registry import FallbackProvider, selecionar_provider

    monkeypatch.delenv("JURIDICO_PROVIDER", raising=False)
    monkeypatch.setenv("JURIDICO_PROVIDER_COMERCIAL", "judit")
    monkeypatch.setenv("JURIDICO_PROVIDER_API_KEY", "chave-de-teste")
    assert isinstance(selecionar_provider(), FallbackProvider)


def test_get_provider_e_singleton(monkeypatch):
    from mcp_juridico_brasil.shared.provider import get_provider, reset_provider

    monkeypatch.delenv("JURIDICO_PROVIDER", raising=False)
    reset_provider()
    assert get_provider() is get_provider()


# ---------------------------------------------------------------------------
# Comunica / DJEN
# ---------------------------------------------------------------------------


def test_normalizar_remove_acentos_e_caixa():
    assert normalizar("Município de Pradópolis") == "MUNICIPIO DE PRADOPOLIS"


def test_filtro_descarta_homonimo():
    itens = [
        {"destinatarios": [{"nome": "MUNICIPIO DE PRADOPOLIS"}]},
        {"destinatarios": [{"nome": "PREFEITURA MUNICIPAL DE PRADÓPOLIS"}]},
        {"destinatarios": [{"nome": "RESIDENCIAL PRADOPOLIS SPE LTDA"}]},
        {"destinatarios": [{"nome": "MUNICIPIO DE GUARIBA"}]},
    ]
    r = filtrar_por_destinatario(itens, ["PRADOPOLIS"], ["MUNICIPIO", "PREFEITURA"])
    assert len(r) == 2


async def test_busca_sem_filtro_e_recusada():
    from mcp_juridico_brasil._core.errors import JuridicoAPIError
    from mcp_juridico_brasil.comunica.client import ComunicaClient

    with pytest.raises(JuridicoAPIError):
        await ComunicaClient().buscar()


# ---------------------------------------------------------------------------
# Helpers de parsing do DJEN promovidos ao cliente
# ---------------------------------------------------------------------------


def test_limpar_html_converte_br_em_quebra():
    from mcp_juridico_brasil.comunica.client import limpar_html

    assert limpar_html("Fica<br>intimado") == "Fica\nintimado"
    assert limpar_html("<b>Reu</b> intimado") == "Reu intimado"
    assert limpar_html(None) == ""


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("no prazo de 15 (quinze) dias", 15),
        ("prazo legal de 5 dias", 5),
        ("em 10 dias uteis para manifestar", 10),
        ("nenhum prazo aqui", None),
        (None, None),
    ],
)
def test_prazo_mencionado(texto, esperado):
    from mcp_juridico_brasil.comunica.client import prazo_mencionado

    assert prazo_mencionado(texto) == esperado


def test_identificar_polo():
    from mcp_juridico_brasil.comunica.client import identificar_polo

    assert identificar_polo("A") == "ativo"
    assert identificar_polo("p") == "passivo"
    assert identificar_polo(None) == "nao_informado"
    assert identificar_polo("X") == "nao_informado"


# ---------------------------------------------------------------------------
# Decreto-Lei 779/69 — prazo do ente público na Justiça do Trabalho
# ---------------------------------------------------------------------------


async def test_trabalhista_contestacao_e_quadruplo():
    """Art. 1º, II, do DL 779/69. Era o erro de maior impacto do acervo."""
    r = await calcular_proximo_prazo(
        NUM, "TRT15", tipo_ato="Contestacao", uf="SP", data_intimacao_iso="2026-09-02",
        parte_fazenda_publica=True, rito="trabalhista",
    )
    assert r["multiplicador"] == 4
    assert r["dias_uteis_prazo"] == 60
    assert "779/69" in str(r["fundamento_prazo"])
    assert "QUADRUPLO" in str(r["fundamento_prazo"])


async def test_trabalhista_recurso_e_dobro():
    """Art. 1º, III, do DL 779/69."""
    r = await calcular_proximo_prazo(
        NUM, "TRT15", tipo_ato="Recurso de Apelacao", uf="SP",
        data_intimacao_iso="2026-09-02", parte_fazenda_publica=True, rito="trabalhista",
    )
    assert r["multiplicador"] == 2
    assert "779/69" in str(r["fundamento_prazo"])


async def test_trabalhista_nao_invoca_o_art_183_como_razao():
    r = await calcular_proximo_prazo(
        NUM, "TRT15", tipo_ato="Contestacao", uf="SP", data_intimacao_iso="2026-09-02",
        parte_fazenda_publica=True, rito="trabalhista",
    )
    assert "nao se aplica a este rito" in str(r["fundamento_prazo"])
    assert "779/69" in str(r["base_legal"])


async def test_rito_comum_segue_no_art_183():
    """Regressão: a mudança do trabalhista não pode alterar o rito comum."""
    r = await calcular_proximo_prazo(
        NUM, "TJSP", tipo_ato="Contestacao", uf="SP", data_intimacao_iso="2026-09-02",
        parte_fazenda_publica=True, rito="comum",
    )
    assert r["multiplicador"] == 2
    assert r["dias_uteis_prazo"] == 30
    assert "183" in str(r["base_legal"])
