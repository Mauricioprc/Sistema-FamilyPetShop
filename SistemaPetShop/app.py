
from flask_migrate import Migrate
import locale
import calendar
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func, case
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify


# Tenta configurar o locale para Português do Brasil para formatar datas
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        print("Atenção: Locale 'pt_BR' não encontrado. O mês pode continuar em inglês.")

# --- Configuração do App e Banco de Dados ---
app = Flask(__name__)
app.secret_key = 'coloque-uma-frase-secreta-bem-longa-aqui'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance','petshop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- NOVO FILTRO DE MOEDA ---
def format_currency(value):
    """Formata um valor float para a moeda local (com separador de milhares e vírgula decimal)."""
    if value is None:
        return "0,00"
    # Usa a formatação de locale para garantir separador de milhares e decimal corretos (pt_BR)
    return locale.format_string("%.2f", value, grouping=True)

# Registra o filtro no Jinja2
app.jinja_env.filters['currency'] = format_currency
# --- FIM DO NOVO FILTRO ---

# --- Modelos do Banco de Dados (Versão Revisada) ---

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_tutor = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    nome_pet = db.Column(db.String(100), nullable=False)
    raca_pet = db.Column(db.String(50))
    def __repr__(self): return f'<Cliente {self.nome_tutor}>'

