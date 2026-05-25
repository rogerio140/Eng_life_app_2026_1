from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from functools import wraps
from database import Database

auth_bp = Blueprint("auth", __name__)
db = Database()

def login_required(f):
    """Decorador para exigir login em rotas"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.before_app_request
def check_authentication():
    """Verifica autenticação para rotas protegidas"""
    # Rotas que não precisam de autenticação
    public_routes = ["auth.login", "auth.logout", "health", "static", "auth.index"]
    
    # Permite acesso a rotas de API sem autenticação de sessão
    # A autenticação de API deve ser tratada dentro dos próprios endpoints da API
    if request.path.startswith('/api/') or request.endpoint in public_routes:
        return

    if request.endpoint and request.endpoint not in public_routes:
        if 'usuario_id' not in session:
            if request.endpoint != 'auth.index':
                flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('auth.login'))

@auth_bp.route("/")
def index():
    """Página inicial - redireciona para login ou dashboard"""
    if 'usuario_id' in session:
        return redirect(url_for('routes.dashboard')) # Redireciona para o dashboard do módulo routes
    return redirect(url_for('auth.login'))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Página de login"""
    if 'usuario_id' in session:
        return redirect(url_for('routes.dashboard'))
    
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")
        
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('login.html')
        
        usuario = db.verificar_usuario(email, senha)
        
        if usuario:
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            session['usuario_email'] = usuario['email']
            session['usuario_tipo'] = usuario['tipo']
            
            flash(f'Bem-vindo, {usuario["nome"]}!', 'success')
            return redirect(url_for('routes.dashboard'))
        else:
            flash('Email ou senha incorretos.', 'danger')
    
    return render_template('login.html')

@auth_bp.route("/logout")
def logout():
    """Rota para logout"""
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))
