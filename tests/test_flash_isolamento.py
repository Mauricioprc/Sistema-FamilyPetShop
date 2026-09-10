"""
Garante que uma mensagem flash do site publico nunca aparece numa tela
do admin, e vice-versa, mesmo quando o navegador nao chega a carregar a
proxima pagina esperada logo em seguida (ex: aba fechada, conexao caiu
no meio do redirect). Ver app.py:_marcar_origem_flash.
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


def _proxima_data_util():
    d = date.today() + timedelta(days=3)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


def test_flash_publico_nao_vaza_pro_admin_se_navegador_nao_seguir_redirect(db, client):
    """
    Simula o pior caso: o cliente dispara uma solicitacao com erro (sem
    seguir o redirect que mostraria a mensagem na propria pagina publica)
    e, na sequencia (mesmo navegador/sessao), um admin loga e abre a
    agenda. A mensagem do cliente nao pode aparecer ali.
    """
    # Solicitacao invalida (falta telefone) -> seta uma flash publica,
    # mas NAO segue o redirect (follow_redirects=False, como se a aba
    # tivesse sido fechada nesse instante).
    dados = {
        'cf-turnstile-response': 'token-de-teste',
        'data': _proxima_data_util().isoformat(),
        'telefone': '',
        'nome_tutor': 'Cliente Teste',
        'nome_pet': 'Rex',
        'nome_servico': 'Banho',
        'preco': '40.00',
    }
    r0 = client.post('/solicitar_agendamento', data=dados)
    assert r0.status_code in (302, 303)  # confirma que a flash foi criada e nao exibida ainda

    _login(client)
    r1 = client.get('/admin/agenda')
    html = r1.get_data(as_text=True)
    assert 'obrigat' not in html.lower()  # "...sao obrigatorios." nao pode aparecer aqui


def test_flash_admin_nao_vaza_pro_site_publico(db, client):
    """Inverso: uma flash de acao do admin nao pode aparecer se, na
    sequencia, a mesma sessao/navegador visitar o site publico."""
    from models import Cliente, Atendimento

    cliente = Cliente(nome_tutor='Ana', telefone='35999990000', nome_pet='Rex')
    db.session.add(cliente)
    db.session.commit()
    atendimento = Atendimento(
        data=date.today(), cliente_id=cliente.id, nome_servico='Banho', preco=40.0
    )
    db.session.add(atendimento)
    db.session.commit()

    _login(client)
    # Acao administrativa que gera flash (ex: exclusao de atendimento)
    r0 = client.post(f'/admin/atendimento/excluir/{atendimento.id}')
    assert r0.status_code in (302, 303)

    r1 = client.get('/insta')
    html = r1.get_data(as_text=True)
    assert 'excluido com sucesso' not in html.lower()


def test_flash_publico_normal_continua_aparecendo_na_propria_pagina(db, client):
    """Garantia de que a protecao nao quebrou o caso normal: a mensagem
    de erro do site publico continua aparecendo pro proprio cliente."""
    dados = {
        'cf-turnstile-response': 'token-de-teste',
        'data': _proxima_data_util().isoformat(),
        'telefone': '',
        'nome_tutor': 'Cliente Teste',
        'nome_pet': 'Rex',
        'nome_servico': 'Banho',
        'preco': '40.00',
    }
    r = client.post('/solicitar_agendamento', data=dados, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert 'obrigat' in html.lower()


def test_flash_login_invalido_continua_aparecendo_na_tela_de_login(db, client):
    """A pagina de login roda sem usuario autenticado, mas nao e' uma
    rota publica de cliente — suas proprias mensagens (login invalido)
    nao podem ser escondidas pela mesma protecao."""
    r = client.post('/admin/login', data={'username': 'errado', 'password': 'errado'},
                    follow_redirects=True)
    html = r.get_data(as_text=True)
    assert 'invalid' in html.lower() or 'inválid' in html.lower() or 'incorret' in html.lower()
