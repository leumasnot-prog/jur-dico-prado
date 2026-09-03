"""acompanhamentos: "me avisa deste processo"

Revision ID: a3d70b915c48
Revises: 8f21c4ad9e07
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3d70b915c48'
down_revision = '8f21c4ad9e07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acompanhamentos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("numero_processo", sa.String(length=25), nullable=False),
        sa.Column("dias_antecedencia", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["numero_processo"], ["processos.numero_processo"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Uma pessoa acompanha um processo uma vez só. Marcar de novo atualiza
        # a antecedência em vez de criar uma segunda linha.
        sa.UniqueConstraint("usuario_id", "numero_processo", name="uq_acompanhamento"),
    )
    op.create_index("ix_acompanhamentos_usuario_id", "acompanhamentos", ["usuario_id"])
    op.create_index("ix_acompanhamentos_numero_processo", "acompanhamentos", ["numero_processo"])


def downgrade() -> None:
    """Descarta as marcações: ao voltar, ninguém acompanha nada."""
    op.drop_table("acompanhamentos")
