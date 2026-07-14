"""
DESATIVADO — este módulo não é mais importado por app.py nem registrado
como blueprint. Mantido aqui só de referência; para reativar, é preciso
mover chatbot.py e chatbot_estado.py de volta para rotas/ e services/,
restaurar as variáveis WHATSAPP_* em config.py e o registro do blueprint
em app.py.

Chatbot de FAQ + autoatendimento via WhatsApp Cloud API.

Continua sem IA: todo reconhecimento é por palavra-chave fixa ou clique em
botão, nunca por interpretação livre de texto. Zero custo de API externa,
zero risco de resposta inventada.

Fluxo:
  1. Cliente manda qualquer mensagem de texto
     -> bot responde com boas-vindas + menu:
        Horário / Endereço / Agendar Banho / Consultar Meus Dados

  2. Se o texto já contém uma palavra-chave reconhecida (ex: "agendamento"),
     o bot pula direto para a etapa correspondente, sem esperar o clique.

  3. "Consultar Meus Dados" inicia um mini-fluxo com confirmação de
     identidade:
       a) bot localiza o cliente pelo telefone de quem mandou a mensagem
          e pergunta "[Nome] é você?"
       b) Sim  -> menu: Meus Agendamentos / Meus Pacotes / Pendências
          Não  -> encerra o fluxo e orienta a falar com a equipe
       c) cada opção do menu consulta o banco e responde

  Dados sensíveis (valores, datas de vencimento, histórico financeiro)
  NUNCA são enviados por aqui. "Pendências" só informa SE existe pendência
  em aberto, sem valor nem detalhe — quem cobra de fato é a equipe, pelo
  canal que já existe no sistema (ver rotas/whatsapp.py).

Identificação do cliente: o número que chega no webhook (formato
internacional, ex: 5535988117265) é comparado com o telefone cadastrado
usando os últimos 9 dígitos de cada um (ver chave_comparacao_telefone em
utils.py) — tolera cadastros sem DDD ou com máscara, mas significa que
números compartilhados entre pessoas podem encontrar o cliente errado.
A confirmação de identidade ("é você?") existe justamente para mitigar
isso, mas é um clique, não uma autenticação real — por isso o limite do
que é exposto aqui é deliberadamente conservador.

Estado de conversa (em qual etapa cada telefone está) é mantido em
services/chatbot_estado.py, num SQLite separado do banco principal —
ver aquele módulo para o motivo de não usar memória nem o petshop.db.

Rotas:
  GET  /webhook/whatsapp  -> verificação do webhook (handshake da Meta)
  POST /webhook/whatsapp  -> recebimento de mensagens

IMPORTANTE: edite as constantes em "Respostas — edite aqui" para
atualizar horário, endereço, preços e o link de agendamento sem tocar
no resto do código.
"""
import logging
import re
import unicodedata
from datetime import date

import requests
from flask import Blueprint, current_app, jsonify, request

from extensions import csrf
from models import Atendimento, Cliente, Pacote, StatusAtendimento, StatusPacote
from utils import chave_comparacao_telefone

from . import chatbot_estado

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

MSG_MENU_CONTINUACAO = 'Em que posso te ajudar?'

LINK_AGENDAMENTO = '[link do agendamento online]'

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
    'agendar': (
        '✂️🛁 *Agende seu banho ou tosa*\n\n'
        'Acesse o link abaixo para escolher o serviço, ver os preços e '
        'marcar o melhor horário:\n\n'
        f'{LINK_AGENDAMENTO}'
    ),
}

MSG_FALLBACK = (
    'Não entendi sua mensagem. 🐶\n'
    'Toque em uma das opções abaixo ou aguarde que '
    'nossa equipe te responde em breve!'
)

MSG_IDENTIDADE_NEGADA = (
    'Sem problemas! 🐾\n'
    'Foi acionada nossa equipe para te atender pessoalmente. '
    'Aguarde só um instante.'
)

MSG_PEDIR_DUVIDA = (
    'Sem problemas! 🐾 Pode escrever sua dúvida aqui abaixo que '
    'assim que possível alguém da nossa equipe te responde.\n\n'
    'Nosso atendimento é em horário comercial, então se for fora '
    'desse horário a resposta pode demorar um pouquinho — mas '
    'fica tranquilo(a) que vamos te responder! 💛'
)

