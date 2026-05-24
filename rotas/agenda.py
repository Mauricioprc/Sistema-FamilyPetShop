from datetime import date, datetime, timedelta
from flask_login import login_required
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from extensions import db
from models import Atendimento, Pacote, Cliente, StatusAtendimento, StatusPagamento
from rotas import clientes
from services.agenda_service import (
    registrar_atendimento_pacote,
    registrar_atendimento_avulso,
    confirmar_presenca
)
from utils import devolver_credito, parse_preco

agenda_bp = Blueprint('agenda', __name__)


@agenda_bp.route('/agenda')
@login_required
def agenda_do_dia():
    data_str = request.args.get('data', date.today().isoformat())
    try:
        data_sel = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        data_sel = date.today()

    atendimentos = Atendimento.query.filter(
        Atendimento.data == data_sel,
        Atendimento.status_presenca == StatusAtendimento.AGENDADO.value
    ).order_by(Atendimento.id).all()

    return render_template('agenda.html',
                           atendimentos=atendimentos,
                           data_selecionada=data_sel,
                           hoje=date.today(),
                           dia_anterior=data_sel - timedelta(days=1),
                           proximo_dia=data_sel + timedelta(days=1))


@agenda_bp.route('/atendimentos')
@login_required
def historico():
    hoje = date.today()
    data_str = request.args.get('data', hoje.isoformat())
    try:
        data_sel = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        data_sel = hoje

    atendimentos = Atendimento.query.filter(
        Atendimento.data == data_sel,
        Atendimento.status_presenca.in_([
            StatusAtendimento.PRESENTE.value,
            StatusAtendimento.FALTOU.value
        ])
    ).order_by(Atendimento.id).all()

    return render_template('atendimentos.html',
                           atendimentos=atendimentos,
                           data_selecionada=data_sel,
                           dia_anterior=data_sel - timedelta(days=1),
                           proximo_dia=data_sel + timedelta(days=1))


@agenda_bp.route('/atendimentos/novo', methods=['GET', 'POST'])
@login_required
def novo():

    hoje = date.today()
    limite_atraso = hoje - timedelta(days=10)

    if request.method == 'POST':
        tipo = request.form.get('tipo_atendimento')
        if tipo == 'pacote':
            sucesso, msg = registrar_atendimento_pacote(request.form)
        else:
            sucesso, msg = registrar_atendimento_avulso(request.form)

        flash(msg, 'success' if sucesso else 'danger')
        if sucesso:
            return redirect(url_for('agenda.agenda_do_dia'))

    # 1. Busca no banco de dados
    clientes = Cliente.query.order_by(Cliente.nome_tutor).all()
    pacotes_ativos = Pacote.query.filter(
        Pacote.status == 'Ativo',
        Pacote.creditos_usados < Pacote.creditos_totais
    ).all()
    
    # 2. Dicionário de informações para o Javascript
    pacotes_info = {p.id: {'usados': p.creditos_usados, 'totais': p.creditos_totais}
                    for p in pacotes_ativos}
    
    for c in clientes:
        # Verifica pendência nos pacotes filtrando pela data_vencimento
        divida_pacotes = sum(
            p.preco_pacote for p in c.pacotes.filter_by(status_pagamento='Pendente')
            if p.data_vencimento and p.data_vencimento <= limite_atraso
        )
        # Verifica pendência nos atendimentos avulsos presentes filtrando pela data
        divida_atendimentos = sum(
            a.preco for a in c.atendimentos.filter_by(status_pagamento='Pendente', status_presenca='Presente')
            if a.data and a.data <= limite_atraso
        )
        c.total_divida = divida_pacotes + divida_atendimentos
        

    # 4. Repasse da dívida para os pacotes 
    for p in pacotes_ativos:
        p.cliente.total_divida = p.cliente.total_divida

    # 5. Renderização 
    return render_template('novo_atendimento.html',
                           clientes=clientes,
                           pacotes=pacotes_ativos,
                           pacotes_info=pacotes_info)

