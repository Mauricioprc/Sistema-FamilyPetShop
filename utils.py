import calendar
import locale
import os
import uuid
import logging
from datetime import timedelta, date, datetime
from werkzeug.utils import secure_filename
from typing import Optional, Set

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURAÇÃO DE LOCALE
# ============================================

def configurar_locale():
    """Configurar locale para português brasileiro"""
    locales_disponiveis = [
        'pt_BR.UTF-8',
        'pt_BR.utf8',
        'Portuguese_Brazil.1252',
        'pt_BR'
    ]
    
    for loc in locales_disponiveis:
        try:
            locale.setlocale(locale.LC_ALL, loc)
            logger.info(f"Locale configurado: {loc}")
            return
        except locale.Error:
            continue
    
    logger.warning("Locale pt_BR não encontrado. Usando locale padrão.")


# ============================================
# FORMATAÇÃO DE MOEDA
# ============================================

def format_currency(value: Optional[float]) -> str:
    """
    Formatar valor para moeda brasileira
    
    Args:
        value: Valor a formatar
        
    Returns:
        String formatada como moeda (R$ X.XXX,XX)
    """
    if value is None or value == 0:
        return "R$ 0,00"
    
    try:
        return locale.format_string("R$ %.2f", value, grouping=True)
    except Exception as e:
        logger.error(f"Erro ao formatar moeda: {e}")
        return f"R$ {value:.2f}"


def parse_preco(valor_str: str) -> float:
    """
    Converter string de preço para float
    
    Args:
        valor_str: String com preço (ex: "R$ 1.250,50")
        
    Returns:
        Float com o valor ou 0.0 se inválido
    """
    if not valor_str or not isinstance(valor_str, str):
        return 0.0

    try:
        limpo = valor_str.replace('R$', '').strip()

        # Detectar formato brasileiro (com vírgula decimal) vs ponto decimal
        tem_virgula = ',' in limpo
        tem_ponto = '.' in limpo

        if tem_virgula:
            # Formato brasileiro: 1.250,50 ou 50,00
            limpo = limpo.replace('.', '').replace(',', '.')
        # Se só tem ponto (50.00 ou 1250.50), mantém como está

        resultado = float(limpo) if limpo else 0.0
        return max(0.0, resultado)
    except (ValueError, AttributeError) as e:
        logger.warning(f"Erro ao fazer parse de preco '{valor_str}': {e}")
        return 0.0


# ============================================
# VALIDAÇÃO E UPLOAD DE ARQUIVOS
# ============================================

def allowed_file(filename: str, allowed_extensions: Set[str]) -> bool:
    """
    Verificar se arquivo é permitido
    
    Args:
        filename: Nome do arquivo
        allowed_extensions: Set de extensões permitidas
        
    Returns:
        True se arquivo é permitido, False caso contrário
    """
    if not filename or '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_extensions


def validar_imagem(file, max_size_mb: int = 5) -> Optional[str]:
    """
    Validar arquivo de imagem com verificações de segurança
    
    Args:
        file: Arquivo enviado (Flask FileStorage)
        max_size_mb: Tamanho máximo em MB
        
    Returns:
        Mensagem de erro ou None se válido
    """
    if not file:
        return "Nenhum arquivo foi enviado."
    
    if file.filename == '':
        return "Nome do arquivo vazio."
    
    # Validar extensão
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if not allowed_file(file.filename, allowed_extensions):
        return f"Tipo de arquivo inválido. Permitidos: {', '.join(allowed_extensions)}"
    
    # Validar tamanho
    max_size_bytes = max_size_mb * 1024 * 1024
    file.seek(0, os.SEEK_END)
    tamanho = file.tell()
    file.seek(0)
    
    if tamanho > max_size_bytes:
        return f"Arquivo muito grande. Máximo: {max_size_mb}MB"
    
    # Verificar magic bytes (tipo MIME real)
    magic_bytes = file.read(32)
    file.seek(0)
    
    # Definir assinaturas conhecidas
    assinaturas = {
        b'\xFF\xD8\xFF': 'jpg',      # JPEG
        b'\x89PNG\r\n': 'png',        # PNG
        b'GIF87a': 'gif',             # GIF87a
        b'GIF89a': 'gif',             # GIF89a
        b'RIFF': 'webp',              # WEBP (simplificado)
    }
    
    tipo_detectado = None
    for assinatura, tipo in assinaturas.items():
        if magic_bytes.startswith(assinatura):
            tipo_detectado = tipo
            break
    
    if not tipo_detectado:
        logger.warning(f"Tipo MIME não validado para arquivo: {file.filename}")
        return "Tipo de arquivo não reconhecido como imagem válida."
    
    return None


