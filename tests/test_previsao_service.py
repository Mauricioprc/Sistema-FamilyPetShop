"""
Testes de integracao para o servico de previsao de recebimento.
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


def _criar_cliente(db, nome='Teste'):
    from models import Cliente
    c = Cliente(nome_tutor=nome, telefone='11999999999', nome_pet='Rex')
    db.session.add(c)
    db.session.commit()
    return c


def _criar_pacote_pago(db, cliente_id, data_vencimento, data_pagamento, preco=100.0):
    from models import Pacote, StatusPagamento
    p = Pacote(
        cliente_id=cliente_id, nome_servico='Banho', creditos_totais=4,
        preco_pacote=preco, status_pagamento=StatusPagamento.PAGO.value,
        data_vencimento=data_vencimento, data_pagamento=data_pagamento,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _criar_pacote_pendente(db, cliente_id, data_vencimento, preco=100.0):
    from models import Pacote, StatusPagamento
    p = Pacote(
        cliente_id=cliente_id, nome_servico='Banho', creditos_totais=4,
        preco_pacote=preco, status_pagamento=StatusPagamento.PENDENTE.value,
        data_vencimento=data_vencimento,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _criar_atendimento_avulso_pago(db, cliente_id, data, data_pagamento, preco=50.0):
    from models import Atendimento, StatusPagamento
    a = Atendimento(
        cliente_id=cliente_id, data=data, nome_servico='Banho', preco=preco,
        status_pagamento=StatusPagamento.PAGO.value, data_pagamento=data_pagamento,
    )
    db.session.add(a)
    db.session.commit()
    return a


def _criar_atendimento_pago_pacote(db, cliente_id, pacote_id, data, preco=0.0):
    from models import Atendimento, StatusPagamento
    a = Atendimento(
        cliente_id=cliente_id, data=data, nome_servico='Banho', preco=preco,
        status_pagamento=StatusPagamento.PAGO_PACOTE.value, pacote_id=pacote_id,
    )
    db.session.add(a)
    db.session.commit()
    return a


def test_cliente_pontual(app, db):
    from services.previsao_service import coletar_atrasos_por_cliente, calcular_perfis_clientes, PERFIL_PONTUAL
    c = _criar_cliente(db)
    base = date(2026, 1, 1)
    for i in range(3):
        _criar_pacote_pago(db, c.id, base + timedelta(days=i * 10), base + timedelta(days=i * 10 + 1))

    atrasos = coletar_atrasos_por_cliente()
    perfis = calcular_perfis_clientes(atrasos)
    assert perfis[c.id]['perfil'] == PERFIL_PONTUAL


def test_cliente_atrasa_regular(app, db):
    from services.previsao_service import coletar_atrasos_por_cliente, calcular_perfis_clientes, PERFIL_ATRASA_REGULAR
    c = _criar_cliente(db)
    base = date(2026, 1, 1)
    for i, atraso in enumerate([5, 6, 5]):
        _criar_pacote_pago(db, c.id, base + timedelta(days=i * 10), base + timedelta(days=i * 10 + atraso))

    atrasos = coletar_atrasos_por_cliente()
    perfis = calcular_perfis_clientes(atrasos)
    assert perfis[c.id]['perfil'] == PERFIL_ATRASA_REGULAR


def test_cliente_imprevisivel(app, db):
    from services.previsao_service import coletar_atrasos_por_cliente, calcular_perfis_clientes, PERFIL_IMPREVISIVEL
    c = _criar_cliente(db)
    base = date(2026, 1, 1)
    for i, atraso in enumerate([0, 20, 1, 30]):
        _criar_pacote_pago(db, c.id, base + timedelta(days=i * 40), base + timedelta(days=i * 40 + atraso))

    atrasos = coletar_atrasos_por_cliente()
    perfis = calcular_perfis_clientes(atrasos)
    assert perfis[c.id]['perfil'] == PERFIL_IMPREVISIVEL


def test_cliente_sem_historico_usa_fallback(app, db):
    from services.previsao_service import gerar_previsao_recebimento
    # Cliente com historico consolidado (atraso mediano ~5 dias)
    c_historico = _criar_cliente(db, 'Historico')
    base = date(2026, 1, 1)
    for i, atraso in enumerate([5, 5, 5]):
        _criar_pacote_pago(db, c_historico.id, base + timedelta(days=i * 10), base + timedelta(days=i * 10 + atraso))

    # Cliente novo sem nenhum pagamento concluido
    c_novo = _criar_cliente(db, 'Novo')
    vencimento = date(2026, 3, 1)
    _criar_pacote_pendente(db, c_novo.id, vencimento)

    resultado = gerar_previsao_recebimento(3, 2026)
    item_novo = next(i for i in resultado['itens'] if i['cliente_nome'] == 'Novo')
    assert item_novo['perfil'] == 'sem_historico'
    assert item_novo['data_prevista'] == vencimento + timedelta(days=5)


def test_pago_pacote_nao_entra_no_historico(app, db):
    from services.previsao_service import coletar_atrasos_por_cliente
    c = _criar_cliente(db)
    p = _criar_pacote_pago(db, c.id, date(2026, 1, 1), date(2026, 1, 3))
    # Atendimentos "Pago (Pacote)" sao so o registro do banho dentro do pacote,
    # nao devem contar como eventos de pagamento independentes.
    _criar_atendimento_pago_pacote(db, c.id, p.id, date(2026, 1, 5))
    _criar_atendimento_pago_pacote(db, c.id, p.id, date(2026, 1, 12))

    atrasos = coletar_atrasos_por_cliente()
    # Apenas o atraso do proprio pacote deve aparecer, nao os atendimentos do pacote.
    assert atrasos[c.id] == [2]


def test_banco_vazio_fallback_nao_quebra(app, db):
    from services.previsao_service import gerar_previsao_recebimento
    c = _criar_cliente(db)
    vencimento = date(2026, 3, 1)
    _criar_pacote_pendente(db, c.id, vencimento)

    resultado = gerar_previsao_recebimento(3, 2026)
    assert resultado['tem_dado_suficiente'] is False
    item = resultado['itens'][0]
    assert item['perfil'] == 'sem_historico'
    # Sem fallback disponivel, usamos a propria data de referencia (sem estourar erro).
    assert item['data_prevista'] == vencimento


def test_atendimento_avulso_pago_entra_no_historico(app, db):
    from services.previsao_service import coletar_atrasos_por_cliente
    c = _criar_cliente(db)
    _criar_atendimento_avulso_pago(db, c.id, date(2026, 1, 1), date(2026, 1, 4))

    atrasos = coletar_atrasos_por_cliente()
    assert atrasos[c.id] == [3]


def test_totais_previsto_e_nominal(app, db):
    from services.previsao_service import gerar_previsao_recebimento
    c = _criar_cliente(db, 'ComHistorico')
    base = date(2026, 1, 1)
    for i in range(3):
        _criar_pacote_pago(db, c.id, base + timedelta(days=i * 10), base + timedelta(days=i * 10 + 5))

    # Vencimento nominal em fevereiro, mas com atraso mediano de 5 dias a previsao cai em marco.
    _criar_pacote_pendente(db, c.id, date(2026, 2, 27), preco=200.0)

    resultado_fev = gerar_previsao_recebimento(2, 2026)
    resultado_mar = gerar_previsao_recebimento(3, 2026)

    assert resultado_fev['total_vencimento_nominal'] == 200.0
    assert resultado_mar['total_previsto'] == 200.0
