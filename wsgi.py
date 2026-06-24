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

# Garante a pasta instance/ e as tabelas do banco antes do primeiro request
instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

with app.app_context():
    from extensions import db
    db.create_all()
