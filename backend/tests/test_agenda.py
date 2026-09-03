"""Agenda pessoal, pendências e "me avisa deste processo".

O que estes testes protegem, em ordem de importância:
  1. A agenda é PESSOAL — ninguém vê o prazo alheio como se fosse seu.
  2. `/pendencias` não pertence a mês nenhum: prazo vencido em agosto continua
     aparecendo em setembro, senão sumiria ao virar a página do calendário.
  3. Acompanhar é idempotente e não duplica alerta para quem já é responsável.
"""

from __future__ import annotations

import datetime

import pytest
import pytest_asyncio

from app.models import Acompanhamento, Processo, Publicacao, StatusTriagem, Triagem

HOJE = datetime.date.today()


@pytest_asyncio.fixture
async def acervo_agenda(sessao, usuarios):
    """Três publicações: uma do procurador, uma do assessor, uma vencida."""
    proc = usuarios["procurador"]
    outro = usuarios["assessor"]

    casos = [
        ("A", "00000000000000000001", proc.id, HOJE + datetime.timedelta(days=2), "novo"),
        ("B", "00000000000000000002", outro.id, HOJE + datetime.timedelta(days=2), "novo"),
        ("C", "00000000000000000003", proc.id, HOJE - datetime.timedelta(days=20), "novo"),
        ("D", "00000000000000000004", proc.id, HOJE + datetime.timedelta(days=2), "concluido"),
    ]
    for pid, numero, dono, venc, estado in casos:
        sessao.add(Processo(numero_processo=numero, numero_formatado=f"proc-{pid}",
                            tribunal="TJSP", classe="PROCEDIMENTO COMUM",
                            polo_do_ente="passivo", partes_contrarias=[], advogados=[]))
        await sessao.flush()
        sessao.add(Publicacao(
            id=pid, numero_processo=numero,
            data_disponibilizacao=HOJE - datetime.timedelta(days=30), tribunal="TJSP",
            classe="PROCEDIMENTO COMUM", partes=[], advogados=[], texto="x",
            ato_inferido="Contestacao", rito_inferido="comum", vencimento=venc))
        await sessao.flush()
        sessao.add(Triagem(publicacao_id=pid, responsavel_id=dono, status=estado))
    await sessao.commit()
    return usuarios


async def _cab(token, papel="procurador"):
    return {"Authorization": f"Bearer {await token(papel)}"}


# ── A agenda é pessoal ────────────────────────────────────────────────────

async def test_agenda_traz_so_o_que_e_meu(cliente, token, acervo_agenda):
    r = await cliente.get("/acervo/agenda", headers=await _cab(token))
    assert r.status_code == 200
    ids = {i["id"] for lista in r.json()["dias"].values() for i in lista}
    assert "A" in ids and "D" in ids      # do procurador
    assert "B" not in ids                 # do assessor — não é meu


async def test_chefia_pode_ver_a_agenda_inteira(cliente, token, acervo_agenda):
    r = await cliente.get("/acervo/agenda?de_todos=true", headers=await _cab(token, "chefe"))
    ids = {i["id"] for lista in r.json()["dias"].values() for i in lista}
    assert {"A", "B", "D"} <= ids


async def test_agenda_marca_os_dias_sem_expediente(cliente, token, acervo_agenda):
    """É o dado que explica por que um prazo pulou de data — sem ele o
    calendário mente por omissão."""
    r = await cliente.get("/acervo/agenda?mes=2026-09", headers=await _cab(token))
    nao_uteis = r.json()["nao_uteis"]
    assert "2026-09-05" in nao_uteis   # sábado
    assert "2026-09-06" in nao_uteis   # domingo
    assert "2026-09-07" in nao_uteis   # Independência
    assert "2026-09-08" not in nao_uteis


async def test_mes_invalido_e_recusado(cliente, token, acervo_agenda):
    r = await cliente.get("/acervo/agenda?mes=setembro", headers=await _cab(token))
    assert r.status_code == 422


async def test_severidade_classifica_pelo_estado_da_triagem(cliente, token, acervo_agenda):
    r = await cliente.get("/acervo/agenda", headers=await _cab(token))
    por_id = {i["id"]: i for lista in r.json()["dias"].values() for i in lista}
    assert por_id["A"]["severidade"] == "critico"
    assert por_id["D"]["severidade"] == "feito"   # concluído não é mais urgência


# ── Pendências: o que não pode sumir ao virar o mês ───────────────────────

