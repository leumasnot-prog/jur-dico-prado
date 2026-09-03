"""Cria um usuário do painel, com papel e OAB opcionais.

    python -m app.criar_usuario "Nome Completo" email@pradopolis.sp.gov.br procurador
    python -m app.criar_usuario "Nome" email@x.gov.br procurador --oab SP/274238

Papéis: chefe, procurador, assessor, estagiario.

A OAB não é decoração: é a chave do roteamento automático. Publicação que
intima aquela inscrição cai sozinha na fila do procurador, sem ninguém
distribuir à mão.

A senha é pedida sem eco e nunca vira argumento de linha de comando — argumento
fica no histórico do shell e na lista de processos da máquina.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.seguranca import hash_senha
from app.models import Papel, Procurador, Usuario

MINIMO = 10
PAPEIS = {str(p) for p in Papel}


async def criar(nome: str, email: str, papel: str, senha: str, oab: str | None) -> None:
    async with get_sessionmaker()() as sessao:
        ja = await sessao.scalar(select(Usuario).where(Usuario.email == email.lower()))
        if ja is not None:
            print(f"Já existe usuário com o e-mail {email}.")
            raise SystemExit(1)

        usuario = Usuario(nome=nome, email=email.lower(),
                          senha_hash=hash_senha(senha), papel=papel)
        sessao.add(usuario)
        await sessao.flush()

        if oab:
            uf, _, numero = oab.partition("/")
            if not numero:
                print("OAB no formato UF/NUMERO, por exemplo SP/274238.")
                raise SystemExit(1)
            sessao.add(Procurador(usuario_id=usuario.id,
                                  oab_uf=uf.strip().upper(), oab_numero=numero.strip()))
        await sessao.commit()

    print(f"Criado: {nome} <{email}> como {papel}" + (f", OAB {oab}" if oab else ""))


def main() -> None:
    argumentos = sys.argv[1:]
    oab = None
    if "--oab" in argumentos:
        i = argumentos.index("--oab")
        try:
            oab = argumentos[i + 1]
        except IndexError:
            print("--oab precisa de um valor, por exemplo SP/274238.")
            raise SystemExit(2) from None
        argumentos = argumentos[:i] + argumentos[i + 2:]

    if len(argumentos) != 3:
        print(__doc__)
        raise SystemExit(2)
    nome, email, papel = argumentos
    if papel not in PAPEIS:
        print(f"Papel inválido: {papel}. Use um de: {', '.join(sorted(PAPEIS))}.")
        raise SystemExit(2)

    senha = getpass.getpass(f"Senha de {nome} (mínimo {MINIMO} caracteres): ")
    if len(senha) < MINIMO:
        print(f"A senha precisa de ao menos {MINIMO} caracteres.")
        raise SystemExit(1)
    if senha != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.")
        raise SystemExit(1)

    asyncio.run(criar(nome, email, papel, senha, oab))


if __name__ == "__main__":
    main()
