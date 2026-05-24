import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Garante que a pasta instance existe antes de criar o banco
    instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
    os.makedirs(instance_path, exist_ok=True)

    with app.app_context():
        from extensions import db
        db.create_all()

    app.run(debug=app.config['DEBUG'])