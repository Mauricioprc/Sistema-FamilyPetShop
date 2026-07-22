"""
Servicos de negocio para pacotes.
"""
import json
from datetime import datetime, date
from extensions import db
from models import Atendimento, Pacote, StatusPagamento
from utils import parse_preco, calcular_datas_pacote, calcular_datas_renovacao, proximo_vencimento_mensal
import logging

logger = logging.getLogger(__name__)


def criar_pacote(form_data: dict) -> tuple[bool, str, Pacote | None]:
    """
    Cria um novo pacote e agenda os atendimentos se necessario.
    Retorna (sucesso, mensagem, pacote).
    """
    try:
        creditos = int(form_data.get('creditos_totais', 0))
        if creditos <= 0:
            return False, 'Numero de creditos deve ser maior que zero.', None

        preco = parse_preco(form_data.get('preco_pacote', '0'))
        if preco < 0:
            return False, 'Preco nao pode ser negativo.', None

        tipo = form_data.get('tipo_agendamento')
        dia_semana_raw = form_data.get('dia_semana')
        dia_semana = int(dia_semana_raw) if tipo != 'nenhum' and dia_semana_raw else None

        pacote = Pacote(
            cliente_id=form_data['cliente_id'],
            nome_servico=form_data['nome_servico'].strip(),
            creditos_totais=creditos,
            preco_pacote=preco,
            tipo_agendamento=tipo,
            dia_semana_fixo=dia_semana
        )
        db.session.add(pacote)
        db.session.flush()

        if tipo != 'nenhum':
            datas = []
            datas_str = form_data.get('datas_agendadas')
            
            # Tenta utilizar as datas exatas que o utilizador confirmou no ecrã
            if datas_str:
                try:
                    datas_lista = json.loads(datas_str)
                    # As datas vêm no formato DD/MM/YYYY, vamos converter para um objeto date do Python
                    datas = [datetime.strptime(d, '%d/%m/%Y').date() for d in datas_lista]
                except Exception as e:
                    logger.error(f"Erro ao converter datas agendadas vindas do HTML: {e}")
            
            # Mecanismo de segurança: se as datas não vierem do front-end por algum motivo, calcula pelo modo tradicional
            if not datas:
                # O formato do input date padrão do HTML é YYYY-MM-DD
                data_inicio = datetime.strptime(form_data['data_inicio'], '%Y-%m-%d').date()
                datas = calcular_datas_pacote(data_inicio, creditos, tipo, dia_semana)

            # --- Vencimento como o 1º banho ---
            if datas:
                pacote.data_vencimento = datas[0]
            # -------------------------------------------------------------

            for d in datas:
                db.session.add(Atendimento(
                    data=d,
                    cliente_id=form_data['cliente_id'],
                    nome_servico=form_data['nome_servico'],
                    preco=0,
                    pacote_id=pacote.id,
                    status_pagamento=StatusPagamento.PAGO_PACOTE.value
                ))
        db.session.commit()
        return True, 'Pacote criado com sucesso!', pacote

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao criar pacote: {e}")
        return False, 'Erro ao criar pacote.', None


def renovar_pacote(dados: dict) -> tuple[bool, str]:
    """
    Renova um pacote concluido criando um novo com os mesmos parametros.
    Retorna (sucesso, mensagem).
    """
    try:
        ultima = date.fromisoformat(dados['ultima_data_str'])
        creditos = dados['creditos_totais']
        tipo = dados.get('tipo_agendamento')
        dia_semana = dados.get('dia_semana_fixo')

        novo_pacote = Pacote(
            cliente_id=dados['cliente_id'],
            nome_servico=dados['nome_servico'],
            creditos_totais=creditos,
            preco_pacote=dados['preco_pacote'],
            dia_semana_fixo=dia_semana,
            tipo_agendamento=tipo
        )
        db.session.add(novo_pacote)
        db.session.flush()

        datas = calcular_datas_renovacao(ultima, creditos, tipo, dia_semana)

        # Se o pacote anterior teve o vencimento customizado manualmente,
        # o novo continua na mesma regra (fixo mensal) em vez de voltar a
        # seguir a data do 1º banho do novo ciclo.
        if dados.get('vencimento_customizado') and dados.get('data_vencimento_anterior'):
            data_anterior = date.fromisoformat(dados['data_vencimento_anterior'])
            novo_pacote.data_vencimento = proximo_vencimento_mensal(data_anterior)
            novo_pacote.vencimento_customizado = True
        elif datas:
            novo_pacote.data_vencimento = datas[0]

        for d in datas:
            db.session.add(Atendimento(
                data=d,
                cliente_id=dados['cliente_id'],
                nome_servico=dados['nome_servico'],
                preco=0,
                pacote_id=novo_pacote.id,
                status_pagamento=StatusPagamento.PAGO_PACOTE.value
            ))

        db.session.commit()
        return True, 'Pacote renovado com sucesso!'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao renovar pacote: {e}")
        return False, 'Erro ao renovar pacote.'