"""
Ponto de entrada para servidores WSGI de produção (Gunicorn, uWSGI, etc).

Uso (local, simulando produção):
    gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app

Em plataformas como Render/Railway, o comando de start já vem do Procfile.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

config_name = os.environ.get('FLASK_ENV', 'production')
app = create_app(config_name)

# Tabelas do banco: gerenciadas via `flask db upgrade` (rodado no build do
# Render / manualmente em dev), não mais criadas automaticamente no boot.
# A pasta de instância (INSTANCE_DIR ou instance/ padrão) já é garantida
# dentro de create_app().
