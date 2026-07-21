from datetime import date, datetime, timedelta
from flask_login import login_required
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func, case, or_
from extensions import db
from models import Cliente, Atendimento, Pacote

clientes_bp = Blueprint('clientes', __name__)


def _validar_cliente(form) -> tuple[bool, str]:
    """Valida dados do formulario de cliente."""
    nome_tutor = form.get('nome_tutor', '').strip()
    telefone = form.get('telefone', '').strip()
    nome_pet = form.get('nome_pet', '').strip()

    if len(nome_tutor) < 2:
        return False, 'Nome do tutor deve ter ao menos 2 caracteres.'
    if len(nome_pet) < 1:
        return False, 'Nome do pet e obrigatorio.'
    if len(telefone) < 8:
        return False, 'Telefone invalido.'
    return True, ''


@clientes_bp.route('/clientes')
@login_required
def listar():
    query = request.args.get('q', '')
    filtro = request.args.get('filtro', '') 
    page = request.args.get('page', 1, type=int)

    hoje = date.today()
    limite_atraso = hoje - timedelta(days=10) # <-- CRIAMOS A REGRA DOS 10 DIAS
    
    # Base da query
    q = Cliente.query

    # Lógica de filtros especiais
    if filtro == 'sumidos':
        trinta_dias_atras = hoje - timedelta(days=30)
        subquery = db.session.query(Atendimento.cliente_id).group_by(Atendimento.cliente_id).having(func.max(Atendimento.data) < trinta_dias_atras)
        q = q.filter(Cliente.id.in_(subquery))
    elif filtro == 'devedores':
            # Clientes com atendimentos ou pacotes com 10+ DIAS de atraso
            q_atend = db.session.query(Atendimento.cliente_id).filter(
                Atendimento.status_pagamento == 'Pendente',
                Atendimento.status_presenca == 'Presente',
                Atendimento.data <= limite_atraso # <-- Aplicamos o limite
            )
            q_pacot = db.session.query(Pacote.cliente_id).filter(
                Pacote.status_pagamento == 'Pendente',
                Pacote.data_vencimento <= limite_atraso # <-- Aplicamos o limite
            )
            q = q.filter(Cliente.id.in_(q_atend.union(q_pacot)))

    if query:
        termo = f"%{query}%"
        q = q.filter((Cliente.nome_tutor.like(termo)) | (Cliente.nome_pet.like(termo)))

    # Cadastro incompleto: sem telefone válido ou sem endereço cadastrado
    cadastro_incompleto = case(
        (or_(
            Cliente.telefone.is_(None),
            Cliente.telefone == '',
            func.length(Cliente.telefone) < 8,
            Cliente.endereco.is_(None),
            Cliente.endereco == ''
        ), 0),
        else_=1
    )

    pagination = q.order_by(cadastro_incompleto, Cliente.nome_tutor).paginate(page=page, per_page=12, error_out=False)

    # Dados extras para os cards, calculados em lote (evita N+1 queries no loop)
    cliente_ids = [c.id for c in pagination.items]

    ultima_presenca_map = {}
    divida_atend_map = {}
    divida_pacot_map = {}

    if cliente_ids:
        ultimas_presencas = db.session.query(
            Atendimento.cliente_id,
            func.max(Atendimento.data).label('ultima_data')
        ).filter(
            Atendimento.cliente_id.in_(cliente_ids),
            Atendimento.status_presenca == 'Presente'
        ).group_by(Atendimento.cliente_id).all()
        ultima_presenca_map = {r.cliente_id: r.ultima_data for r in ultimas_presencas}

        dividas_atend = db.session.query(
            Atendimento.cliente_id,
            func.sum(Atendimento.preco).label('total')
        ).filter(
            Atendimento.cliente_id.in_(cliente_ids),
            Atendimento.status_pagamento == 'Pendente',
            Atendimento.status_presenca == 'Presente',
            Atendimento.data <= limite_atraso # <-- Aplicamos o limite
        ).group_by(Atendimento.cliente_id).all()
        divida_atend_map = {r.cliente_id: r.total or 0 for r in dividas_atend}

        dividas_pacot = db.session.query(
            Pacote.cliente_id,
            func.sum(Pacote.preco_pacote).label('total')
        ).filter(
            Pacote.cliente_id.in_(cliente_ids),
            Pacote.status_pagamento == 'Pendente',
            Pacote.data_vencimento <= limite_atraso # <-- Aplicamos o limite
        ).group_by(Pacote.cliente_id).all()
        divida_pacot_map = {r.cliente_id: r.total or 0 for r in dividas_pacot}

    for cliente in pagination.items:
        cliente.cadastro_incompleto = (
            not cliente.telefone or len(cliente.telefone) < 8 or not cliente.endereco
        )
        ultima_data = ultima_presenca_map.get(cliente.id)
        cliente.dias_ausente = (hoje - ultima_data).days if ultima_data else None
        cliente.total_divida = divida_atend_map.get(cliente.id, 0) + divida_pacot_map.get(cliente.id, 0)

    return render_template('index.html', clientes=pagination.items, pagination=pagination, query=query, filtro_ativo=filtro)

