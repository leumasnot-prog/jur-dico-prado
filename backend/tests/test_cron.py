"""Acionamento externo (GitHub Actions) das rotas /cron/*.

Protegido por segredo estático, não por login — quem chama é um workflow, não
uma pessoa. O caso que mais importa aqui é o segredo vazio: sem
`CRON_SECRET` configurado, as rotas precisam ficar fechadas para sempre, não
abertas por omissão.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from app.models import Auditoria, Publicacao

SEGREDO = "segredo-do-github-actions"
CABECALHO = {"X-Cron-Secret": SEGREDO}


@pytest.fixture
def cron_config(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "cron_secret", SEGREDO, raising=False)
    return settings


async def test_sem_cabecalho_e_recusado(cliente, cron_config):
    r = await cliente.post("/cron/varredura")
    assert r.status_code == 403
    r = await cliente.post("/cron/hermes")
    assert r.status_code == 403


async def test_segredo_errado_e_recusado(cliente, cron_config):
    r = await cliente.post("/cron/hermes", headers={"X-Cron-Secret": "chute"})
    assert r.status_code == 403


async def test_cron_secret_vazio_fecha_a_rota_mesmo_com_algum_cabecalho(cliente, monkeypatch):
    """Sem configurar nada, a rota tem de recusar — nunca abrir por omissão."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "cron_secret", "", raising=False)
    r = await cliente.post("/cron/hermes", headers={"X-Cron-Secret": ""})
    assert r.status_code == 403


async def test_varredura_via_cron_persiste_e_audita(cliente, sessao, usuarios, cron_config,
                                                     djen_falso):
    djen_falso([{
        "id": "cron-1", "numero_processo": "00000000000000000001",
        "numeroprocessocommascara": "0000000-00.0000.0.00.0001",
        "data_disponibilizacao": datetime.date.today().isoformat(), "siglaTribunal": "TJSP",
        "nomeOrgao": "1ª Vara", "nomeClasse": "PROCEDIMENTO COMUM",
        "tipoComunicacao": "Intimação", "tipoDocumento": "Notificação", "meiocompleto": "DJEN",
        "link": "https://exemplo/x", "texto": "Fica intimado no prazo de 15 dias.",
        "destinatarios": [{"nome": "MUNICIPIO DE PRADOPOLIS", "polo": "P"}],
        "destinatarioadvogados": [],
    }])
    r = await cliente.post("/cron/varredura", headers=CABECALHO)
    assert r.status_code == 200
    assert r.json()["publicacoes_novas"] == 1
    assert await sessao.get(Publicacao, "cron-1") is not None

    aud = (await sessao.execute(
        select(Auditoria).where(Auditoria.acao == "varredura_cron"))).scalars().all()
    assert len(aud) == 1


async def test_hermes_via_cron_dispara_resumo_e_alertas(cliente, sessao, usuarios, cron_config,
                                                         monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TOKEN-DE-TESTE", raising=False)
    monkeypatch.setattr(settings, "telegram_chat_id_grupo", "-100999", raising=False)

    class TelegramFalso:
        configurado = True

        async def enviar(self, chat_id, texto, botoes=None):
            return {"message_id": 1}

    monkeypatch.setattr("app.hermes.agendador.ClienteTelegram", TelegramFalso)

    r = await cliente.post("/cron/hermes", headers=CABECALHO)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resumo_diario_enviado"] is True
    assert corpo["alertas_enviados"] == 0  # acervo vazio no teste

    # Segunda chamada no mesmo "dia" não repete o resumo — a garantia de
    # não-duplicar já é do banco (índice parcial), isto só confirma o efeito.
    r2 = await cliente.post("/cron/hermes", headers=CABECALHO)
    assert r2.json()["resumo_diario_enviado"] is False


async def test_chamar_hermes_sem_ninguem_configurado_nao_quebra(cliente, sessao, usuarios,
                                                                cron_config):
    """Sem TELEGRAM_BOT_TOKEN nem grupo, a rota responde 200 e não tenta enviar nada."""
    r = await cliente.post("/cron/hermes", headers=CABECALHO)
    assert r.status_code == 200
    assert r.json() == {"resumo_diario_enviado": False, "alertas_enviados": 0}


async def test_falha_na_varredura_explica_a_causa(cliente, cron_config, monkeypatch):
    """Um 500 pelado num endpoint de cron e inutil: quem le e o log de uma
    GitHub Action, sem acesso ao dashboard do host. Aconteceu em producao — o
    primeiro disparo devolveu 500 e nao houve como saber por que."""
    async def _explode(*a, **kw):
        raise ConnectionError("nao foi possivel alcancar o DJEN")

    monkeypatch.setattr("app.services.acervo.varrer_e_persistir", _explode)
    r = await cliente.post("/cron/varredura", headers=CABECALHO)
    assert r.status_code == 502
    assert "ConnectionError" in r.json()["detail"]
    assert "DJEN" in r.json()["detail"]


async def test_falha_fica_na_trilha_de_auditoria(cliente, sessao, cron_config, monkeypatch):
    async def _explode(*a, **kw):
        raise ConnectionError("rede fora")

    monkeypatch.setattr("app.services.acervo.varrer_e_persistir", _explode)
    await cliente.post("/cron/varredura", headers=CABECALHO)

    aud = (await sessao.execute(
        select(Auditoria).where(Auditoria.acao == "varredura_cron_falhou"))).scalars().all()
    assert len(aud) == 1
    assert "ConnectionError" in aud[0].detalhe["erro"]


async def test_diagnostico_diz_o_que_alcanca(cliente, cron_config, monkeypatch):
    import httpx

    # Derruba SO a chamada externa. O proprio `cliente` de teste e um
    # httpx.AsyncClient: substituir o metodo inteiro quebraria a requisicao do
    # teste antes de ela chegar ao servico.
    original = httpx.AsyncClient.get

    async def _so_a_externa(self, url, **kw):
        if str(url).startswith("https://"):
            raise OSError("host inalcancavel")
        return await original(self, url, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "get", _so_a_externa)

    r = await cliente.get("/cron/diagnostico", headers=CABECALHO)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["banco"] == "ok"          # o banco de teste responde
    assert "OSError" in corpo["djen"]      # o DJEN, nao
    assert "OSError" in corpo["djen_com_user_agent"]
    assert corpo["telegram"] == "sem token configurado"


async def test_diagnostico_exige_segredo(cliente, cron_config):
    assert (await cliente.get("/cron/diagnostico")).status_code == 403
