"""Ingestão, idempotência, roteamento por OAB, triagem e auditoria."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select

from app.models import Auditoria, Processo, Publicacao, Triagem

HOJE = datetime.date.today()


def _comunicacao(id_: str, numero: str, oab: str = "SP/274238", tribunal: str = "TRT15") -> dict:
    """Payload no formato do DJEN, como o serviço realmente recebe."""
    return {
        "id": id_, "numero_processo": numero, "numeroprocessocommascara": numero,
        "data_disponibilizacao": HOJE.isoformat(), "siglaTribunal": tribunal,
        "nomeOrgao": "1ª Vara", "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
        "tipoComunicacao": "Intimação", "tipoDocumento": "Notificação",
        "meiocompleto": "DJEN", "link": "https://exemplo/x",
        "texto": "Fica intimado<br>no prazo de 15 (quinze) dias.",
        "destinatarios": [{"nome": "MUNICIPIO DE PRADOPOLIS", "polo": "P"},
                          {"nome": "FULANO DE TAL", "polo": "A"}],
        "destinatarioadvogados": [
            {"advogado": {"nome": "Dr. Fulano", "uf_oab": oab.split("/")[0],
                          "numero_oab": oab.split("/")[1]}}
        ],
    }


@pytest.fixture
def djen_falso(monkeypatch):
    """Substitui só a rede. O parsing, o cálculo e a persistência são os reais."""
    def _instalar(comunicacoes: list[dict]):
        class _Cliente:
            # Espelha a assinatura real: o servico constroi o cliente com
            # timeout proprio, e um duble que ignora isso deixa passar erro.
            def __init__(self, base_url=None, timeout=None):
                self.timeout = timeout

            async def buscar(self, **kw):
                return comunicacoes
        monkeypatch.setattr("mcp_juridico_brasil.comunica.client.ComunicaClient", _Cliente)
    return _instalar


async def test_varredura_persiste_processo_e_publicacao(sessao, usuarios, djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029")])
    r = await varrer_e_persistir(sessao)

    assert r["comunicacoes_confirmadas"] == 1
    assert r["publicacoes_novas"] == 1
    assert await sessao.scalar(select(func.count()).select_from(Processo)) == 1
    assert await sessao.scalar(select(func.count()).select_from(Publicacao)) == 1


async def test_varredura_e_idempotente(sessao, usuarios, djen_falso):
    """Rodar duas vezes não duplica nada e não perde nada."""
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029")])
    await varrer_e_persistir(sessao)
    segunda = await varrer_e_persistir(sessao)

    assert segunda["publicacoes_novas"] == 0
    assert await sessao.scalar(select(func.count()).select_from(Publicacao)) == 1


async def test_homonimo_e_descartado(sessao, usuarios, djen_falso):
    """'Residencial Pradópolis SPE Ltda' não é o Município."""
    from app.services.acervo import varrer_e_persistir

    homonimo = _comunicacao("2", "00108216020255150030")
    homonimo["destinatarios"] = [{"nome": "RESIDENCIAL PRADOPOLIS SPE LTDA", "polo": "P"}]
    djen_falso([_comunicacao("1", "00108216020255150029"), homonimo])

    r = await varrer_e_persistir(sessao)
    assert r["comunicacoes_brutas"] == 2
    assert r["comunicacoes_confirmadas"] == 1
    assert r["descartadas_por_homonimia"] == 1


async def test_roteamento_por_oab_atribui_ao_procurador(sessao, usuarios, djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029", oab="SP/274238")])
    r = await varrer_e_persistir(sessao)

    assert r["atribuidas_por_oab"] == 1
    tri = await sessao.get(Triagem, "1")
    assert tri.responsavel_id == usuarios["procurador"].id


async def test_oab_desconhecida_nao_some_fica_sem_dono(sessao, usuarios, djen_falso):
    """Publicação sem OAB cadastrada vai para a fila do chefe, nunca desaparece."""
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029", oab="SP/999999")])
    r = await varrer_e_persistir(sessao)

    assert r["atribuidas_por_oab"] == 0
    assert await sessao.get(Publicacao, "1") is not None
    assert await sessao.get(Triagem, "1") is None


async def test_prazo_trabalhista_usa_o_dl_779(sessao, usuarios, djen_falso):
    """Contestação trabalhista: 15 dias úteis em quádruplo, não em dobro."""
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029", tribunal="TRT15")])
    await varrer_e_persistir(sessao)

    pub = await sessao.get(Publicacao, "1")
    assert pub.rito_inferido == "trabalhista"
    assert pub.ato_inferido == "Contestacao"
    assert pub.vencimento is not None
    # 60 dias úteis empurram o vencimento para bem além de 30 dias corridos.
    assert (pub.vencimento - HOJE).days > 60


async def test_texto_chega_limpo_e_prazo_do_texto_e_lido(sessao, usuarios, djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029")])
    await varrer_e_persistir(sessao)

    pub = await sessao.get(Publicacao, "1")
    assert "<br>" not in (pub.texto or "")
    assert pub.prazo_no_texto == 15


async def test_triagem_grava_auditoria(cliente, token, sessao, usuarios, djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029")])
    await varrer_e_persistir(sessao)

    r = await cliente.patch("/acervo/publicacoes/1/triagem",
                            json={"status": "concluido", "anotacao": "protocolado"},
                            headers={"Authorization": f"Bearer {await token('procurador')}"})
    assert r.status_code == 200

    linhas = await sessao.execute(select(Auditoria).where(Auditoria.acao == "triagem"))
    aud = linhas.scalars().first()
    assert aud is not None
    assert aud.detalhe["para"] == "concluido"
    assert aud.usuario_id == usuarios["procurador"].id


async def test_so_o_chefe_atribui_a_outra_pessoa(cliente, token, sessao, usuarios, djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029", oab="SP/999999")])
    await varrer_e_persistir(sessao)
    outro = usuarios["assessor"].id

    negado = await cliente.patch(
        "/acervo/publicacoes/1/triagem",
        json={"status": "andamento", "responsavel_id": outro},
        headers={"Authorization": f"Bearer {await token('procurador')}"})
    assert negado.status_code == 403

    permitido = await cliente.patch(
        "/acervo/publicacoes/1/triagem",
        json={"status": "andamento", "responsavel_id": outro},
        headers={"Authorization": f"Bearer {await token('chefe')}"})
    assert permitido.status_code == 200


async def test_atribuir_a_si_mesmo_e_permitido(cliente, token, sessao, usuarios, djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029", oab="SP/999999")])
    await varrer_e_persistir(sessao)

    r = await cliente.patch(
        "/acervo/publicacoes/1/triagem",
        json={"status": "andamento", "responsavel_id": usuarios["procurador"].id},
        headers={"Authorization": f"Bearer {await token('procurador')}"})
    assert r.status_code == 200


async def test_triagem_de_publicacao_inexistente_e_404(cliente, token, usuarios):
    r = await cliente.patch("/acervo/publicacoes/nao-existe/triagem",
                            json={"status": "novo"},
                            headers={"Authorization": f"Bearer {await token('chefe')}"})
    assert r.status_code == 404


async def test_status_invalido_e_recusado(cliente, token, usuarios):
    r = await cliente.patch("/acervo/publicacoes/1/triagem",
                            json={"status": "inventado"},
                            headers={"Authorization": f"Bearer {await token('chefe')}"})
    assert r.status_code == 422


async def test_segredo_de_justica_some_para_estagiario(cliente, token, sessao, usuarios,
                                                       djen_falso):
    from app.services.acervo import varrer_e_persistir

    djen_falso([_comunicacao("1", "00108216020255150029")])
    await varrer_e_persistir(sessao)
    proc = await sessao.get(Processo, "00108216020255150029")
    proc.segredo_justica = True
    await sessao.commit()

    for papel, esperado in (("chefe", 1), ("procurador", 1), ("estagiario", 0), ("assessor", 0)):
        r = await cliente.get("/acervo/publicacoes",
                              headers={"Authorization": f"Bearer {await token(papel)}"})
        assert len(r.json()) == esperado, f"papel {papel}"
