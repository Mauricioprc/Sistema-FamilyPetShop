from datetime import datetime, date, timedelta
from flask_login import login_required
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from sqlalchemy import or_
from extensions import db
from models import Atendimento, Pacote, Cliente, StatusPacote
from rotas import clientes
from services.pacote_service import criar_pacote, renovar_pacote
from utils import parse_preco, calcular_datas_pacote, calcular_datas_renovacao
import json

pacotes_bp = Blueprint('pacotes', __name__)


@pacotes_bp.route('/pacotes')
@login_required
def listar():
    # 1. Capturar todos os filtros
    query = request.args.get('q', '')
    filtro = request.args.get('filtro', 'ativos')
    status_pagamento = request.args.get('status_pagamento', '') 
    mes = request.args.get('mes', '') 
    
    hoje = date.today()

    # 2. Iniciar a consulta
    q = Pacote.query.order_by(Pacote.id.desc())

    # Filtro de Texto
    if query:
        termo = '%' + query + '%'
        q = q.join(Cliente).filter(
            or_(Cliente.nome_tutor.like(termo), Cliente.nome_pet.like(termo))
        )

    # Filtro de Abas
    if filtro == 'ativos':
        q = q.filter(Pacote.status == StatusPacote.ATIVO.value)
    elif filtro == 'concluidos':
        # Aqui está a correção! Usamos or_ para buscar as duas variações de texto
        q = q.filter(or_(
            Pacote.status == StatusPacote.CONCLUIDO.value,  
            Pacote.status == 'Concluído'                    
        ))

    # Filtro Financeiro
    if status_pagamento == 'pago':
        q = q.filter(Pacote.status_pagamento == 'Pago')
    elif status_pagamento == 'pendente':
        q = q.filter(Pacote.status_pagamento == 'Pendente')

    # Filtro de Mês 
    if mes:
        from sqlalchemy import extract
        q = q.filter(extract('month', Pacote.data_vencimento) == int(mes))

    # 3. BUSCA TOTAL 
    pacotes = q.all()

    # 4. Buscar primeira data
    if pacotes:
        pacote_ids = [p.id for p in pacotes]
        from sqlalchemy import func
        primeiros = db.session.query(
            Atendimento.pacote_id,
            func.min(Atendimento.data).label('primeira_data')
        ).filter(
            Atendimento.pacote_id.in_(pacote_ids)
        ).group_by(Atendimento.pacote_id).all()

        datas_map = {r.pacote_id: r.primeira_data for r in primeiros}
        for p in pacotes:
            p.data_inicio = datas_map.get(p.id)

    # Retorna para o HTML (sem a variável pagination)
    return render_template('pacotes.html',
                           pacotes=pacotes,
                           query=query,
                           filtro_ativo=filtro,
                           Atendimento=Atendimento,
                           hoje=hoje)


