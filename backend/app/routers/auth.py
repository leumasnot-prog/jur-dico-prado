"""Rotas de autenticação e gestão de usuários."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.seguranca import (
    PODE_GERIR_USUARIOS,
    conferir_senha,
    hash_senha,
    ler_token,
    registrar,
    requer_papel,
    token_de_acesso,
    token_de_renovacao,
    usuario_atual,
)
from app.models import Papel, Procurador, Usuario

router = APIRouter(prefix="/auth", tags=["auth"])


class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    papel: str
    ativo: bool
    oabs: list[str] = []


class UsuarioIn(BaseModel):
    nome: str = Field(min_length=2, max_length=160)
    email: EmailStr
    senha: str = Field(min_length=10, description="Mínimo de 10 caracteres.")
    papel: Papel = Papel.PROCURADOR
    oabs: list[str] = Field(default=[], description="Ex.: ['SP/274238']")


def _saida(u: Usuario) -> UsuarioOut:
    return UsuarioOut(id=u.id, nome=u.nome, email=u.email, papel=u.papel, ativo=u.ativo,
                      oabs=[f"{o.oab_uf}/{o.oab_numero}" for o in u.oabs if o.ativo])


@router.post("/login", response_model=Tokens, summary="Autentica e devolve os tokens")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> Tokens:
    achado = await sessao.execute(select(Usuario).where(Usuario.email == form.username.lower()))
    usuario = achado.scalar_one_or_none()

    # Mensagem idêntica para e-mail inexistente e senha errada: distinguir os dois
    # entrega ao atacante a lista de e-mails válidos do órgão.
    senha_ok = usuario is not None and conferir_senha(form.password, usuario.senha_hash)
    if usuario is None or not usuario.ativo or not senha_ok:
        await registrar(sessao, acao="login_falhou", entidade="usuario",
                        entidade_id=form.username.lower(), request=request)
        await sessao.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciais inválidas.")

    await registrar(sessao, acao="login", usuario_id=usuario.id, request=request)
    await sessao.commit()
    return Tokens(access_token=token_de_acesso(usuario.id),
                  refresh_token=token_de_renovacao(usuario.id))


class Renovacao(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Tokens, summary="Renova o token de acesso")
async def renovar(
    corpo: Renovacao, sessao: Annotated[AsyncSession, Depends(get_session)]
) -> Tokens:
    uid = ler_token(corpo.refresh_token, tipo_esperado="refresh")
    usuario = await sessao.get(Usuario, uid)
    if usuario is None or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inexistente ou inativo.")
    return Tokens(access_token=token_de_acesso(uid), refresh_token=token_de_renovacao(uid))


@router.get("/eu", response_model=UsuarioOut, summary="Dados do usuário autenticado")
async def eu(usuario: Annotated[Usuario, Depends(usuario_atual)]) -> UsuarioOut:
    return _saida(usuario)


@router.get("/usuarios", response_model=list[UsuarioOut], summary="Lista usuários")
async def listar(
    _: Annotated[Usuario, Depends(requer_papel(*PODE_GERIR_USUARIOS))],
    sessao: Annotated[AsyncSession, Depends(get_session)],
) -> list[UsuarioOut]:
    from sqlalchemy.orm import selectinload

    achado = await sessao.execute(select(Usuario).options(selectinload(Usuario.oabs))
                                  .order_by(Usuario.nome))
    return [_saida(u) for u in achado.scalars()]


@router.post("/usuarios", response_model=UsuarioOut, status_code=201,
             summary="Cadastra usuário e vincula OAB")
async def criar(
    corpo: UsuarioIn,
    chefe: Annotated[Usuario, Depends(requer_papel(*PODE_GERIR_USUARIOS))],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> UsuarioOut:
    email = corpo.email.lower()
    ja = await sessao.execute(select(Usuario).where(Usuario.email == email))
    if ja.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe usuário com este e-mail.")

    usuario = Usuario(nome=corpo.nome, email=email, senha_hash=hash_senha(corpo.senha),
                      papel=corpo.papel)
    sessao.add(usuario)
    await sessao.flush()

    for rotulo in corpo.oabs:
        uf, _, numero = rotulo.partition("/")
        sessao.add(Procurador(usuario_id=usuario.id, oab_uf=uf.upper().strip(),
                              oab_numero="".join(c for c in numero if c.isdigit())))
    # A senha NÃO entra no detalhe da auditoria.
    await registrar(sessao, acao="usuario_criado", usuario_id=chefe.id, entidade="usuario",
                    entidade_id=str(usuario.id),
                    detalhe={"papel": str(corpo.papel), "oabs": corpo.oabs}, request=request)
    await sessao.commit()
    await sessao.refresh(usuario, ["oabs"])
    return _saida(usuario)
