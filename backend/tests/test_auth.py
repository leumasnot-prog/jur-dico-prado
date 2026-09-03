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
