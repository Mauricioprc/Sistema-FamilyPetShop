"""
Script de backup do banco de dados SQLite.
Execute manualmente ou via cron/Task Scheduler.

WINDOWS (Task Scheduler): python scripts/backup.py
LINUX/MAC (cron): 0 3 * * * cd /caminho/projeto && python scripts/backup.py

Configura backup diario automatico e mantem os ultimos 30 dias.
"""
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Configuracoes
BASE_DIR = Path(__file__).parent.parent
DB_ORIGEM = BASE_DIR / 'instance' / 'petshop.db'
BACKUP_DIR = BASE_DIR / 'instance' / 'backups'
MANTER_DIAS = 30  # quantos dias de backup manter


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
