"""
Tela de Conversas: inbox simplificado para a equipe responder o cliente
manualmente pelo mesmo número do bot, sem depender de WhatsApp
Coexistence (que exige um provedor BSP pago — ver discussão no chat com
o desenvolvedor; decidiu-se não contratar por ora).

Como funciona:
  - Lista as conversas de hoje, mais qualquer alerta de atendente ainda
    pendente de dias anteriores (ver services/chatbot_estado).
  - Ao abrir uma conversa, mostra o histórico do dia e permite enviar
    mensagem livre, que sai pela mesma WhatsApp Cloud API do bot
    (rotas/chatbot.py:_enviar_texto) — então o cliente nunca recebe a
    resposta de um número diferente do bot.
  - 'Atender': bot fica em silêncio para aquele telefone enquanto a
    equipe conversa manualmente.
  - 'Finalizar atendimento': bot continua em silêncio por mais 1h
    (cortesia, evita o bot interromper uma última mensagem do cliente),
    depois volta a responder normalmente.
  - Cliente pode digitar 'Rex' para trazer o bot de volta antes disso,
    sem precisar esperar a equipe finalizar.
"""
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from services import chatbot_estado

conversas_bp = Blueprint('conversas', __name__, url_prefix='/conversas')


@conversas_bp.route('/', methods=['GET'])
@login_required
def listar():
    """Tela principal — a lista de conversas em si é carregada via JS
    (ver /conversas/lista), igual ao padrão já usado pelo sininho de
    alertas em base.html."""
    return render_template('conversas.html')


@conversas_bp.route('/lista', methods=['GET'])
@login_required
def lista_json():
    conversas_hoje = chatbot_estado.listar_conversas_do_dia()
    telefones_hoje = {c['telefone'] for c in conversas_hoje}

    # Alertas pendentes de qualquer dia que ainda não apareceram na
    # lista de hoje (ex: pedido de ontem, ainda não respondido).
    pendentes_antigos = [
        a for a in chatbot_estado.listar_alertas()
        if a['telefone'] not in telefones_hoje
    ]

    for a in pendentes_antigos:
        conversas_hoje.append({
            'telefone': a['telefone'],
            'ultima_mensagem_em': a['criado_em'],
            'nome_cliente': a['nome_cliente'],
        })

    conversas_hoje.sort(key=lambda c: c['ultima_mensagem_em'], reverse=True)

    # Enriquece cada conversa com o status de atendimento, para a lista
    # já mostrar se está em atendimento ativo, em silêncio de cortesia,
    # ou livre — sem precisar abrir cada uma para saber.
    for c in conversas_hoje:
        c['atendimento_ativo'] = chatbot_estado.atendimento_ativo(c['telefone'])
        c['bot_em_silencio'] = chatbot_estado.bot_em_silencio(c['telefone'])
        c['tem_alerta_pendente'] = any(
            a['telefone'] == c['telefone'] for a in chatbot_estado.listar_alertas()
        )

    return jsonify({'conversas': conversas_hoje})


@conversas_bp.route('/<telefone>/historico', methods=['GET'])
@login_required
def historico(telefone):
    return jsonify({
        'mensagens': chatbot_estado.historico_do_dia(telefone),
        'atendimento_ativo': chatbot_estado.atendimento_ativo(telefone),
        'bot_em_silencio': chatbot_estado.bot_em_silencio(telefone),
    })


@conversas_bp.route('/<telefone>/enviar', methods=['POST'])
@login_required
def enviar(telefone):
    texto = (request.get_json(silent=True) or {}).get('texto', '').strip()
    if not texto:
        return jsonify({'status': 'erro', 'mensagem': 'Texto vazio'}), 400

    # Import local para evitar import circular (chatbot.py também
    # importa deste módulo de rotas indiretamente via app.py).
    from rotas.chatbot import _enviar_texto
    _enviar_texto(telefone, texto, direcao='saida_atendente')

    return jsonify({'status': 'ok'})


@conversas_bp.route('/<telefone>/atender', methods=['POST'])
@login_required
def atender(telefone):
    chatbot_estado.assumir_atendimento(telefone)
    chatbot_estado.remover_alertas_do_telefone(telefone)
    return jsonify({'status': 'ok'})


@conversas_bp.route('/<telefone>/finalizar', methods=['POST'])
@login_required
def finalizar(telefone):
    chatbot_estado.finalizar_atendimento(telefone)
    return jsonify({'status': 'ok'})
