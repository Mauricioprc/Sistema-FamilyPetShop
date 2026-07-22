"""
Servico de previsao de recebimento.

Estima quando pendencias (pacotes e atendimentos avulsos) serao
efetivamente pagas, com base no historico de atraso de cada cliente,
em vez de assumir que todo mundo paga exatamente na data de vencimento.
"""
import statistics
from collections import defaultdict
from datetime import date, timedelta
from extensions import db
from models import Atendimento, Pacote, StatusPagamento

# Limiar de MAD (desvio absoluto mediano) acima do qual o cliente e
# considerado "imprevisivel" (atrasos muito variados, dificeis de prever).
LIMIAR_IMPREVISIVEL_DIAS = 7

# Limiar de mediana de atraso: ate esse numero de dias o cliente e
# considerado "pontual"; acima disso, "atrasa, mas e regular".
LIMIAR_PONTUAL_DIAS = 3

# Numero minimo de amostras de atraso para calcularmos um perfil
# proprio do cliente. Abaixo disso usamos o fallback geral do negocio.
AMOSTRAS_MINIMAS = 3

PERFIL_PONTUAL = 'pontual'
PERFIL_ATRASA_REGULAR = 'atrasa_regular'
PERFIL_IMPREVISIVEL = 'imprevisivel'
PERFIL_SEM_HISTORICO = 'sem_historico'


def coletar_atrasos_por_cliente() -> dict:
    """
    Retorna {cliente_id: [atraso_dias, ...]} com base em pagamentos ja
    concluidos, usando queries em lote (sem N+1).
    """
    atrasos = defaultdict(list)

    pacotes_pagos = db.session.query(
        Pacote.cliente_id, Pacote.data_vencimento, Pacote.data_pagamento
    ).filter(
        Pacote.status_pagamento == StatusPagamento.PAGO.value,
        Pacote.data_vencimento.isnot(None),
        Pacote.data_pagamento.isnot(None),
    ).all()

    for cliente_id, data_vencimento, data_pagamento in pacotes_pagos:
        atrasos[cliente_id].append((data_pagamento - data_vencimento).days)

    atendimentos_pagos = db.session.query(
        Atendimento.cliente_id, Atendimento.data, Atendimento.data_pagamento
    ).filter(
        Atendimento.status_pagamento == StatusPagamento.PAGO.value,
        Atendimento.pacote_id.is_(None),
        Atendimento.data_pagamento.isnot(None),
    ).all()

    for cliente_id, data_referencia, data_pagamento in atendimentos_pagos:
        atrasos[cliente_id].append((data_pagamento - data_referencia).days)

    return dict(atrasos)


def _classificar_perfil(mediana: float, mad: float) -> str:
    if mad > LIMIAR_IMPREVISIVEL_DIAS:
        return PERFIL_IMPREVISIVEL
    if mediana <= LIMIAR_PONTUAL_DIAS:
        return PERFIL_PONTUAL
    return PERFIL_ATRASA_REGULAR


def calcular_perfis_clientes(atrasos_por_cliente: dict) -> dict:
    """
    Retorna {cliente_id: {'perfil': str, 'atraso_estimado': float}} para
    clientes com amostras suficientes.
    """
    perfis = {}
    for cliente_id, atrasos in atrasos_por_cliente.items():
        if len(atrasos) < AMOSTRAS_MINIMAS:
            continue
        mediana = statistics.median(atrasos)
        mad = statistics.median([abs(a - mediana) for a in atrasos])
        perfis[cliente_id] = {
            'perfil': _classificar_perfil(mediana, mad),
            'atraso_estimado': mediana,
        }
    return perfis


def calcular_atraso_mediano_geral(atrasos_por_cliente: dict) -> float | None:
    """
    Mediana de todos os atrasos de todos os clientes com amostras
    suficientes, usada como fallback para clientes sem historico
    proprio. Retorna None se nao houver dado suficiente no negocio todo.
    """
    todos_atrasos = []
    for atrasos in atrasos_por_cliente.values():
        if len(atrasos) >= AMOSTRAS_MINIMAS:
            todos_atrasos.extend(atrasos)

    if not todos_atrasos:
        return None
    return statistics.median(todos_atrasos)