class Pacote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_servico = db.Column(db.String(100), nullable=False)
    creditos_totais = db.Column(db.Integer, nullable=False)
    creditos_usados = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='Ativo')
    preco_pacote = db.Column(db.Float, nullable=False)
    status_pagamento = db.Column(db.String(50), default='Pendente')
    data_pagamento = db.Column(db.Date, nullable=True)
    metodo_pagamento = db.Column(db.String(50), nullable=True)
    dia_semana_fixo = db.Column(db.Integer, nullable=True)
    tipo_agendamento = db.Column(db.String(20), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    cliente = db.relationship('Cliente', backref=db.backref('pacotes', lazy=True))
    atendimentos = db.relationship('Atendimento', backref='pacote', lazy='dynamic')

    def __repr__(self): return f'<Pacote {self.id}>'

class Atendimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    nome_servico = db.Column(db.String(100), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    status_pagamento = db.Column(db.String(50), default='Pendente')
    data_pagamento = db.Column(db.Date, nullable=True)
    metodo_pagamento = db.Column(db.String(50), nullable=True)
    status_presenca = db.Column(db.String(50), default='Agendado')
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    pacote_id = db.Column(db.Integer, db.ForeignKey('pacote.id'), nullable=True)
    cliente = db.relationship('Cliente', backref=db.backref('atendimentos', lazy=True))
    def __repr__(self): return f'<Atendimento {self.id}>'

class Despesa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    def __repr__(self): return f'<Despesa {self.descricao}>'


# --- Rotas (organizadas por módulo) ---

# Rota Principal (Dashboard)
@app.route('/dashboard')
def dashboard():
    hoje = date.today()

    # --- NOVOS INDICADORES EM TEMPO REAL ---
    atendimentos_hoje = Atendimento.query.filter(
        Atendimento.data == hoje,
        Atendimento.status_presenca == 'Agendado'
    ).order_by(Atendimento.id).all()
    
    num_atendimentos_hoje = len(atendimentos_hoje)

    # Nota: A lógica de faturamento do dia é complexa, vou simplificá-la para buscar pagamentos registrados HOJE
    faturamento_atendimentos_hoje = db.session.query(func.sum(Atendimento.preco)).filter(
        Atendimento.data_pagamento == hoje,
        Atendimento.pacote_id == None # Apenas avulsos
    ).scalar() or 0.0

    faturamento_pacotes_hoje = db.session.query(func.sum(Pacote.preco_pacote)).filter(
        Pacote.data_pagamento == hoje
    ).scalar() or 0.0
    
    faturamento_hoje = faturamento_atendimentos_hoje + faturamento_pacotes_hoje


    total_a_receber_avulsos = db.session.query(func.sum(Atendimento.preco)).filter(Atendimento.status_pagamento == 'Pendente').scalar() or 0.0
    total_a_receber_pacotes = db.session.query(func.sum(Pacote.preco_pacote)).filter(Pacote.status_pagamento == 'Pendente').scalar() or 0.0
    total_a_receber_geral = total_a_receber_avulsos + total_a_receber_pacotes

    # --- LÓGICA DO FILTRO DE DATA (PARA O RELATÓRIO MENSAL) ---
    ano_selecionado = request.args.get('ano', hoje.year, type=int)
    mes_selecionado = request.args.get('mes', hoje.month, type=int)
    primeiro_dia = date(ano_selecionado, mes_selecionado, 1)
    ultimo_dia_num = calendar.monthrange(ano_selecionado, mes_selecionado)[1]
    ultimo_dia = date(ano_selecionado, mes_selecionado, ultimo_dia_num)
    
    # --- CÁLCULOS PARA O RELATÓRIO MENSAL ---
    receita_atendimentos_mes = db.session.query(func.sum(Atendimento.preco)).filter(
        Atendimento.pacote_id == None,
        Atendimento.status_pagamento == 'Pago',
        Atendimento.data_pagamento.between(primeiro_dia, ultimo_dia)
    ).scalar() or 0.0

    receita_pacotes_mes = db.session.query(func.sum(Pacote.preco_pacote)).filter(
        Pacote.status_pagamento == 'Pago',
        Pacote.data_pagamento.between(primeiro_dia, ultimo_dia)
    ).scalar() or 0.0
    
    total_receitas_mes = receita_atendimentos_mes + receita_pacotes_mes

    total_despesas_petshop_mes = db.session.query(func.sum(Despesa.valor)).filter(
    Despesa.tipo.in_(['PETSHOP', 'LETICIA', 'EDUARDA', 'CASA' ]), 
    Despesa.data.between(primeiro_dia, ultimo_dia)
    ).scalar() or 0.0
    
    lucro_mes = total_receitas_mes - total_despesas_petshop_mes
    
    anos_disponiveis = range(hoje.year - 1, hoje.year + 2)
    mes_ano_titulo = primeiro_dia.strftime('%B de %Y').capitalize()

    return render_template('dashboard.html',
                           # Dados para o painel em tempo real
                           num_atendimentos_hoje=num_atendimentos_hoje,
                           atendimentos_hoje=atendimentos_hoje,
                           faturamento_hoje=faturamento_hoje,
                           total_a_receber=total_a_receber_geral,
                           # Dados para o relatório mensal
                           total_receitas_mes=total_receitas_mes,
                           total_despesas_petshop_mes=total_despesas_petshop_mes,
                           lucro_mes=lucro_mes,
                           mes_ano_titulo=mes_ano_titulo,
                           anos=anos_disponiveis,
                           ano_selecionado=ano_selecionado,
                           mes_selecionado=mes_selecionado)

# Rotas de Clientes
@app.route('/clientes')
def listar_clientes():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    clientes_query = Cliente.query
    if query:
        search_term = f"%{query}%"
        clientes_query = clientes_query.filter(or_(Cliente.nome_tutor.like(search_term), Cliente.nome_pet.like(search_term)))
    pagination = clientes_query.order_by(Cliente.nome_tutor).paginate(page=page, per_page=10, error_out=False)
    clientes_nesta_pagina = pagination.items
    return render_template('index.html', clientes=clientes_nesta_pagina, pagination=pagination, query=query)

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_cliente():
    if request.method == 'POST':
        novo_cliente = Cliente(nome_tutor=request.form['nome_tutor'], telefone=request.form['telefone'], nome_pet=request.form['nome_pet'], raca_pet=request.form['raca_pet'])
        db.session.add(novo_cliente)
        db.session.commit()
        flash('Cliente adicionado com sucesso!', 'success')
        return redirect(url_for('listar_clientes'))
    
    return render_template('adicionar.html')

@app.route('/cliente/editar/<int:cliente_id>', methods=['GET', 'POST'])
def editar_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    if request.method == 'POST':
        cliente.nome_tutor = request.form['nome_tutor']
        cliente.telefone = request.form['telefone']
        cliente.nome_pet = request.form['nome_pet']
        cliente.raca_pet = request.form['raca_pet']
        db.session.commit()
        flash('Cliente editado com sucesso!', 'success')
        return redirect(url_for('listar_clientes'))
    return render_template('editar_cliente.html', cliente=cliente)

@app.route('/cliente/excluir/<int:cliente_id>', methods=['POST'])
def excluir_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)

    # 1. Encontra e apaga todos os atendimentos do cliente
    atendimentos_para_apagar = Atendimento.query.filter_by(cliente_id=cliente.id).all()
    for atendimento in atendimentos_para_apagar:
        db.session.delete(atendimento)
    
    # 2. Encontra e apaga todos os pacotes do cliente
    pacotes_para_apagar = Pacote.query.filter_by(cliente_id=cliente.id).all()
    for pacote in pacotes_para_apagar:
        db.session.delete(pacote)
        
    # 3. Agora, apaga o cliente
    db.session.delete(cliente)
    
    db.session.commit()
    flash('Cliente excluido com sucesso!', 'success')

    
    return redirect(url_for('listar_clientes'))

@app.route('/cliente/<int:cliente_id>')
def detalhe_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    
    query = request.args.get('q', '')
    data_inicio_str = request.args.get('data_inicio', '')
    data_fim_str = request.args.get('data_fim', '')

    atendimentos_query_base = Atendimento.query.filter_by(cliente_id=cliente_id)
    
    if query:
        search_term = f"%{query}%"
        atendimentos_query_base = atendimentos_query_base.filter(Atendimento.nome_servico.like(search_term))
    if data_inicio_str and data_fim_str:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        atendimentos_query_base = atendimentos_query_base.filter(Atendimento.data.between(data_inicio, data_fim))

    atendimentos_agendados = atendimentos_query_base.filter_by(status_presenca='Agendado').order_by(Atendimento.data.asc()).all()
    atendimentos_realizados = atendimentos_query_base.filter_by(status_presenca='Presente').order_by(Atendimento.data.desc()).all()
    atendimentos_faltas = atendimentos_query_base.filter_by(status_presenca='Faltou').order_by(Atendimento.data.desc()).all()

    pacotes_cliente = Pacote.query.filter_by(cliente_id=cliente_id).order_by(Pacote.id.desc()).all()
    
    for pacote in pacotes_cliente:
        primeiro_atendimento = Atendimento.query.filter_by(pacote_id=pacote.id).order_by(Atendimento.data.asc()).first()
        pacote.data_inicio = primeiro_atendimento.data if primeiro_atendimento else None
    
    return render_template('detalhe_cliente.html', 
                           cliente=cliente, 
                           atendimentos_agendados=atendimentos_agendados,
                           atendimentos_realizados=atendimentos_realizados,
                           atendimentos_faltas=atendimentos_faltas,
                           pacotes=pacotes_cliente,
                           query=query,
                           data_inicio=data_inicio_str,
                           data_fim=data_fim_str, 
                           Atendimento=Atendimento)

# 3. Rota para a página pagamentos
@app.route('/financeiro')
def financeiro():
    query = request.args.get('q', '')
    vista = request.args.get('vista', 'todos')

    atendimentos_pendentes = []
    pacotes_pendentes = []
    
    # --- NOVAS VARIÁVEIS PARA OS TOTAIS ---
    total_avulsos = 0.0
    total_pacotes = 0.0

    if vista in ['todos', 'atendimentos']:
        query_atendimentos = Atendimento.query.filter_by(status_pagamento='Pendente')
        if query:
            search_term = f"%{query}%"
            query_atendimentos = query_atendimentos.join(Cliente).filter(or_(Cliente.nome_tutor.like(search_term), Cliente.nome_pet.like(search_term)))
        atendimentos_pendentes = query_atendimentos.order_by(Atendimento.data.asc()).all()
        # Calcula o total dos atendimentos encontrados
        total_avulsos = sum(atendimento.preco for atendimento in atendimentos_pendentes)

    if vista in ['todos', 'pacotes']:
        query_pacotes = Pacote.query.filter_by(status_pagamento='Pendente')
        if query:
            search_term = f"%{query}%"
            query_pacotes = query_pacotes.join(Cliente).filter(or_(Cliente.nome_tutor.like(search_term), Cliente.nome_pet.like(search_term)))
        
        pacotes_pendentes = query_pacotes.order_by(Pacote.id.asc()).all()
        # Calcula o total dos pacotes encontrados
        total_pacotes = sum(pacote.preco_pacote for pacote in pacotes_pendentes)

        for pacote in pacotes_pendentes:
            primeiro_atendimento = Atendimento.query.filter_by(pacote_id=pacote.id).order_by(Atendimento.data.asc()).first()
            pacote.data_inicio = primeiro_atendimento.data if primeiro_atendimento else None

    total_geral = total_avulsos + total_pacotes

    return render_template('financeiro.html', 
                           atendimentos=atendimentos_pendentes, 
                           pacotes=pacotes_pendentes, 
                           query=query, 
                           vista_ativa=vista,
                           total_avulsos=total_avulsos,
                           total_pacotes=total_pacotes,
                           total_geral=total_geral)


# Rota para registrar o pagamento de um PACOTE
@app.route('/pacote/registrar_pagamento/<int:pacote_id>', methods=['GET', 'POST'])
def registrar_pagamento_pacote(pacote_id):
    pacote = Pacote.query.get_or_404(pacote_id)
    if request.method == 'POST':
        pacote.status_pagamento = 'Pago'
        data_str = request.form['data_pagamento']
        pacote.data_pagamento = datetime.strptime(data_str, '%Y-%m-%d').date()
        pacote.metodo_pagamento = request.form['metodo_pagamento']
        db.session.commit()
        flash('Pagamento de pacote registrado com sucesso!', 'success')
        return redirect(url_for('financeiro'))
    return render_template('registrar_pagamento_pacote.html', pacote=pacote)

# Rota para registrar o pagamento de um ATENDIMENTO AVULSO
@app.route('/atendimento/registrar_pagamento/<int:atendimento_id>', methods=['GET', 'POST'])
def registrar_pagamento(atendimento_id):
    atendimento = Atendimento.query.get_or_404(atendimento_id)
    if request.method == 'POST':
        atendimento.status_pagamento = 'Pago'
        data_str = request.form['data_pagamento']
        atendimento.data_pagamento = datetime.strptime(data_str, '%Y-%m-%d').date()
        atendimento.metodo_pagamento = request.form['metodo_pagamento']
        db.session.commit()
        flash('Pagamento de atendimento registrado com sucesso!', 'success')
        return redirect(url_for('financeiro'))
    return render_template('registrar_pagamento.html', atendimento=atendimento)

# 3. Rota para a página inicial e para listar os clientes
@app.route('/')
def index():
    return redirect(url_for('agenda_do_dia'))

# Rota para a página de atendimentos (Histórico de Concluídos)
@app.route('/atendimentos')
def listar_atendimentos():
    # Pega a data da URL. Se não vier, usa a data de hoje.
    hoje = date.today()
    data_selecionada_str = request.args.get('data', hoje.isoformat())
    try:
        data_selecionada = datetime.strptime(data_selecionada_str, '%Y-%m-%d').date()
    except ValueError:
        data_selecionada = hoje

    # Busca os atendimentos para a data selecionada que foram concluídos ('Presente' ou 'Faltou')
    atendimentos_do_dia = Atendimento.query.filter(
        Atendimento.data == data_selecionada,
        Atendimento.status_presenca.in_(['Presente', 'Faltou'])
    ).order_by(Atendimento.id).all()
    
    # Calcula as datas para os botões de navegação
    dia_anterior = data_selecionada - timedelta(days=1)
    proximo_dia = data_selecionada + timedelta(days=1)
    
    return render_template('atendimentos.html', 
                           atendimentos=atendimentos_do_dia, 
                           data_selecionada=data_selecionada,
                           dia_anterior=dia_anterior,
                           proximo_dia=proximo_dia)

# Rota para registrar novo atendimento
@app.route('/atendimentos/novo', methods=['GET', 'POST'])
def novo_atendimento():
    if request.method == 'POST':
        tipo_atendimento = request.form.get('tipo_atendimento')

        if tipo_atendimento == 'pacote':
            pacote_id = request.form.get('pacote_id')
            data_str = request.form.get('data_pacote')
            observacao = request.form.get('obs_pacote')
            
            if pacote_id and data_str:
                pacote = Pacote.query.get(pacote_id)
                data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()

                if pacote and pacote.creditos_usados < pacote.creditos_totais:
                    novo = Atendimento(
                        data=data_obj,
                        nome_servico=pacote.nome_servico, 
                        cliente_id=pacote.cliente_id,
                        preco=0, # Pacote tem preço 0 para atendimentos
                        observacao=observacao,
                        pacote_id=pacote.id,
                        status_pagamento='Pago (Pacote)'
                    )
                    db.session.add(novo)
                    db.session.commit()
                else:
                    flash('Erro: Pacote inválido ou sem créditos.', 'danger')

        else: # Lógica para atendimento avulso
            cliente_id = request.form.get('cliente_id')
            data_str = request.form.get('data')
            nome_servico = request.form.get('servico')
            
            # Limpeza robusta do campo de preço
            preco_str = request.form.get('preco', '0').replace('R$', '').replace('.', '').replace(',', '.').strip()
            preco = float(preco_str) if preco_str else 0.0
            
            observacao = request.form.get('obs_avulso')
            
            if cliente_id and data_str and nome_servico:
                try:
                    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
                    novo = Atendimento(
                        data=data_obj, 
                        cliente_id=cliente_id, 
                        nome_servico=nome_servico,
                        preco=preco,
                        observacao=observacao
                    )
                    db.session.add(novo)
                    db.session.commit()
                except ValueError:
                    flash('Erro: Data ou valor inválido.', 'danger')
                    return redirect(url_for('novo_atendimento'))
            else:
                flash('Erro: Campos obrigatórios incompletos.', 'danger')
        
        flash('Novo atendimento registrado com sucesso!', 'success')
        return redirect(url_for('agenda_do_dia'))
    
    # --- LÓGICA DO GET ATUALIZADA ---
    clientes = Cliente.query.all()
    pacotes_ativos = Pacote.query.filter(Pacote.status == 'Ativo', Pacote.creditos_usados < Pacote.creditos_totais).all()
    
    # Cria um dicionário com os detalhes dos pacotes para o JavaScript
    pacotes_info = {p.id: {'usados': p.creditos_usados, 'totais': p.creditos_totais} for p in pacotes_ativos}

    return render_template('novo_atendimento.html', 
                           clientes=clientes, 
                           pacotes=pacotes_ativos,
                           pacotes_info=pacotes_info) # <-- Nova variável enviada

# Rota para editar um atendimento (GET para mostrar, POST para salvar)
@app.route('/atendimento/editar/<int:atendimento_id>', methods=['GET', 'POST'])
def editar_atendimento(atendimento_id):
    atendimento = Atendimento.query.get_or_404(atendimento_id)

    if request.method == 'POST':
        # --- LÓGICA DE GERENCIAMENTO DE CRÉDITOS ---
        status_antigo = atendimento.status_presenca
        status_novo = request.form['status_presenca']

        if atendimento.pacote_id:
            pacote = Pacote.query.get(atendimento.pacote_id)
            if pacote:
                # Caso 1: Estava 'Presente' e agora NÃO ESTÁ MAIS (devolve o crédito)
                if status_antigo == 'Presente' and status_novo != 'Presente':
                    if pacote.creditos_usados > 0:
                        pacote.creditos_usados -= 1
                    if pacote.status == 'Concluído': # Se estava concluído, volta a ser ativo
                        pacote.status = 'Ativo'
                
                # Caso 2: NÃO estava 'Presente' e agora ESTÁ (consome o crédito)
                elif status_antigo != 'Presente' and status_novo == 'Presente':
                    if pacote.creditos_usados < pacote.creditos_totais:
                        pacote.creditos_usados += 1
                    if pacote.creditos_usados >= pacote.creditos_totais: # Se usou o último, conclui
                        pacote.status = 'Concluído'

        # --- FIM DA LÓGICA DE CRÉDITOS ---

        # Pega os outros dados do formulário e atualiza
        try:
            atendimento.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
        except ValueError:
            flash('Erro: Data inválida.', 'danger')
            return redirect(url_for('detalhe_cliente', cliente_id=atendimento.cliente_id))

        atendimento.status_presenca = status_novo
        atendimento.observacao = request.form['observacao']

        # Só permite alterar serviço e preço se não for de pacote
        if not atendimento.pacote_id:
            atendimento.nome_servico = request.form['nome_servico']
            
            # Limpeza robusta do campo de preço
            preco_str = request.form.get('preco', '0').replace('R$', '').replace('.', '').replace(',', '.').strip()
            atendimento.preco = float(preco_str) if preco_str else 0.0
        
        db.session.commit()
        flash('Atendimento editado com sucesso!', 'success')
        return redirect(url_for('detalhe_cliente', cliente_id=atendimento.cliente_id))

    # A parte GET é só para carregar a página se acessada diretamente (não usada pelo modal)
    return redirect(url_for('detalhe_cliente', cliente_id=atendimento.cliente_id))

# Rota para excluir um atendimento
@app.route('/atendimento/excluir/<int:atendimento_id>', methods=['POST'])
def excluir_atendimento(atendimento_id):
    atendimento = Atendimento.query.get_or_404(atendimento_id)
    cliente_id_para_redirect = atendimento.cliente_id # Guarda o ID do cliente antes de apagar

    # Lógica de devolução de crédito se o atendimento JÁ FOI DADO (Presente)
    if atendimento.pacote_id and atendimento.status_presenca == 'Presente':
        pacote = Pacote.query.get(atendimento.pacote_id)
        if pacote:
            # Garante que o crédito não fique negativo
            if pacote.creditos_usados > 0:
                pacote.creditos_usados -= 1
            
            # Se o pacote estava concluído, ele volta a ser ativo
            if pacote.status == 'Concluído':
                pacote.status = 'Ativo'
    
    db.session.delete(atendimento)
    db.session.commit()
    flash('Atendimento excluído com sucesso!', 'success')
    
    # Redireciona de volta para a página de detalhes do cliente de onde viemos
    return redirect(url_for('detalhe_cliente', cliente_id=cliente_id_para_redirect))


# Rota para listar as despesas
@app.route('/despesas')
def listar_despesas():
    query = request.args.get('q', '')
    filtro_tipo = request.args.get('filtro', '')
    hoje = date.today()
    ano_selecionado = request.args.get('ano', hoje.year, type=int)
    mes_selecionado = request.args.get('mes', hoje.month, type=int)

    primeiro_dia = date(ano_selecionado, mes_selecionado, 1)
    ultimo_dia_num = calendar.monthrange(ano_selecionado, mes_selecionado)[1]
    ultimo_dia = date(ano_selecionado, mes_selecionado, ultimo_dia_num)

    despesas_query = Despesa.query.filter(Despesa.data.between(primeiro_dia, ultimo_dia)).order_by(Despesa.data.desc())

    if query:
        search_term = f"%{query}%"
        despesas_query = despesas_query.filter(Despesa.descricao.like(search_term))
    
    if filtro_tipo in ['PETSHOP', 'CASA', 'LETICIA', 'EDUARDA']:
        despesas_query = despesas_query.filter_by(tipo=filtro_tipo)
    
    despesas = despesas_query.all()
    
    total_geral = sum(d.valor for d in despesas)
    total_petshop = sum(d.valor for d in despesas if d.tipo == 'PETSHOP')
    total_casa = sum(d.valor for d in despesas if d.tipo == 'CASA')
    total_leticia = sum(d.valor for d in despesas if d.tipo == 'LETICIA')
    total_eduarda = sum(d.valor for d in despesas if d.tipo == 'EDUARDA')
    
    anos_disponiveis = range(hoje.year - 1, hoje.year + 2)
    mes_ano_titulo = primeiro_dia.strftime('%B de %Y').capitalize()
        
    return render_template('despesas.html', 
                           despesas=despesas, 
                           query=query, 
                           filtro_ativo=filtro_tipo,
                           total_geral=total_geral,
                           total_petshop=total_petshop,
                           total_casa=total_casa,
                           total_leticia=total_leticia,
                           total_eduarda=total_eduarda,
                           anos=anos_disponiveis,
                           ano_selecionado=ano_selecionado,
                           mes_selecionado=mes_selecionado,
                           mes_ano_titulo=mes_ano_titulo)

# Rota para adicionar nova despesa
@app.route('/despesas/nova', methods=['GET', 'POST'])
def nova_despesa():
    if request.method == 'POST':
        tipo = request.form['tipo']
        descricao = request.form['descricao']
        data_str = request.form['data']

        # Limpa o valor recebido da máscara antes de converter
        valor_str = request.form.get('valor', '0').replace('R$', '').replace('.', '').replace(',', '.').strip()
        valor = float(valor_str) if valor_str else 0.0
        
        try:
            data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
            nova = Despesa(tipo=tipo, descricao=descricao, valor=valor, data=data_obj)
            db.session.add(nova)
            db.session.commit()
            flash('Despesa adicionada com sucesso!', 'success')
        except ValueError:
            flash('Erro: Data ou valor inválido.', 'danger')

        return redirect(url_for('listar_despesas'))

    return render_template('nova_despesa.html')

# Rota para editar uma despesa
@app.route('/despesa/editar/<int:despesa_id>', methods=['GET', 'POST'])
def editar_despesa(despesa_id):
    despesa = Despesa.query.get_or_404(despesa_id)
    if request.method == 'POST':
        despesa.tipo = request.form['tipo']
        despesa.descricao = request.form['descricao']
        data_str = request.form['data']
        
        # Limpa o valor recebido da máscara antes de converter
        valor_str = request.form.get('valor', '0').replace('R$', '').replace('.', '').replace(',', '.').strip()
        despesa.valor = float(valor_str) if valor_str else 0.0

        try:
            despesa.data = datetime.strptime(data_str, '%Y-%m-%d').date()
            db.session.commit()
            flash('Despesa editada com sucesso!', 'success')
        except ValueError:
            flash('Erro: Data ou valor inválido.', 'danger')

        return redirect(url_for('listar_despesas'))
        
    return render_template('editar_despesa.html', despesa=despesa)

# Rota para excluir uma despesa
@app.route('/despesa/excluir/<int:despesa_id>', methods=['POST'])
def excluir_despesa(despesa_id):
    despesa = Despesa.query.get_or_404(despesa_id)
    db.session.delete(despesa)
    db.session.commit()
    flash('Despesa excluida com sucesso!', 'success')
    return redirect(url_for('listar_despesas'))

# Rota para listar os pacotes
@app.route('/pacotes')
def listar_pacotes():
    query = request.args.get('q', '')
    filtro_status = request.args.get('filtro', 'ativos')

    pacotes_query = Pacote.query.order_by(Pacote.id.desc())

    if query:
        search_term = f"%{query}%"
        pacotes_query = pacotes_query.join(Cliente).filter(
            or_(
                Cliente.nome_tutor.like(search_term),
                Cliente.nome_pet.like(search_term)
            )
        )
    
    if filtro_status == 'ativos':
        pacotes_query = pacotes_query.filter(Pacote.status == 'Ativo')
    elif filtro_status == 'concluidos':
        pacotes_query = pacotes_query.filter(Pacote.status == 'Concluído')
    
    pacotes = pacotes_query.all()

    # Para cada pacote, busca a data do primeiro atendimento
    for pacote in pacotes:
        primeiro_atendimento = Atendimento.query.filter_by(pacote_id=pacote.id).order_by(Atendimento.data.asc()).first()
        pacote.data_inicio = primeiro_atendimento.data if primeiro_atendimento else None
        
    return render_template('pacotes.html', 
                           pacotes=pacotes, 
                           query=query,
                           filtro_ativo=filtro_status,
                           Atendimento=Atendimento)

# rota de agenda
@app.route('/agenda')
def agenda_do_dia():
    # Pega a data da URL. Se não vier, usa a data de hoje.
    data_selecionada_str = request.args.get('data', date.today().isoformat())
    try:
        data_selecionada = datetime.strptime(data_selecionada_str, '%Y-%m-%d').date()
    except ValueError:
        data_selecionada = date.today()

    # Busca os atendimentos para a data selecionada
    atendimentos_do_dia = Atendimento.query.filter(
        Atendimento.data == data_selecionada,
        Atendimento.status_presenca == 'Agendado'
    ).order_by(Atendimento.id).all()
    
    # Calcula as datas para os botões de navegação
    dia_anterior = data_selecionada - timedelta(days=1)
    proximo_dia = data_selecionada + timedelta(days=1)  
    
    return render_template('agenda.html', 
                           atendimentos=atendimentos_do_dia, 
                           data_selecionada=data_selecionada,
                           dia_anterior=dia_anterior,
                           proximo_dia=proximo_dia)

# Rota para confirmar a presença em um atendimento
@app.route('/atendimento/confirmar/<int:atendimento_id>', methods=['POST'])
def confirmar_presenca(atendimento_id):
    atendimento = Atendimento.query.get_or_404(atendimento_id)
    
    # Limpa qualquer pacote de renovação antigo da sessão para começar do zero
    session.pop('pacote_para_renovar', None)

    # Só altera o status se já não for 'Presente'
    if atendimento.status_presenca != 'Presente':
        atendimento.status_presenca = 'Presente'
        
        if atendimento.pacote_id:
            pacote = Pacote.query.get(atendimento.pacote_id)
            if pacote and pacote.creditos_usados < pacote.creditos_totais:
                pacote.creditos_usados += 1
                if pacote.creditos_usados >= pacote.creditos_totais:
                    pacote.status = 'Concluído'

                    # --- LÓGICA DE RENOVAÇÃO ATIVADA AQUI ---
                    # Busca a última data de atendimento concluído para ser a base do próximo pacote
                    ultimo_atendimento = Atendimento.query.filter_by(pacote_id=pacote.id, status_presenca='Presente').order_by(Atendimento.data.desc()).first()
                    
                    session['pacote_para_renovar'] = {
                        'cliente_id': pacote.cliente_id,
                        'nome_servico': pacote.nome_servico,
                        'creditos_totais': pacote.creditos_totais,
                        'preco_pacote': pacote.preco_pacote,
                        'dia_semana_fixo': pacote.dia_semana_fixo,
                        'tipo_agendamento': pacote.tipo_agendamento,
                        'ultima_data_str': ultimo_atendimento.data.isoformat() if ultimo_atendimento else date.today().isoformat()
                    }

    db.session.commit()
    # Adiciona a data da agenda para voltar ao dia correto
    flash('Presença confirmada!', 'success')
    return redirect(url_for('agenda_do_dia', data=atendimento.data.isoformat()))

# Rota para marcar falta (e reagendar)
@app.route('/atendimento/falta/<int:atendimento_id>', methods=['POST'])
def marcar_falta(atendimento_id):
    atendimento = Atendimento.query.get_or_404(atendimento_id)
    
    # 1. Altera o status do atendimento original para 'Faltou'
    atendimento.status_presenca = 'Faltou'
    
    # 2. Verifica se o atendimento original pertence a um pacote
    if atendimento.pacote_id:
        pacote = Pacote.query.get(atendimento.pacote_id)
        
        # O ponto de partida para o cálculo deve ser a data do atendimento atual.
        data_base_calculo = atendimento.data
        
        # Define o passo de tempo com base no tipo de agendamento
        if pacote.tipo_agendamento == 'semanal':
            pulo = timedelta(weeks=1)
        elif pacote.tipo_agendamento == 'quinzenal':
            pulo = timedelta(weeks=2)
        else:
            pulo = timedelta(days=1) # Fallback seguro

        # 3. Calcula a primeira data proposta para o reagendamento
        nova_data = data_base_calculo + pulo
        
        # 4. Verifica se a nova data cai no dia da semana fixo, se aplicável
        if pacote.dia_semana_fixo is not None:
            while nova_data.weekday() != pacote.dia_semana_fixo:
                nova_data += timedelta(days=1)

        # 5. Loop para encontrar a primeira data disponível
        # Verifica se já existe um atendimento com o mesmo pacote e data
        while Atendimento.query.filter_by(
            pacote_id=pacote.id,
            data=nova_data,
            status_presenca='Agendado'
        ).first():
            # Se um agendamento já existe, pule para a próxima data
            nova_data += pulo
            # E recalcule para o dia da semana fixo se aplicável
            if pacote.dia_semana_fixo is not None:
                 while nova_data.weekday() != pacote.dia_semana_fixo:
                    nova_data += timedelta(days=1)

        # 6. Cria o novo agendamento com a data finalmente encontrada
        novo_atendimento = Atendimento(
            data=nova_data,
            nome_servico=atendimento.nome_servico,
            preco=0, # Preço zero pois está coberto pelo pacote
            observacao=atendimento.observacao,
            status_pagamento='Pago (Pacote)', # Status pago, pois o pacote já foi pago
            cliente_id=atendimento.cliente_id,
            pacote_id=atendimento.pacote_id,
            status_presenca='Agendado'
        )
        db.session.add(novo_atendimento)
        flash(f'Falta registrada. Atendimento reagendado para {nova_data.strftime("%d/%m/%Y")}.', 'danger')
    
    # Para atendimentos avulsos, a lógica original se mantém
    else:
        atendimento.status_pagamento = 'Cancelado (Falta)'
        flash('Falta registrada. Atendimento avulso cancelado (Falta).', 'danger')
    
    db.session.commit()
    
    # Redireciona de volta para a agenda do dia original
    return redirect(url_for('agenda_do_dia', data=atendimento.data.isoformat()))

# tela novo pacote 
@app.route('/pacotes/novo', methods=['GET', 'POST'])
def novo_pacote():
    if request.method == 'POST':
        tipo_agendamento = request.form.get('tipo_agendamento')
        
        # Limpeza robusta do campo de preço do pacote
        preco_pacote_str = request.form.get('preco_pacote', '0').replace('R$', '').replace('.', '').replace(',', '.').strip()
        preco_pacote = float(preco_pacote_str) if preco_pacote_str else 0.0

        pacote_novo = Pacote(
            cliente_id=request.form['cliente_id'],
            nome_servico=request.form['nome_servico'],
            creditos_totais=int(request.form['creditos_totais']),
            preco_pacote=preco_pacote,
            dia_semana_fixo=int(request.form.get('dia_semana')) if tipo_agendamento != 'nenhum' and request.form.get('dia_semana') else None,
            tipo_agendamento=tipo_agendamento 
        )
        db.session.add(pacote_novo)
        db.session.commit() # Salva o pacote aqui para garantir o ID definitivo

        if tipo_agendamento in ['semanal', 'quinzenal']:
            data_inicio_str = request.form.get('data_inicio')
            
            try:
                data_atual = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Erro na data de início do agendamento.', 'danger')
                return redirect(url_for('novo_pacote'))
                
            creditos_totais = int(request.form['creditos_totais'])
            dia_semana_escolhido = int(request.form.get('dia_semana'))
            
            datas_agendadas = []
            
            # 1. Encontra a primeira data que corresponde ao dia da semana escolhido
            dias_a_frente = dia_semana_escolhido - data_atual.weekday()
            if dias_a_frente < 0:
                dias_a_frente += 7
            proxima_data = data_atual + timedelta(days=dias_a_frente)
            
            pulo = timedelta(weeks=1) if tipo_agendamento == 'semanal' else timedelta(weeks=2)

            for i in range(creditos_totais):
                datas_agendadas.append(proxima_data)
                proxima_data += pulo

            for data_agendada in datas_agendadas:
                novo_agendamento = Atendimento(
                    data=data_agendada, 
                    cliente_id=request.form['cliente_id'], 
                    nome_servico=request.form['nome_servico'],
                    preco=0,
                    pacote_id=pacote_novo.id,
                    status_pagamento='Pago (Pacote)'
                )
                db.session.add(novo_agendamento)
            
            db.session.commit() # Salva os atendimentos com o ID do pacote

        flash('Pacote adicionado com sucesso!', 'success')

        return redirect(url_for('listar_pacotes'))
     
   
    clientes = Cliente.query.all()
    return render_template('novo_pacote.html', clientes=clientes)


# Rota para calcular as datas do pacote via AJAX e devolver para o JavaScript
@app.route('/pacotes/calcular_datas', methods=['POST'])
def calcular_datas_pacote():
    try:
        tipo_agendamento = request.form.get('tipo_agendamento')
        data_inicio_str = request.form.get('data_inicio')
        creditos_totais = int(request.form.get('creditos_totais'))
        
        if not all([data_inicio_str, creditos_totais]):
            return jsonify({'success': False, 'message': 'Dados incompletos.'}), 400

        datas_calculadas = []
        data_atual = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()

        if tipo_agendamento == 'semanal' or tipo_agendamento == 'quinzenal':
            dia_semana_escolhido = int(request.form.get('dia_semana'))
            
            # Acha a primeira data que corresponde ao dia da semana escolhido
            dias_a_frente = dia_semana_escolhido - data_atual.weekday()
            if dias_a_frente < 0:
                dias_a_frente += 7
            proxima_data = data_atual + timedelta(days=dias_a_frente)
            
            # Define o pulo: 1 semana para semanal, 2 semanas para quinzenal
            pulo = timedelta(weeks=1) if tipo_agendamento == 'semanal' else timedelta(weeks=2)

            for i in range(creditos_totais):
                datas_calculadas.append(proxima_data)
                proxima_data += pulo

        datas_formatadas = [d.strftime('%d/%m/%Y (%A)').capitalize() for d in datas_calculadas]
        return jsonify({'success': True, 'datas_formatadas': datas_formatadas})

    except Exception as e:
        print(f"Erro ao calcular datas: {e}")
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

# Rota para editar um pacote via modal
@app.route('/pacote/editar/<int:pacote_id>', methods=['POST'])
def editar_pacote(pacote_id):
    pacote = Pacote.query.get_or_404(pacote_id)
    
    # Pega os dados do formulário
    pacote.nome_servico = request.form['nome_servico']
    
    # Limpeza robusta do campo de preço
    preco_str = request.form.get('preco_pacote', '0').replace('R$', '').replace('.', '').replace(',', '.').strip()
    pacote.preco_pacote = float(preco_str) if preco_str else 0.0

    # Lógica de segurança para os créditos
    novos_creditos_totais = int(request.form.get('creditos_totais', 0))
    if novos_creditos_totais >= pacote.creditos_usados:
        pacote.creditos_totais = novos_creditos_totais
        # Se o pacote estava concluído e aumentamos os créditos, ele volta a ser ativo
        if pacote.status == 'Concluído' and pacote.creditos_totais > pacote.creditos_usados:
            pacote.status = 'Ativo'
        # Se diminuirmos e esgotarmos os créditos, ele pode voltar a ser 'Concluído'
        elif pacote.status == 'Ativo' and pacote.creditos_totais <= pacote.creditos_usados:
            pacote.status = 'Concluído'

    db.session.commit()
    flash('Pacote editado com sucesso!', 'success')
    return redirect(request.referrer or url_for('listar_pacotes'))

# Rota para excluir um pacote
@app.route('/pacote/excluir/<int:pacote_id>', methods=['POST'])
def excluir_pacote(pacote_id):
    pacote = Pacote.query.get_or_404(pacote_id)

    # Regra de negócio: só permite excluir se não foi usado
    if pacote.creditos_usados == 0:
        # Encontra e apaga todos os agendamentos futuros ligados a este pacote
        atendimentos_para_apagar = Atendimento.query.filter_by(pacote_id=pacote.id).all()
        for atendimento in atendimentos_para_apagar:
            db.session.delete(atendimento)

        # Agora, apaga o pacote em si
        db.session.delete(pacote)

        db.session.commit() # Salva todas as exclusões de uma vez
        flash('Pacote excluido com sucesso!', 'success')
    else:
        flash('Erro: Pacote não pode ser excluído pois já possui créditos usados.', 'danger')
        
    return redirect(request.referrer or url_for('listar_pacotes'))

# Rota para calcular as datas do pacote via AJAX e devolver para o JavaScript
@app.route('/pacote/calcular_renovacao', methods=['POST'])
def calcular_datas_renovacao():
    try:
        pacote_antigo = session.get('pacote_para_renovar')
        if not pacote_antigo:
            return jsonify({'success': False, 'message': 'Dados do pacote não encontrados.'}), 400

        creditos_totais = int(pacote_antigo['creditos_totais'])
        tipo_agendamento = pacote_antigo['tipo_agendamento']
        ultima_data = date.fromisoformat(pacote_antigo['ultima_data_str'])
        
        datas_calculadas = []
        
        if tipo_agendamento in ['semanal', 'quinzenal']:
            dia_semana_fixo = pacote_antigo.get('dia_semana_fixo')
            
            # 1. Encontra a próxima data que corresponde ao dia da semana fixo
            dias_a_frente = dia_semana_fixo - ultima_data.weekday()
            if dias_a_frente <= 0:
                dias_a_frente += 7
            
            proxima_data = ultima_data + timedelta(days=dias_a_frente)

            # CORREÇÃO CRÍTICA: Se for quinzenal, pule a primeira semana.
            if tipo_agendamento == 'quinzenal':
                proxima_data += timedelta(weeks=1)

            # 2. Define o pulo para os próximos agendamentos
            pulo = timedelta(weeks=1) if tipo_agendamento == 'semanal' else timedelta(weeks=2)
            
            # 3. Gera a lista de todas as novas datas
            for _ in range(creditos_totais):
                datas_calculadas.append(proxima_data)
                proxima_data += pulo

        datas_formatadas = [d.strftime('%d/%m/%Y (%A)').capitalize() for d in datas_calculadas]
        return jsonify({'success': True, 'datas_formatadas': datas_formatadas})

    except Exception as e:
        print(f"Erro ao calcular datas de renovação: {e}")
        return jsonify({'success': False, 'message': 'Erro interno ao calcular datas.'}), 500
    
# Rota para renovar o pacote com base nos dados da session
@app.route('/pacote/renovar', methods=['POST'])
def renovar_pacote():
    pacote_antigo = session.get('pacote_para_renovar')
    if not pacote_antigo:
        flash('Erro: Dados do pacote expirados ou não encontrados.', 'danger')
        return redirect(url_for('agenda_do_dia'))

    pacote_novo = Pacote(
        cliente_id=pacote_antigo['cliente_id'],
        nome_servico=pacote_antigo['nome_servico'],
        creditos_totais=pacote_antigo['creditos_totais'],
        preco_pacote=pacote_antigo['preco_pacote'],
        dia_semana_fixo=pacote_antigo.get('dia_semana_fixo'),
        tipo_agendamento=pacote_antigo.get('tipo_agendamento')
    )
    db.session.add(pacote_novo)
    db.session.commit() # SALVA O PACOTE PARA OBTER O ID DEFINITIVO

    # --- LÓGICA DE CÁLCULO DE DATAS (CORRIGIDA) ---
    tipo_agendamento = pacote_antigo.get('tipo_agendamento')
    creditos_totais = int(pacote_antigo['creditos_totais'])
    ultima_data = date.fromisoformat(pacote_antigo['ultima_data_str'])
    
    datas_agendadas = []

    if tipo_agendamento in ['semanal', 'quinzenal']:
        dia_semana_fixo = pacote_antigo.get('dia_semana_fixo')
        
        # 1. Encontra a próxima data que corresponde ao dia da semana fixo
        dias_a_frente = dia_semana_fixo - ultima_data.weekday()
        if dias_a_frente <= 0:
            dias_a_frente += 7
        
        proxima_data = ultima_data + timedelta(days=dias_a_frente)

        # CORREÇÃO CRÍTICA: Se for quinzenal, pule a primeira semana.
        if tipo_agendamento == 'quinzenal':
            proxima_data += timedelta(weeks=1)

        # 2. Define o pulo para os próximos agendamentos
        pulo = timedelta(weeks=1) if tipo_agendamento == 'semanal' else timedelta(weeks=2)

        # 3. Gera a lista de todas as novas datas
        for _ in range(creditos_totais):
            datas_agendadas.append(proxima_data)
            proxima_data += pulo
    # --- FIM DA LÓGICA CORRIGIDA ---
        
    for data_agendada in datas_agendadas:
        novo_agendamento = Atendimento(
            data=data_agendada,
            cliente_id=pacote_antigo['cliente_id'],
            nome_servico=pacote_antigo['nome_servico'],
            preco=0,
            pacote_id=pacote_novo.id, # USA O ID DEFINITIVO DO PACOTE
            status_pagamento='Pago (Pacote)'
        )
        db.session.add(novo_agendamento)
        
    db.session.commit() # SALVA OS ATENDIMENTOS
    session.pop('pacote_para_renovar', None)
    flash('Pacote renovado e agendamentos criados com sucesso!', 'success')
    return redirect(url_for('agenda_do_dia'))

# Rota para limpar a session caso o usuário clique em "Não, obrigado"
@app.route('/pacote/limpar_renovacao')
def limpar_sessao_renovacao():
    session.pop('pacote_para_renovar', None)
    return redirect(url_for('agenda_do_dia'))   


# Atualizar data na agenda 
@app.route('/atendimento/editar_data/<int:atendimento_id>', methods=['POST'])
def editar_data_atendimento(atendimento_id):
    atendimento = Atendimento.query.get_or_404(atendimento_id)
    
    nova_data_str = request.form.get('nova_data')
    data_agenda_original = request.form.get('data_agenda_original') # Para voltar à mesma página

    if nova_data_str:
        try:
            nova_data = datetime.strptime(nova_data_str, '%Y-%m-%d').date()
            atendimento.data = nova_data
            db.session.commit()
            flash(f'Atendimento reagendado para {nova_data.strftime("%d/%m/%Y")}.', 'success')
        except ValueError:
            flash('Erro: Nova data inválida.', 'danger')

    # Redireciona de volta para o dia que o usuário estava visualizando na agenda
    return redirect(url_for('agenda_do_dia', data=data_agenda_original))


# --- Bloco de Execução ---
def criar_banco_se_nao_existir():
    # Garante que a pasta 'instance' existe
    instance_path = os.path.join(basedir, 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
    with app.app_context():
        # A migração é geralmente responsável por criar as tabelas, mas 
        # garantimos que o contexto esteja ativo.
        db.create_all()


if __name__ == '__main__':
    criar_banco_se_nao_existir()
    app.run(debug=True)