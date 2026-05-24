import calendar
from datetime import date, datetime, timedelta
from flask_login import login_required
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from extensions import db
from models import Atendimento, Pacote, Despesa, Cliente
from utils import parse_preco

financeiro_bp = Blueprint('financeiro', __name__)


@financeiro_bp.route('/financeiro')
@login_required
def listar():
    query = request.args.get('q', '')
    vista = request.args.get('vista', 'todos')
    filtro_status = request.args.get('status', 'todos')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')
    
    hoje = date.today()
    previsao_limite = hoje + timedelta(days=7)

    # 1. CÁLCULO GLOBAL: Total Atrasado (Para o Card Vermelho)
    atrasados_avulso = db.session.query(db.func.sum(Atendimento.preco)).filter(
        Atendimento.status_pagamento == 'Pendente',
        Atendimento.status_presenca == 'Presente',
        Atendimento.data < hoje
    ).scalar() or 0
    atrasados_pacote = db.session.query(db.func.sum(Pacote.preco_pacote)).filter(
        Pacote.status_pagamento == 'Pendente',
        Pacote.data_vencimento < hoje
    ).scalar() or 0
    total_atrasado = atrasados_avulso + atrasados_pacote

    # 2. CÁLCULO FUTURO: Previsão 7 Dias APENAS AVULSOS (Para o Card Verde)
    # Filtramos onde pacote_id é None
    total_previsao_avulsos = db.session.query(db.func.sum(Atendimento.preco)).filter(
        Atendimento.status_pagamento == 'Pendente',
        Atendimento.pacote_id == None,
        Atendimento.data.between(hoje, previsao_limite)
    ).scalar() or 0

    # --- LÓGICA DE FILTRAGEM DA LISTA ---
    atendimentos_pendentes = []
    pacotes_pendentes = []

    if vista in ('todos', 'atendimentos'):
        q = Atendimento.query.filter_by(status_pagamento='Pendente')
        if filtro_status == 'vencidos':
            q = q.filter(Atendimento.data < hoje, Atendimento.status_presenca == 'Presente')
        if data_inicio:
            q = q.filter(Atendimento.data >= datetime.strptime(data_inicio, '%Y-%m-%d').date())
        if data_fim:
            q = q.filter(Atendimento.data <= datetime.strptime(data_fim, '%Y-%m-%d').date())
        if query:
            termo = f"%{query}%"
            q = q.join(Cliente).filter(or_(Cliente.nome_tutor.like(termo), Cliente.nome_pet.like(termo)))
        atendimentos_pendentes = q.order_by(Atendimento.data.asc()).all()

    if vista in ('todos', 'pacotes'):
        q = Pacote.query.filter_by(status_pagamento='Pendente')
        if filtro_status == 'vencidos':
            q = q.filter(Pacote.data_vencimento < hoje)
        if data_inicio:
            q = q.filter(Pacote.data_vencimento >= datetime.strptime(data_inicio, '%Y-%m-%d').date())
        if data_fim:
            q = q.filter(Pacote.data_vencimento <= datetime.strptime(data_fim, '%Y-%m-%d').date())
        if query:
            termo = f"%{query}%"
            q = q.join(Cliente).filter(or_(Cliente.nome_tutor.like(termo), Cliente.nome_pet.like(termo)))
        pacotes_pendentes = q.order_by(Pacote.data_vencimento.asc()).all()

    # 3. CÁLCULO DINÂMICO: Total da Lista Atual (Para o Card Azul)
    # Soma apenas o que passou pelos filtros acima
    total_exibido = sum(a.preco for a in atendimentos_pendentes) + sum(p.preco_pacote for p in pacotes_pendentes)

    return render_template('financeiro.html',
                           atendimentos=atendimentos_pendentes,
                           pacotes=pacotes_pendentes,
                           query=query,
                           vista_ativa=vista,
                           status_ativo=filtro_status,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           total_atrasado=total_atrasado,
                           total_previsao_avulsos=total_previsao_avulsos,
                           total_exibido=total_exibido,
                           hoje=hoje)


