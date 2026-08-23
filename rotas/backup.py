"""
Blueprint de backup do banco de dados.

Disponibiliza:
- GET /backup/status   -> verifica se já passou 1 dia desde o último backup
- GET /backup/download -> baixa o petshop.db, envia uma cópia para o Google
  Drive (se configurado) e marca a data do backup como "hoje"

Existe porque em produção (PythonAnywhere Free) não há como agendar uma
tarefa automática (Tasks é recurso pago) — então o próprio sistema lembra
o usuário logado, todo dia, de clicar para gerar o backup.

O controle de "última data de backup" é guardado em instance/last_backup.json
(arquivo simples, não precisa de tabela no banco).
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Blueprint, current_app, jsonify, send_file
from flask_login import login_required

from utils import enviar_backup_para_drive

logger = logging.getLogger(__name__)
backup_bp = Blueprint('backup', __name__, url_prefix='/backup')

INTERVALO_DIAS = 1


def _arquivo_controle() -> Path:
    """Caminho do arquivo que guarda a data do último backup."""
    return Path(current_app.instance_path) / 'last_backup.json'


def _ler_ultimo_backup() -> Optional[datetime]:
    arquivo = _arquivo_controle()
    if not arquivo.exists():
        return None
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
        return datetime.fromisoformat(dados['ultimo_backup'])
    except Exception as e:
        logger.warning(f'Erro ao ler last_backup.json: {e}')
        return None


def _registrar_backup_agora() -> None:
    arquivo = _arquivo_controle()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    dados = {'ultimo_backup': datetime.now().isoformat()}
    arquivo.write_text(json.dumps(dados), encoding='utf-8')


@backup_bp.route('/status')
@login_required
def status():
    """
    Retorna se já é hora de avisar o usuário para fazer backup.
    Se nunca foi feito um backup, já considera que está na hora.
    """
    ultimo = _ler_ultimo_backup()

    if ultimo is None:
        return jsonify({
            'precisa_backup': True,
            'dias_desde_ultimo': None
        })

    dias_passados = (datetime.now() - ultimo).days
    precisa = dias_passados >= INTERVALO_DIAS

    return jsonify({
        'precisa_backup': precisa,
        'dias_desde_ultimo': dias_passados
    })


@backup_bp.route('/download')
@login_required
def download():
    """
    Envia o arquivo petshop.db para download, envia uma cópia para o
    Google Drive (se GOOGLE_SERVICE_ACCOUNT_FILE/GOOGLE_DRIVE_FOLDER_ID
    estiverem configurados) e marca o backup como feito hoje.
    """
    db_path = Path(current_app.instance_path) / 'petshop.db'

    if not db_path.exists():
        logger.error(f'Arquivo de banco nao encontrado em {db_path}')
        return jsonify({'erro': 'Banco de dados nao encontrado.'}), 404

    _registrar_backup_agora()

    nome_arquivo = f"backup_petshop_{datetime.now().strftime('%Y-%m-%d_%H%M')}.db"
    logger.info(f'Backup do banco baixado: {nome_arquivo}')

    # Envio ao Drive nao deve impedir o download caso falhe.
    try:
        enviado = enviar_backup_para_drive(
            db_path, nome_arquivo,
            current_app.config.get('GOOGLE_SERVICE_ACCOUNT_FILE'),
            current_app.config.get('GOOGLE_DRIVE_FOLDER_ID')
        )
        if enviado:
            logger.info(f'Backup tambem enviado ao Google Drive: {nome_arquivo}')
    except Exception as e:
        logger.error(f'Erro ao enviar backup ao Google Drive: {e}')

    return send_file(
        db_path,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype='application/octet-stream'
    )
