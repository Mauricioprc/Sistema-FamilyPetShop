"""
Testes de integracao para o vencimento customizavel de pacotes:
- criacao normal (comportamento existente, nao deve quebrar)
- edicao manual da data_vencimento (rotas/pacotes.py::editar)
- renovacao respeitando vencimento_customizado (services/pacote_service.py::renovar_pacote)
"""
import pytest
from datetime import date
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


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True


def _criar_cliente(db):
    from models import Cliente
    c = Cliente(nome_tutor='Teste', telefone='11999999999', nome_pet='Rex')
    db.session.add(c)
    db.session.commit()
    return c


def test_criar_pacote_vencimento_automatico_pelo_primeiro_banho(app, db):
    from services.pacote_service import criar_pacote
    c = _criar_cliente(db)
    sucesso, msg, pacote = criar_pacote({
        'cliente_id': str(c.id),
        'nome_servico': 'Banho',
        'creditos_totais': '4',
        'preco_pacote': '120',
        'tipo_agendamento': 'semanal',
        'dia_semana': '1',  # terca
        'data_inicio': '2026-01-05'  # segunda
    })
    assert sucesso is True
    assert pacote.vencimento_customizado is False
    assert pacote.data_vencimento == date(2026, 1, 6)  # primeira terca a partir de 05/01


def test_editar_pacote_com_data_diferente_marca_customizado(app, db, client):
    from models import Pacote
    c = _criar_cliente(db)
    p = Pacote(cliente_id=c.id, nome_servico='Banho', creditos_totais=4, preco_pacote=100.0,
               tipo_agendamento='semanal', dia_semana_fixo=1, data_vencimento=date(2026, 1, 10))
    db.session.add(p)
    db.session.commit()
    pid = p.id

    _login(client)
    client.post(f'/pacote/editar/{pid}', data={
        'nome_servico': 'Banho', 'preco_pacote': '100,00', 'creditos_totais': '4',
        'data_vencimento': '2026-02-15'
    })

    db.session.expire_all()
    p2 = db.session.get(Pacote, pid)
    assert p2.vencimento_customizado is True
    assert p2.data_vencimento == date(2026, 2, 15)


def test_editar_pacote_sem_mudar_data_nao_marca_customizado(app, db, client):
    from models import Pacote
    c = _criar_cliente(db)
    p = Pacote(cliente_id=c.id, nome_servico='Banho', creditos_totais=4, preco_pacote=100.0,
               tipo_agendamento='semanal', dia_semana_fixo=1, data_vencimento=date(2026, 1, 10))
    db.session.add(p)
    db.session.commit()
    pid = p.id

    _login(client)
    client.post(f'/pacote/editar/{pid}', data={
        'nome_servico': 'Banho', 'preco_pacote': '100,00', 'creditos_totais': '4',
        'data_vencimento': '2026-01-10'  # mesma data
    })

    db.session.expire_all()
    p2 = db.session.get(Pacote, pid)
    assert p2.vencimento_customizado is False
    assert p2.data_vencimento == date(2026, 1, 10)


def test_renovar_pacote_customizado_usa_proximo_mes_mesma_dia(app, db):
    from services.pacote_service import renovar_pacote
    from models import Pacote
    c = _criar_cliente(db)

    dados = {
        'cliente_id': c.id,
        'nome_servico': 'Banho',
        'creditos_totais': 4,
        'preco_pacote': 100.0,
        'dia_semana_fixo': 1,
        'tipo_agendamento': 'semanal',
        'ultima_data_str': '2026-01-06',
        'vencimento_customizado': True,
        'data_vencimento_anterior': '2026-01-31'
    }
    sucesso, msg = renovar_pacote(dados)
    assert sucesso is True

    novo = Pacote.query.order_by(Pacote.id.desc()).first()
    assert novo.vencimento_customizado is True
    # dia 31 de janeiro -> fevereiro (28 dias em 2026, nao bissexto)
    assert novo.data_vencimento == date(2026, 2, 28)


def test_renovar_pacote_sem_customizacao_usa_primeiro_banho_do_ciclo(app, db):
    from services.pacote_service import renovar_pacote
    from models import Pacote
    c = _criar_cliente(db)

    dados = {
        'cliente_id': c.id,
        'nome_servico': 'Banho',
        'creditos_totais': 4,
        'preco_pacote': 100.0,
        'dia_semana_fixo': 1,
        'tipo_agendamento': 'semanal',
        'ultima_data_str': '2026-01-06',
        'vencimento_customizado': False,
        'data_vencimento_anterior': None
    }
    sucesso, msg = renovar_pacote(dados)
    assert sucesso is True

    novo = Pacote.query.order_by(Pacote.id.desc()).first()
    assert novo.vencimento_customizado is False
    assert novo.data_vencimento == date(2026, 1, 13)  # primeira terca apos a ultima data
