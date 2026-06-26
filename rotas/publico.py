from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from extensions import db, limiter
from models import Atendimento, Cliente, Avaliacao, StatusAtendimento, StatusPagamento
from utils import parse_preco, salvar_imagem, formatar_telefone_whatsapp
from config import Config
from rotas.whatsapp import _montar_url  # ✅ usa a mesma codificação (quote) da API centralizada

publico_bp = Blueprint('publico', __name__)


# Rate limiting mais restritivo para rotas publicas
LIMITE_PUBLICO = "10 per minute"


@publico_bp.route('/solicitar_agendamento', methods=['GET', 'POST'])
@limiter.limit(LIMITE_PUBLICO)
def solicitar_agendamento():
    if request.method == 'POST':
        data_str = request.form.get('data', '')
        if not data_str:
            flash('Data e obrigatoria.', 'danger')
            return redirect(url_for('publico.solicitar_agendamento'))

        try:
            data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Data invalida.', 'danger')
            return redirect(url_for('publico.solicitar_agendamento'))

        if data_obj.weekday() == 6:
            flash('Desculpe, nao funcionamos aos domingos. Por favor, escolha outra data.', 'danger')
            return redirect(url_for('publico.solicitar_agendamento'))

        telefone = request.form.get('telefone', '').strip()
        nome_tutor = request.form.get('nome_tutor', '').strip()
        nome_pet = request.form.get('nome_pet', '').strip()

        if not telefone or not nome_tutor or not nome_pet:
            flash('Nome, pet e telefone sao obrigatorios.', 'danger')
            return redirect(url_for('publico.solicitar_agendamento'))

        try:
            peso_raw = request.form.get('peso_pet', '0').replace(',', '.').strip()
            peso = float(peso_raw) if peso_raw else None
            if peso and peso < 0:
                peso = None
        except (ValueError, TypeError):
            peso = None

        dados_cliente = {
            'nome_tutor': nome_tutor,
            'nome_pet': nome_pet,
            'raca_pet': request.form.get('raca_pet', '').strip() or None,
            'tipo_pet': request.form.get('tipo_pet'),
            'sexo_pet': request.form.get('sexo_pet'),
            'castrado': request.form.get('castrado'),
            'temperamento': request.form.get('temperamento'),
            'peso_pet': peso,
        }

        cliente = Cliente.query.filter_by(telefone=telefone).first()
        if not cliente:
            cliente = Cliente(telefone=telefone, **dados_cliente)
            db.session.add(cliente)
        else:
            for campo, valor in dados_cliente.items():
                setattr(cliente, campo, valor)

        db.session.flush()

        adicionais = ', '.join(request.form.getlist('adicionais'))
        novo = Atendimento(
            data=data_obj,
            nome_servico=request.form.get('nome_servico', ''),
            preco=parse_preco(request.form.get('preco', '0.00')),
            observacao=request.form.get('observacao'),
            adicionais=adicionais,
            status_pagamento=StatusPagamento.PENDENTE.value,
            status_presenca=StatusAtendimento.SOLICITADO_ONLINE.value,
            horario_preferido=request.form.get('horario_preferido'),
            transporte=request.form.get('transporte'),
            endereco_busca=request.form.get('endereco_busca')
        )
        cliente.atendimentos.append(novo)
        db.session.add(novo)
        db.session.commit()

        flash('Solicitacao enviada! Entraremos em contato para confirmar.', 'success')
        return redirect(url_for('publico.confirmacao'))

    return render_template('solicitar_agendamento.html')


@publico_bp.route('/confirmacao_agendamento')
def confirmacao():
    return render_template('confirmacao_agendamento.html')


@publico_bp.route('/insta')
def links_insta():
    # CORRIGIDO: Avaliacao.data agora existe no model
    avaliacoes = Avaliacao.query.filter_by(aprovada=True).order_by(
        Avaliacao.data.desc()).limit(3).all()
    return render_template('links_insta.html', avaliacoes=avaliacoes)


