"""Autenticação e a matriz de permissões — uma asserção por linha da matriz.

Os casos NEGATIVOS são os que importam: um teste que só confirma que o chefe
entra não prova nada sobre o estagiário não entrar.
"""

from __future__ import annotations

import pytest


async def test_login_devolve_os_dois_tokens(cliente, usuarios):
    r = await cliente.post("/auth/login",
                           data={"username": "chefe@t.gov.br", "password": "senha-de-teste-longa"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["access_token"] and corpo["refresh_token"]
    assert corpo["token_type"] == "bearer"


async def test_senha_errada_e_email_inexistente_dao_a_mesma_resposta(cliente, usuarios):
    """Distinguir os dois entrega ao atacante a lista de e-mails válidos do órgão."""
    a = await cliente.post("/auth/login",
                           data={"username": "chefe@t.gov.br", "password": "errada"})
    b = await cliente.post("/auth/login",
                           data={"username": "ninguem@t.gov.br", "password": "errada"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


async def test_usuario_inativo_nao_entra(cliente, usuarios, sessao):
    usuarios["procurador"].ativo = False
    await sessao.commit()
    r = await cliente.post("/auth/login",
                           data={"username": "procurador@t.gov.br",
                                 "password": "senha-de-teste-longa"})
    assert r.status_code == 401


async def test_refresh_nao_serve_como_token_de_acesso(cliente, usuarios):
    r = await cliente.post("/auth/login",
                           data={"username": "chefe@t.gov.br", "password": "senha-de-teste-longa"})
    refresh = r.json()["refresh_token"]
    eu = await cliente.get("/auth/eu", headers={"Authorization": f"Bearer {refresh}"})
    assert eu.status_code == 401


async def test_token_expirado_devolve_401_e_nao_500(cliente, usuarios):
    import datetime

    from jose import jwt

    from app.core.config import settings

    passado = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(hours=2)
    vencido = jwt.encode({"sub": "1", "tipo": "access", "exp": passado},
                         settings.jwt_secret, algorithm=settings.jwt_algoritmo)
    r = await cliente.get("/auth/eu", headers={"Authorization": f"Bearer {vencido}"})
    assert r.status_code == 401


async def test_sem_token_e_401(cliente, usuarios):
    assert (await cliente.get("/acervo/publicacoes")).status_code == 401


async def test_refresh_renova(cliente, usuarios):
    login = await cliente.post("/auth/login",
                               data={"username": "chefe@t.gov.br",
                                     "password": "senha-de-teste-longa"})
    r = await cliente.post("/auth/refresh",
                           json={"refresh_token": login.json()["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]


# --- Matriz de permissões (§4 da TASK-2) ------------------------------------


@pytest.mark.parametrize(
    "papel,esperado",
    [("chefe", 200), ("procurador", 403), ("assessor", 403), ("estagiario", 403)],
)
async def test_so_o_chefe_gerencia_usuarios(cliente, token, papel, esperado):
    r = await cliente.get("/auth/usuarios",
                          headers={"Authorization": f"Bearer {await token(papel)}"})
    assert r.status_code == esperado


@pytest.mark.parametrize("papel", ["chefe", "procurador", "assessor", "estagiario"])
async def test_todos_veem_publicacoes(cliente, token, papel):
    r = await cliente.get("/acervo/publicacoes",
                          headers={"Authorization": f"Bearer {await token(papel)}"})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "papel,esperado",
    [("chefe", 200), ("procurador", 200), ("assessor", 403), ("estagiario", 403)],
)
async def test_so_chefe_e_procurador_disparam_varredura(cliente, token, papel, esperado,
                                                        monkeypatch):
    async def _fake(sessao, **kw):
        return {"processos": 0, "publicacoes_novas": 0}

    monkeypatch.setattr("app.services.acervo.varrer_e_persistir", _fake)
    r = await cliente.post("/acervo/varredura",
                           headers={"Authorization": f"Bearer {await token(papel)}"})
    assert r.status_code == esperado


async def test_senha_nunca_aparece_em_repr(usuarios):
    u = usuarios["chefe"]
    assert "senha_hash" not in repr(u)
    assert u.senha_hash not in repr(u)


# ── Ciclo de vida da senha ────────────────────────────────────────────────

async def test_troca_de_senha_exige_a_senha_atual(cliente, token, usuarios):
    cab = {"Authorization": f"Bearer {await token('procurador')}"}
    r = await cliente.post("/auth/senha", headers=cab,
                           json={"senha_atual": "chute-errado",
                                 "senha_nova": "nova-senha-bem-longa"})
    assert r.status_code == 403


async def test_troca_de_senha_funciona_e_a_antiga_para_de_valer(cliente, token, usuarios):
    cab = {"Authorization": f"Bearer {await token('procurador')}"}
    r = await cliente.post("/auth/senha", headers=cab,
                           json={"senha_atual": "senha-de-teste-longa",
                                 "senha_nova": "outra-senha-bem-longa"})
    assert r.status_code == 200

    antiga = await cliente.post("/auth/login", data={"username": "procurador@t.gov.br",
                                                    "password": "senha-de-teste-longa"})
    assert antiga.status_code == 401
    nova = await cliente.post("/auth/login", data={"username": "procurador@t.gov.br",
                                                  "password": "outra-senha-bem-longa"})
    assert nova.status_code == 200


async def test_senha_nova_precisa_ser_diferente(cliente, token, usuarios):
    cab = {"Authorization": f"Bearer {await token('procurador')}"}
    r = await cliente.post("/auth/senha", headers=cab,
                           json={"senha_atual": "senha-de-teste-longa",
                                 "senha_nova": "senha-de-teste-longa"})
    assert r.status_code == 400


async def test_senha_curta_e_recusada(cliente, token, usuarios):
    cab = {"Authorization": f"Bearer {await token('procurador')}"}
    r = await cliente.post("/auth/senha", headers=cab,
                           json={"senha_atual": "senha-de-teste-longa", "senha_nova": "curta"})
    assert r.status_code == 422


async def test_so_a_chefia_redefine_senha_de_terceiro(cliente, token, usuarios):
    alvo = usuarios["procurador"].id
    cab = {"Authorization": f"Bearer {await token('procurador')}"}
    r = await cliente.post(f"/auth/usuarios/{alvo}/senha", headers=cab,
                           json={"senha_nova": "provisoria-longa-123"})
    assert r.status_code == 403


async def test_chefia_redefine_e_a_troca_fica_auditada(cliente, token, sessao, usuarios):
    from sqlalchemy import select

    from app.models import Auditoria

    alvo = usuarios["procurador"]
    cab = {"Authorization": f"Bearer {await token('chefe')}"}
    r = await cliente.post(f"/auth/usuarios/{alvo.id}/senha", headers=cab,
                           json={"senha_nova": "provisoria-longa-123"})
    assert r.status_code == 200

    entrou = await cliente.post("/auth/login", data={"username": "procurador@t.gov.br",
                                                    "password": "provisoria-longa-123"})
    assert entrou.status_code == 200

    aud = (await sessao.execute(select(Auditoria).where(
        Auditoria.acao == "senha_redefinida_pela_chefia"))).scalars().all()
    assert len(aud) == 1
    assert aud[0].usuario_id == usuarios["chefe"].id
    assert aud[0].entidade_id == str(alvo.id)
    # A senha NUNCA entra na trilha — nem a antiga, nem a nova.
    assert "provisoria" not in str(aud[0].detalhe)


async def test_redefinir_senha_de_inexistente_e_404(cliente, token, usuarios):
    cab = {"Authorization": f"Bearer {await token('chefe')}"}
    r = await cliente.post("/auth/usuarios/9999/senha", headers=cab,
                           json={"senha_nova": "provisoria-longa-123"})
    assert r.status_code == 404
