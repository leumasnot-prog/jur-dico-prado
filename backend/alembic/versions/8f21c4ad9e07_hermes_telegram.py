"""Hermes: vínculo com o Telegram e trilha de envios

Revision ID: 8f21c4ad9e07
Revises: 1027a4b3f12e
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '8f21c4ad9e07'
down_revision = '1027a4b3f12e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_vinculos",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.String(length=32), nullable=True),
        sa.Column("telegram_chat_id", sa.String(length=32), nullable=True),
        sa.Column("nome_telegram", sa.String(length=160), nullable=True),
        sa.Column("codigo", sa.String(length=16), nullable=True),
        sa.Column("codigo_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("opt_in_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id"),
        sa.UniqueConstraint("telegram_user_id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_index("ix_telegram_vinculos_telegram_user_id", "telegram_vinculos",
                    ["telegram_user_id"])
    op.create_index("ix_telegram_vinculos_codigo", "telegram_vinculos", ["codigo"])

    op.create_table(
        "hermes_envios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chave", sa.String(length=120), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("destino", sa.String(length=32), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("publicacao_id", sa.String(length=40), nullable=True),
        sa.Column("sucesso", sa.Boolean(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["publicacao_id"], ["publicacoes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hermes_envios_chave", "hermes_envios", ["chave"])
    op.create_index("ix_hermes_envios_tipo", "hermes_envios", ["tipo"])
    op.create_index("ix_hermes_criado", "hermes_envios", ["criado_em"])

    # O CORAÇÃO DA TASK: índice parcial único. É ele — e não o código Python —
    # que torna impossível enviar dois avisos da mesma publicação ao mesmo
    # destinatário. `sucesso IS NOT FALSE` cobre o reservado (NULL) e o
    # entregue (TRUE); a falha (FALSE) sai do índice e libera nova tentativa.
    op.create_index("uq_hermes_chave", "hermes_envios", ["chave"], unique=True,
                    postgresql_where=sa.text("sucesso IS NOT FALSE"))


def downgrade() -> None:
    """Descarta a trilha de envios: ao voltar, o Hermes pode reavisar o que já avisou."""
    op.drop_index("uq_hermes_chave", table_name="hermes_envios")
    op.drop_table("hermes_envios")
    op.drop_table("telegram_vinculos")