@agenda_bp.route('/atendimento/editar/<int:atendimento_id>', methods=['POST'])
@login_required
def editar(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    
    # Usamos .get() com valores padrão para evitar o Erro 400
    status_novo = request.form.get('status_presenca', atendimento.status_presenca)
    data_str = request.form.get('data')
    
    if data_str:
        try:
            atendimento.data = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Data inválida.', 'danger')

    atendimento.status_presenca = status_novo
    atendimento.observacao = request.form.get('observacao', atendimento.observacao)

    # Só altera nome e preço se não for pacote
    if not atendimento.pacote_id:
        atendimento.nome_servico = request.form.get('nome_servico', atendimento.nome_servico)
        preco_str = request.form.get('preco', '0')
        atendimento.preco = parse_preco(preco_str)

    db.session.commit()
    flash('Atendimento atualizado!', 'success')
    return redirect(request.referrer or url_for('clientes.detalhe', cliente_id=atendimento.cliente_id))


@agenda_bp.route('/atendimento/excluir/<int:atendimento_id>', methods=['POST'])
@login_required
def excluir(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    cliente_id = atendimento.cliente_id

    if atendimento.pacote_id and atendimento.status_presenca == StatusAtendimento.PRESENTE.value:
        pacote = Pacote.query.get(atendimento.pacote_id)
        if pacote:
            devolver_credito(pacote)

    db.session.delete(atendimento)
    db.session.commit()
    flash('Atendimento excluido com sucesso!', 'success')
    return redirect(url_for('clientes.detalhe', cliente_id=cliente_id))


@agenda_bp.route('/atendimento/confirmar/<int:atendimento_id>', methods=['POST'])
@login_required
def confirmar_presenca_route(atendimento_id):
    session.pop('pacote_para_renovar', None)
    sucesso, msg, dados_renovacao = confirmar_presenca(atendimento_id)

    # Buscamos o atendimento para extrair os dados do cliente
    atendimento = Atendimento.query.get(atendimento_id)
    
    if dados_renovacao and atendimento:
        # Injetamos o telefone e nomes para usar no botão do WhatsApp
        dados_renovacao['telefone_cliente'] = atendimento.cliente.telefone
        dados_renovacao['nome_tutor'] = atendimento.cliente.nome_tutor
        dados_renovacao['nome_pet'] = atendimento.cliente.nome_pet
        session['pacote_para_renovar'] = dados_renovacao

    data_str = atendimento.data.isoformat() if atendimento else date.today().isoformat()

    flash(msg, 'success' if sucesso else 'danger')
    return redirect(url_for('agenda.agenda_do_dia', data=data_str))


@agenda_bp.route('/atendimento/falta/<int:atendimento_id>', methods=['POST'])
@login_required
def marcar_falta(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    atendimento.status_presenca = StatusAtendimento.FALTOU.value

    if atendimento.pacote_id:
        pacote = Pacote.query.get(atendimento.pacote_id)
        if not pacote:
            flash('Pacote nao encontrado.', 'danger')
            return redirect(url_for('agenda.agenda_do_dia',
                                    data=atendimento.data.isoformat()))

        pulo = timedelta(weeks=1) if pacote.tipo_agendamento == 'semanal' else timedelta(weeks=2)
        nova_data = atendimento.data + pulo

        if pacote.dia_semana_fixo is not None:
            while nova_data.weekday() != pacote.dia_semana_fixo:
                nova_data += timedelta(days=1)

        while Atendimento.query.filter_by(
            pacote_id=pacote.id,
            data=nova_data,
            status_presenca=StatusAtendimento.AGENDADO.value
        ).first():
            nova_data += pulo
            if pacote.dia_semana_fixo is not None:
                while nova_data.weekday() != pacote.dia_semana_fixo:
                    nova_data += timedelta(days=1)

        db.session.add(Atendimento(
            data=nova_data,
            nome_servico=atendimento.nome_servico,
            preco=0,
            observacao=atendimento.observacao,
            status_pagamento=StatusPagamento.PAGO_PACOTE.value,
            cliente_id=atendimento.cliente_id,
            pacote_id=atendimento.pacote_id,
            status_presenca=StatusAtendimento.AGENDADO.value
        ))
        flash(f'Falta registrada. Reagendado para {nova_data.strftime("%d/%m/%Y")}.', 'warning')
    else:
        atendimento.status_pagamento = StatusPagamento.CANCELADO.value
        flash('Falta registrada. Atendimento avulso cancelado.', 'danger')

    db.session.commit()
    return redirect(url_for('agenda.agenda_do_dia', data=atendimento.data.isoformat()))


@agenda_bp.route('/atendimento/editar_data/<int:atendimento_id>', methods=['POST'])
@login_required
def editar_data(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    data_agenda_original = request.form.get('data_agenda_original')
    nova_data_str = request.form.get('nova_data')

    if nova_data_str:
        try:
            atendimento.data = datetime.strptime(nova_data_str, '%Y-%m-%d').date()
            db.session.commit()
            flash(f'Atendimento reagendado para {atendimento.data.strftime("%d/%m/%Y")}.', 'success')
        except ValueError:
            flash('Erro: Nova data invalida.', 'danger')

    return redirect(url_for('agenda.agenda_do_dia', data=data_agenda_original))
