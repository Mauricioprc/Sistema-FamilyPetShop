"""
Estado de conversa e alertas de atendente do chatbot do WhatsApp.

O webhook do WhatsApp é stateless por natureza (cada POST da Meta chega
isolado), mas o fluxo de "consultar meus dados" precisa lembrar, entre uma
mensagem e a próxima, que aquele telefone já confirmou identidade. Este
módulo também guarda os alertas de "cliente pediu para falar com
atendente", consumidos pelo header do sistema via polling.

Por que um arquivo SQLite próprio em vez de:
  - dicionário em memória: o app roda com 2 workers gunicorn (ver wsgi.py),
    cada worker tem sua própria memória — a confirmação de identidade
    poderia "desaparecer" se a resposta do cliente cair no outro worker.
  - tabela no banco principal (petshop.db) via SQLAlchemy: exigiria nova
    migration Alembic só para dados totalmente transitórios, que não tem
    valor histórico nenhum (nem o estado de conversa, nem os alertas —
    depois de respondidos ou adiados, não precisam ficar guardados).

Este arquivo usa sqlite3 puro (stdlib, sem dependência nova) e fica em
instance/chatbot_estado.db — separado do petshop.db, pode ser apagado a
qualquer momento sem perda de dados de negócio.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

# Mesmo padrão de caminho usado em config.py (basedir/instance/)
_BASEDIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
_DB_PATH = os.path.join(_BASEDIR, 'instance', 'chatbot_estado.db')

# Depois desse tempo sem resposta, a confirmação de identidade expira e o
# cliente precisa confirmar de novo (evita "é você?" de 3 dias atrás sendo
# reaproveitado por engano).
TTL_SEGUNDOS = 15 * 60  # 15 minutos


def _conectar() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS estado_conversa (
            telefone TEXT PRIMARY KEY,
            etapa TEXT NOT NULL,
            cliente_id INTEGER,
            atualizado_em REAL NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alerta_atendente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefone TEXT NOT NULL,
            nome_cliente TEXT,
            criado_em REAL NOT NULL
        )
    ''')
    return conn


@contextmanager
def _conexao():
    conn = _conectar()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def definir_etapa(telefone: str, etapa: str, cliente_id: int | None = None) -> None:
    """Grava em qual etapa do fluxo aquele telefone está agora."""
    with _conexao() as conn:
        conn.execute(
            '''INSERT INTO estado_conversa (telefone, etapa, cliente_id, atualizado_em)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(telefone) DO UPDATE SET
                   etapa = excluded.etapa,
                   cliente_id = excluded.cliente_id,
                   atualizado_em = excluded.atualizado_em''',
            (telefone, etapa, cliente_id, time.time())
        )


def obter_estado(telefone: str) -> tuple[str, int | None] | None:
    """
    Retorna (etapa, cliente_id) para o telefone, ou None se não houver
    estado ativo (nunca teve, ou expirou pelo TTL).
    """
    with _conexao() as conn:
        row = conn.execute(
            'SELECT etapa, cliente_id, atualizado_em FROM estado_conversa WHERE telefone = ?',
            (telefone,)
        ).fetchone()

    if not row:
        return None

    etapa, cliente_id, atualizado_em = row
    if time.time() - atualizado_em > TTL_SEGUNDOS:
        limpar_estado(telefone)
        return None

    return etapa, cliente_id


def limpar_estado(telefone: str) -> None:
    with _conexao() as conn:
        conn.execute('DELETE FROM estado_conversa WHERE telefone = ?', (telefone,))


# ---------------------------------------------------------------------------
# Alertas de "cliente pediu para falar com atendente"
# ---------------------------------------------------------------------------

def criar_alerta(telefone: str, nome_cliente: str | None) -> None:
    """
    Registra um pedido de atendimento humano. Não há deduplicação: se o
    mesmo cliente pedir de novo antes do primeiro alerta ser resolvido,
    fica um alerta por pedido — a equipe decide ignorar repetidos
    clicando 'Responder mais tarde' em cada um.
    """
    with _conexao() as conn:
        conn.execute(
            'INSERT INTO alerta_atendente (telefone, nome_cliente, criado_em) VALUES (?, ?, ?)',
            (telefone, nome_cliente, time.time())
        )


def listar_alertas() -> list[dict]:
    """Retorna todos os alertas pendentes, mais antigos primeiro."""
    with _conexao() as conn:
        rows = conn.execute(
            'SELECT id, telefone, nome_cliente, criado_em FROM alerta_atendente ORDER BY criado_em ASC'
        ).fetchall()

    return [
        {'id': r[0], 'telefone': r[1], 'nome_cliente': r[2], 'criado_em': r[3]}
        for r in rows
    ]


def contar_alertas() -> int:
    with _conexao() as conn:
        return conn.execute('SELECT COUNT(*) FROM alerta_atendente').fetchone()[0]


def remover_alerta(alerta_id: int) -> None:
    with _conexao() as conn:
        conn.execute('DELETE FROM alerta_atendente WHERE id = ?', (alerta_id,))
