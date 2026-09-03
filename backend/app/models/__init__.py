"""Modelos do acervo processual.

Separação deliberada entre PUBLICACAO e TRIAGEM: a publicação veio do diário
oficial e é imutável; a triagem pertence ao departamento e muda o tempo todo.
Misturar as duas faria cada mudança de status reescrever o dado oficial.
"""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import agora
from app.core.db import Base


class Papel(enum.StrEnum):
    CHEFE = "chefe"
    PROCURADOR = "procurador"
    ASSESSOR = "assessor"
    ESTAGIARIO = "estagiario"


class StatusTriagem(enum.StrEnum):
    NOVO = "novo"
    ANDAMENTO = "andamento"
    CONCLUIDO = "concluido"
    SEM_PROVIDENCIA = "sem_providencia"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    # Hash Argon2id. Nunca a senha em claro, nunca em log.
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20), default=Papel.PROCURADOR)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    # lazy="selectin": em contexto assíncrono o carregamento preguiçoso estoura
    # com MissingGreenlet ao ser tocado fora da sessão. O usuário tem poucas OABs
    # e quase sempre queremos elas juntas.
    oabs: Mapped[list[Procurador]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # senha_hash fora do repr, de propósito
        return f"<Usuario {self.id} {self.email} {self.papel}>"


class Procurador(Base):
    """Vínculo usuário ↔ OAB. É a chave do roteamento automático de publicações.

    Um usuário pode ter mais de uma inscrição (seccionais diferentes).
    """

    __tablename__ = "procuradores"
    __table_args__ = (UniqueConstraint("oab_numero", "oab_uf", name="uq_oab"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    oab_numero: Mapped[str] = mapped_column(String(20), index=True)
    oab_uf: Mapped[str] = mapped_column(String(2), default="SP")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    usuario: Mapped[Usuario] = relationship(back_populates="oabs")


class Processo(Base):
    """Acervo permanente. Sobrevive à janela da varredura."""

    __tablename__ = "processos"

    numero_processo: Mapped[str] = mapped_column(String(25), primary_key=True)
    numero_formatado: Mapped[str | None] = mapped_column(String(30))
    tribunal: Mapped[str] = mapped_column(String(12), index=True)
    orgao: Mapped[str | None] = mapped_column(Text)
    classe: Mapped[str | None] = mapped_column(Text)
    polo_do_ente: Mapped[str] = mapped_column(String(20), default="nao_informado")
    segredo_justica: Mapped[bool] = mapped_column(Boolean, default=False)
    partes_contrarias: Mapped[list] = mapped_column(JSONB, default=list)
    advogados: Mapped[list] = mapped_column(JSONB, default=list)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True),
                                                             default=agora, onupdate=agora)

    publicacoes: Mapped[list[Publicacao]] = relationship(back_populates="processo",
                                                         cascade="all, delete-orphan")


class Publicacao(Base):
    """Imutável: veio do diário oficial e não se reescreve.

    Campos livres (orgao, classe, tipo_*, meio) são Text e não VARCHAR: o CNJ não
    garante tamanho neles. O STJ envia uma frase inteira em `tipo_documento` onde
    o TJSP envia uma palavra — descoberto com dados reais, não em teoria.

    O VENCIMENTO é gravado apenas para permitir índice e ordenação em SQL. A
    fonte de verdade continua sendo o cálculo do MCP, refeito na leitura — assim
    corrigir uma regra ou cadastrar um feriado vale para todo o acervo, sem migração.
    """

    __tablename__ = "publicacoes"
    __table_args__ = (
        Index("ix_pub_venc", "vencimento"),
        Index("ix_pub_data", "data_disponibilizacao"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    numero_processo: Mapped[str] = mapped_column(
        ForeignKey("processos.numero_processo", ondelete="CASCADE"), index=True
    )
    data_disponibilizacao: Mapped[datetime.date] = mapped_column(Date)
    tribunal: Mapped[str] = mapped_column(String(12), index=True)
    orgao: Mapped[str | None] = mapped_column(Text)
    classe: Mapped[str | None] = mapped_column(Text)
    tipo_comunicacao: Mapped[str | None] = mapped_column(Text)
    tipo_documento: Mapped[str | None] = mapped_column(Text)
    meio: Mapped[str | None] = mapped_column(Text)
    link_validacao: Mapped[str | None] = mapped_column(Text)
    partes: Mapped[list] = mapped_column(JSONB, default=list)
    advogados: Mapped[list] = mapped_column(JSONB, default=list)
    texto: Mapped[str | None] = mapped_column(Text)
    prazo_no_texto: Mapped[int | None] = mapped_column(Integer)
    ato_inferido: Mapped[str | None] = mapped_column(String(120))
    rito_inferido: Mapped[str | None] = mapped_column(String(40))
    vencimento: Mapped[datetime.date | None] = mapped_column(Date)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    processo: Mapped[Processo] = relationship(back_populates="publicacoes")
    triagem: Mapped[Triagem | None] = relationship(back_populates="publicacao",
                                                   uselist=False, cascade="all, delete-orphan")


class Triagem(Base):
    """Mutável, pertence ao departamento."""

    __tablename__ = "triagem"

    publicacao_id: Mapped[str] = mapped_column(
        ForeignKey("publicacoes.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default=StatusTriagem.NOVO, index=True)
    responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    anotacao: Mapped[str | None] = mapped_column(Text)
    atualizado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True),
                                                             default=agora, onupdate=agora)
    atualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id",
                                                                    ondelete="SET NULL"))

    publicacao: Mapped[Publicacao] = relationship(back_populates="triagem")


class Auditoria(Base):
    """SOMENTE INSERÇÃO. Sem UPDATE, sem DELETE — é o que a torna confiável."""

    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_aud_criado", "criado_em"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    acao: Mapped[str] = mapped_column(String(60), index=True)
    entidade: Mapped[str | None] = mapped_column(String(40))
    entidade_id: Mapped[str | None] = mapped_column(String(60))
    detalhe: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(60))
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)


__all__ = [
    "Auditoria",
    "Papel",
    "Processo",
    "Procurador",
    "Publicacao",
    "StatusTriagem",
    "Triagem",
    "Usuario",
]