@publico_bp.route('/submeter_avaliacao', methods=['POST'])
@limiter.limit(LIMITE_PUBLICO)
def submeter_avaliacao():
    try:
        nome_cliente = request.form.get('nome_cliente', '').strip()
        avaliacao_texto = request.form.get('avaliacao_texto', '').strip()

        if not nome_cliente or not avaliacao_texto:
            flash('Por favor, preencha o nome e o comentario.', 'error')
            return redirect(url_for('publico.links_insta'))

        # Validar nota
        try:
            nota = int(request.form.get('nota', 5))
            nota = max(1, min(5, nota))  # clamp entre 1 e 5
        except (ValueError, TypeError):
            nota = 5

        filename = salvar_imagem(
            request.files.get('foto_pet'),
            Config.UPLOAD_FOLDER,
            Config.ALLOWED_EXTENSIONS
        )

        # CORRIGIDO: usar datetime.utcnow() para o campo 'data'
        nova = Avaliacao(
            nome_cliente=nome_cliente,
            nome_pet=request.form.get('nome_pet', '').strip() or None,
            avaliacao_texto=avaliacao_texto,
            nota=nota,
            imagem_pet=filename,
            aprovada=True,
            data=datetime.utcnow()
        )
        db.session.add(nova)
        db.session.commit()
        flash('Obrigado! A foto do seu pet vai ficar linda no mural.', 'success')
    except Exception:
        db.session.rollback()
        flash('Ocorreu um erro ao enviar. Tente novamente.', 'error')

    return redirect(url_for('publico.links_insta'))


# --- Rotas ADMINISTRATIVAS ---

@publico_bp.route('/solicitacoes')
@login_required
def listar_solicitacoes():
    solicitacoes = Atendimento.query.filter_by(
        status_presenca=StatusAtendimento.SOLICITADO_ONLINE.value
    ).order_by(Atendimento.id.desc()).all()
    return render_template('solicitacoes.html', solicitacoes=solicitacoes)


@publico_bp.route('/solicitacao/confirmar/<int:atendimento_id>', methods=['POST'])
@login_required
def confirmar_solicitacao(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)

    try:
        data_obj = datetime.strptime(request.form['data'], '%Y-%m-%d')
    except ValueError:
        return jsonify({'success': False, 'message': 'Data invalida.'}), 400

    atendimento.data = data_obj.date()
    
    obs_nova = request.form.get('observacao', '').strip()
    if obs_nova:
        # Se o admin escreveu algo, junta à observação original do cliente
        atendimento.observacao = f"Observação Cliente: {atendimento.observacao}\n---\nNota PetShop: {obs_nova}"
    
    atendimento.status_presenca = StatusAtendimento.AGENDADO.value
    atendimento.preco = parse_preco(request.form.get('preco', '0'))
    db.session.commit()

    tutor = atendimento.cliente.nome_tutor
    pet = atendimento.cliente.nome_pet
    servico = atendimento.nome_servico
    data_fmt = data_obj.strftime('%d/%m/%Y')
    preco_fmt = 'R$ {:.2f}'.format(atendimento.preco)

    mensagem = (
        '\u2728 *Agendamento Confirmado!* \u2728\n\n'
        'Ola, {}! \U0001f43e\n\n'
        'Seu agendamento no *Family Pet Shop* foi confirmado!\n'
        '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n'
        '\U0001f436 *Pet:* {}\n'
        '\U0001f4c5 *Data:* {}\n'
        '\U0001f6c1 *Servicos:* {}\n'
        '\U0001f4b0 *Valor:* {}\n\n'
        '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n'
        '\U0001f4cd Caso precise alterar, nos avise com antecedencia!\n\n'
        'Ate breve! \U0001f43e\u2728'
    ).format(tutor, pet, data_fmt, servico, preco_fmt)

    telefone = formatar_telefone_whatsapp(atendimento.cliente.telefone)
    whatsapp_url = _montar_url(telefone, mensagem)
    return jsonify({'success': True, 'whatsapp_url': whatsapp_url})


@publico_bp.route('/solicitacao/recusar/<int:atendimento_id>', methods=['POST'])
@login_required
def recusar_solicitacao(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    tutor = atendimento.cliente.nome_tutor
    data_fmt = atendimento.data.strftime('%d/%m/%Y')

    mensagem = (
        'Ola, {}! \U0001f43e Infelizmente nao teremos disponibilidade '
        'para o dia {}. Podemos verificar outra data?'
    ).format(tutor, data_fmt)

    telefone = formatar_telefone_whatsapp(atendimento.cliente.telefone)
    whatsapp_url = _montar_url(telefone, mensagem)

    db.session.delete(atendimento)
    db.session.commit()
    return jsonify({'success': True, 'whatsapp_url': whatsapp_url})
