"""
Estado de conversa, histórico de mensagens e modo de atendimento humano
do chatbot do WhatsApp.

O webhook do WhatsApp é stateless por natureza (cada POST da Meta chega
isolado), mas vários fluxos precisam de memória entre uma mensagem e a
próxima:
  - 'consultar meus dados' precisa lembrar que o telefone já confirmou
    identidade (estado_conversa);
  - a tela de Conversas precisa de um histórico real de mensagens
    trocadas, já que o bot processa e esquece por padrão (mensagem);
  - quando um atendente assume uma conversa manualmente pela tela de
    Conversas, o bot precisa saber que deve ficar em silêncio para
    aquele telefone (atendimento_humano).

Por que um arquivo SQLite próprio em vez de:
  - dicionário em memória: o app roda com 2 workers gunicorn (ver wsgi.py),
    cada worker tem sua própria memória — o estado poderia "desaparecer"
    se a próxima requisição cair no outro worker.
  - tabela no banco principal (petshop.db) via SQLAlchemy: exigiria nova
    migration Alembic, e este é um volume de escrita bem mais alto
    (toda mensagem do bot) que não precisa das garantias do banco
    principal de negócio.

Este arquivo usa sqlite3 puro (stdlib, sem dependência nova) e fica em
instance/chatbot_estado.db — separado do petshop.db.
"""
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

# Mesmo padrão de caminho usado em config.py (basedir/instance/)
_BASEDIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
_DB_PATH = os.path.join(_BASEDIR, 'instance', 'chatbot_estado.db')

# Depois desse tempo sem resposta, a confirmação de identidade expira e o
# cliente precisa confirmar de novo (evita "é você?" de 3 dias atrás sendo
# reaproveitado por engano).
TTL_SEGUNDOS = 15 * 60  # 15 minutos

# Quanto tempo o bot continua em silêncio depois que o atendente clica em
# "Finalizar atendimento" — janela de segurança para uma última mensagem
# do cliente não cair de volta no bot imediatamente.
SILENCIO_POS_ATENDIMENTO_SEGUNDOS = 60 * 60  # 1 hora

