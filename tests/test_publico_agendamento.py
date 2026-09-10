"""
Testes de integracao de ponta a ponta para as paginas PUBLICAS (cliente):
- / e /insta (landing + mural de avaliacoes)
- /solicitar_agendamento (wizard de agendamento online)
- /confirmacao_agendamento
- /submeter_avaliacao

Usa a TURNSTILE_SITE_KEY/SECRET_KEY de teste do Cloudflare (sempre-passa),
configuradas em config.TestingConfig, entao o token pode ser qualquer
string nao vazia.
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


def _proxima_data_util(dia_semana_evitar=6):
    """Retorna uma data futura que nao cai no dia da semana informado (6=domingo)."""
    d = date.today() + timedelta(days=3)
    while d.weekday() == dia_semana_evitar:
        d += timedelta(days=1)
    return d


def _proximo_domingo():
    d = date.today() + timedelta(days=1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d


def _dados_form_validos(data_obj):
    return {
        'cf-turnstile-response': 'token-de-teste',
        'data': data_obj.isoformat(),
        'telefone': '35999998888',
        'nome_tutor': 'Cliente Teste',
        'nome_pet': 'Rex',
        'raca_pet': 'Vira-lata',
        'tipo_pet': 'Cachorro',
        'sexo_pet': 'Macho',
        'castrado': 'Nao',
        'temperamento': 'Manso',
        'peso_pet': '15',
        'nome_servico': 'Banho & Tosa Máquina',
        'preco': '180.00',
        'adicionais': [],
        'horario_preferido': '11:00',
        'transporte': 'Táxi Dog',
        'endereco_busca': 'Rua Teste, 123',
        'observacao': 'Cuidado, late um pouco.',
    }


def test_home_e_insta_carregam(client, db):
    for url in ('/', '/insta'):
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'Family Pet Shop' in html
        assert '/solicitar_agendamento' in html


def test_pagina_solicitar_agendamento_carrega_com_turnstile(client, db):
    resp = client.get('/solicitar_agendamento')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'cf-turnstile' in html
    # Precos dos servicos principais (ver static/js/modules/pacotes.js)
    assert 'data-base-price' in html
    assert 'data-taxi-price="20.00"' in html


def test_submeter_agendamento_cria_cliente_e_atendimento(client, db):
    from models import Cliente, Atendimento, StatusAtendimento, StatusPagamento

    data_obj = _proxima_data_util()
    resp = client.post('/solicitar_agendamento', data=_dados_form_validos(data_obj),
                       follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Solicitacao enviada' in html or 'Solicitação enviada' in html or 'confirmacao' in resp.request.path

    cliente = Cliente.query.filter_by(telefone='35999998888').first()
    assert cliente is not None
    assert cliente.nome_tutor == 'Cliente Teste'
    assert cliente.nome_pet == 'Rex'
    assert cliente.peso_pet == 15.0

    atendimento = Atendimento.query.filter_by(cliente_id=cliente.id).first()
    assert atendimento is not None
    assert atendimento.data == data_obj
    assert atendimento.nome_servico == 'Banho & Tosa Máquina'
    assert atendimento.preco == 180.0
    assert atendimento.status_presenca == StatusAtendimento.SOLICITADO_ONLINE.value
    assert atendimento.status_pagamento == StatusPagamento.PENDENTE.value
    assert atendimento.transporte == 'Táxi Dog'
    assert atendimento.endereco_busca == 'Rua Teste, 123'
    assert atendimento.eh_solicitacao_online is True


def test_submeter_agendamento_cliente_existente_atualiza_cadastro(client, db):
    from models import Cliente

    data_obj = _proxima_data_util()
    dados = _dados_form_validos(data_obj)
    client.post('/solicitar_agendamento', data=dados)

    # Mesmo telefone, pet com nome diferente -> deve atualizar o cadastro
    # existente em vez de duplicar o cliente.
    dados2 = _dados_form_validos(data_obj + timedelta(days=1))
    dados2['nome_pet'] = 'Rex Atualizado'
    client.post('/solicitar_agendamento', data=dados2)

    clientes = Cliente.query.filter_by(telefone='35999998888').all()
    assert len(clientes) == 1
    assert clientes[0].nome_pet == 'Rex Atualizado'


def test_recusa_agendamento_aos_domingos(client, db):
    from models import Atendimento

    domingo = _proximo_domingo()
    resp = client.post('/solicitar_agendamento', data=_dados_form_validos(domingo),
                       follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'domingo' in html.lower()
    assert Atendimento.query.count() == 0


def test_recusa_agendamento_sem_campos_obrigatorios(client, db):
    from models import Atendimento

    data_obj = _proxima_data_util()
    dados = _dados_form_validos(data_obj)
    dados['nome_tutor'] = ''
    resp = client.post('/solicitar_agendamento', data=dados, follow_redirects=True)
    assert resp.status_code == 200
    assert Atendimento.query.count() == 0


def test_recusa_agendamento_sem_turnstile(client, db):
    from models import Atendimento

    data_obj = _proxima_data_util()
    dados = _dados_form_validos(data_obj)
    dados['cf-turnstile-response'] = ''
    resp = client.post('/solicitar_agendamento', data=dados, follow_redirects=True)
    assert resp.status_code == 200
    assert Atendimento.query.count() == 0


def test_confirmacao_agendamento_carrega(client, db):
    resp = client.get('/confirmacao_agendamento')
    assert resp.status_code == 200


def test_submeter_avaliacao_fica_pendente_de_moderacao(client, db):
    from models import Avaliacao

    resp = client.post('/submeter_avaliacao', data={
        'cf-turnstile-response': 'token-de-teste',
        'nome_cliente': 'Fulano',
        'nome_pet': 'Totó',
        'avaliacao_texto': 'Adorei o atendimento!',
        'nota': '5',
    }, follow_redirects=True)
    assert resp.status_code == 200

    avaliacao = Avaliacao.query.filter_by(nome_cliente='Fulano').first()
    assert avaliacao is not None
    assert avaliacao.aprovada is False  # so aparece no mural apos moderacao

    # E o mural publico nao deve mostrar a avaliacao ainda nao aprovada
    home_html = client.get('/').get_data(as_text=True)
    assert 'Adorei o atendimento!' not in home_html


def test_submeter_avaliacao_sem_turnstile_nao_salva(client, db):
    from models import Avaliacao

    client.post('/submeter_avaliacao', data={
        'cf-turnstile-response': '',
        'nome_cliente': 'Sem Captcha',
        'avaliacao_texto': 'Teste',
        'nota': '5',
    })
    assert Avaliacao.query.filter_by(nome_cliente='Sem Captcha').first() is None
