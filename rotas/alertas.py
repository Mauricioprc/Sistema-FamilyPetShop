"""
Alertas de "cliente pediu para falar com atendente", originados pelo
chatbot do WhatsApp (ver rotas/chatbot.py e services/chatbot_estado.py).

Consumidos pelo header do sistema (templates/base.html) via polling
JavaScript a cada 1 minuto: o badge mostra a contagem, e um dropdown
lista cada alerta com dois botões — "Responder" (abre o WhatsApp direto
com aquele número, via link wa.me) e "Responder mais tarde" (remove o
alerta da lista, sem deixar registro — não é dado de negócio que precise
de histórico, é só um lembrete operacional transitório).
"""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from services import chatbot_estado

alertas_bp = Blueprint('alertas', __name__, url_prefix='/alertas')


@alertas_bp.route('/contagem', methods=['GET'])
@login_required
def contagem():
    """Usado pelo polling do header — só o número, para ser bem leve."""
    return jsonify({'total': chatbot_estado.contar_alertas()})


@alertas_bp.route('/listar', methods=['GET'])
@login_required
def listar():
    """Lista completa, usada para preencher o dropdown ao abrir o sininho."""
    return jsonify({'alertas': chatbot_estado.listar_alertas()})


@alertas_bp.route('/<int:alerta_id>/resolver', methods=['POST'])
@login_required
def resolver(alerta_id):
    """
    Remove o alerta da lista — usado tanto por 'Responder' quanto por
    'Responder mais tarde', já que em ambos os casos o alerta não deve
    mais aparecer (a diferença entre os dois botões é só o que o
    JavaScript faz no navegador antes de chamar esta rota: abrir ou não
    o link do WhatsApp).
    """
    chatbot_estado.remover_alerta(alerta_id)
    return jsonify({'status': 'ok'})