# Enquanto o atendente está com a conversa aberta (antes de finalizar),
# representamos isso como uma data bem no futuro — mais simples do que
# um campo booleano separado, já que toda a lógica de "está em silêncio"
# já gira em torno de comparar com o horário atual.
_ATENDIMENTO_SEM_PRAZO = 4102444800.0  # ano 2100


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
            duvida TEXT,
            criado_em REAL NOT NULL
        )
    ''')
    # Auto-migração leve: se a tabela já existia de uma versão anterior
    # (sem a coluna 'duvida'), adiciona agora. Seguro fazer isso aqui
    # sem backup, diferente do petshop.db — este arquivo guarda só dados
    # transitórios (alertas pendentes), não histórico de negócio.
    colunas = [row[1] for row in conn.execute('PRAGMA table_info(alerta_atendente)')]
    if 'duvida' not in colunas:
        conn.execute('ALTER TABLE alerta_atendente ADD COLUMN duvida TEXT')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS mensagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefone TEXT NOT NULL,
            nome_cliente TEXT,
            direcao TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            enviado_em REAL NOT NULL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mensagem_telefone ON mensagem (telefone, enviado_em)')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS atendimento_humano (
            telefone TEXT PRIMARY KEY,
            silencio_ate REAL NOT NULL
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

def criar_alerta(telefone: str, nome_cliente: str | None, duvida: str | None = None) -> None:
    """
    Registra um pedido de atendimento humano, com o texto da dúvida que
    o cliente escreveu (ver MSG_PEDIR_DUVIDA em rotas/chatbot.py). Não
    há deduplicação: se o mesmo cliente pedir de novo antes do primeiro
    alerta ser resolvido, fica um alerta por pedido — a equipe decide
    ignorar repetidos clicando 'Responder mais tarde' em cada um.
    """
    with _conexao() as conn:
        conn.execute(
            'INSERT INTO alerta_atendente (telefone, nome_cliente, duvida, criado_em) VALUES (?, ?, ?, ?)',
            (telefone, nome_cliente, duvida, time.time())
        )


def listar_alertas() -> list[dict]:
    """Retorna todos os alertas pendentes, mais antigos primeiro."""
    with _conexao() as conn:
        rows = conn.execute(
            'SELECT id, telefone, nome_cliente, duvida, criado_em FROM alerta_atendente ORDER BY criado_em ASC'
        ).fetchall()

    return [
        {'id': r[0], 'telefone': r[1], 'nome_cliente': r[2], 'duvida': r[3], 'criado_em': r[4]}
        for r in rows
    ]


def remover_alertas_do_telefone(telefone: str) -> None:
    """Usada quando o atendente assume a conversa manualmente — os
    alertas daquele telefone deixam de fazer sentido como 'pendentes',
    já que alguém já está cuidando."""
    with _conexao() as conn:
        conn.execute('DELETE FROM alerta_atendente WHERE telefone = ?', (telefone,))


# ---------------------------------------------------------------------------
# Histórico de mensagens (para a tela de Conversas)
# ---------------------------------------------------------------------------

def registrar_mensagem(telefone: str, nome_cliente: str | None, direcao: str, conteudo: str) -> None:
    """
    direcao: 'entrada' (cliente -> bot), 'saida_bot' (bot -> cliente) ou
    'saida_atendente' (humano -> cliente, pela tela de Conversas).
    """
    with _conexao() as conn:
        conn.execute(
            'INSERT INTO mensagem (telefone, nome_cliente, direcao, conteudo, enviado_em) VALUES (?, ?, ?, ?, ?)',
            (telefone, nome_cliente, direcao, conteudo, time.time())
        )


def historico_do_dia(telefone: str) -> list[dict]:
    """Mensagens de hoje (horário local do servidor) para um telefone, mais antigas primeiro."""
    inicio_do_dia = datetime.now(timezone.utc).astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()

    with _conexao() as conn:
        rows = conn.execute(
            '''SELECT direcao, conteudo, enviado_em FROM mensagem
               WHERE telefone = ? AND enviado_em >= ?
               ORDER BY enviado_em ASC''',
            (telefone, inicio_do_dia)
        ).fetchall()

    return [{'direcao': r[0], 'conteudo': r[1], 'enviado_em': r[2]} for r in rows]


def listar_conversas_do_dia() -> list[dict]:
    """
    Telefones com pelo menos uma mensagem hoje, mais o nome mais recente
    associado e o horário da última mensagem — para a lista da tela de
    Conversas. Telefones com alerta pendente de dias anteriores são
    incluídos por listar_alertas() separadamente; esta função cobre só
    'hoje'.
    """
    inicio_do_dia = datetime.now(timezone.utc).astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()

    with _conexao() as conn:
        rows = conn.execute(
            '''SELECT telefone, MAX(enviado_em) as ultima, 
                      (SELECT nome_cliente FROM mensagem m2 WHERE m2.telefone = m1.telefone 
                       AND m2.nome_cliente IS NOT NULL ORDER BY enviado_em DESC LIMIT 1) as nome
               FROM mensagem m1
               WHERE enviado_em >= ?
               GROUP BY telefone
               ORDER BY ultima DESC''',
            (inicio_do_dia,)
        ).fetchall()

    return [{'telefone': r[0], 'ultima_mensagem_em': r[1], 'nome_cliente': r[2]} for r in rows]


# ---------------------------------------------------------------------------
# Modo de atendimento humano (bot em silêncio para um telefone)
# ---------------------------------------------------------------------------

def assumir_atendimento(telefone: str) -> None:
    """Atendente clicou 'Atender' — bot fica em silêncio sem prazo definido."""
    with _conexao() as conn:
        conn.execute(
            '''INSERT INTO atendimento_humano (telefone, silencio_ate) VALUES (?, ?)
               ON CONFLICT(telefone) DO UPDATE SET silencio_ate = excluded.silencio_ate''',
            (telefone, _ATENDIMENTO_SEM_PRAZO)
        )


def finalizar_atendimento(telefone: str) -> None:
    """Atendente clicou 'Finalizar atendimento' — bot continua em silêncio
    por mais SILENCIO_POS_ATENDIMENTO_SEGUNDOS, depois volta a responder."""
    with _conexao() as conn:
        conn.execute(
            '''INSERT INTO atendimento_humano (telefone, silencio_ate) VALUES (?, ?)
               ON CONFLICT(telefone) DO UPDATE SET silencio_ate = excluded.silencio_ate''',
            (telefone, time.time() + SILENCIO_POS_ATENDIMENTO_SEGUNDOS)
        )


def bot_em_silencio(telefone: str) -> bool:
    """True se o bot não deve responder a este telefone agora."""
    with _conexao() as conn:
        row = conn.execute(
            'SELECT silencio_ate FROM atendimento_humano WHERE telefone = ?',
            (telefone,)
        ).fetchone()

    if not row:
        return False
    return time.time() < row[0]


def atendimento_ativo(telefone: str) -> bool:
    """
    True especificamente quando o atendente está com a conversa aberta
    (clicou 'Atender' e ainda não finalizou) — diferente da janela de
    1h pós-atendimento, que também deixa o bot em silêncio mas não conta
    como 'atendimento ativo' para fins de exibir o botão certo na tela.
    """
    with _conexao() as conn:
        row = conn.execute(
            'SELECT silencio_ate FROM atendimento_humano WHERE telefone = ?',
            (telefone,)
        ).fetchone()

    if not row:
        return False
    # Qualquer prazo muito distante (> 1 dia) é tratado como "sem prazo
    # definido", ou seja, atendimento ainda ativo — evita comparar com o
    # valor exato de _ATENDIMENTO_SEM_PRAZO, que é só um detalhe interno.
    return row[0] > time.time() + (24 * 60 * 60)