MSG_DUVIDA_REGISTRADA = (
    'Recebido! 🐾 Sua mensagem já está com a nossa equipe, em breve '
    'alguém te responde por aqui mesmo.'
)

MSG_CLIENTE_NAO_ENCONTRADO = (
    'Não consegui localizar seu cadastro pelo número deste WhatsApp. 🐾\n'
    'Fale com a nossa equipe para verificarmos o telefone cadastrado.'
)

LINK_SITE = 'https://familypetshopp.pythonanywhere.com/insta'

MSG_SAIDA = (
    'Tudo bem! 🐾 Se precisar de algo, é só mandar uma mensagem que '
    'estou à disposição.\n\n'
    'Aproveita e dá uma olhadinha no nosso site — tem nossos trabalhos '
    'e você pode deixar um feedback pra gente também: \n'
    f'{LINK_SITE}'
)

MSG_PERGUNTA_CONTINUAR = 'Posso te ajudar com mais alguma coisa?'

# Palavras-chave reconhecidas em texto livre. Tudo em minúsculo, sem
# acento (ver _normalizar_texto). Cada uma já pula direto para a etapa
# correspondente, sem esperar o cliente tocar no botão.
PALAVRAS_CHAVE = {
    'horario': ('horario de funcionamento', 'que horas', 'horario'),
    'endereco': ('endereco', 'localizacao', 'onde fica', 'fica onde'),
    'agendar': ('agendar', 'marcar banho', 'marcar tosa', 'fazer agendamento'),
    'meus_dados': (
        'meus agendamentos', 'meus pacotes', 'minhas pendencias',
        'consultar meus dados', 'meus dados',
    ),
}

# IDs de botão que reaproveitam o texto fixo de RESPOSTAS
BOTOES_RESPOSTA_DIRETA = {'horario', 'endereco', 'agendar'}

# Palavras que, em QUALQUER etapa do fluxo (mesmo dentro de "meus dados"),
# sempre encerram o que estiver em andamento e voltam ao menu principal.
# Existe para o cliente nunca ficar "presso" num submenu sem saída.
PALAVRAS_SAIDA = (
    'sair', 'voltar', 'menu', 'cancelar', 'encerrar',
    'tchau', 'obrigado', 'obrigada', 'valeu',
)

# Palavra-chave que traz o bot de volta mesmo enquanto ele está em
# silêncio (atendimento humano ativo, ou na 1h de cortesia após o
# atendente finalizar). Existe para o cliente nunca ficar sem saída caso
# queira voltar a falar com o bot antes do silêncio expirar sozinho.
PALAVRA_VOLTAR_AO_BOT = 'rex'


# ---------------------------------------------------------------------------
# Envio de mensagens (Graph API)
# ---------------------------------------------------------------------------

def _enviar_mensagem(payload: dict, direcao: str = 'saida_bot') -> None:
    """Envia uma mensagem via WhatsApp Cloud API (Graph API da Meta).
    direcao: 'saida_bot' (padrão, fluxo automático) ou 'saida_atendente'
    (quando chamada a partir da tela de Conversas)."""
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
        else:
            _registrar_envio_no_historico(payload, direcao)
    except requests.RequestException as e:
        logger.error(f'Falha de rede ao enviar mensagem WhatsApp: {e}')


def _registrar_envio_no_historico(payload: dict, direcao: str) -> None:
    """Extrai telefone e um texto representável do payload enviado, e
    grava no histórico (ver services/chatbot_estado.registrar_mensagem)."""
    telefone = payload.get('to')
    if not telefone:
        return

    if payload.get('type') == 'text':
        conteudo = payload.get('text', {}).get('body', '')
    elif payload.get('type') == 'interactive':
        corpo = payload.get('interactive', {}).get('body', {}).get('text', '')
        botoes = payload.get('interactive', {}).get('action', {}).get('buttons', [])
        titulos = ', '.join(b['reply']['title'] for b in botoes)
        conteudo = f'{corpo} [{titulos}]' if titulos else corpo
    else:
        conteudo = f"[{payload.get('type', '?')}]"

    chatbot_estado.registrar_mensagem(telefone, None, direcao, conteudo)