async def test_pendencias_incluem_vencido_de_mes_anterior(cliente, token, acervo_agenda):
    r = await cliente.get("/acervo/pendencias", headers=await _cab(token))
    ids = {i["id"] for i in r.json()}
    assert "C" in ids, "prazo vencido tem de continuar aparecendo"
    assert "A" in ids
    assert "D" not in ids, "concluído não é pendência"
    assert "B" not in ids, "pendência de outra pessoa não é minha"


async def test_pendencias_ignoram_prazo_folgado(cliente, token, sessao, acervo_agenda):
    pub = await sessao.get(Publicacao, "A")
    pub.vencimento = HOJE + datetime.timedelta(days=60)
    await sessao.commit()
    r = await cliente.get("/acervo/pendencias", headers=await _cab(token))
    assert "A" not in {i["id"] for i in r.json()}


# ── "Me avisa deste processo" ─────────────────────────────────────────────

async def test_acompanhar_e_idempotente(cliente, token, sessao, acervo_agenda):
    from sqlalchemy import func, select

    cab = await _cab(token)
    for dias in (3, 7):
        r = await cliente.put("/acervo/processos/00000000000000000002/acompanhar",
                              headers=cab, json={"dias_antecedencia": dias})
        assert r.status_code == 200
        assert r.json()["dias_antecedencia"] == dias
    total = await sessao.scalar(select(func.count()).select_from(Acompanhamento))
    assert total == 1, "marcar de novo atualiza, não duplica"


async def test_processo_acompanhado_entra_na_minha_agenda(cliente, token, acervo_agenda):
    """O processo é do assessor, mas eu pedi para ser avisado dele."""
    cab = await _cab(token)
    assert "B" not in {i["id"] for lista in
                       (await cliente.get("/acervo/agenda", headers=cab)).json()["dias"].values()
                       for i in lista}

    await cliente.put("/acervo/processos/00000000000000000002/acompanhar",
                      headers=cab, json={"dias_antecedencia": 3})

    itens = {i["id"]: i for lista in
             (await cliente.get("/acervo/agenda", headers=cab)).json()["dias"].values()
             for i in lista}
    assert "B" in itens
    assert itens["B"]["acompanhado"] is True
    assert itens["B"]["meu"] is False, "acompanhar não me torna responsável"


async def test_desacompanhar_tira_da_agenda(cliente, token, acervo_agenda):
    cab = await _cab(token)
    await cliente.put("/acervo/processos/00000000000000000002/acompanhar",
                      headers=cab, json={"dias_antecedencia": 3})
    r = await cliente.delete("/acervo/processos/00000000000000000002/acompanhar", headers=cab)
    assert r.status_code == 200 and r.json()["acompanhado"] is False
    assert "B" not in {i["id"] for lista in
                       (await cliente.get("/acervo/agenda", headers=cab)).json()["dias"].values()
                       for i in lista}


async def test_acompanhar_processo_inexistente_e_404(cliente, token, acervo_agenda):
    r = await cliente.put("/acervo/processos/99999999999999999999/acompanhar",
                          headers=await _cab(token), json={"dias_antecedencia": 3})
    assert r.status_code == 404


async def test_agenda_exige_autenticacao(cliente):
    assert (await cliente.get("/acervo/agenda")).status_code == 401
    assert (await cliente.get("/acervo/pendencias")).status_code == 401


# ── Atribuição: a auxiliar administrativa distribui ───────────────────────

async def test_assessor_pode_atribuir_a_outra_pessoa(cliente, token, acervo_agenda):
    """Distribuir os feitos É o trabalho da auxiliar administrativa."""
    alvo = acervo_agenda["procurador"].id
    r = await cliente.patch("/acervo/publicacoes/B/triagem",
                            headers=await _cab(token, "assessor"),
                            json={"status": "novo", "responsavel_id": alvo})
    assert r.status_code == 200
    assert r.json()["responsavel_id"] == alvo


async def test_estagiario_nao_atribui_a_outra_pessoa(cliente, token, acervo_agenda):
    r = await cliente.patch("/acervo/publicacoes/B/triagem",
                            headers=await _cab(token, "estagiario"),
                            json={"status": "novo",
                                  "responsavel_id": acervo_agenda["procurador"].id})
    assert r.status_code == 403


async def test_equipe_lista_quem_recebe_atribuicao(cliente, token, acervo_agenda):
    r = await cliente.get("/acervo/equipe", headers=await _cab(token, "assessor"))
    assert r.status_code == 200
    pessoas = r.json()
    assert {p["papel"] for p in pessoas} == {"chefe", "procurador", "assessor", "estagiario"}
    # E-mail não sai: a tela precisa de nome e papel, e devolver mais dado
    # pessoal do que a tela usa é vazamento.
    assert all("email" not in p for p in pessoas)


