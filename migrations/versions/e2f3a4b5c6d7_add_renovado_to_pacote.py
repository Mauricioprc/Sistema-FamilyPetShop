"""add renovado to pacote

Revision ID: e2f3a4b5c6d7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def _tem_coluna(tabela, coluna):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return coluna in [c['name'] for c in insp.get_columns(tabela)]


def upgrade():
    if not _tem_coluna('pacote', 'renovado'):
        # server_default popula as linhas ja existentes (SQLite exige um
        # default ao adicionar coluna NOT NULL em tabela nao vazia).
        with op.batch_alter_table('pacote', schema=None) as batch_op:
            batch_op.add_column(sa.Column('renovado', sa.Boolean(), nullable=False,
                                           server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('pacote', schema=None) as batch_op:
        batch_op.drop_column('renovado')
