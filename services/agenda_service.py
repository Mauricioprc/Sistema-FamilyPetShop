"""
Servicos de negocio para agendamentos e atendimentos.
Logica de negocio separada das rotas para facilitar testes e reuso.
"""
from datetime import datetime
from extensions import db
from models import Atendimento, Pacote, StatusAtendimento, StatusPagamento
from utils import consumir_credito, devolver_credito, parse_preco
import logging

logger = logging.getLogger(__name__)


def registrar_atendimento_pacote(form_data: dict) -> tuple[bool, str]:
    """
    Registra um atendimento vinculado a um pacote.
    Retorna (sucesso, mensagem).
    """
    pacote_id = form_data.get('pacote_id')
    data_str = form_data.get('data_pacote')

    if not pacote_id or not data_str:
        return False, 'Pacote e data sao obrigatorios.'

    pacote = Pacote.query.get(pacote_id)
    if not pacote:
        return False, 'Pacote nao encontrado.'
    if pacote.creditos_usados >= pacote.creditos_totais:
        return False, 'Pacote sem creditos disponiveis.'

    try:
        novo = Atendimento(
            data=datetime.strptime(data_str, '%Y-%m-%d').date(),
            nome_servico=pacote.nome_servico,
            cliente_id=pacote.cliente_id,
            preco=0,
            observacao=form_data.get('obs_pacote'),
            pacote_id=pacote.id,
            status_pagamento=StatusPagamento.PAGO_PACOTE.value
        )
        db.session.add(novo)
        db.session.commit()
        return True, 'Atendimento registrado com sucesso!'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao registrar atendimento pacote: {e}")
        return False, 'Erro ao registrar atendimento.'


def registrar_atendimento_avulso(form_data: dict) -> tuple[bool, str]:
    """
    Registra um atendimento avulso.
    Retorna (sucesso, mensagem).
    """
    cliente_id = form_data.get('cliente_id')
    data_str = form_data.get('data')
    nome_servico = form_data.get('servico')

    if not all([cliente_id, data_str, nome_servico]):
        return False, 'Campos obrigatorios incompletos.'

    # Validar servico
    if len(nome_servico.strip()) < 2:
        return False, 'Nome do servico muito curto.'

    try:
        preco = parse_preco(form_data.get('preco', '0'))
        if preco < 0:
            return False, 'Preco nao pode ser negativo.'

        novo = Atendimento(
            data=datetime.strptime(data_str, '%Y-%m-%d').date(),
            cliente_id=cliente_id,
            nome_servico=nome_servico.strip(),
            preco=preco,
            observacao=form_data.get('obs_avulso')
        )
        db.session.add(novo)
        db.session.commit()
        return True, 'Atendimento registrado com sucesso!'
    except ValueError:
        return False, 'Data ou valor invalido.'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao registrar atendimento avulso: {e}")
        return False, 'Erro ao registrar atendimento.'


def confirmar_presenca(atendimento_id: int) -> tuple[bool, str, dict | None]:
    """
    Confirma presenca de um atendimento.
    Retorna (sucesso, mensagem, dados_renovacao_se_necessario).
    """
    atendimento = Atendimento.query.get(atendimento_id)
    if not atendimento:
        return False, 'Atendimento nao encontrado.', None

    dados_renovacao = None

    if atendimento.status_presenca != StatusAtendimento.PRESENTE.value:
        atendimento.status_presenca = StatusAtendimento.PRESENTE.value

        if atendimento.pacote_id:
            pacote = Pacote.query.get(atendimento.pacote_id)
            if pacote:
                concluido = consumir_credito(pacote)
                if concluido:
                    ultimo = Atendimento.query.filter_by(
                        pacote_id=pacote.id,
                        status_presenca=StatusAtendimento.PRESENTE.value
                    ).order_by(Atendimento.data.desc()).first()

                    dados_renovacao = {
                        'cliente_id': pacote.cliente_id,
                        'nome_servico': pacote.nome_servico,
                        'creditos_totais': pacote.creditos_totais,
                        'preco_pacote': pacote.preco_pacote,
                        'dia_semana_fixo': pacote.dia_semana_fixo,
                        'tipo_agendamento': pacote.tipo_agendamento,
                        'ultima_data_str': ultimo.data.isoformat() if ultimo else None,
                        'vencimento_customizado': pacote.vencimento_customizado,
                        'data_vencimento_anterior': pacote.data_vencimento.isoformat() if pacote.data_vencimento else None
                    }

    try:
        db.session.commit()
        return True, 'Presenca confirmada!', dados_renovacao
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao confirmar presenca: {e}")
        return False, 'Erro ao confirmar presenca.', None
