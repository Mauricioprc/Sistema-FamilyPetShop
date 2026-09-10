"""
Testes de integracao para o fluxo de mensagens de pacote:
- 1o banho do pacote -> pergunta se quer enviar as datas do pacote.
- Ultimo banho do pacote (concluido) -> resumo (presenca + pagamento),
  sem mais enviar "datas novas" na mensagem.
"""
import json
from datetime import date, timedelta
from urllib.parse import unquote

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


def test_primeiro_banho_pergunta_e_nao_o_ultimo(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=2)
    _login(client)

    resp = client.post(
        f'/admin/atendimento/confirmar/{atendimentos[0].id}',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    data = resp.get_json()
    assert data['success'] is True
    assert data['precisa_perguntar_primeiro_banho'] is True
    assert data['precisa_renovar'] is False


def test_ultimo_banho_conclui_pacote_sem_perguntar_primeiro(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=1)
    _login(client)

    resp = client.post(
        f'/admin/atendimento/confirmar/{atendimentos[0].id}',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    data = resp.get_json()
    # Pacote de 1 credito: 1o banho == ultimo banho -> so conclusao, sem pergunta de 1o banho
    assert data['precisa_renovar'] is True
    assert data['precisa_perguntar_primeiro_banho'] is False


def test_modal_primeiro_banho_mostra_todas_as_datas_com_status(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=2)
    _login(client)

    client.post(f'/admin/atendimento/confirmar/{atendimentos[0].id}',
                headers={'X-Requested-With': 'XMLHttpRequest'})

    resp = client.get(f'/admin/agenda?data={atendimentos[0].data.isoformat()}')
    html = resp.get_data(as_text=True)
    assert 'Primeiro Banho do Pacote' in html
    assert atendimentos[0].data.strftime('%d/%m/%Y') in html
    assert atendimentos[1].data.strftime('%d/%m/%Y') in html
    assert 'Presente' in html
    assert 'Agendado' in html


def test_whatsapp_primeiro_banho_lista_todas_as_datas(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=2)
    _login(client)

    client.post(f'/admin/atendimento/confirmar/{atendimentos[0].id}',
                headers={'X-Requested-With': 'XMLHttpRequest'})

    resp = client.get(f'/api/whatsapp/pacote_primeiro_banho/{pacote.id}')
    body = resp.get_json()
    texto = unquote(body['url'].split('text=', 1)[1])

    assert 'primeiro banho' in texto.lower()
    assert atendimentos[0].data.strftime('%d/%m/%Y') in texto
    assert atendimentos[1].data.strftime('%d/%m/%Y') in texto
    assert 'Presente' in texto   # 1o banho ja confirmado
    assert 'Agendado' in texto   # 2o banho ainda nao aconteceu
    assert 'renovado' not in texto.lower()


def test_whatsapp_pacote_concluido_mostra_resumo_e_pagamento(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=2)
    _login(client)

    client.post(f'/admin/atendimento/confirmar/{atendimentos[0].id}',
                headers={'X-Requested-With': 'XMLHttpRequest'})
    client.post(f'/admin/atendimento/confirmar/{atendimentos[1].id}',
                headers={'X-Requested-With': 'XMLHttpRequest'})

    resp = client.get(f'/api/whatsapp/pacote_concluido/{pacote.id}')
    body = resp.get_json()
    texto = unquote(body['url'].split('text=', 1)[1])

    assert 'finalizado' in texto.lower()
    assert atendimentos[0].data.strftime('%d/%m/%Y') in texto
    assert atendimentos[1].data.strftime('%d/%m/%Y') in texto
    assert texto.count('Presente') == 2
    assert 'Pendente' in texto        # status_pagamento default do Pacote
    assert 'nova' not in texto.lower()  # nao deve mais falar de "novas datas"


def test_whatsapp_pacote_concluido_mostra_falta(db, client):
    _, pacote, atendimentos = _criar_pacote_com_atendimentos(db, creditos=2)
    _login(client)

    client.post(f'/admin/atendimento/confirmar/{atendimentos[0].id}',
                headers={'X-Requested-With': 'XMLHttpRequest'})
    client.post(f'/admin/atendimento/falta/{atendimentos[1].id}',
                headers={'X-Requested-With': 'XMLHttpRequest'})

    from models import Pacote
    pacote_db = Pacote.query.get(pacote.id)
    pacote_db.status_pagamento = 'Pago'
    _db.session.commit()

    resp = client.get(f'/api/whatsapp/pacote_concluido/{pacote.id}')
    body = resp.get_json()
    texto = unquote(body['url'].split('text=', 1)[1])
    assert 'Faltou' in texto
    assert 'Pago' in texto
