"""
Chatbot de FAQ via WhatsApp Cloud API.

Responde automaticamente perguntas repetitivas (horário, endereço, preços)
usando botões interativos nativos do WhatsApp — sem texto livre, sem IA,
sem ambiguidade.

Fluxo:
  1. Cliente manda QUALQUER mensagem de texto
     -> bot responde com 3 botões: Horário / Endereço / Preços
  2. Cliente TOCA em um botão
     -> bot responde com a informação fixa correspondente

Rotas:
  GET  /webhook/whatsapp  -> verificação do webhook (handshake da Meta)
  POST /webhook/whatsapp  -> recebimento de mensagens

IMPORTANTE: edite as constantes em "Respostas — edite aqui" para
atualizar horário, endereço e preços sem tocar no resto do código.
"""
import logging

import requests
from flask import Blueprint, current_app, jsonify, request
from extensions import csrf

logger = logging.getLogger(__name__)
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/webhook')

GRAPH_API_VERSION = 'v21.0'

# ---------------------------------------------------------------------------
# Respostas — edite aqui para atualizar as informações do petshop
# ---------------------------------------------------------------------------

MSG_BOAS_VINDAS = (
    '🐾 Olá! Bem-vindo(a) ao *Family Pet Shop*!\n'
    'Em que posso te ajudar?'
)

RESPOSTAS = {
    'horario': (
        '🕐 *Nosso horário de atendimento:*\n\n'
        'Segunda a sexta: 08h às 18h\n'
        'Sábado: 08h às 13h\n'
        'Domingo: fechado'
    ),
    'endereco': (
        '📍 *Nosso endereço:*\n\n'
        'Rua Exemplo, 123 - Centro\n'
        'Três Pontas - MG\n\n'
        'https://maps.google.com/?q=Rua+Exemplo+123+Tres+Pontas+MG'
    ),
    'precos': (
        '💰 *Nossos preços (a partir de):*\n\n'
        '🛁 Banho: R$ 40,00\n'
        '✂️ Tosa: R$ 60,00\n'
        '🛁✂️ Banho + Tosa: R$ 90,00\n\n'
        'O valor final pode variar conforme porte e raça do pet. '
        'Quer agendar? Acesse: [link do agendamento online]'
    ),
}

MSG_FALLBACK = (
    'Não entendi sua mensagem. 🐶\n'
    'Toque em uma das opções abaixo ou aguarde que '
    'nossa equipe te responde em breve!'
)


# ---------------------------------------------------------------------------
# Envio de mensagens (Graph API)
# ---------------------------------------------------------------------------

def _enviar_mensagem(payload: dict) -> None:
    """Envia uma mensagem via WhatsApp Cloud API (Graph API da Meta)."""
    token = current_app.config.get('WHATSAPP_TOKEN')
    phone_id = current_app.config.get('WHATSAPP_PHONE_NUMBER_ID')

    if not token or not phone_id:
        logger.error('WHATSAPP_TOKEN ou WHATSAPP_PHONE_NUMBER_ID não configurados.')
        return

    url = f'https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_id}/messages'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code >= 400:
            logger.error(f'Erro ao enviar mensagem WhatsApp: {resp.status_code} - {resp.text}')
    except requests.RequestException as e:
        logger.error(f'Falha de rede ao enviar mensagem WhatsApp: {e}')


def _enviar_texto(telefone: str, texto: str) -> None:
    _enviar_mensagem({
        'messaging_product': 'whatsapp',
        'to': telefone,
        'type': 'text',
        'text': {'body': texto},
    })


def _enviar_botoes_boas_vindas(telefone: str) -> None:
    _enviar_mensagem({
        'messaging_product': 'whatsapp',
        'to': telefone,
        'type': 'interactive',
        'interactive': {
            'type': 'button',
            'body': {'text': MSG_BOAS_VINDAS},
            'action': {
                'buttons': [
                    {'type': 'reply', 'reply': {'id': 'horario', 'title': 'Horário'}},
                    {'type': 'reply', 'reply': {'id': 'endereco', 'title': 'Endereço'}},
                    {'type': 'reply', 'reply': {'id': 'precos', 'title': 'Preços'}},
                ]
            },
        },
    })


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@chatbot_bp.route('/whatsapp', methods=['GET'])
def verificar_webhook():
    """
    Handshake exigido pela Meta ao configurar o webhook no painel.
    A Meta chama essa rota uma única vez (e sempre que você reconfigurar).
    """
    verify_token = current_app.config.get('WHATSAPP_VERIFY_TOKEN')

    modo = request.args.get('hub.mode')
    token_recebido = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if modo == 'subscribe' and token_recebido == verify_token:
        logger.info('Webhook do WhatsApp verificado com sucesso.')
        return challenge, 200

    logger.warning('Tentativa de verificação de webhook com token inválido.')
    return 'Token de verificação inválido', 403


@chatbot_bp.route('/whatsapp', methods=['POST'])
@csrf.exempt
def receber_mensagem():
    """
    Recebe eventos de mensagens enviadas pelos clientes via WhatsApp.
    Sempre responde 200 rapidamente (a Meta reenvia se não receber 200).
    """
    dados = request.get_json(silent=True) or {}

    try:
        entrada = dados['entry'][0]['changes'][0]['value']
        mensagens = entrada.get('messages')

        if not mensagens:
            # Pode ser um evento de status (entregue/lido), não uma mensagem nova
            return jsonify({'status': 'ignorado'}), 200

        mensagem = mensagens[0]
        telefone = mensagem['from']

        if mensagem['type'] == 'interactive':
            botao_id = mensagem['interactive']['button_reply']['id']
            resposta = RESPOSTAS.get(botao_id, MSG_FALLBACK)
            _enviar_texto(telefone, resposta)

        elif mensagem['type'] == 'text':
            # Texto livre -> sempre manda o menu de botões (sem tentar interpretar)
            _enviar_botoes_boas_vindas(telefone)

        else:
            _enviar_texto(telefone, MSG_FALLBACK)

    except (KeyError, IndexError) as e:
        logger.warning(f'Payload inesperado do webhook WhatsApp: {e}')

    return jsonify({'status': 'recebido'}), 200