def _enviar_texto(telefone: str, texto: str, direcao: str = 'saida_bot') -> None:
    _enviar_mensagem({
        'messaging_product': 'whatsapp',
        'to': telefone,
        'type': 'text',
        'text': {'body': texto},
    }, direcao=direcao)


def _enviar_botoes(telefone: str, corpo: str, botoes: list[tuple[str, str]]) -> None:
    """
    botoes: lista de (id, titulo). Máximo 3 — limite da própria API do
    WhatsApp para mensagens interativas do tipo "button".
    """
    _enviar_mensagem({
        'messaging_product': 'whatsapp',
        'to': telefone,
        'type': 'interactive',
        'interactive': {
            'type': 'button',
            'body': {'text': corpo},
            'action': {
                'buttons': [
                    {'type': 'reply', 'reply': {'id': bid, 'title': titulo}}
                    for bid, titulo in botoes
                ]
            },
        },
    })


def _enviar_menu_principal(telefone: str, primeiro_contato: bool = True) -> None:
    texto_corpo = MSG_BOAS_VINDAS if primeiro_contato else MSG_MENU_CONTINUACAO
    _enviar_botoes(telefone, texto_corpo, [
        ('horario', 'Horário'),
        ('endereco', 'Endereço'),
        ('agendar', 'Agendar Banho'),
    ])
    # 4ª opção numa segunda mensagem (limite de 3 botões por mensagem)
    _enviar_botoes(telefone, 'Ou, se preferir:', [
        ('meus_dados', 'Consultar Meus Dados'),
    ])


def _enviar_confirmacao_identidade(telefone: str, cliente: Cliente) -> None:
    _enviar_botoes(
        telefone,
        f'🐾 Encontrei um cadastro em nome de *{cliente.nome_tutor}*. '
        f'É você?',
        [
            ('identidade_sim', 'Sim, sou eu'),
            ('identidade_nao', 'Não'),
        ]
    )


def _enviar_menu_meus_dados(telefone: str) -> None:
    _enviar_botoes(telefone, 'O que você gostaria de consultar?', [
        ('dados_agendamentos', 'Meus Agendamentos'),
        ('dados_pacotes', 'Meus Pacotes'),
        ('dados_pendencias', 'Pendências'),
    ])
    # 4ª opção numa mensagem própria (limite de 3 botões por mensagem).
    _enviar_botoes(telefone, 'Ou:', [
        ('dados_pet_pronto', 'Meu Pet Está Pronto?'),
    ])
    # Saída sempre visível, pra nunca depender só do cliente adivinhar
    # uma palavra de saída.
    _enviar_botoes(telefone, 'Ou, se já for tudo:', [
        ('encerrar', 'Encerrar'),
    ])


def _enviar_pergunta_continuar(telefone: str) -> None:
    """
    Pergunta de fechamento mandada após qualquer resposta de conteúdo
    (horário, endereço, agendar, ou qualquer consulta dentro de 'Meus
    Dados'). 'Sim' leva o cliente de volta a um menu (qual menu depende
    de onde ele veio — ver etapa 'aguardando_continuar:*' no handler de
    estado); 'Não' encerra com a mensagem de despedida.
    """
    _enviar_botoes(telefone, MSG_PERGUNTA_CONTINUAR, [
        ('continuar_sim', 'Sim'),
        ('continuar_nao', 'Não'),
    ])


def _enviar_oferta_atendente(telefone: str, texto_contexto: str) -> None:
    """
    Usada quando o bot bate no limite do que sabe resolver (mensagem não
    reconhecida, ou cliente não encontrado pelo telefone). Pergunta se
    ainda dá para ajudar por aqui mesmo (volta ao menu) ou se o cliente
    prefere falar com a equipe — nesse caso, o próximo passo é capturar
    a dúvida por escrito (ver etapa 'aguardando_texto_duvida').
    """
    _enviar_botoes(telefone, texto_contexto + '\n\n' + MSG_PERGUNTA_CONTINUAR, [
        ('continuar_sim', 'Sim'),
        ('falar_atendente', 'Falar com atendente'),
    ])


