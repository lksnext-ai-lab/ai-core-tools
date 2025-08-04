from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from model.user import User
from extensions import db
from api.api_auth import is_omniadmin
from services.agent_cache_service import CheckpointerCacheService
from utils.logger import get_logger
import re

logger = get_logger(__name__)

auth_blueprint = Blueprint('auth', __name__, url_prefix='/auth')

def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@auth_blueprint.route('/login', methods=['GET', 'POST'])
def email_login():
    """Email/password login"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email y contraseña son requeridos', 'error')
            return render_template('auth/login.html')
        
        if not is_valid_email(email):
            flash('Formato de email inválido', 'error')
            return render_template('auth/login.html')
        
        # Buscar usuario
        user = db.session.query(User).filter_by(email=email).first()
        
        if not user or user.is_google_user or not user.check_password(password):
            flash('Email o contraseña incorrectos', 'error')
            return render_template('auth/login.html')
        
        # Login exitoso
        session["user"] = {'email': user.email, 'name': user.name}
        session["is_omniadmin"] = is_omniadmin(user.email)
        session['user_id'] = user.user_id
        login_user(user)
        
        logger.info(f"User {user.email} logged in with email/password")
        return redirect(url_for('home'))
    
    return render_template('auth/login.html')

@auth_blueprint.route('/register', methods=['GET', 'POST'])
def register():
    """User registration with email/password"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validaciones
        if not email or not name or not password:
            flash('Todos los campos son requeridos', 'error')
            return render_template('auth/register.html')
        
        if not is_valid_email(email):
            flash('Formato de email inválido', 'error')
            return render_template('auth/register.html')
        
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'error')
            return render_template('auth/register.html')
        
        # Verificar si el usuario ya existe
        existing_user = db.session.query(User).filter_by(email=email).first()
        if existing_user:
            flash('Ya existe un usuario con ese email', 'error')
            return render_template('auth/register.html')
        
        # Crear nuevo usuario
        try:
            user = User(email=email, name=name, is_google_user=False)
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Crear suscripción gratuita si está en modo ONLINE
            from utils.config import get_app_config
            app_config = get_app_config()
            if app_config['AICT_MODE'] == 'ONLINE':
                from services.subscription_service import SubscriptionService
                SubscriptionService.create_free_subscription(user.user_id)
            
            flash('Cuenta creada exitosamente. Ya puedes iniciar sesión.', 'success')
            logger.info(f"New user registered: {user.email}")
            return redirect(url_for('auth.email_login'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating user: {str(e)}")
            flash('Error al crear la cuenta. Inténtalo de nuevo.', 'error')
            return render_template('auth/register.html')
    
    return render_template('auth/register.html')

@auth_blueprint.route('/logout')
@login_required
def logout():
    """Logout for both Google and email users"""
    CheckpointerCacheService.invalidate_all()
    session.clear()
    logout_user()
    return redirect(url_for('index'))
