import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

# ✅ Agora lê o ambiente correto do .env (development | production)
# Antes estava sempre fixo em 'development', mesmo em produção.
config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    # Garante que a pasta instance existe antes de criar o banco
    instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
    os.makedirs(instance_path, exist_ok=True)

    with app.app_context():
        from extensions import db
        db.create_all()

    # ⚠️ Este modo (app.run) é apenas para desenvolvimento local.
    # Em produção, use Gunicorn (veja wsgi.py e Procfile).
    app.run(debug=app.config['DEBUG'])
