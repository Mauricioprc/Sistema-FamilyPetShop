"""add vencimento_customizado to pacote

Revision ID: dcaf33253b12
Revises:
Create Date: 2026-07-21 20:14:47.723627

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dcaf33253b12'
down_revision = 'a0a0a0a0a0a0'
branch_labels = None
depends_on = None


def _tem_coluna(tabela, coluna):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return coluna in [c['name'] for c in insp.get_columns(tabela)]


def upgrade():
    # Guard: a migration baseline (a0a0a0a0a0a0) ja cria 'pacote' com essa
    # coluna quando parte dos models atuais. So adiciona aqui se realmente
    # faltar (ex: banco restaurado de uma epoca anterior a esse campo).
    if not _tem_coluna('pacote', 'vencimento_customizado'):
        # server_default popula as linhas ja existentes (SQLite exige um
        # default ao adicionar coluna NOT NULL em tabela nao vazia).
        with op.batch_alter_table('pacote', schema=None) as batch_op:
            batch_op.add_column(sa.Column('vencimento_customizado', sa.Boolean(), nullable=False,
                                           server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('pacote', schema=None) as batch_op:
        batch_op.drop_column('vencimento_customizado')