# ---------------------------------------------------------------------------
# Reconhecimento de palavra-chave (sem IA — apenas comparação de texto)
# ---------------------------------------------------------------------------

def _normalizar_texto(texto: str) -> str:
    """Minúsculas e sem acento, para comparação tolerante a variação de digitação."""
    sem_acento = unicodedata.normalize('NFKD', texto or '')
    sem_acento = ''.join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def _identificar_palavra_chave(texto: str) -> str | None:
    """Retorna a chave da etapa (ex: 'horario') se alguma palavra bater, senão None."""
    texto_normalizado = _normalizar_texto(texto)
    for etapa, palavras in PALAVRAS_CHAVE.items():
        if any(palavra in texto_normalizado for palavra in palavras):
            return etapa
    return None


def _mensagem_pede_saida(mensagem: dict) -> bool:
    """
    True se a mensagem deve encerrar qualquer fluxo em andamento — seja
    por clicar no botão 'Encerrar', seja por digitar uma palavra de saída.
    """
    if mensagem.get('type') == 'interactive':
        botao_id = mensagem.get('interactive', {}).get('button_reply', {}).get('id')
        return botao_id == 'encerrar'

    if mensagem.get('type') == 'text':
        texto_normalizado = _normalizar_texto(mensagem.get('text', {}).get('body', ''))
        return any(palavra in texto_normalizado for palavra in PALAVRAS_SAIDA)

    return False


def _mensagem_pede_volta_ao_bot(mensagem: dict) -> bool:
    """True se o cliente digitou a palavra-chave 'Rex' — usada para sair
    do silêncio do bot mesmo durante atendimento humano ativo."""
    if mensagem.get('type') != 'text':
        return False
    texto_normalizado = _normalizar_texto(mensagem.get('text', {}).get('body', ''))
    # Remove pontuação antes de separar em palavras, senão "rex," ou
    # "rex!" não bate com a palavra-chave 'rex' exata.
    palavras = re.findall(r'\w+', texto_normalizado)
    return PALAVRA_VOLTAR_AO_BOT in palavras


def _texto_para_historico(mensagem: dict) -> str:
    """Extrai uma representação textual de qualquer tipo de mensagem do
    WhatsApp, para registrar no histórico mesmo quando não é texto puro."""
    tipo = mensagem.get('type')
    if tipo == 'text':
        return mensagem.get('text', {}).get('body', '')
    if tipo == 'interactive':
        botao = mensagem.get('interactive', {}).get('button_reply', {})
        return f"[botão: {botao.get('title', botao.get('id', '?'))}]"
    return f'[{tipo}]'


# ---------------------------------------------------------------------------
# Consultas ao banco (sem IA — apenas SQL determinístico)
# ---------------------------------------------------------------------------

def _buscar_cliente_por_telefone(telefone_whatsapp: str) -> Cliente | None:
    """
    Localiza o Cliente cujo telefone cadastrado combina com o número que
    mandou a mensagem, comparando apenas os últimos 9 dígitos.

    Atenção: telefones compartilhados entre pessoas podem casar com o
    cliente errado — daí a confirmação "é você?" antes de revelar
    qualquer dado, e o limite do que é revelado mesmo após confirmar.
    """
    chave_recebida = chave_comparacao_telefone(telefone_whatsapp)
    if not chave_recebida:
        return None

    candidatos = Cliente.query.filter(Cliente.ativo.is_(True)).all()
    for cliente in candidatos:
        if chave_comparacao_telefone(cliente.telefone) == chave_recebida:
            return cliente
    return None


def _texto_proximos_agendamentos(cliente: Cliente, limite: int = 3) -> str:
    proximos = (
        Atendimento.query
        .filter(
            Atendimento.cliente_id == cliente.id,
            Atendimento.status_presenca == StatusAtendimento.AGENDADO.value,
            Atendimento.data >= date.today(),
        )
        .order_by(Atendimento.data.asc())
        .limit(limite)
        .all()
    )

    if not proximos:
        return (
            f'Não encontrei nenhum agendamento futuro para o(a) '
            f'{cliente.nome_pet}. 🐶\nQuer marcar um horário?'
        )

    linhas = [f'📅 {a.data.strftime("%d/%m/%Y")} — {a.nome_servico}' for a in proximos]
    return (
        f'🐾 Agendamentos do(a) {cliente.nome_pet}:\n\n' + '\n'.join(linhas)
    )


