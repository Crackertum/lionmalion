import os
import secrets
import string
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_talisman import Talisman
from whitenoise import WhiteNoise
from agora_token_builder import RtcTokenBuilder

from models import db, User, Announcement, Message, AuditLog
from forms import LoginForm, RegistrationForm, AnnouncementForm, MessageForm, SettingsForm
from config import config_by_name

# Initialize Flask extensions
bcrypt = Bcrypt()
migrate = Migrate()
login_manager = LoginManager()
talisman = Talisman()

def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Security: Talisman (Content Security Policy)
    csp = {
        'default-src': [
            '\'self\'',
            'https://fonts.googleapis.com',
            'https://fonts.gstatic.com',
            'https://cdnjs.cloudflare.com',
            'https://download.agora.io'
        ],
        'script-src': [
            '\'self\'',
            '\'unsafe-inline\'',
            'https://cdnjs.cloudflare.com',
            'https://download.agora.io'
        ],
        'style-src': [
            '\'self\'',
            '\'unsafe-inline\'',
            'https://fonts.googleapis.com',
            'https://cdnjs.cloudflare.com'
        ]
    }
    talisman.init_app(
        app, 
        content_security_policy=csp,
        force_https=app.config.get('TALISMAN_FORCE_HTTPS', True),
        content_security_policy_report_only=False
    )
    
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    
    # Static files with WhiteNoise
    app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/', prefix='static/')
    
    # Initialize database on first run (SQLite compatibility)
    with app.app_context():
        db.create_all()
        # Create initial admin if no users exist
        if not User.query.first():
            admin_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = User(username='admin', email='admin@lionmalion.local', 
                         password_hash=admin_pw, name='System Administrator', role='admin')
            db.session.add(admin)
            db.session.commit()
            print(">>> INITIAL HIGH-COMMAND ADMIN CREATED: admin / admin123")
    
    return app

app = create_app(os.environ.get('FLASK_ENV', 'development'))

# --- Utilities ---
def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static', 'profile_pics', picture_fn)
    os.makedirs(os.path.dirname(picture_path), exist_ok=True)
    form_picture.save(picture_path)
    return picture_fn

@app.template_filter('zfill')
def zfill_filter(value, width=2):
    return str(value).zfill(width)

# Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://",
)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_activity(action, user_id=None):
    log = AuditLog(user_id=user_id or (current_user.id if current_user.is_authenticated else None),
                   action=action, ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()

# --- Logging Configuration ---
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/lion_malion.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Lion Malion platform startup')

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter((User.username == form.username_email.data) | 
                                 (User.email == form.username_email.data)).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            if not user.is_active:
                flash('Access Revoked: Identification suspended by higher command.', 'danger')
                return render_template('login.html', form=form)
            
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_activity('Authenticated into high-command protocols')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Authentication Failure: Unauthorized credentials.', 'danger')
            log_activity(f'Unauthorized login attempt: {form.username_email.data}')
            
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    log_activity('Severed connection')
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    unread_count = Message.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    new_announcements = Announcement.query.filter_by(is_pinned=True).all()
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(5).all()
    return render_template('dashboard.html', 
                                unread_count=unread_count, 
                                pinned=new_announcements,
                                logs=recent_logs)

@app.route('/announcements', methods=['GET', 'POST'])
@login_required
def announcements():
    form = AnnouncementForm()
    if current_user.role == 'admin' and form.validate_on_submit():
        ann = Announcement(title=form.title.data, 
                           content=form.content.data, 
                           type=form.type.data,
                           is_pinned=form.is_pinned.data,
                           author_id=current_user.id)
        db.session.add(ann)
        log_activity(f'Disseminated bulletin: {form.title.data}')
        db.session.commit()
        flash('Bulletin disseminated across the network.', 'success')
        return redirect(url_for('announcements'))
    
    all_announcements = Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()
    return render_template('announcements.html', announcements=all_announcements, form=form)

@app.route('/messages', methods=['GET', 'POST'])
@login_required
def messages():
    all_users_raw = User.query.filter(User.id != current_user.id, User.is_active == True).all()
    form = MessageForm()
    
    choices = [(u.id, u.name) for u in all_users_raw]
    if current_user.role == 'admin':
        choices.insert(0, (0, '📢 GLOBAL BROADCAST'))
    form.recipient_id.choices = choices
    
    if form.validate_on_submit():
        recipient_id = form.recipient_id.data
        attachment_fn = None
        original_fn = None
        
        if form.attachment.data:
            file = form.attachment.data
            random_hex = secrets.token_hex(8)
            _, f_ext = os.path.splitext(file.filename)
            attachment_fn = random_hex + f_ext
            original_fn = file.filename
            upload_path = os.path.join(app.root_path, 'static', 'uploads', 'messages')
            os.makedirs(upload_path, exist_ok=True)
            file.save(os.path.join(upload_path, attachment_fn))

        if recipient_id == 0:
            if current_user.role != 'admin': abort(403)
            msg = Message(sender_id=current_user.id, recipient_id=None, content=form.content.data, 
                          file_path=attachment_fn, original_filename=original_fn)
            db.session.add(msg)
            log_activity('Transmitted global broadcast')
        else:
            msg = Message(sender_id=current_user.id, recipient_id=recipient_id, content=form.content.data,
                          file_path=attachment_fn, original_filename=original_fn)
            db.session.add(msg)
        
        db.session.commit()
        flash('Data transmitted via secure stream.', 'success')
        return redirect(url_for('messages', contact=recipient_id))
    
    contact_id = request.args.get('contact', type=int)
    thread = []
    if contact_id is not None:
        if contact_id == 0:
            thread = Message.query.filter_by(recipient_id=None).order_by(Message.timestamp.asc()).all()
        else:
            Message.query.filter_by(sender_id=contact_id, recipient_id=current_user.id).update({'is_read': True})
            db.session.commit()
            thread = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.recipient_id == contact_id)) |
                ((Message.sender_id == contact_id) & (Message.recipient_id == current_user.id))
            ).order_by(Message.timestamp.asc()).all()
    
    contacts = []
    if current_user.role == 'admin' or Message.query.filter_by(recipient_id=None).first():
        contacts.append({'user': {'id': 0, 'name': 'Global Broadcasts', 'role': 'System'}, 'unread': 0})

    for u in all_users_raw:
        has_chat = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == u.id)) |
            ((Message.sender_id == u.id) & (Message.recipient_id == current_user.id))
        ).first()
        
        if has_chat or contact_id == u.id:
            unread = Message.query.filter_by(sender_id=u.id, recipient_id=current_user.id, is_read=False).count()
            contacts.append({'user': u, 'unread': unread})

    return render_template('messages.html', contacts=contacts, thread=thread, form=form, 
                           active_contact=contact_id, all_users=all_users_raw)

