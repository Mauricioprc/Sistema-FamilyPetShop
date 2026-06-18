"""
API centralizada para geração de links WhatsApp.

Todos os endpoints retornam JSON: { "url": "https://wa.me/..." }
O frontend abre a URL via window.open().

Endpoints:
  GET  /api/whatsapp/lembrete/<atendimento_id>      → Lembrete de confirmação (agenda)
  GET  /api/whatsapp/falta/<atendimento_id>         → Aviso de falta (histórico)
  GET  /api/whatsapp/cobranca/<atendimento_id>      → Cobrança de atendimento avulso (financeiro)
  GET  /api/whatsapp/cobranca_pacote/<pacote_id>    → Cobrança de pacote (financeiro)
  GET  /api/whatsapp/reagendamento/<atendimento_id> → Aviso de reagendamento (agenda)
  GET  /api/whatsapp/cobranca_cliente/<cliente_id>  → Cobrança detalhada (detalhe do cliente)
"""

from datetime import date, timedelta
from urllib.parse import quote_plus

from flask import Blueprint, jsonify, request
from flask_login import login_required

from extensions import db
from models import Atendimento, Cliente, Pacote

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/api/whatsapp')


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _limpar_telefone(telefone: str) -> str:
    """Remove formatação e garante DDI 55."""
    numero = ''.join(c for c in telefone if c.isdigit())
    if not numero.startswith('55'):
        numero = '55' + numero
    return numero


def _montar_url(telefone: str, mensagem: str) -> str:
    return 'https://wa.me/{}?text={}'.format(
        _limpar_telefone(telefone),
        quote_plus(mensagem)
    )


def _erro(msg: str, status: int = 404):
    return jsonify({'erro': msg}), status


# ---------------------------------------------------------------------------
# Mensagens — edite aqui para alterar os textos
# ---------------------------------------------------------------------------

def _msg_lembrete(atendimento: Atendimento) -> str:
    hoje = date.today()
    if atendimento.data == hoje:
        dia_texto = 'hoje'
    else:
        dia_texto = 'o dia ' + atendimento.data.strftime('%d/%m')

    return (
        'Olá {tutor}! 🐶 Passando para confirmar o agendamento de '
        '{servico} do(a) {pet} para {dia}. '
        'Qualquer dúvida é só chamar! 😉'
    ).format(
        tutor=atendimento.cliente.nome_tutor,
        servico=atendimento.nome_servico,
        pet=atendimento.cliente.nome_pet,
        dia=dia_texto,
    )


def _msg_falta(atendimento: Atendimento) -> str:
    return (
        'Olá {tutor}! 🐶 Sentimos a falta do(a) {pet} '
        'hoje no {servico}! 😢 Aconteceu algum imprevisto? '
        'Vamos reagendar para não perder o ritmo de limpeza? 🛁'
    ).format(
        tutor=atendimento.cliente.nome_tutor,
        pet=atendimento.cliente.nome_pet,
        servico=atendimento.nome_servico,
    )


def _msg_cobranca_atendimento(atendimento: Atendimento) -> str:
    return (
        'Olá {tutor}! 😊 Tudo bem? Passando para lembrar do acerto do '
        '{servico} do(a) {pet} realizado no dia {data} '
        '(R$ {valor}). Qualquer dúvida, estamos à disposição! 🙏'
    ).format(
        tutor=atendimento.cliente.nome_tutor,
        servico=atendimento.nome_servico,
        pet=atendimento.cliente.nome_pet,
        data=atendimento.data.strftime('%d/%m'),
        valor='{:.2f}'.format(atendimento.preco).replace('.', ','),
    )


def _msg_cobranca_pacote(pacote: Pacote) -> str:
    return (
        'Olá {tutor}! 😊 Tudo bem? Passando para lembrar do acerto do pacote de '
        '{servico} do(a) {pet} '
        '(R$ {valor}). Qualquer dúvida, estamos à disposição! 🙏'
    ).format(
        tutor=pacote.cliente.nome_tutor,
        servico=pacote.nome_servico,
        pet=pacote.cliente.nome_pet,
        valor='{:.2f}'.format(pacote.preco_pacote).replace('.', ','),
    )