@pacotes_bp.route('/pacotes/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if request.method == 'POST':
        sucesso, msg, _ = criar_pacote(request.form)
        flash(msg, 'success' if sucesso else 'danger')
        if sucesso:
            return redirect(url_for('pacotes.listar'))

    # Buscamos os clientes
    clientes = Cliente.query.order_by(Cliente.nome_tutor).all()
    
    hoje = date.today()
    limite_atraso = hoje - timedelta(days=10)
    
    # Calculamos a dívida de cada um (Apenas > 10 dias de atraso)
    for c in clientes:
        # Soma pacotes pendentes vencidos há mais de 10 dias
        divida_pacotes = sum(
            p.preco_pacote for p in c.pacotes.filter_by(status_pagamento='Pendente')
            if p.data_vencimento and p.data_vencimento <= limite_atraso
        )
        
        # Soma atendimentos avulsos pendentes e que o pet esteve presente, há mais de 10 dias
        divida_atendimentos = sum(
            a.preco for a in c.atendimentos.filter_by(status_pagamento='Pendente', status_presenca='Presente')
            if a.data and a.data <= limite_atraso
        )
        
        # Guarda o total para usar no data-divida no HTML
        c.total_divida = divida_pacotes + divida_atendimentos

    return render_template('novo_pacote.html', clientes=clientes)

@pacotes_bp.route('/pacotes/calcular-datas', methods=['POST'])
@login_required
def calcular_datas():
    try:
        # 1. Pegamos os dados como texto puro primeiro
        data_inicio_str = request.form.get('data_inicio')
        creditos_str = request.form.get('creditos_totais')
        tipo = request.form.get('tipo_agendamento')
        dias_str = request.form.get('dias_selecionados')

        # 2. Lógica de Investigação (O que está a faltar?)
        faltam = []
        if not data_inicio_str: faltam.append("Data de Início (data_inicio)")
        if not creditos_str: faltam.append("Créditos Totais (creditos_totais)")
        if not dias_str: faltam.append("Dias Selecionados (dias_selecionados)")

        if faltam:
            return jsonify({'success': False, 'message': f'Campos em falta: {", ".join(faltam)}'}), 400

        # 3. Se passou na validação, convertemos os tipos
        creditos = int(creditos_str)
        dias_selecionados = [int(d) for d in json.loads(dias_str)]
        data_atual = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        datas_agendadas = []

        if tipo == 'seguidos':
            # Percorre o calendário pescando os dias certos
            while len(datas_agendadas) < creditos:
                if data_atual.weekday() in dias_selecionados:
                    datas_agendadas.append(data_atual)
                data_atual += timedelta(days=1)
        else:
            # Mantém a lógica semanal ou quinzenal
            dia_alvo = dias_selecionados[0]
            while data_atual.weekday() != dia_alvo:
                data_atual += timedelta(days=1)
                
            intervalo = 14 if tipo == 'quinzenal' else 7
            for _ in range(creditos):
                datas_agendadas.append(data_atual)
                data_atual += timedelta(days=intervalo)

        datas_formatadas = [d.strftime('%d/%m/%Y') for d in datas_agendadas]
        return jsonify({'success': True, 'datas_formatadas': datas_formatadas})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro no servidor: {str(e)}'}), 500


@pacotes_bp.route('/pacote/editar/<int:pacote_id>', methods=['POST'])
@login_required
def editar(pacote_id):
    pacote = db.get_or_404(Pacote, pacote_id)
    
    pacote.nome_servico = request.form.get('nome_servico', pacote.nome_servico)
    pacote.preco_pacote = parse_preco(request.form.get('preco_pacote', str(pacote.preco_pacote)))

    try:
        # Evita erro se o campo vier vazio ou com texto inválido
        novos_creditos = int(request.form.get('creditos_totais', pacote.creditos_totais))
        if novos_creditos >= pacote.creditos_usados:
            pacote.creditos_totais = novos_creditos
    except ValueError:
        pass

    nova_data_str = request.form.get('data_vencimento')
    if nova_data_str:
        try:
            nova_data = datetime.strptime(nova_data_str, '%Y-%m-%d').date()
            if nova_data != pacote.data_vencimento:
                pacote.data_vencimento = nova_data
                pacote.vencimento_customizado = True
        except ValueError:
            flash('Data de vencimento inválida.', 'danger')

    db.session.commit()
    flash('Pacote atualizado!', 'success')
    return redirect(request.referrer or url_for('pacotes.listar'))


@pacotes_bp.route('/pacote/excluir/<int:pacote_id>', methods=['POST'])
@login_required
def excluir(pacote_id):
    pacote = db.get_or_404(Pacote, pacote_id)
    if pacote.creditos_usados > 0:
        flash('Erro: Pacote nao pode ser excluido pois ja possui creditos usados.', 'danger')
    else:
        db.session.delete(pacote)
        db.session.commit()
        flash('Pacote excluido com sucesso!', 'success')
    return redirect(request.referrer or url_for('pacotes.listar'))


@pacotes_bp.route('/pacote/calcular_renovacao', methods=['POST'])
@login_required
def calcular_renovacao():
    try:
        dados = session.get('pacote_para_renovar')
        if not dados:
            return jsonify({'success': False, 'message': 'Dados do pacote nao encontrados.'}), 400

        ultima = date.fromisoformat(dados['ultima_data_str'])
        datas = calcular_datas_renovacao(
            ultima, dados['creditos_totais'],
            dados['tipo_agendamento'], dados['dia_semana_fixo']
        )
        datas_fmt = [d.strftime('%d/%m/%Y (%A)').capitalize() for d in datas]
        return jsonify({'success': True, 'datas_formatadas': datas_fmt})
    except Exception:
        return jsonify({'success': False, 'message': 'Erro ao calcular datas.'}), 500


@pacotes_bp.route('/pacote/renovar', methods=['POST'])
@login_required
def renovar():
    dados = session.get('pacote_para_renovar')
    if not dados:
        flash('Erro: Dados do pacote expirados.', 'danger')
        return redirect(url_for('agenda.agenda_do_dia'))

    sucesso, msg = renovar_pacote(dados)
    flash(msg, 'success' if sucesso else 'danger')
    if sucesso:
        session.pop('pacote_para_renovar', None)
    return redirect(url_for('agenda.agenda_do_dia'))


@pacotes_bp.route('/pacote/limpar_renovacao')
@login_required
def limpar_renovacao():
    session.pop('pacote_para_renovar', None)
    return redirect(url_for('agenda.agenda_do_dia'))




