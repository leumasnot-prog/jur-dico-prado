"""Autenticação, hash de senha e autorização por papel.

REGRAS BLOQUEANTES:
- Senha nunca em claro, nunca em log, nunca em repr. Hash Argon2id.
- Permissão é verificada NO BACKEND, sempre. Esconder botão no frontend é
  conforto de interface, não segurança.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import agora, settings
from app.core.db import get_session
from app.models import Papel, Usuario

_hasher = PasswordHasher()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, senha)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _criar_token(sub: str, tipo: str, expira: datetime.timedelta) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET não configurado — o serviço não pode emitir tokens.")
    agora_utc = datetime.datetime.now(tz=datetime.UTC)
    corpo = {"sub": sub, "tipo": tipo, "iat": agora_utc, "exp": agora_utc + expira}
    return jwt.encode(corpo, settings.jwt_secret, algorithm=settings.jwt_algoritmo)


def token_de_acesso(usuario_id: int) -> str:
    return _criar_token(str(usuario_id), "access",
                        datetime.timedelta(minutes=settings.access_token_minutos))


def token_de_renovacao(usuario_id: int) -> str:
    return _criar_token(str(usuario_id), "refresh",
                        datetime.timedelta(days=settings.refresh_token_dias))


def ler_token(token: str, tipo_esperado: str = "access") -> int:
    """Devolve o id do usuário. 401 em token inválido, expirado ou de outro tipo."""
    try:
        corpo = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algoritmo])
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido ou expirado.") from exc
    if corpo.get("tipo") != tipo_esperado:
        # Um refresh token não pode ser usado como credencial de acesso.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tipo de token incorreto.")
    return int(corpo["sub"])


async def usuario_atual(
    token: Annotated[str | None, Depends(oauth2)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
) -> Usuario:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticação necessária.")
    uid = ler_token(token)
    usuario = await sessao.get(Usuario, uid)
    if usuario is None or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inexistente ou inativo.")
    return usuario


def requer_papel(*papeis: Papel):
    """Dependência de autorização. Use em toda rota que não seja pública."""

    async def _checar(usuario: Annotated[Usuario, Depends(usuario_atual)]) -> Usuario:
        if usuario.papel not in {str(p) for p in papeis}:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Ação restrita a: {', '.join(sorted(str(p) for p in papeis))}.",
            )
        return usuario

    return _checar


# Conjuntos usados nas rotas, nomeados pela intenção e não pela lista de papéis.
TODOS = (Papel.CHEFE, Papel.PROCURADOR, Papel.ASSESSOR, Papel.ESTAGIARIO)
PODE_VER_SIGILOSO = (Papel.CHEFE, Papel.PROCURADOR)
# A auxiliar administrativa distribui os feitos entre os procuradores — e
# distribuir É o trabalho dela. Deixar isso só com a chefia criaria um gargalo
# artificial no lugar exato onde o acervo entra na fila da equipe.
PODE_ATRIBUIR = (Papel.CHEFE, Papel.ASSESSOR)
PODE_GERIR_USUARIOS = (Papel.CHEFE,)
PODE_VARRER = (Papel.CHEFE, Papel.PROCURADOR)


async def registrar(
    sessao: AsyncSession, *, acao: str, usuario_id: int | None = None,
    entidade: str | None = None, entidade_id: str | None = None,
    detalhe: dict | None = None, request: Request | None = None,
) -> None:
    """Grava na trilha de auditoria. Somente inserção."""
    from app.models import Auditoria

    sessao.add(Auditoria(
        usuario_id=usuario_id, acao=acao, entidade=entidade, entidade_id=entidade_id,
        detalhe=detalhe or {}, ip=(request.client.host if request and request.client else None),
        criado_em=agora(),
    ))