def _msg_reagendamento(atendimento: Atendimento, nova_data_str: str) -> str:
    """nova_data_str no formato AAAA-MM-DD vindo do frontend."""
    from datetime import datetime
    try:
        nova_data = datetime.strptime(nova_data_str, '%Y-%m-%d').date()
        data_fmt = nova_data.strftime('%d/%m/%Y')
    except ValueError:
        data_fmt = nova_data_str

    return (
        'Olá {tutor}! 😊 Passando para informar que o {servico} do(a) '
        '{pet} foi reagendado para o dia {data}. '
        'Qualquer dúvida é só chamar! 🐶'
    ).format(
        tutor=atendimento.cliente.nome_tutor,
        servico=atendimento.nome_servico,
        pet=atendimento.cliente.nome_pet,
        data=data_fmt,
    )


def _msg_cobranca_cliente(cliente: Cliente) -> str:
    """Mensagem detalhada com todos os débitos do cliente."""
    limite_atraso = date.today() - timedelta(days=10)

    linhas = [
        'Olá {tutor}! 😊 Tudo bem?'.format(tutor=cliente.nome_tutor),
        'Passando para fazer uma atualização da ficha do(a) {pet}. 🐶'.format(
            pet=cliente.nome_pet
        ),
        'Constam os seguintes valores em aberto há alguns dias:',
        '',
    ]

    total = 0.0

    for pacote in cliente.pacotes_em_atraso:
        val = pacote.preco_pacote or 0.0
        total += val
        linhas.append(
            '- *Pacote: {servico}* (Venc.: {venc}) — R$ {val}'.format(
                servico=pacote.nome_servico,
                venc=pacote.data_vencimento.strftime('%d/%m/%Y'),
                val='{:.2f}'.format(val).replace('.', ','),
            )
        )

    for avulso in cliente.atendimentos_avulsos_em_atraso:
        val = avulso.preco or 0.0
        total += val
        linhas.append(
            '- *Avulso: {servico}* em {data} — R$ {val}'.format(
                servico=avulso.nome_servico,
                data=avulso.data.strftime('%d/%m/%Y'),
                val='{:.2f}'.format(val).replace('.', ','),
            )
        )

    linhas += [
        '',
        '*Total pendente: R$ {total}*'.format(
            total='{:.2f}'.format(total).replace('.', ',')
        ),
        '',
        'Consegue confirmar se o pagamento já foi feito ou prefere que '
        'eu envie a chave PIX? Qualquer dúvida, estou à disposição! 🙏',
    ]

    return '\n'.join(linhas)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@whatsapp_bp.route('/lembrete/<int:atendimento_id>')
@login_required
def lembrete(atendimento_id):
    """Lembrete de confirmação de agendamento."""
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    url = _montar_url(atendimento.cliente.telefone, _msg_lembrete(atendimento))
    return jsonify({'url': url})


@whatsapp_bp.route('/falta/<int:atendimento_id>')
@login_required
def falta(atendimento_id):
    """Aviso de falta ao cliente."""
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    url = _montar_url(atendimento.cliente.telefone, _msg_falta(atendimento))
    return jsonify({'url': url})


@whatsapp_bp.route('/cobranca/<int:atendimento_id>')
@login_required
def cobranca_atendimento(atendimento_id):
    """Cobrança de atendimento avulso pendente."""
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    url = _montar_url(
        atendimento.cliente.telefone,
        _msg_cobranca_atendimento(atendimento)
    )
    return jsonify({'url': url})


@whatsapp_bp.route('/cobranca_pacote/<int:pacote_id>')
@login_required
def cobranca_pacote(pacote_id):
    """Cobrança de pacote pendente."""
    pacote = db.get_or_404(Pacote, pacote_id)
    url = _montar_url(pacote.cliente.telefone, _msg_cobranca_pacote(pacote))
    return jsonify({'url': url})


@whatsapp_bp.route('/reagendamento/<int:atendimento_id>')
@login_required
def reagendamento(atendimento_id):
    """
    Aviso de reagendamento.
    Espera o query param ?nova_data=AAAA-MM-DD.
    """
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    nova_data = request.args.get('nova_data', '')
    if not nova_data:
        return _erro('Parâmetro nova_data obrigatório.', 400)

    url = _montar_url(
        atendimento.cliente.telefone,
        _msg_reagendamento(atendimento, nova_data)
    )
    return jsonify({'url': url})


@whatsapp_bp.route('/cobranca_cliente/<int:cliente_id>')
@login_required
def cobranca_cliente(cliente_id):
    """Cobrança detalhada com todos os débitos do cliente."""
    cliente = db.get_or_404(Cliente, cliente_id)
    url = _montar_url(cliente.telefone, _msg_cobranca_cliente(cliente))
    return jsonify({'url': url})