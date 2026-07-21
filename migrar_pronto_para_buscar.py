#!/usr/bin/env python3
"""
Migração: adiciona a coluna 'pronto_para_buscar' na tabela 'atendimento'.

Necessária porque o projeto não usa Flask-Migrate/Alembic de fato — o
schema é criado só por db.create_all(), que NÃO adiciona coluna nova em
tabela já existente. Sem rodar este script, o sistema vai quebrar com
"no such column: atendimento.pronto_para_buscar" em qualquer página que
toque na tabela de atendimentos.

Uso (no PythonAnywhere, dentro de um Bash console, na pasta do projeto):

    python3 migrar_pronto_para_buscar.py

Faz backup automático do banco antes de qualquer alteração. Se a coluna
já existir (rodar duas vezes por engano), o script detecta e não faz
nada — seguro de rodar mais de uma vez.
"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main():
    caminho_banco = Path(__file__).parent / 'instance' / 'petshop.db'

    if not caminho_banco.exists():
        print(f'ERRO: banco não encontrado em {caminho_banco}')
        sys.exit(1)

    conn = sqlite3.connect(str(caminho_banco))
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=5000;')
    colunas = [row[1] for row in conn.execute('PRAGMA table_info(atendimento)')]

    if 'pronto_para_buscar' in colunas:
        print('Coluna pronto_para_buscar já existe. Nada a fazer.')
        conn.close()
        return

    backup = caminho_banco.with_suffix(
        f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    shutil.copy2(caminho_banco, backup)
    print(f'Backup criado em: {backup}')

    conn.execute(
        'ALTER TABLE atendimento ADD COLUMN pronto_para_buscar '
        'BOOLEAN NOT NULL DEFAULT 0'
    )
    conn.commit()
    conn.close()
    print('Coluna pronto_para_buscar adicionada com sucesso.')


if __name__ == '__main__':
    main()