def salvar_imagem(file, upload_folder: str, allowed_extensions: Set[str]) -> Optional[str]:
    """
    Salvar arquivo de imagem com nome único
    
    Args:
        file: Arquivo enviado (Flask FileStorage)
        upload_folder: Pasta para salvar arquivo
        allowed_extensions: Set de extensões permitidas
        
    Returns:
        Nome do arquivo salvo ou None se falhou
    """
    # Validar arquivo
    erro = validar_imagem(file)
    if erro:
        logger.warning(f"Erro ao validar imagem: {erro}")
        return None
    
    try:
        # Extrair extensão
        filename_seguro = secure_filename(file.filename)
        if '.' not in filename_seguro:
            logger.error(f"Filename sem extensão: {file.filename}")
            return None
        
        ext = filename_seguro.rsplit('.', 1)[1].lower()
        
        # Gerar nome único
        nome_unico = f"{uuid.uuid4().hex}.{ext}"
        
        # Garantir pasta existe
        os.makedirs(upload_folder, exist_ok=True)
        
        # Salvar arquivo
        caminho_completo = os.path.join(upload_folder, nome_unico)
        file.save(caminho_completo)
        
        logger.info(f"Imagem salva com sucesso: {nome_unico}")
        return nome_unico
        
    except Exception as e:
        logger.error(f"Erro ao salvar imagem: {e}")
        return None


# ============================================
# FUNÇÕES DE DATA/HORA
# ============================================

def parse_date_param(data_str: str, default: Optional[date] = None) -> date:
    """
    Fazer parse de parâmetro de data com tratamento de erro
    
    Args:
        data_str: String com data (formato: %Y-%m-%d)
        default: Data padrão se parsing falha
        
    Returns:
        Data ou data padrão/hoje
    """
    if not data_str:
        return default or date.today()
    
    try:
        return datetime.strptime(data_str, '%Y-%m-%d').date()
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao fazer parse de data '{data_str}': {e}")
        return default or date.today()


def calcular_datas_pacote(
    data_inicio: date,
    creditos_totais: int,
    tipo_agendamento: str,
    dia_semana: int
) -> list:
    """
    Calcular datas de atendimento para novo pacote
    
    Args:
        data_inicio: Data inicial do pacote
        creditos_totais: Total de créditos
        tipo_agendamento: 'semanal' ou 'quinzenal'
        dia_semana: Dia da semana (0=seg, 6=dom)
        
    Returns:
        Lista de datas para agendamentos
    """
    try:
        dias_a_frente = dia_semana - data_inicio.weekday()
        if dias_a_frente < 0:
            dias_a_frente += 7
        
        proxima = data_inicio + timedelta(days=dias_a_frente)
        pulo = timedelta(weeks=1) if tipo_agendamento == 'semanal' else timedelta(weeks=2)
        
        return [proxima + pulo * i for i in range(creditos_totais)]
    except Exception as e:
        logger.error(f"Erro ao calcular datas do pacote: {e}")
        return []


def calcular_datas_renovacao(
    ultima_data: date,
    creditos_totais: int,
    tipo_agendamento: str,
    dia_semana_fixo: int
) -> list:
    """
    Calcular datas de atendimento para renovação de pacote
    
    Args:
        ultima_data: Última data do pacote anterior
        creditos_totais: Total de créditos para nova renovação
        tipo_agendamento: 'semanal' ou 'quinzenal'
        dia_semana_fixo: Dia da semana fixo (0=seg, 6=dom)
        
    Returns:
        Lista de datas para agendamentos
    """
    try:
        dias_a_frente = dia_semana_fixo - ultima_data.weekday()
        if dias_a_frente <= 0:
            dias_a_frente += 7
        
        proxima = ultima_data + timedelta(days=dias_a_frente)
        
        if tipo_agendamento == 'quinzenal':
            proxima += timedelta(weeks=1)
        
        pulo = timedelta(weeks=1) if tipo_agendamento == 'semanal' else timedelta(weeks=2)
        
        return [proxima + pulo * i for i in range(creditos_totais)]
    except Exception as e:
        logger.error(f"Erro ao calcular datas de renovação: {e}")
        return []