def _texto_pacotes_ativos(cliente: Cliente) -> str:
    pacotes = (
        Pacote.query
        .filter(
            Pacote.cliente_id == cliente.id,
            Pacote.status == StatusPacote.ATIVO.value,
        )
        .all()
    )

    if not pacotes:
        return f'O(a) {cliente.nome_pet} não tem pacotes ativos no momento.'

    linhas = [
        f'📦 {p.nome_servico} — {p.creditos_usados}/{p.creditos_totais} créditos usados'
        for p in pacotes
    ]
    return f'🐾 Pacotes ativos do(a) {cliente.nome_pet}:\n\n' + '\n'.join(linhas)


def _texto_pendencias(cliente: Cliente) -> str:
    # Reaproveita a regra de negócio já existente no model (10+ dias de
    # atraso), em vez de duplicar a lógica aqui.
    if cliente.tem_divida_atrasada:
        return (
            'Encontrei pendências em aberto no seu cadastro. 🐾\n'
            'Nossa equipe vai entrar em contato para regularizar — '
            'qualquer dúvida, pode falar com a gente por aqui mesmo!'
        )
    return 'Nenhuma pendência em aberto no seu cadastro. Tudo certo! ✅'


def _texto_pet_pronto(cliente: Cliente) -> str:
    """
    Responde se o(s) pet(s) do cliente que estão no petshop hoje já
    terminaram o serviço. Só considera atendimentos de hoje com
    status_presenca == 'Presente' — isto é, o pet já chegou e ainda
    está sendo atendido (ou já terminou).
    """
    atendimentos_hoje = (
        Atendimento.query
        .filter(
            Atendimento.cliente_id == cliente.id,
            Atendimento.data == date.today(),
            Atendimento.status_presenca == StatusAtendimento.PRESENTE.value,
        )
        .all()
    )

    if not atendimentos_hoje:
        return (
            f'Não encontrei nenhum atendimento do(a) {cliente.nome_pet} '
            f'em andamento hoje no petshop. 🐶'
        )

    prontos = [a for a in atendimentos_hoje if a.pronto_para_buscar]
    em_andamento = [a for a in atendimentos_hoje if not a.pronto_para_buscar]

    if prontos and not em_andamento:
        return f'🎉 Sim! O(a) {cliente.nome_pet} já está pronto(a) para buscar!'

    if em_andamento and not prontos:
        return f'Ainda não! O(a) {cliente.nome_pet} ainda está em atendimento. 🛁'

    # Caso raro: mais de um atendimento hoje, com status misto
    return (
        f'O(a) {cliente.nome_pet} tem mais de um atendimento hoje: '
        f'{len(prontos)} já pronto(s) e {len(em_andamento)} ainda em '
        f'andamento. Fale com a equipe para mais detalhes.'
    )


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


def _iniciar_consulta_meus_dados(telefone: str) -> None:
    cliente = _buscar_cliente_por_telefone(telefone)
    if not cliente:
        chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_principal')
        _enviar_oferta_atendente(telefone, MSG_CLIENTE_NAO_ENCONTRADO)
        return

    chatbot_estado.definir_etapa(telefone, 'aguardando_confirmacao_identidade', cliente.id)
    _enviar_confirmacao_identidade(telefone, cliente)


