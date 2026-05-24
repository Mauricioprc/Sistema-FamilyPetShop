from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import UserMixin, login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from urllib.parse import urlparse
from extensions import login_manager
import logging

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)


class AdminUser(UserMixin):
    def __init__(self, username: str, password_hash: str):
        self.id = '1'
        self.username = username
        self._password_hash = password_hash

    def check_password(self, senha: str) -> bool:
        try:
            return check_password_hash(self._password_hash, senha)
        except Exception as e:
            logger.error(f"Erro ao verificar senha: {e}")
            return False


def _criar_admin():
    try:
        username = current_app.config.get('ADMIN_USERNAME')
        password_hash = current_app.config.get('ADMIN_PASSWORD_HASH')
        if not username or not password_hash:
            logger.error("ADMIN_USERNAME ou ADMIN_PASSWORD_HASH nao configurados")
            return None
        return AdminUser(username, password_hash)
    except Exception as e:
        logger.error(f"Erro ao criar admin user: {e}")
        return None


@login_manager.user_loader
def load_user(user_id):
    if user_id == '1':
        return _criar_admin()
    return None


@login_manager.unauthorized_handler
def unauthorized():
    flash('Voce precisa fazer login para acessar esta pagina.', 'warning')
    return redirect(url_for('auth.login', next=request.url))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Usuario e senha sao obrigatorios.', 'danger')
            logger.warning(f"Login com campos vazios: {username}")
            return render_template('login.html')

        admin = _criar_admin()
        if not admin:
            flash('Erro ao validar credenciais. Contate o administrador.', 'danger')
            logger.error("Admin user nao pode ser carregado")
            return render_template('login.html')

        if username == admin.username and admin.check_password(password):
            login_user(admin, remember=request.form.get('lembrar') == 'on')
            logger.info(f"Login bem-sucedido: {username} | IP: {request.remote_addr}")

            # CORRIGIDO: proteção contra open redirect usando url_parse
            next_page = request.args.get('next')
            if next_page:
                parsed = urlparse(next_page)
                # Bloqueia URLs absolutas e com netloc (//evil.com, http://evil.com)
                if parsed.netloc or not parsed.path.startswith('/'):
                    next_page = None

            flash('Login realizado com sucesso!', 'success')
            return redirect(next_page or url_for('agenda.agenda_do_dia'))

        logger.warning(f"Tentativa de login invalida: {username} | IP: {request.remote_addr}")
        flash('Usuario ou senha incorretos.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logger.info(f"Logout: {request.remote_addr}")
    logout_user()
    flash('Voce saiu do sistema.', 'success')
    return redirect(url_for('auth.login'))