@financeiro_bp.route('/atendimento/registrar_pagamento/<int:atendimento_id>', methods=['GET', 'POST'])
@login_required
def registrar_pagamento(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    if request.method == 'POST':
        atendimento.status_pagamento = 'Pago'
        atendimento.data_pagamento = datetime.strptime(request.form['data_pagamento'], '%Y-%m-%d').date()
        atendimento.metodo_pagamento = request.form['metodo_pagamento']
        
        # Salvando as taxas da maquininha
        atendimento.taxa_maquina = float(request.form.get('taxa_maquina', 0) or 0)
        atendimento.valor_liquido = float(request.form.get('valor_liquido', atendimento.preco))
        
        db.session.commit()
        flash('Pagamento do banho avulso registrado com sucesso!', 'success')
        return redirect(url_for('financeiro.listar'))
        
    return render_template('registrar_pagamento.html', atendimento=atendimento)


@financeiro_bp.route('/pacote/registrar_pagamento/<int:pacote_id>', methods=['GET', 'POST'])
@login_required
def registrar_pagamento_pacote(pacote_id):
    pacote = db.get_or_404(Pacote, pacote_id)
    if request.method == 'POST':
        pacote.status_pagamento = 'Pago'
        pacote.data_pagamento = datetime.strptime(request.form['data_pagamento'], '%Y-%m-%d').date()
        pacote.metodo_pagamento = request.form['metodo_pagamento']
        
        # Salvando as taxas da maquininha
        pacote.taxa_maquina = float(request.form.get('taxa_maquina', 0) or 0)
        pacote.valor_liquido = float(request.form.get('valor_liquido', pacote.preco_pacote))
        
        db.session.commit()
        flash('Pagamento do pacote registrado com sucesso!', 'success')
        return redirect(url_for('financeiro.listar'))
        
    return render_template('registrar_pagamento.html', pacote=pacote)


@financeiro_bp.route('/despesas')
@login_required
def despesas():
    query = request.args.get('q', '')
    filtro_tipo = request.args.get('filtro', '')
    hoje = date.today()
    ano = request.args.get('ano', hoje.year, type=int)
    mes = request.args.get('mes', hoje.month, type=int)

    primeiro_dia = date(ano, mes, 1)
    ultimo_dia = date(ano, mes, calendar.monthrange(ano, mes)[1])

    q = Despesa.query.filter(
        Despesa.data.between(primeiro_dia, ultimo_dia)
    ).order_by(Despesa.data.desc())

    if query:
        q = q.filter(Despesa.descricao.like('%' + query + '%'))
    if filtro_tipo in ('PETSHOP', 'CASA', 'LETICIA', 'EDUARDA'):
        q = q.filter_by(tipo=filtro_tipo)

    despesas = q.all()

    return render_template('despesas.html',
                           despesas=despesas,
                           query=query,
                           filtro_ativo=filtro_tipo,
                           total_geral=sum(d.valor for d in despesas),
                           total_petshop=sum(d.valor for d in despesas if d.tipo == 'PETSHOP'),
                           total_casa=sum(d.valor for d in despesas if d.tipo == 'CASA'),
                           total_leticia=sum(d.valor for d in despesas if d.tipo == 'LETICIA'),
                           total_eduarda=sum(d.valor for d in despesas if d.tipo == 'EDUARDA'),
                           anos=range(hoje.year - 1, hoje.year + 2),
                           ano_selecionado=ano,
                           mes_selecionado=mes,
                           mes_ano_titulo=primeiro_dia.strftime('%B de %Y').capitalize())


@financeiro_bp.route('/despesas/nova', methods=['GET', 'POST'])
@login_required
def nova_despesa():
    if request.method == 'POST':
        try:
            nova = Despesa(
                tipo=request.form['tipo'],
                descricao=request.form['descricao'],
                valor=parse_preco(request.form.get('valor', '0')),
                data=datetime.strptime(request.form['data'], '%Y-%m-%d').date()
            )
            db.session.add(nova)
            db.session.commit()
            flash('Despesa adicionada com sucesso!', 'success')
        except ValueError:
            flash('Erro: Data ou valor invalido.', 'danger')
        return redirect(url_for('financeiro.despesas'))
    return render_template('nova_despesa.html')


@financeiro_bp.route('/despesa/editar/<int:despesa_id>', methods=['GET', 'POST'])
@login_required
def editar_despesa(despesa_id):
    despesa = db.get_or_404(Despesa, despesa_id)
    if request.method == 'POST':
        despesa.tipo = request.form['tipo']
        despesa.descricao = request.form['descricao']
        despesa.valor = parse_preco(request.form.get('valor', '0'))
        try:
            despesa.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
            db.session.commit()
            flash('Despesa editada com sucesso!', 'success')
        except ValueError:
            flash('Erro: Data invalida.', 'danger')
        return redirect(url_for('financeiro.despesas'))
    return render_template('editar_despesa.html', despesa=despesa)


@financeiro_bp.route('/despesa/excluir/<int:despesa_id>', methods=['POST'])
@login_required
def excluir_despesa(despesa_id):
    despesa = db.get_or_404(Despesa, despesa_id)
    db.session.delete(despesa)
    db.session.commit()
    flash('Despesa excluida com sucesso!', 'success')
    return redirect(url_for('financeiro.despesas'))