def _tratar_resposta_com_estado(telefone: str, mensagem: dict, etapa: str, cliente_id: int) -> None:
    """Trata a mensagem quando o telefone está no meio do fluxo de 'meus dados'."""
    if etapa == 'aguardando_confirmacao_identidade':
        if mensagem.get('type') != 'interactive':
            # Cliente digitou texto em vez de tocar no botão — não
            # adivinha, repete a pergunta de confirmação.
            cliente = Cliente.query.get(cliente_id)
            if cliente:
                _enviar_confirmacao_identidade(telefone, cliente)
            return

        botao_id = mensagem['interactive']['button_reply']['id']
        if botao_id == 'identidade_sim':
            chatbot_estado.definir_etapa(telefone, 'menu_meus_dados', cliente_id)
            _enviar_menu_meus_dados(telefone)
        else:
            chatbot_estado.limpar_estado(telefone)
            _enviar_texto(telefone, MSG_IDENTIDADE_NEGADA)
        return

    if etapa == 'menu_meus_dados':
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_principal')
            _enviar_oferta_atendente(telefone, MSG_CLIENTE_NAO_ENCONTRADO)
            return

        if mensagem.get('type') != 'interactive':
            _enviar_menu_meus_dados(telefone)
            return

        botao_id = mensagem['interactive']['button_reply']['id']
        if botao_id == 'dados_agendamentos':
            _enviar_texto(telefone, _texto_proximos_agendamentos(cliente))
        elif botao_id == 'dados_pacotes':
            _enviar_texto(telefone, _texto_pacotes_ativos(cliente))
        elif botao_id == 'dados_pendencias':
            _enviar_texto(telefone, _texto_pendencias(cliente))
        elif botao_id == 'dados_pet_pronto':
            _enviar_texto(telefone, _texto_pet_pronto(cliente))
        else:
            _enviar_menu_meus_dados(telefone)
            return
        # Após entregar a resposta, pergunta se o cliente quer continuar
        # (volta para este mesmo menu de dados se disser Sim) em vez de
        # simplesmente reenviar o menu ou ficar mudo.
        chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_dados', cliente_id)
        _enviar_pergunta_continuar(telefone)
        return

    if etapa.startswith('aguardando_continuar:'):
        destino = etapa.split(':', 1)[1]  # 'menu_dados' ou 'menu_principal'

        if mensagem.get('type') != 'interactive':
            # Texto livre em vez de um dos botões -> repete a pergunta
            _enviar_pergunta_continuar(telefone)
            return

        botao_id = mensagem['interactive']['button_reply']['id']
        if botao_id == 'continuar_sim':
            if destino == 'menu_dados':
                chatbot_estado.definir_etapa(telefone, 'menu_meus_dados', cliente_id)
                _enviar_menu_meus_dados(telefone)
            else:
                chatbot_estado.limpar_estado(telefone)
                _enviar_menu_principal(telefone, primeiro_contato=False)
        elif botao_id == 'falar_atendente':
            # Guarda o destino de 'voltar' para o caso do cliente ter
            # clicado errado (ver etapa 'aguardando_texto_duvida').
            chatbot_estado.definir_etapa(telefone, f'aguardando_texto_duvida:{destino}', cliente_id)
            _enviar_botoes(telefone, MSG_PEDIR_DUVIDA, [
                ('voltar_menu', 'Voltar ao menu'),
            ])
        else:
            chatbot_estado.limpar_estado(telefone)
            _enviar_texto(telefone, MSG_SAIDA)
        return

    if etapa.startswith('aguardando_texto_duvida:'):
        destino = etapa.split(':', 1)[1]

        if mensagem.get('type') == 'interactive':
            botao_id = mensagem['interactive']['button_reply']['id']
            if botao_id == 'voltar_menu':
                if destino == 'menu_dados':
                    chatbot_estado.definir_etapa(telefone, 'menu_meus_dados', cliente_id)
                    _enviar_menu_meus_dados(telefone)
                else:
                    chatbot_estado.limpar_estado(telefone)
                    _enviar_menu_principal(telefone, primeiro_contato=False)
            else:
                # Botão desconhecido nesse contexto -> repete a oferta
                _enviar_botoes(telefone, MSG_PEDIR_DUVIDA, [
                    ('voltar_menu', 'Voltar ao menu'),
                ])
            return

        if mensagem.get('type') == 'text':
            texto_duvida = mensagem.get('text', {}).get('body', '').strip()
            nome_cliente = None
            if cliente_id:
                cliente_existente = Cliente.query.get(cliente_id)
                if cliente_existente:
                    nome_cliente = cliente_existente.nome_tutor

            chatbot_estado.criar_alerta(telefone, nome_cliente, texto_duvida)
            chatbot_estado.limpar_estado(telefone)
            _enviar_texto(telefone, MSG_DUVIDA_REGISTRADA)
            return

        # Tipo de mensagem que não é texto nem botão (ex: áudio, imagem)
        # enquanto se espera a dúvida escrita -> orienta a escrever.
        _enviar_botoes(telefone, MSG_PEDIR_DUVIDA, [
            ('voltar_menu', 'Voltar ao menu'),
        ])
        return