# ── Hermes: quem acompanha também é avisado ───────────────────────────────

async def test_acompanhante_recebe_alerta_alem_do_responsavel(sessao, acervo_agenda,
                                                              monkeypatch):
    from app.core.config import settings
    from app.hermes.agendador import coletar_para_acompanhantes

    monkeypatch.setattr(settings, "hermes_dias_criticos", 3, raising=False)
    chefe = acervo_agenda["chefe"]
    # O chefe pede para ser avisado do processo A, cujo responsável é o procurador.
    sessao.add(Acompanhamento(usuario_id=chefe.id,
                              numero_processo="00000000000000000001", dias_antecedencia=5))
    await sessao.commit()

    pares = await coletar_para_acompanhantes(sessao)
    assert [(i.publicacao_id, u) for i, u in pares] == [("A", chefe.id)]


async def test_responsavel_que_tambem_acompanha_nao_e_avisado_duas_vezes(sessao, acervo_agenda):
    from app.hermes.agendador import coletar_para_acompanhantes

    proc = acervo_agenda["procurador"]
    sessao.add(Acompanhamento(usuario_id=proc.id,
                              numero_processo="00000000000000000001", dias_antecedencia=5))
    await sessao.commit()
    assert await coletar_para_acompanhantes(sessao) == []


async def test_antecedencia_maior_alcanca_prazo_que_o_padrao_ignoraria(sessao, acervo_agenda,
                                                                       monkeypatch):
    """Quem se atrapalha com prazo pede 10 dias e é cobrado bem antes do corte."""
    from app.core.config import settings
    from app.hermes.agendador import coletar_para_acompanhantes

    monkeypatch.setattr(settings, "hermes_dias_criticos", 3, raising=False)
    pub = await sessao.get(Publicacao, "B")
    pub.vencimento = HOJE + datetime.timedelta(days=9)
    await sessao.commit()

    chefe = acervo_agenda["chefe"]
    sessao.add(Acompanhamento(usuario_id=chefe.id,
                              numero_processo="00000000000000000002", dias_antecedencia=10))
    await sessao.commit()

    assert "B" in {i.publicacao_id for i, _ in await coletar_para_acompanhantes(sessao)}


async def test_triagem_concluida_nao_alerta_acompanhante(sessao, acervo_agenda):
    from app.hermes.agendador import coletar_para_acompanhantes

    chefe = acervo_agenda["chefe"]
    sessao.add(Acompanhamento(usuario_id=chefe.id,
                              numero_processo="00000000000000000004", dias_antecedencia=10))
    await sessao.commit()
    assert await coletar_para_acompanhantes(sessao) == []


@pytest.mark.parametrize("estado", [StatusTriagem.CONCLUIDO, StatusTriagem.SEM_PROVIDENCIA])
async def test_resolvido_sai_das_pendencias(cliente, token, sessao, acervo_agenda, estado):
    tri = await sessao.get(Triagem, "A")
    tri.status = estado
    await sessao.commit()
    r = await cliente.get("/acervo/pendencias", headers=await _cab(token))
    assert "A" not in {i["id"] for i in r.json()}


async def test_grupo_sabe_de_quem_e_o_processo_sem_telegram(sessao, acervo_agenda, monkeypatch):
    """Achado com dados reais: 30 avisos disseram "sem responsável atribuído"
    sobre processos que TÊM dono — o dono só não tinha vinculado o Telegram.
    O grupo lia "ninguém está cuidando disso" quando alguém estava."""
    from app.core.config import settings
    from app.hermes.agendador import varrer_alertas

    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TESTE", raising=False)
    monkeypatch.setattr(settings, "telegram_chat_id_grupo", "-100999", raising=False)

    enviadas: list[tuple[str, str]] = []

    class Bot:
        configurado = True

        async def enviar(self, chat_id, texto, botoes=None):
            enviadas.append((str(chat_id), texto))
            return {"message_id": 1}

    await varrer_alertas(sessao, Bot())

    # "A" é do procurador, que não vinculou Telegram nenhum neste teste.
    do_grupo = [t for c, t in enviadas if c == "-100999"]
    assert do_grupo, "o aviso não pode simplesmente sumir"
    assert any("sem Telegram vinculado" in t for t in do_grupo)
    assert not any("sem responsável atribuído" in t for t in do_grupo), \
        "há responsável — dizer o contrário desinforma a equipe"
    assert any("Teste Papel.PROCURADOR" in t or "procurador" in t.lower() for t in do_grupo)
