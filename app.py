import os
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, app, redirect, url_for, render_template
from flask_login import login_required
from config import Config, config
from extensions import db, migrate, login_manager, csrf, limiter
from utils import configurar_locale, format_currency
from flask import current_app


def get_file_hash(filename):
    """
    Retorna timestamp do arquivo para forçar refresh no navegador
    """
    try:
        # Usa o diretório estático oficial da aplicação Flask
        filepath = os.path.join(current_app.static_folder, filename)
        if os.path.exists(filepath):
            return int(os.path.getmtime(filepath))
    except Exception as e:
        logging.warning(f'Erro ao obter hash do arquivo {filename}: {e}')
    return int(time.time())

def setup_logging(app):
    """Configurar logging estruturado"""
    log_dir = os.path.join(app.instance_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'petshop.log'),
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('PetShop Control iniciado')

    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def create_app(config_name='development'):
    """
    Factory para criar a aplicação Flask
    
    Args:
        config_name: 'development', 'testing' ou 'production'
    """
    app = Flask(__name__)

    if config_name not in config:
        config_name = 'development'
    app.config.from_object(config[config_name])

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    setup_logging(app)
    app.logger.info(f'Aplicacao iniciada em modo: {config_name}')

    try:
        db.init_app(app)
        migrate.init_app(app, db)
        login_manager.init_app(app)
        csrf.init_app(app)
        #limiter.init_app(app)
        app.logger.info('Extensoes inicializadas com sucesso')
    except Exception as e:
        app.logger.error(f'Erro ao inicializar extensoes: {e}')
        raise

    # ✅ NOVO: Desabilitar cache de arquivos estáticos em desenvolvimento
    if app.config['DEBUG']:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        app.logger.info('Cache de assets desabilitado (DEBUG=True)')
    else:
        # Em produção, cache de 30 dias (2592000 segundos)
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 2592000
        app.logger.info('Cache de assets habilitado (30 dias)')

    configurar_locale()
    app.jinja_env.filters['currency'] = format_currency

    # ✅ NOVO: Context processor para cache busting
    @app.context_processor
    def inject_cache_bust():
        def cache_bust(filename):
            hash_value = get_file_hash(filename)
            # Usa o url_for para garantir o caminho '/static/...'
            url_arquivo = url_for('static', filename=filename)
            return f"{url_arquivo}?v={hash_value}"
        return dict(cache_bust=cache_bust)

    _registrar_blueprints(app)
    _registrar_context_processors(app)
    _registrar_error_handlers(app)
    _registrar_rotas(app)

    with app.app_context():
        try:
            db.create_all()
            app.logger.info('Banco de dados criado/verificado')
        except Exception as e:
            app.logger.error(f'Erro ao criar banco de dados: {e}')

    return app


def _registrar_blueprints(app):
    """Registra todos os blueprints da aplicação"""
    try:
        from rotas.auth import auth_bp
        from rotas.dashboard import dashboard_bp
        from rotas.clientes import clientes_bp
        from rotas.agenda import agenda_bp
        from rotas.pacotes import pacotes_bp
        from rotas.financeiro import financeiro_bp
        from rotas.publico import publico_bp
        from rotas.whatsapp import whatsapp_bp
        from rotas.backup import backup_bp
        from rotas.chatbot import chatbot_bp

        for bp in [auth_bp, dashboard_bp, clientes_bp, agenda_bp,
                   pacotes_bp, financeiro_bp, publico_bp, whatsapp_bp, backup_bp, chatbot_bp]:
            app.register_blueprint(bp)
            app.logger.info(f'Blueprint registrado: {bp.name}')
    except ImportError as e:
        app.logger.error(f'Erro ao importar blueprints: {e}')
        raise


def _registrar_context_processors(app):
    """Registra processadores de contexto globais"""
    @app.context_processor
    def inject_globals():
        from models import Atendimento
        from flask_login import current_user

        num_solicitacoes = 0
        if current_user.is_authenticated:
            try:
                num_solicitacoes = Atendimento.query.filter_by(
                    status_presenca='Solicitado_Online'
                ).count()
            except Exception as e:
                app.logger.error(f'Erro ao contar solicitacoes: {e}')

        return dict(num_solicitacoes=num_solicitacoes)


def _registrar_error_handlers(app):
    """Registra handlers para erros HTTP"""
    @app.errorhandler(400)
    def bad_request(e):
        app.logger.warning(f'Erro 400: {e}')
        return render_template('error.html',
                               status_code=400,
                               titulo='Requisicao Invalida',
                               mensagem='A requisicao enviada e invalida.'), 400

    @app.errorhandler(404)
    def pagina_nao_encontrada(e):
        app.logger.warning(f'Erro 404: {e}')
        return render_template('error.html',
                               status_code=404,
                               titulo='Pagina nao encontrada',
                               mensagem='A pagina que voce procura nao existe.'), 404

    @app.errorhandler(429)
    def too_many_requests(e):
        app.logger.warning(f'Erro 429 (Rate limit): {e}')
        return render_template('error.html',
                               status_code=429,
                               titulo='Muitas requisicoes',
                               mensagem='Voce fez muitas solicitacoes. Aguarde um momento e tente novamente.'), 429

    @app.errorhandler(500)
    def erro_interno(e):
        app.logger.error(f'Erro 500: {e}')
        return render_template('error.html',
                               status_code=500,
                               titulo='Erro interno do servidor',
                               mensagem='Ocorreu um erro interno. Contate o administrador.'), 500


def _registrar_rotas(app):
    """Registra rotas raiz"""
    @app.route('/')
    @login_required
    def index():
        return redirect(url_for('agenda.agenda_do_dia'))


if __name__ == '__main__':
    import sys
    
    # Detectar ambiente
    env = os.environ.get('FLASK_ENV', 'development')
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print("\n" + "="*60)
    print("🐾 PETSHOP CONTROL")
    print("="*60)
    print(f"Ambiente: {env}")
    print(f"Debug: {'✅ ATIVADO' if debug_mode else '❌ DESATIVADO'}")
    print("="*60 + "\n")
    
    app = create_app('development' if env == 'development' else 'production')
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=debug_mode,
        use_reloader=debug_mode
    )