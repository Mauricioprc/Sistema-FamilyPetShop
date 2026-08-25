"""baseline: criacao de todas as tabelas a partir dos models atuais

Esta migration existia como uma lacuna no historico: as migrations anteriores
(dcaf33253b12 em diante) sao todas ALTER TABLE, herdadas de uma epoca em que
o schema era criado via db.create_all() e o Flask-Migrate so registrava
alteracoes incrementais em cima de um banco que ja existia. Isso funcionava
enquanto db.create_all() rodava no boot (wsgi.py antigo), mas quebra num
banco totalmente vazio (deploy do zero), porque nao existe nenhuma migration
de CRIACAO das tabelas na cadeia do Alembic.

Esta migration resolve isso criando todas as tabelas via
db.metadata.create_all(), que e seguro/idempotente: pula qualquer tabela que
ja exista (por isso nao quebra bancos que ja tinham sido criados via
db.create_all() antes desta correcao existir).

Revision ID: a0a0a0a0a0a0
Revises:
Create Date: 2026-08-25 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a0a0a0a0a0a0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from extensions import db
    bind = op.get_bind()
    db.metadata.create_all(bind=bind)


def downgrade():
    # Downgrade intencionalmente vazio: esta e uma migration de baseline
    # que so cria o que faltar. Reverter destruiria dados de producao.
    pass