# --- Real-Time Communication (RTC) API ---
@app.route('/api/get_agora_token')
@login_required
def get_agora_token():
    app_id = app.config.get('AGORA_APP_ID')
    app_certificate = app.config.get('AGORA_APP_CERTIFICATE')
    channel_name = request.args.get('channelName')
    
    if not channel_name or not app_id or not app_certificate:
        return jsonify({'error': 'Missing configuration or channel identification'}), 400
    
    # Token expiration time in seconds (3600s = 1h)
    expiration_time_in_seconds = 3600
    current_timestamp = int(datetime.utcnow().timestamp())
    privilege_expired_ts = current_timestamp + expiration_time_in_seconds
    
    # Use RtcTokenBuilder to build a token
    token = RtcTokenBuilder.buildTokenWithUid(
        app_id, app_certificate, channel_name, 0, 1, privilege_expired_ts
    )
    
    return jsonify({'token': token, 'appId': app_id})

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if current_user.role != 'admin': abort(403)
    form = RegistrationForm()
    if form.validate_on_submit():
        temp_pass = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
        hashed_pw = bcrypt.generate_password_hash(temp_pass).decode('utf-8')
        new_user = User(username=form.username.data, 
                        email=form.email.data, 
                        password_hash=hashed_pw, 
                        name=form.name.data,
                        role=form.role.data)
        
        if form.profile_pic.data:
            pic_file = save_picture(form.profile_pic.data)
            new_user.profile_pic = pic_file
            
        db.session.add(new_user)
        db.session.commit()
        log_activity(f'Authorized new network operator: {form.username.data}')
        flash(f'Authorization Granted! Secure Password: {temp_pass}', 'success')
        return redirect(url_for('admin'))
    
    all_users = User.query.all()
    return render_template('admin.html', users=all_users, form=form)

@app.route('/admin/toggle_user/<int:user_id>')
@login_required
def toggle_user(user_id):
    if current_user.role != 'admin': abort(403)
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id: flash('Command Conflict: Cannot suspend self.', 'warning')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        log_activity(f'{"Reinstated" if user.is_active else "Suspended"} operator access: {user.username}')
    return redirect(url_for('admin'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    form = SettingsForm()
    if request.method == 'GET':
        form.name.data = current_user.name
    
    if form.validate_on_submit():
        current_user.name = form.name.data
        if form.profile_pic.data:
            pic_file = save_picture(form.profile_pic.data)
            current_user.profile_pic = pic_file
        if form.new_password.data:
            current_user.password_hash = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
        db.session.commit()
        log_activity('Modified operator identification protocols')
        flash('Identification protocols updated.', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', form=form)

# --- Global Context & Error Handling ---
@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        unread = Message.query.filter_by(recipient_id=current_user.id, is_read=False).count()
        return dict(global_unread=unread)
    return dict(global_unread=0)

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    app.run(port=5000)
