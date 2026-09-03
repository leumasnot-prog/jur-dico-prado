"""Cria o primeiro procurador-chefe. Sem ele, ninguém entra no painel.

    python -m app.criar_chefe "Nome Completo" email@pradopolis.sp.gov.br

A senha é pedida sem eco na tela e nunca é registrada em log, em histórico de
shell ou em argumento de linha de comando — por isso não é aceita como parâmetro.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.seguranca import hash_senha
from app.models import Papel, Usuario

MINIMO = 10


async def criar(nome: str, email: str, senha: str) -> None:
    async with get_sessionmaker()() as sessao:
        ja = await sessao.execute(select(Usuario).where(Usuario.email == email.lower()))
        if ja.scalar_one_or_none() is not None:
            print(f"Já existe usuário com o e-mail {email}.")
            raise SystemExit(1)
        sessao.add(Usuario(nome=nome, email=email.lower(),
                           senha_hash=hash_senha(senha), papel=Papel.CHEFE))
        await sessao.commit()
    print(f"Procurador-chefe criado: {nome} <{email}>")


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    nome, email = sys.argv[1], sys.argv[2]

    senha = getpass.getpass("Senha (mínimo 10 caracteres): ")
    if len(senha) < MINIMO:
        print(f"A senha precisa de ao menos {MINIMO} caracteres.")
        raise SystemExit(1)
    if senha != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.")
        raise SystemExit(1)

    asyncio.run(criar(nome, email, senha))


if __name__ == "__main__":
    main()