def _perfil_e_atraso_do_cliente(cliente_id, perfis: dict, fallback_geral):
    perfil_info = perfis.get(cliente_id)
    if perfil_info is not None:
        return perfil_info['perfil'], perfil_info['atraso_estimado']

    if fallback_geral is None:
        return PERFIL_SEM_HISTORICO, None
    return PERFIL_SEM_HISTORICO, fallback_geral


def _semaforo(data_prevista: date, hoje: date) -> str:
    dias_para_previsao = (data_prevista - hoje).days
    if dias_para_previsao < 0:
        return 'vermelho'
    if dias_para_previsao <= 3:
        return 'amarelo'
    return 'verde'


def _coletar_pendencias():
    """
    Retorna lista de dicts com dados brutos de cada pendencia em aberto
    (pacote ou atendimento avulso), independente de calculo de previsao.
    """
    pendencias = []

    pacotes = Pacote.query.options(db.joinedload(Pacote.cliente)).filter(
        Pacote.status_pagamento == StatusPagamento.PENDENTE.value,
        Pacote.data_vencimento.isnot(None),
    ).all()
    for p in pacotes:
        pendencias.append({
            'cliente_id': p.cliente_id,
            'cliente_nome': p.cliente.nome_tutor,
            'pet_nome': p.cliente.nome_pet,
            'valor': p.preco_pacote,
            'data_referencia': p.data_vencimento,
        })

    atendimentos = Atendimento.query.options(db.joinedload(Atendimento.cliente)).filter(
        Atendimento.status_pagamento == StatusPagamento.PENDENTE.value,
        Atendimento.pacote_id.is_(None),
    ).all()
    for a in atendimentos:
        pendencias.append({
            'cliente_id': a.cliente_id,
            'cliente_nome': a.cliente.nome_tutor,
            'pet_nome': a.cliente.nome_pet,
            'valor': a.preco,
            'data_referencia': a.data,
        })

    return pendencias


def _no_mes(d: date, mes: int, ano: int) -> bool:
    return d.year == ano and d.month == mes


def gerar_previsao_recebimento(mes: int, ano: int) -> dict:
    """
    Gera os dados prontos para exibicao no dashboard: total previsto,
    total pela regra antiga (vencimento nominal) e a lista de itens
    ordenada por data prevista.
    """
    hoje = date.today()

    atrasos_por_cliente = coletar_atrasos_por_cliente()
    perfis = calcular_perfis_clientes(atrasos_por_cliente)
    fallback_geral = calcular_atraso_mediano_geral(atrasos_por_cliente)

    pendencias = _coletar_pendencias()

    total_previsto = 0.0
    total_vencimento_nominal = 0.0
    itens = []

    for pend in pendencias:
        perfil, atraso = _perfil_e_atraso_do_cliente(pend['cliente_id'], perfis, fallback_geral)

        if atraso is None:
            data_prevista = pend['data_referencia']
        else:
            data_prevista = pend['data_referencia'] + timedelta(days=round(atraso))

        if _no_mes(data_prevista, mes, ano):
            total_previsto += pend['valor']

        if _no_mes(pend['data_referencia'], mes, ano):
            total_vencimento_nominal += pend['valor']

        itens.append({
            'cliente_nome': pend['cliente_nome'],
            'pet_nome': pend['pet_nome'],
            'valor': pend['valor'],
            'data_vencimento': pend['data_referencia'],
            'data_prevista': data_prevista,
            'semaforo': _semaforo(data_prevista, hoje),
            'perfil': perfil,
        })

    itens_do_mes = [i for i in itens if _no_mes(i['data_prevista'], mes, ano)]
    itens_do_mes.sort(key=lambda i: i['data_prevista'])

    return {
        'total_previsto': total_previsto,
        'total_vencimento_nominal': total_vencimento_nominal,
        'tem_dado_suficiente': fallback_geral is not None,
        'itens': itens_do_mes,
    }


def listar_vencendo_no_mes(mes: int, ano: int) -> list:
    """
    Visao crua (sem previsao): pendencias cuja data de referencia
    nominal (vencimento do pacote / data do atendimento avulso) cai no
    mes/ano informado.
    """
    pendencias = _coletar_pendencias()
    itens = [
        {
            'cliente_nome': p['cliente_nome'],
            'pet_nome': p['pet_nome'],
            'valor': p['valor'],
            'data_vencimento': p['data_referencia'],
        }
        for p in pendencias if _no_mes(p['data_referencia'], mes, ano)
    ]
    itens.sort(key=lambda i: i['data_vencimento'])
    return itens