@clientes_bp.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar():
    if request.method == 'POST':
        valido, msg = _validar_cliente(request.form)
        if not valido:
            flash(msg, 'danger')
            return render_template('form_cliente.html')

        peso_str = request.form.get('peso_pet', '').strip()
        peso_convertido = float(peso_str) if peso_str else None

        novo = Cliente(
            nome_tutor=request.form['nome_tutor'].strip(),
            telefone=request.form['telefone'].strip(),
            nome_pet=request.form['nome_pet'].strip(),
            raca_pet=request.form.get('raca_pet', '').strip() or None,
            tipo_pet=request.form.get('tipo_pet', '').strip() or None,
            sexo_pet=request.form.get('sexo_pet', '').strip() or None,
            castrado=request.form.get('castrado', '').strip() or None,
            temperamento=request.form.get('temperamento', '').strip() or None,
            peso_pet=peso_convertido,
            endereco=request.form.get('endereco', '').strip() or None
        )
        db.session.add(novo)
        db.session.commit()
        flash('Cliente adicionado com sucesso!', 'success')
        return redirect(url_for('clientes.listar'))
    return render_template('form_cliente.html')


@clientes_bp.route('/cliente/editar/<int:cliente_id>', methods=['GET', 'POST'])
@login_required
def editar(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    if request.method == 'POST':
        valido, msg = _validar_cliente(request.form)
        if not valido:
            flash(msg, 'danger')
            return render_template('form_cliente.html', cliente=cliente)

        cliente.nome_tutor = request.form['nome_tutor'].strip()
        cliente.telefone = request.form['telefone'].strip()
        cliente.nome_pet = request.form['nome_pet'].strip()
        cliente.raca_pet = request.form.get('raca_pet', '').strip() or None
        peso_str = request.form.get('peso_pet', '').strip()
        cliente.peso_pet = float(peso_str) if peso_str else None
        cliente.tipo_pet = request.form.get('tipo_pet', '').strip() or None
        cliente.sexo_pet = request.form.get('sexo_pet', '').strip() or None
        cliente.castrado = request.form.get('castrado', '').strip() or None
        cliente.temperamento = request.form.get('temperamento', '').strip() or None
        cliente.endereco = request.form.get('endereco', '').strip() or None

        db.session.commit()
        flash('Cliente editado com sucesso!', 'success')
        return redirect(url_for('clientes.listar'))
    return render_template('form_cliente.html', cliente=cliente)

@clientes_bp.route('/cliente/excluir/<int:cliente_id>', methods=['POST'])
@login_required
def excluir(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    
    # Verificação de segurança: conta os registros no banco de dados
    tem_atendimento = cliente.atendimentos.count() > 0
    tem_pacote = cliente.pacotes.count() > 0
    
    if tem_atendimento or tem_pacote:
        flash(f'Erro: Não é possível excluir {cliente.nome_pet} pois existem atendimentos ou pacotes registrados.', 'danger')
        return redirect(url_for('clientes.detalhe', cliente_id=cliente_id))
    
    try:
        db.session.delete(cliente)
        db.session.commit()
        flash('Cliente removido com sucesso!', 'success')
        return redirect(url_for('clientes.listar'))
    except Exception as e:
        db.session.rollback()
        flash('Erro ao tentar excluir o cliente. Tente novamente mais tarde.', 'danger')
        return redirect(url_for('clientes.detalhe', cliente_id=cliente_id))

@clientes_bp.route('/cliente/<int:cliente_id>')
@login_required
def detalhe(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    hoje = date.today()
    limite_atraso = hoje - timedelta(days=10) # <-- CRIAMOS A REGRA DOS 10 DIAS
    
    # Cálculos de dívida e ausência para o detalhe (APENAS 10+ DIAS DE ATRASO)
    divida_atend = db.session.query(func.sum(Atendimento.preco)).filter(
        Atendimento.cliente_id == cliente_id, 
        Atendimento.status_pagamento == 'Pendente',
        Atendimento.status_presenca == 'Presente',
        Atendimento.data <= limite_atraso # <-- Aplicamos o limite
    ).scalar() or 0
    divida_pacot = db.session.query(func.sum(Pacote.preco_pacote)).filter(
        Pacote.cliente_id == cliente_id, 
        Pacote.status_pagamento == 'Pendente',
        Pacote.data_vencimento <= limite_atraso # <-- Aplicamos o limite
    ).scalar() or 0
    total_divida = divida_atend + divida_pacot
    
    # ... (o resto da função detalhe continua igual até o return) ...
    
    ultimo = Atendimento.query.filter_by(
        cliente_id=cliente_id, status_presenca='Presente'
    ).order_by(Atendimento.data.desc()).first()
    dias_ausente = (hoje - ultimo.data).days if ultimo else 0

    query = request.args.get('q', '')
    data_inicio_str = request.args.get('data_inicio', '')
    data_fim_str = request.args.get('data_fim', '')

    base_q = Atendimento.query.filter_by(cliente_id=cliente_id)

    if query:
        base_q = base_q.filter(Atendimento.nome_servico.like(f"%{query}%"))

    if data_inicio_str and data_fim_str:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            base_q = base_q.filter(Atendimento.data.between(data_inicio, data_fim))
        except ValueError:
            flash('Datas de filtro invalidas.', 'warning')

    agendados = base_q.filter_by(status_presenca='Agendado').order_by(Atendimento.data.asc()).all()
    realizados = base_q.filter_by(status_presenca='Presente').order_by(Atendimento.data.desc()).all()
    faltas = base_q.filter_by(status_presenca='Faltou').order_by(Atendimento.data.desc()).all()

    pacotes = Pacote.query.filter_by(cliente_id=cliente_id).order_by(Pacote.id.desc()).all()

    if pacotes:
        pacote_ids = [p.id for p in pacotes]
        primeiros = db.session.query(
            Atendimento.pacote_id,
            func.min(Atendimento.data).label('primeira_data')
        ).filter(
            Atendimento.pacote_id.in_(pacote_ids)
        ).group_by(Atendimento.pacote_id).all()

        datas_map = {r.pacote_id: r.primeira_data for r in primeiros}
        for p in pacotes:
            p.data_inicio = datas_map.get(p.id)

    return render_template('detalhe_cliente.html',
                           cliente=cliente,
                           atendimentos_agendados=agendados,
                           atendimentos_realizados=realizados,
                           atendimentos_faltas=faltas,
                           pacotes=pacotes,
                           query=query,
                           data_inicio=data_inicio_str,
                           data_fim=data_fim_str,
                           total_divida=total_divida,
                           dias_ausente=dias_ausente,
                           Atendimento=Atendimento,
                           hoje=hoje,
                           limite_atraso=limite_atraso)