def _tratar_resposta_sem_estado(telefone: str, mensagem: dict) -> None:
    """Trata a mensagem quando não há fluxo de 'meus dados' em andamento."""
    if mensagem['type'] == 'interactive':
        botao_id = mensagem['interactive']['button_reply']['id']
        if botao_id == 'meus_dados':
            _iniciar_consulta_meus_dados(telefone)
        elif botao_id in BOTOES_RESPOSTA_DIRETA:
            _enviar_texto(telefone, RESPOSTAS[botao_id])
            chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_principal')
            _enviar_pergunta_continuar(telefone)
        else:
            chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_principal')
            _enviar_oferta_atendente(telefone, MSG_FALLBACK)
        return

    if mensagem['type'] == 'text':
        texto_recebido = mensagem.get('text', {}).get('body', '')
        etapa = _identificar_palavra_chave(texto_recebido)

        if etapa == 'meus_dados':
            _iniciar_consulta_meus_dados(telefone)
        elif etapa in BOTOES_RESPOSTA_DIRETA:
            _enviar_texto(telefone, RESPOSTAS[etapa])
            chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_principal')
            _enviar_pergunta_continuar(telefone)
        else:
            # Sem palavra-chave reconhecida -> menu completo
            _enviar_menu_principal(telefone)
        return

    chatbot_estado.definir_etapa(telefone, 'aguardando_continuar:menu_principal')
    _enviar_oferta_atendente(telefone, MSG_FALLBACK)


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

        chatbot_estado.registrar_mensagem(
            telefone, None, 'entrada', _texto_para_historico(mensagem)
        )

        if chatbot_estado.bot_em_silencio(telefone):
            if _mensagem_pede_volta_ao_bot(mensagem):
                # 'Rex' traz o bot de volta mesmo durante o silêncio —
                # mas só some o silêncio, não interfere no atendimento
                # humano ativo de verdade: se o atendente ainda estiver
                # com a conversa aberta (clicou Atender, não finalizou),
                # a tela de Conversas continua mostrando normalmente,
                # só o webhook volta a responder por aqui.
                pass
            else:
                # Bot fica quieto: a mensagem já foi registrada no
                # histórico acima, é só isso que a tela de Conversas
                # precisa para mostrar a conversa em andamento.
                return jsonify({'status': 'em_atendimento_humano'}), 200

        estado = chatbot_estado.obter_estado(telefone)

        # Enquanto o cliente está escrevendo a dúvida para a equipe, todo
        # texto livre é capturado como o conteúdo da dúvida — mesmo que
        # contenha palavras como 'tchau' ou 'obrigado' (perfeitamente
        # plausíveis numa reclamação real). Só um botão explícito (ex:
        # 'Voltar ao menu') deve interromper esse fluxo, não uma
        # palavra-chave de saída interpretada por engano.
        aguardando_duvida_em_texto = (
            estado and estado[0].startswith('aguardando_texto_duvida:')
            and mensagem.get('type') == 'text'
        )

        if not aguardando_duvida_em_texto and _mensagem_pede_saida(mensagem):
            chatbot_estado.limpar_estado(telefone)
            _enviar_texto(telefone, MSG_SAIDA)
            return jsonify({'status': 'recebido'}), 200

        if estado:
            etapa, cliente_id = estado
            _tratar_resposta_com_estado(telefone, mensagem, etapa, cliente_id)
        else:
            _tratar_resposta_sem_estado(telefone, mensagem)

    except (KeyError, IndexError) as e:
        logger.warning(f'Payload inesperado do webhook WhatsApp: {e}')

    return jsonify({'status': 'recebido'}), 200
