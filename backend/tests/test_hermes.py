"""Hermes: privacidade, calendário, não-repetição e opt-in.

O teste que mais importa aqui é `test_nome_de_pessoa_natural_nunca_sai`: ele
injeta um nome de pessoa num campo que vai para a mensagem e falha se o nome
aparecer na saída. Os outros protegem o bot de virar ruído.
"""

from __future__ import annotations

import datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import (
    Auditoria,
    EnvioHermes,
    Processo,
    Publicacao,
    StatusTriagem,
    Triagem,
    VinculoTelegram,
)

QUINTA = datetime.date(2026, 9, 3)      # dia útil
SABADO = datetime.date(2026, 9, 5)
INDEPENDENCIA = datetime.date(2026, 9, 7)  # feriado nacional, uma segunda-feira


class TelegramFalso:
    """Registra o que teria sido enviado. Nenhuma rede é tocada."""

    def __init__(self, falhar: bool = False) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.callbacks: list[tuple[str, str, bool]] = []
        self.teclados: list[tuple[str, int]] = []
        self.falhar = falhar

    configurado = True

    async def enviar(self, chat_id, texto, botoes=None):
        if self.falhar:
            from app.hermes.telegram import TelegramErro

            raise TelegramErro("chat not found")
        self.enviados.append((str(chat_id), texto))
        return {"message_id": 1}

    async def responder_callback(self, callback_id, texto="", alerta=False):
        self.callbacks.append((callback_id, texto, alerta))

    async def editar_teclado(self, chat_id, message_id, botoes):
        self.teclados.append((str(chat_id), message_id))


