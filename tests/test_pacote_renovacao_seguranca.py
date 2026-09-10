"""
Testes de integracao para a rede de seguranca da renovacao de pacote:
- o pacote antigo fica marcado como 'renovado' depois de gerar o proximo ciclo,
  para nao ser oferecido de novo;
- a tela de Pacotes ganha um jeito de retomar a renovacao (preparar_renovacao)
  mesmo que a lembranca do modal pos-presenca tenha se perdido.
"""
from datetime import date, timedelta

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


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True


def _criar_pacote_com_atendimentos(db, creditos=2):
    from models import Cliente, Pacote, Atendimento, StatusPagamento

    cliente = Cliente(nome_tutor='Ana Testcliente', telefone='11999990000', nome_pet='Rex')
    db.session.add(cliente)
    db.session.commit()

    pacote = Pacote(
        cliente_id=cliente.id, nome_servico='Banho', creditos_totais=creditos,
        preco_pacote=100.0, tipo_agendamento='semanal', dia_semana_fixo=1
    )
    db.session.add(pacote)
    db.session.flush()

    hoje = date.today()
    atendimentos = []
    for i in range(creditos):
        a = Atendimento(
            data=hoje + timedelta(weeks=i), cliente_id=cliente.id, nome_servico='Banho',
            preco=0, pacote_id=pacote.id, status_pagamento=StatusPagamento.PAGO_PACOTE.value
        )
        db.session.add(a)
        atendimentos.append(a)
    db.session.commit()

    return cliente, pacote, atendimentos


def _concluir_pacote(client, atendimentos):
    for a in atendimentos:
        client.post(f'/admin/atendimento/confirmar/{a.id}',
                    headers={'X-Requested-With': 'XMLHttpRequest'})


def test_renovar_marca_pacote_anterior_como_renovado(db, client):
    from models import Pacote

    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=1)
    _login(client)
    _concluir_pacote(client, atendimentos)  # ja deixa 'pacote_para_renovar' na sessao

    resp = client.post('/admin/pacote/renovar')
    assert resp.status_code in (302, 303)

    pacote_db = Pacote.query.get(pacote.id)
    assert pacote_db.renovado is True

    # Um novo pacote deve ter sido criado para o mesmo cliente/servico
    novos = Pacote.query.filter(Pacote.id != pacote.id).all()
    assert len(novos) == 1


def test_preparar_renovacao_redireciona_para_agenda(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=1)
    _login(client)
    _concluir_pacote(client, atendimentos)

    # Simula a lembranca do modal ter se perdido
    client.get('/admin/pacote/limpar_renovacao')

    resp = client.get(f'/admin/pacote/preparar_renovacao/{pacote.id}')
    assert resp.status_code in (302, 303)
    assert '/admin/agenda' in resp.headers['Location']

    resp2 = client.get(resp.headers['Location'])
    html = resp2.get_data(as_text=True)
    assert 'Pacote Concluído!' in html
    assert 'Renovar Pacote' in html


def test_preparar_renovacao_bloqueia_pacote_ja_renovado(db, client):
    from models import Pacote

    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=1)
    _login(client)
    _concluir_pacote(client, atendimentos)
    client.post('/admin/pacote/renovar')

    resp = client.get(f'/admin/pacote/preparar_renovacao/{pacote.id}', follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'ja foi renovado' in html.lower()


def test_preparar_renovacao_bloqueia_pacote_ainda_ativo(db, client):
    _, pacote, _atendimentos = _criar_pacote_com_atendimentos(db, creditos=2)
    _login(client)
    # Nenhum atendimento confirmado -> pacote continua Ativo

    resp = client.get(f'/admin/pacote/preparar_renovacao/{pacote.id}', follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'ainda nao foi concluido' in html.lower() or 'ainda não foi concluído' in html.lower()


def test_card_pacote_mostra_botao_renovar_apenas_quando_elegivel(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=1)
    _login(client)

    # Ainda ativo: sem botao de renovar
    resp = client.get('/admin/pacotes?filtro=todos')
    html = resp.get_data(as_text=True)
    assert 'Renovar' not in html

    # Concluido e nao renovado: botao aparece
    _concluir_pacote(client, atendimentos)
    resp = client.get('/admin/pacotes?filtro=concluidos')
    html = resp.get_data(as_text=True)
    assert 'Renovar' in html
    assert 'preparar_renovacao' in html

    # Ja renovado: botao some, badge "Renovado" aparece
    client.post('/admin/pacote/renovar')
    resp = client.get('/admin/pacotes?filtro=concluidos')
    html = resp.get_data(as_text=True)
    assert 'preparar_renovacao' not in html
    assert 'Renovado' in html
