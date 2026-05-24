"""
Testes de integracao para services usando banco em memoria.
"""
import pytest
from app import create_app
from extensions import db as _db


@pytest.fixture(scope='function')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


def _criar_cliente(db):
    from models import Cliente
    c = Cliente(nome_tutor='Teste', telefone='11999999999', nome_pet='Rex')
    db.session.add(c)
    db.session.commit()
    return c


def _criar_pacote(db, cliente_id):
    from models import Pacote
    p = Pacote(
        cliente_id=cliente_id,
        nome_servico='Banho',
        creditos_totais=4,
        preco_pacote=100.0,
        tipo_agendamento='semanal',
        dia_semana_fixo=1
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_registrar_avulso_sucesso(app, db):
    from services.agenda_service import registrar_atendimento_avulso
    c = _criar_cliente(db)
    sucesso, msg = registrar_atendimento_avulso({
        'cliente_id': str(c.id),
        'data': '2025-06-10',
        'servico': 'Banho',
        'preco': '50.00'
    })
    assert sucesso is True
    assert 'sucesso' in msg.lower()


def test_registrar_avulso_campos_faltando(app, db):
    from services.agenda_service import registrar_atendimento_avulso
    sucesso, msg = registrar_atendimento_avulso({'cliente_id': '1'})
    assert sucesso is False


def test_registrar_avulso_preco_negativo(app, db):
    from services.agenda_service import registrar_atendimento_avulso
    c = _criar_cliente(db)
    sucesso, msg = registrar_atendimento_avulso({
        'cliente_id': str(c.id),
        'data': '2025-06-10',
        'servico': 'Banho',
        'preco': '-10'
    })
    assert sucesso is False


def test_criar_pacote_sucesso(app, db):
    from services.pacote_service import criar_pacote
    c = _criar_cliente(db)
    sucesso, msg, pacote = criar_pacote({
        'cliente_id': str(c.id),
        'nome_servico': 'Banho mensal',
        'creditos_totais': '4',
        'preco_pacote': '120',
        'tipo_agendamento': 'nenhum',
        'dia_semana': ''
    })
    assert sucesso is True
    assert pacote is not None
    assert pacote.creditos_totais == 4


def test_criar_pacote_creditos_zero(app, db):
    from services.pacote_service import criar_pacote
    c = _criar_cliente(db)
    sucesso, msg, _ = criar_pacote({
        'cliente_id': str(c.id),
        'nome_servico': 'Banho',
        'creditos_totais': '0',
        'preco_pacote': '100',
        'tipo_agendamento': 'nenhum',
        'dia_semana': ''
    })
    assert sucesso is False