@pytest.fixture
def hermes_config(monkeypatch):
    """Configuração mínima do Hermes, sem tocar no .env real."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TOKEN-DE-TESTE", raising=False)
    monkeypatch.setattr(settings, "telegram_chat_id_grupo", "-100999", raising=False)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "segredo-de-webhook", raising=False)
    monkeypatch.setattr(settings, "painel_base_url", "https://painel.teste", raising=False)
    monkeypatch.setattr(settings, "hermes_dias_criticos", 3, raising=False)
    return settings


@pytest.fixture
def hoje_fixo(monkeypatch):
    """Congela "hoje" no agendador do Hermes: prazo depende de data."""
    def _fixar(data: datetime.date):
        monkeypatch.setattr("app.hermes.agendador.hoje", lambda: data)
    return _fixar


@pytest_asyncio.fixture
async def acervo(sessao, usuarios):
    """Um processo trabalhista com prazo curto, com nome de pessoa nas partes."""
    sessao.add(Processo(
        numero_processo="00108216020255150029", numero_formatado="0010821-60.2025.5.15.0029",
        tribunal="TRT15", orgao="1ª Vara do Trabalho", classe="AÇÃO TRABALHISTA",
        polo_do_ente="passivo", partes_contrarias=["JOAO CARLOS DA SILVA"],
    ))
    await sessao.flush()
    sessao.add(Publicacao(
        id="pub-1", numero_processo="00108216020255150029",
        data_disponibilizacao=QUINTA - datetime.timedelta(days=30), tribunal="TRT15",
        classe="AÇÃO TRABALHISTA", tipo_documento="Notificação", meio="DJEN",
        partes=[{"nome": "JOAO CARLOS DA SILVA", "polo": "ativo", "e_o_ente": False},
                {"nome": "MUNICIPIO DE PRADOPOLIS", "polo": "passivo", "e_o_ente": True}],
        advogados=[], texto="Fica intimado o Município para contestar.",
        ato_inferido="Contestacao", rito_inferido="trabalhista",
        vencimento=QUINTA + datetime.timedelta(days=1),
    ))
    await sessao.commit()
    return usuarios


async def _vincular(sessao, usuario, chat="555", tg_id="777"):
    sessao.add(VinculoTelegram(usuario_id=usuario.id, telegram_user_id=tg_id,
                               telegram_chat_id=chat, nome_telegram="Teste", ativo=True,
                               opt_in_em=datetime.datetime.now(tz=datetime.UTC)))
    await sessao.commit()


# ── Ciclo 2: privacidade ──────────────────────────────────────────────────

def test_pessoa_juridica_nao_e_confundida_com_pessoa_natural():
    from app.hermes.formatador import e_pessoa_natural

    assert e_pessoa_natural("JOAO CARLOS DA SILVA")
    assert e_pessoa_natural("Maria Aparecida Souza")
    assert not e_pessoa_natural("MUNICIPIO DE PRADOPOLIS")
    assert not e_pessoa_natural("USINA SANTA ELISA LTDA")
    assert not e_pessoa_natural("BANCO DO BRASIL S/A")
    assert not e_pessoa_natural("SINDICATO DOS TRABALHADORES RURAIS")


def test_nome_de_pessoa_natural_nunca_sai_na_mensagem_de_grupo():
    """O teste central da task. Um nome plantado num campo que VAI para a
    mensagem precisa ser suprimido antes de sair do formatador."""
    from app.hermes.formatador import ItemPrazo, montar_resumo_diario

    envenenado = ItemPrazo(
        publicacao_id="1", numero="0010821-60.2025.5.15.0029", tribunal="TRT15",
        ato="Contestacao de JOAO CARLOS DA SILVA",   # vazamento plantado
        rito="trabalhista", vencimento=QUINTA + datetime.timedelta(days=2),
        dias_restantes=2, partes=("JOAO CARLOS DA SILVA", "MUNICIPIO DE PRADOPOLIS"),
    )
    texto = montar_resumo_diario(
        data=QUINTA, criticos=[envenenado], novas_por_tribunal={"TRT15": 3},
        sem_triagem=3, total_processos=229, base_url="https://painel.teste").upper()

    assert "JOAO" not in texto
    assert "CARLOS" not in texto
    assert "SILVA" not in texto
    assert "[NOME SUPRIMIDO]" in texto
    # O que identifica o caso continua lá: número, tribunal e vencimento.
    assert "0010821-60.2025.5.15.0029" in texto


def test_alerta_privado_tambem_nao_leva_nome_nem_inteiro_teor():
    from app.hermes.formatador import ItemPrazo, montar_alerta_critico

    item = ItemPrazo("1", "0010012-64.2020.5.15.0120", "TRT15",
                     "Contestacao", "trabalhista", QUINTA + datetime.timedelta(days=2), 2,
                     fundamento="Prazo em QUÁDRUPLO (DL 779/69, art. 1º, II).",
                     partes=("PEDRO HENRIQUE ALVES",))
    texto = montar_alerta_critico(item=item, nome_procurador="Dr(a). Ana",
                                  base_url="https://painel.teste").upper()
    assert "PEDRO" not in texto and "HENRIQUE" not in texto and "ALVES" not in texto
    assert "779/69" in texto  # o fundamento continua, que é o que ensina a regra


def test_pessoa_juridica_pode_aparecer():
    """Redigir demais também é defeito: o filtro não pode comer o nome do ente."""
    from app.hermes.formatador import redigir

    texto = "Município de Pradópolis intimado"
    assert redigir(texto, ["MUNICIPIO DE PRADOPOLIS"]) == texto


# ── Ciclo 1: transporte ───────────────────────────────────────────────────

async def test_token_nunca_aparece_no_erro(monkeypatch):
    """A exceção do httpx traz a URL, e a URL traz o token. Tem de sair mascarado."""
    import httpx

    from app.core.config import settings
    from app.hermes.telegram import ClienteTelegram, TelegramErro

    token = "8123456:AAH-segredo-do-bot"
    monkeypatch.setattr(settings, "telegram_bot_token", token, raising=False)
    monkeypatch.setattr("app.hermes.telegram.TENTATIVAS", 1)

    async def _explode(self, url, **kw):
        raise httpx.ConnectError(f"falha ao conectar em {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", _explode)
    with pytest.raises(TelegramErro) as erro:
        await ClienteTelegram(token).enviar("1", "oi")
    assert token not in str(erro.value)
    assert "***TOKEN***" in str(erro.value)


def test_janela_de_silencio_cruza_a_meia_noite(hermes_config):
    s = hermes_config
    assert s.janela_de_silencio(datetime.time(22, 0))    # noite
    assert s.janela_de_silencio(datetime.time(3, 0))     # madrugada
    assert s.janela_de_silencio(datetime.time(6, 59))
    assert not s.janela_de_silencio(datetime.time(8, 0))  # expediente
    assert not s.janela_de_silencio(datetime.time(19, 59))


# ── Ciclo 3: resumo diário e calendário forense ───────────────────────────

async def test_resumo_diario_sai_em_dia_util(sessao, acervo, hermes_config, hoje_fixo):
    from app.hermes.agendador import resumo_diario

    hoje_fixo(QUINTA)
    bot = TelegramFalso()
    assert await resumo_diario(sessao, bot) is True
    assert len(bot.enviados) == 1
    destino, texto = bot.enviados[0]
    assert destino == "-100999"
    assert "0010821-60.2025.5.15.0029" in texto
    assert "JOAO" not in texto.upper()


@pytest.mark.parametrize("data,motivo", [(SABADO, "fim de semana"),
                                         (INDEPENDENCIA, "feriado nacional")])
async def test_resumo_nao_sai_fora_de_dia_util(sessao, acervo, hermes_config, hoje_fixo,
                                               data, motivo):
    from app.hermes.agendador import resumo_diario

    hoje_fixo(data)
    bot = TelegramFalso()
    assert await resumo_diario(sessao, bot) is False, motivo
    assert bot.enviados == []


async def test_resumo_sem_nada_critico_ainda_avisa(sessao, usuarios, hermes_config, hoje_fixo):
    """Silêncio total faz a equipe duvidar se o sistema está no ar."""
    from app.hermes.agendador import resumo_diario

    hoje_fixo(QUINTA)
    bot = TelegramFalso()
    assert await resumo_diario(sessao, bot) is True
    assert "sob controle" in bot.enviados[0][1]


async def test_resumo_nao_repete_no_mesmo_dia(sessao, acervo, hermes_config, hoje_fixo):
    from app.hermes.agendador import resumo_diario

    hoje_fixo(QUINTA)
    bot = TelegramFalso()
    assert await resumo_diario(sessao, bot) is True
    assert await resumo_diario(sessao, bot) is False
    assert len(bot.enviados) == 1


# ── Ciclo 4: alerta crítico e não-repetição ───────────────────────────────

async def test_alerta_vai_ao_privado_do_responsavel(sessao, acervo, hermes_config, hoje_fixo):
    from app.hermes.agendador import varrer_alertas

    procurador = acervo["procurador"]
    await _vincular(sessao, procurador, chat="555")
    sessao.add(Triagem(publicacao_id="pub-1", responsavel_id=procurador.id))
    await sessao.commit()

    hoje_fixo(QUINTA)
    bot = TelegramFalso()
    assert await varrer_alertas(sessao, bot) == 1
    destino, texto = bot.enviados[0]
    assert destino == "555"
    assert "Prazo crítico" in texto


async def test_alerta_nao_repete(sessao, acervo, hermes_config, hoje_fixo):
    """A garantia é do índice único no banco, não de um `if` no Python."""
    from app.hermes.agendador import varrer_alertas

    procurador = acervo["procurador"]
    await _vincular(sessao, procurador)
    sessao.add(Triagem(publicacao_id="pub-1", responsavel_id=procurador.id))
    await sessao.commit()
    hoje_fixo(QUINTA)

    bot = TelegramFalso()
    assert await varrer_alertas(sessao, bot) == 1
    assert await varrer_alertas(sessao, bot) == 0
    assert await varrer_alertas(sessao, bot) == 0
    assert len(bot.enviados) == 1


async def test_envio_que_falha_pode_ser_tentado_de_novo(sessao, acervo, hermes_config,
                                                        hoje_fixo):
    """Falha grava `sucesso=False` e LIBERA a chave — senão um erro de rede
    apagaria o alerta para sempre."""
    from app.hermes.agendador import varrer_alertas

    procurador = acervo["procurador"]
    await _vincular(sessao, procurador)
    sessao.add(Triagem(publicacao_id="pub-1", responsavel_id=procurador.id))
    await sessao.commit()
    hoje_fixo(QUINTA)

    assert await varrer_alertas(sessao, TelegramFalso(falhar=True)) == 0
    bot = TelegramFalso()
    assert await varrer_alertas(sessao, bot) == 1

    registros = (await sessao.execute(select(EnvioHermes).order_by(EnvioHermes.id))).scalars().all()
    assert [r.sucesso for r in registros] == [False, True]


async def test_publicacao_sem_dono_vai_ao_grupo(sessao, acervo, hermes_config, hoje_fixo):
    """O pior destino de um prazo crítico é destino nenhum."""
    from app.hermes.agendador import varrer_alertas

    hoje_fixo(QUINTA)
    bot = TelegramFalso()
    assert await varrer_alertas(sessao, bot) == 1
    destino, texto = bot.enviados[0]
    assert destino == "-100999"
    assert "sem responsável" in texto


async def test_triagem_concluida_nao_gera_alerta(sessao, acervo, hermes_config, hoje_fixo):
    from app.hermes.agendador import varrer_alertas

    sessao.add(Triagem(publicacao_id="pub-1", status=StatusTriagem.CONCLUIDO))
    await sessao.commit()
    hoje_fixo(QUINTA)
    assert await varrer_alertas(sessao, TelegramFalso()) == 0


async def test_silencio_noturno_segura_o_alerta(sessao, acervo, hermes_config, hoje_fixo,
                                                monkeypatch):
    from app.hermes.agendador import varrer_alertas

    hoje_fixo(QUINTA)
    monkeypatch.setattr("app.hermes.agendador.agora",
                        lambda: datetime.datetime(2026, 9, 3, 22, 30))
    bot = TelegramFalso()
    assert await varrer_alertas(sessao, bot) == 0
    assert bot.enviados == []


async def test_palavra_urgente_alerta_mesmo_com_prazo_longo(sessao, acervo, hermes_config,
                                                            hoje_fixo):
    """Penhora não espera o prazo encurtar."""
    from app.hermes.agendador import coletar_criticos

    pub = await sessao.get(Publicacao, "pub-1")
    pub.vencimento = QUINTA + datetime.timedelta(days=40)
    pub.texto = "Intimação de PENHORA sobre as contas do Município."
    await sessao.commit()
    hoje_fixo(QUINTA)

    itens = await coletar_criticos(sessao)
    assert len(itens) == 1
    assert itens[0].motivo == "penhora"


# ── Ciclo 5: opt-in e callback ────────────────────────────────────────────

async def test_opt_in_exige_codigo_pedido_no_painel(cliente, token, sessao, hermes_config,
                                                    monkeypatch):
    bot = TelegramFalso()
    monkeypatch.setattr("app.hermes.webhook.ClienteTelegram", lambda *a, **k: bot)
    jwt = await token("procurador")
    cab = {"Authorization": f"Bearer {jwt}"}

    r = await cliente.get("/hermes/vinculo", headers=cab)
    assert r.json()["situacao"] == "sem_vinculo"

    codigo = (await cliente.post("/hermes/vinculo/codigo", headers=cab)).json()["codigo"]
    assert len(codigo) == 8

    r = await cliente.post("/hermes/telegram/webhook",
                           headers={"X-Telegram-Bot-Api-Secret-Token": "segredo-de-webhook"},
                           json={"message": {"chat": {"id": 4242}, "text": f"/vincular {codigo}",
                                             "from": {"id": 4242, "first_name": "Ana"}}})
    assert r.status_code == 200
    assert "Vinculado" in bot.enviados[-1][1]

    r = await cliente.get("/hermes/vinculo", headers=cab)
    assert r.json()["situacao"] == "vinculado"


async def test_codigo_errado_nao_vincula(cliente, sessao, usuarios, hermes_config, monkeypatch):
    bot = TelegramFalso()
    monkeypatch.setattr("app.hermes.webhook.ClienteTelegram", lambda *a, **k: bot)
    r = await cliente.post("/hermes/telegram/webhook",
                           headers={"X-Telegram-Bot-Api-Secret-Token": "segredo-de-webhook"},
                           json={"message": {"chat": {"id": 9}, "text": "/vincular ABCD1234",
                                             "from": {"id": 9}}})
    assert r.status_code == 200
    assert "não encontrado" in bot.enviados[-1][1]
    assert await sessao.scalar(select(func.count()).select_from(VinculoTelegram)) == 0


async def test_webhook_sem_segredo_e_recusado(cliente, hermes_config):
    r = await cliente.post("/hermes/telegram/webhook", json={"message": {}})
    assert r.status_code == 403
    r = await cliente.post("/hermes/telegram/webhook",
                           headers={"X-Telegram-Bot-Api-Secret-Token": "chute"},
                           json={"message": {}})
    assert r.status_code == 403


async def test_clique_de_usuario_nao_cadastrado_e_recusado(cliente, sessao, acervo,
                                                           hermes_config, monkeypatch):
    bot = TelegramFalso()
    monkeypatch.setattr("app.hermes.webhook.ClienteTelegram", lambda *a, **k: bot)
    r = await cliente.post("/hermes/telegram/webhook",
                           headers={"X-Telegram-Bot-Api-Secret-Token": "segredo-de-webhook"},
                           json={"callback_query": {"id": "cb1", "from": {"id": 31337},
                                                    "data": "visto:pub-1",
                                                    "message": {"message_id": 5,
                                                                "chat": {"id": 31337}}}})
    assert r.status_code == 200
    _, texto, alerta = bot.callbacks[-1]
    assert "não está vinculado" in texto
    assert alerta is True
    assert await sessao.get(Triagem, "pub-1") is None


async def test_clique_marca_triagem_e_registra_quem_clicou(cliente, sessao, acervo,
                                                           hermes_config, monkeypatch):
    bot = TelegramFalso()
    monkeypatch.setattr("app.hermes.webhook.ClienteTelegram", lambda *a, **k: bot)
    procurador = acervo["procurador"]
    await _vincular(sessao, procurador, tg_id="777")

    r = await cliente.post("/hermes/telegram/webhook",
                           headers={"X-Telegram-Bot-Api-Secret-Token": "segredo-de-webhook"},
                           json={"callback_query": {"id": "cb2", "from": {"id": 777},
                                                    "data": "visto:pub-1",
                                                    "message": {"message_id": 5,
                                                                "chat": {"id": 555}}}})
    assert r.status_code == 200
    tri = await sessao.get(Triagem, "pub-1")
    assert tri is not None and tri.status == "andamento"
    assert tri.atualizado_por_id == procurador.id
    assert bot.teclados == [("555", 5)]  # botões removidos após o clique

    aud = (await sessao.execute(
        select(Auditoria).where(Auditoria.acao == "triagem"))).scalars().all()
    assert aud and aud[-1].detalhe["origem"] == "telegram"


async def test_desvincular_apaga_o_opt_in(cliente, token, sessao, acervo, hermes_config):
    jwt = await token("procurador")
    cab = {"Authorization": f"Bearer {jwt}"}
    await _vincular(sessao, acervo["procurador"])
    r = await cliente.delete("/hermes/vinculo", headers=cab)
    assert r.status_code == 200
    assert await sessao.scalar(select(func.count()).select_from(VinculoTelegram)) == 0


async def test_vinculo_exige_autenticacao(cliente):
    assert (await cliente.get("/hermes/vinculo")).status_code == 401
    assert (await cliente.post("/hermes/vinculo/codigo")).status_code == 401


# ── Regressões colhidas na verificação de ponta a ponta ───────────────────

def test_nome_do_destinatario_nao_e_redigido():
    """Achado com dados reais: o procurador Carlos Menezes recebeu um alerta de
    processo movido por João Carlos, e o filtro devolveu
    "Prazo crítico — [nome suprimido] Menezes". O nome de quem RECEBE não é
    dado de terceiro."""
    from app.hermes.formatador import ItemPrazo, montar_alerta_critico

    item = ItemPrazo("1", "0010821-60.2025.5.15.0029", "TRT15", "Contestacao",
                     "trabalhista", QUINTA + datetime.timedelta(days=1), 1,
                     partes=("JOAO CARLOS DA SILVA",))
    texto = montar_alerta_critico(item=item, nome_procurador="Carlos Menezes",
                                  base_url="https://painel.teste")
    assert "Carlos Menezes" in texto
    assert "[nome suprimido]" not in texto
    # E o terceiro continua fora: "João" e "Silva" não são fichas do destinatário.
    assert "JOAO" not in texto.upper() and "SILVA" not in texto.upper()


async def test_urgencia_por_palavra_nao_entra_como_prazo_vencendo(sessao, acervo,
                                                                  hermes_config, hoje_fixo):
    """Achado com dados reais: uma penhora com vencimento em 24 dias úteis foi
    listada sob o título "prazos vencendo em até 3 dias úteis". Uma linha errada
    num boletim de prazo corrói a confiança no boletim inteiro."""
    from app.hermes.agendador import coletar_resumo
    from app.hermes.formatador import montar_resumo_diario

    pub = await sessao.get(Publicacao, "pub-1")
    pub.vencimento = QUINTA + datetime.timedelta(days=40)
    pub.texto = "Determinada a PENHORA sobre as contas do Município."
    await sessao.commit()
    hoje_fixo(QUINTA)

    dados = await coletar_resumo(sessao)
    assert dados["criticos"] == []
    assert len(dados["urgentes"]) == 1

    texto = montar_resumo_diario(
        data=QUINTA, criticos=dados["criticos"], urgentes=dados["urgentes"],
        novas_por_tribunal={}, sem_triagem=0, total_processos=1,
        base_url="https://painel.teste")
    assert "Nenhum prazo crítico" in texto
    assert "publicação sinalizada" in texto
    assert "penhora" in texto


async def test_hermes_nao_depende_da_varredura_estar_ligada(hermes_config, monkeypatch):
    """VARREDURA_ATIVA e HERMES_ATIVO são chaves independentes. Uma segunda
    instância que não varre o DJEN ainda precisa avisar."""
    from app.core.config import settings
    from app.services import agendador

    monkeypatch.setattr(settings, "varredura_ativa", False, raising=False)
    monkeypatch.setattr(settings, "hermes_ativo", True, raising=False)
    # AsyncIOScheduler.start() exige um loop em execução: o teste é async.
    sched = agendador.iniciar()
    try:
        assert sched is not None
        ids = {j.id for j in sched.get_jobs()}
        assert "varredura_djen" not in ids
        assert {"hermes_resumo", "hermes_alertas"} <= ids
    finally:
        agendador.parar()


def test_tudo_desligado_nao_sobe_agendador(hermes_config, monkeypatch):
    from app.core.config import settings
    from app.services import agendador

    monkeypatch.setattr(settings, "varredura_ativa", False, raising=False)
    monkeypatch.setattr(settings, "hermes_ativo", False, raising=False)
    assert agendador.iniciar() is None
