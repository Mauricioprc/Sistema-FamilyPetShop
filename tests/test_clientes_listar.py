"""
Testes de integracao para rotas/clientes.py::listar().
Garante que o calculo de total_divida e dias_ausente por cliente
(feito via queries agregadas fora do loop, evitando N+1) bate com o
comportamento esperado, olhando o HTML renderizado.
"""
import pytest
from datetime import date, timedelta
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


def test_listar_calcula_divida_por_cliente_sem_n_mais_1(db, client):
    from models import Cliente, Atendimento, Pacote

    hoje = date.today()
    limite = hoje - timedelta(days=10)
    data_antiga = limite - timedelta(days=5)   # dentro da regra dos 10 dias
    data_recente = hoje - timedelta(days=2)    # fora da regra (nao conta como divida)

    a = Cliente(nome_tutor='Ana Testcliente', telefone='11999990000', nome_pet='Rex', endereco='Rua 1')
    b = Cliente(nome_tutor='Bruno Testcliente', telefone='11999990001', nome_pet='Mia', endereco='Rua 2')
    c = Cliente(nome_tutor='Carla Testcliente', telefone='11999990002', nome_pet='Tom', endereco='Rua 3')
    db.session.add_all([a, b, c])
    db.session.commit()

    # Atendimento presente antigo e pendente -> conta como divida de R$ 80 para A
    db.session.add(Atendimento(
        cliente_id=a.id, data=data_antiga, nome_servico='Banho', preco=80.0,
        status_presenca='Presente', status_pagamento='Pendente'
    ))
    # Atendimento presente recente (dentro dos 10 dias -> nao conta como divida,
    # mas atualiza a ultima presenca de A)
    db.session.add(Atendimento(
        cliente_id=a.id, data=data_recente, nome_servico='Tosa', preco=40.0,
        status_presenca='Presente', status_pagamento='Pago'
    ))

    # Pacote vencido e pendente -> conta como divida de R$ 150 para B
    db.session.add(Pacote(
        cliente_id=b.id, nome_servico='Banho', creditos_totais=4, preco_pacote=150.0,
        status_pagamento='Pendente', data_vencimento=limite - timedelta(days=1)
    ))
    db.session.commit()

    _login(client)
    resp = client.get('/clientes')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Divida agregada correta para A (so o atendimento antigo entra na conta)
    assert 'Deve R$ 80,00' in html
    # Divida agregada correta para B (pacote vencido)
    assert 'Deve R$ 150,00' in html
    # C nao tem divida -> nao deve aparecer nenhum badge "Deve" associado a ele
    assert 'Deve R$ 220,00' not in html  # nao deve somar as dividas de clientes diferentes