def proximo_vencimento_mensal(data_anterior: date) -> date:
    """
    Retorna o mesmo dia do mes seguinte a data_anterior. Se o mes
    seguinte nao tiver esse dia (ex: dia 31 em fevereiro), usa o
    ultimo dia daquele mes.
    """
    ano = data_anterior.year + (1 if data_anterior.month == 12 else 0)
    mes = 1 if data_anterior.month == 12 else data_anterior.month + 1
    ultimo_dia_mes = calendar.monthrange(ano, mes)[1]
    dia = min(data_anterior.day, ultimo_dia_mes)
    return date(ano, mes, dia)


# ============================================
# GERENCIAMENTO DE CRÉDITOS
# ============================================

def consumir_credito(pacote) -> bool:
    """
    Consumir crédito de um pacote
    
    Args:
        pacote: Objeto Pacote
        
    Returns:
        True se pacote foi concluído agora, False caso contrário
    """
    if pacote.creditos_usados >= pacote.creditos_totais:
        return False
    
    pacote.creditos_usados += 1
    
    if pacote.creditos_usados >= pacote.creditos_totais:
        pacote.status = 'Concluido'
        return True
    
    return False


def devolver_credito(pacote) -> None:
    """
    Devolver crédito para um pacote
    
    Args:
        pacote: Objeto Pacote
    """
    if pacote.creditos_usados > 0:
        pacote.creditos_usados -= 1
    
    if pacote.status == 'Concluido':
        pacote.status = 'Ativo'


# ============================================
# TELEFONE/WHATSAPP
# ============================================

def formatar_telefone_whatsapp(telefone: str) -> str:
    """
    Formatar telefone para padrão WhatsApp
    
    Args:
        telefone: Telefone com formatação livre
        
    Returns:
        Telefone formatado para WhatsApp (ex: 5511999887766)
    """
    try:
        # Remover tudo que não é dígito
        numero = ''.join(filter(str.isdigit, telefone))
        
        # Adicionar código do país se não houver
        if not numero.startswith('55'):
            numero = '55' + numero
        
        return numero
    except Exception as e:
        logger.error(f"Erro ao formatar telefone: {e}")
        return telefone


def chave_comparacao_telefone(telefone: str, digitos: int = 9) -> str:
    """
    Extrai os últimos N dígitos de um telefone para fins de comparação.

    Usada para casar o número que chega no webhook do WhatsApp (formato
    internacional completo, ex: 5535988117265) com o telefone salvo no
    cadastro do cliente — que no banco real está em formatos inconsistentes
    (com/sem DDD, com/sem máscara, às vezes só 9 dígitos).

    Comparar apenas os últimos dígitos evita depender de DDI/DDD estarem
    presentes ou formatados igual nos dois lados.

    Args:
        telefone: Telefone em qualquer formato
        digitos: Quantidade de dígitos finais a manter (padrão 9, cobre
                 celular com nono dígito sem DDD)

    Returns:
        String com os últimos `digitos` dígitos, ou string vazia se o
        telefone não tiver dígitos suficientes para uma comparação confiável.
    """
    numero = ''.join(filter(str.isdigit, telefone or ''))
    if len(numero) < digitos:
        return ''
    return numero[-digitos:]


def validar_telefone(telefone: str) -> bool:
    """
    Validar se telefone tem formato mínimo válido
    
    Args:
        telefone: Telefone a validar
        
    Returns:
        True se válido, False caso contrário
    """
    try:
        numero = ''.join(filter(str.isdigit, telefone))
        # Mínimo 10 dígitos (2 DDD + 8 dígitos) ou 11 com nono dígito (celular)
        return len(numero) >= 10
    except:
        return False