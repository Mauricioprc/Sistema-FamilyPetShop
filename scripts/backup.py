"""
Script de backup do banco de dados SQLite.
Execute manualmente, via cron/Task Scheduler (local) ou via Tasks do
PythonAnywhere (producao).

LOCAL (Windows, Task Scheduler): python scripts/backup.py
LOCAL (Linux/Mac, cron): 0 3 * * * cd /caminho/projeto && python scripts/backup.py
PRODUCAO (PythonAnywhere, aba Tasks): diario, comando:
    cd /home/SEU_USUARIO/Sistema-FamilyPetShop && python scripts/backup.py

Configura backup diario automatico e mantem os ultimos 30 dias.

Envio automatico para o Google Drive (opcional):
Alem da copia local em instance/backups, o script tambem envia o backup
do dia para o Google Drive via uma Service Account do Google, se as
variaveis GOOGLE_SERVICE_ACCOUNT_FILE e GOOGLE_DRIVE_FOLDER_ID estiverem
configuradas no .env. Veja o passo a passo no README.md ("Backup do
banco de dados"). Sem essas variaveis, o envio ao Drive e simplesmente
pulado (o backup local continua acontecendo normalmente).

Usamos a API do Google (via HTTPS em www.googleapis.com/accounts.google.com)
em vez do rclone porque funciona igual tanto local quanto no PythonAnywhere
Free (que so libera saida de internet para uma lista de dominios
conhecidos, e as APIs do Google estao nela) — nao depende de instalar um
binario externo nem de um fluxo de login via navegador no servidor.
"""
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Configuracoes
BASE_DIR = Path(__file__).parent.parent
DB_ORIGEM = BASE_DIR / 'instance' / 'petshop.db'
BACKUP_DIR = BASE_DIR / 'instance' / 'backups'
MANTER_DIAS = 30  # quantos dias de backup manter

# Caminho do arquivo JSON da Service Account (ex: instance/google-service-account.json)
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE', '').strip()
# ID da pasta do Drive compartilhada com a Service Account (fica na URL da pasta)
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '').strip()


def enviar_para_drive(caminho_backup: Path) -> None:
    """
    Envia uma copia do backup para uma pasta do Google Drive usando uma
    Service Account (sem necessidade de login interativo no servidor).

    Falha aqui NAO derruba o backup local: so registra um aviso, pois
    o arquivo local ja foi salvo com sucesso antes desta etapa.
    """
    if not GOOGLE_SERVICE_ACCOUNT_FILE or not GOOGLE_DRIVE_FOLDER_ID:
        return  # envio ao Drive desativado (variaveis nao configuradas)

    keyfile = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
    if not keyfile.is_absolute():
        keyfile = BASE_DIR / keyfile

    if not keyfile.exists():
        print(f"⚠️  Arquivo da Service Account nao encontrado em {keyfile} (backup local OK).")
        return

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        credenciais = service_account.Credentials.from_service_account_file(
            str(keyfile), scopes=['https://www.googleapis.com/auth/drive.file']
        )
        servico = build('drive', 'v3', credentials=credenciais, cache_discovery=False)

        metadata = {'name': caminho_backup.name, 'parents': [GOOGLE_DRIVE_FOLDER_ID]}
        midia = MediaFileUpload(str(caminho_backup), mimetype='application/octet-stream', resumable=False)
        servico.files().create(body=metadata, media_body=midia, fields='id').execute()

        print(f"☁️  Enviado para o Google Drive: {caminho_backup.name}")
    except ImportError:
        print("⚠️  Dependencias do Google Drive nao instaladas (google-api-python-client, "
              "google-auth) — envio ao Drive pulado (backup local OK). "
              "Rode: pip install -r requirements.txt")
    except Exception as e:
        print(f"⚠️  Erro ao enviar para o Drive (backup local OK): {e}")


def fazer_backup():
    if not DB_ORIGEM.exists():
        print(f"ERRO: Banco nao encontrado em {DB_ORIGEM}")
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = BACKUP_DIR / f'petshop_{timestamp}.db'

    shutil.copy2(DB_ORIGEM, destino)
    tamanho = destino.stat().st_size / 1024
    print(f"✅ Backup criado: {destino.name} ({tamanho:.1f} KB)")

    enviar_para_drive(destino)

    # Remover backups antigos
    corte = datetime.now() - timedelta(days=MANTER_DIAS)
    removidos = 0
    for arq in BACKUP_DIR.glob('petshop_*.db'):
        try:
            # Extrair data do nome do arquivo
            partes = arq.stem.split('_')
            if len(partes) >= 2:
                data_arq = datetime.strptime(partes[1], '%Y%m%d')
                if data_arq < corte:
                    arq.unlink()
                    removidos += 1
        except (ValueError, IndexError):
            pass

    if removidos:
        print(f"🗑️  {removidos} backup(s) antigo(s) removido(s)")

    # Listar backups existentes
    backups = sorted(BACKUP_DIR.glob('petshop_*.db'))
    print(f"📦 Total de backups: {len(backups)}")
    return True


def listar_backups():
    if not BACKUP_DIR.exists():
        print("Nenhum backup encontrado.")
        return

    backups = sorted(BACKUP_DIR.glob('petshop_*.db'), reverse=True)
    if not backups:
        print("Nenhum backup encontrado.")
        return

    print(f"\n{'Arquivo':<35} {'Tamanho':>10} {'Data'}")
    print('-' * 65)
    for b in backups:
        tamanho = b.stat().st_size / 1024
        data = datetime.fromtimestamp(b.stat().st_mtime).strftime('%d/%m/%Y %H:%M')
        print(f"{b.name:<35} {tamanho:>8.1f} KB   {data}")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'listar':
        listar_backups()
    else:
        fazer_backup()
