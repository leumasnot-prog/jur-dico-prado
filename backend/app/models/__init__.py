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
    text,
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


class VinculoTelegram(Base):
    """Opt-in do usuario no Hermes. Uma linha por usuario, dois estados.

    PENDENTE: `codigo` preenchido, `telegram_user_id` vazio — o usuario pediu o
    codigo no painel e ainda nao falou com o bot.
    VINCULADO: `telegram_user_id` preenchido, `codigo` nulo.

    Ninguem e cadastrado sem autorizar: o vinculo so nasce quando a propria
    pessoa envia o codigo ao bot, de dentro do Telegram dela.
    """

    __tablename__ = "telegram_vinculos"

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    telegram_user_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(32))
    nome_telegram: Mapped[str | None] = mapped_column(String(160))
    codigo: Mapped[str | None] = mapped_column(String(16), unique=True, index=True)
    codigo_expira_em: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    opt_in_em: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    usuario: Mapped[Usuario] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # codigo fora do repr: e credencial de curta vida
        return f"<VinculoTelegram usuario={self.usuario_id} ativo={self.ativo}>"


class EnvioHermes(Base):
    """Trilha dos avisos enviados. Responde "quem foi avisado do que, e quando".

    A UNICIDADE E DO BANCO, nao do codigo: o indice parcial abaixo torna
    impossivel gravar dois envios bem-sucedidos com a mesma `chave`. E o que
    garante "no maximo um alerta por publicacao" mesmo se o agendador rodar duas
    vezes ou dois processos subirem em paralelo.

    `sucesso` tem tres estados de proposito:
      None  = reservado, envio em curso  -> ja bloqueia duplicata
      True  = entregue                   -> bloqueia para sempre
      False = falhou                     -> LIBERA a chave para nova tentativa
    """

    __tablename__ = "hermes_envios"
    __table_args__ = (
        Index(
            "uq_hermes_chave",
            "chave",
            unique=True,
            postgresql_where=text("sucesso IS NOT FALSE"),
        ),
        Index("ix_hermes_criado", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(120), index=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    destino: Mapped[str] = mapped_column(String(32))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    publicacao_id: Mapped[str | None] = mapped_column(
        ForeignKey("publicacoes.id", ondelete="SET NULL")
    )
    sucesso: Mapped[bool | None] = mapped_column(Boolean, default=None)
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Acompanhamento(Base):
    """"Me avisa deste processo" — o usuário pede lembrete de um feito específico.

    Existe separado de `Triagem.responsavel_id` de propósito: responsável é
    ATRIBUIÇÃO (quem responde pelo caso, definido pela chefia ou pela auxiliar),
    e acompanhamento é INTERESSE (quem quer ser cobrado, definido pela própria
    pessoa). Um procurador acompanha o processo do colega enquanto ele está de
    férias sem virar responsável por ele; e alguém que se atrapalha com prazo
    pode acompanhar os próprios casos com antecedência maior que a padrão.
    """

    __tablename__ = "acompanhamentos"
    __table_args__ = (
        UniqueConstraint("usuario_id", "numero_processo", name="uq_acompanhamento"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    numero_processo: Mapped[str] = mapped_column(
        ForeignKey("processos.numero_processo", ondelete="CASCADE"), index=True
    )
    # Quantos dias úteis antes do vencimento o Hermes começa a cobrar. O padrão
    # do sistema é 3; quem quer mais fôlego pede mais, no próprio processo.
    dias_antecedencia: Mapped[int] = mapped_column(Integer, default=3)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)


__all__ = [
    "Acompanhamento",
    "Auditoria",
    "EnvioHermes",
    "Papel",
    "Processo",
    "Procurador",
    "Publicacao",
    "StatusTriagem",
    "Triagem",
    "Usuario",
    "VinculoTelegram",
]
