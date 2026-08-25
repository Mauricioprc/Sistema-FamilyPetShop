"""add data_prevista_pagamento (override manual da previsao) a pacote e atendimento

Revision ID: b1c2d3e4f5a6
Revises: dcaf33253b12
Create Date: 2026-08-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'dcaf33253b12'
branch_labels = None
depends_on = None


def _tem_coluna(tabela, coluna):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return coluna in [c['name'] for c in insp.get_columns(tabela)]


def upgrade():
    # Guard: a migration baseline (a0a0a0a0a0a0) ja cria essas colunas
    # quando parte dos models atuais. So adiciona aqui se realmente faltar.
    if not _tem_coluna('pacote', 'data_prevista_pagamento'):
        with op.batch_alter_table('pacote', schema=None) as batch_op:
            batch_op.add_column(sa.Column('data_prevista_pagamento', sa.Date(), nullable=True))

    if not _tem_coluna('atendimento', 'data_prevista_pagamento'):
        with op.batch_alter_table('atendimento', schema=None) as batch_op:
            batch_op.add_column(sa.Column('data_prevista_pagamento', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('atendimento', schema=None) as batch_op:
        batch_op.drop_column('data_prevista_pagamento')

    with op.batch_alter_table('pacote', schema=None) as batch_op:
        batch_op.drop_column('data_prevista_pagamento')
