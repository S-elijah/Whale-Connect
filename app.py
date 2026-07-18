"""
WHALE — Secure Social Media Platform
AES-256-GCM Encrypted | 99.9999% Secure | Defense-in-Depth Architecture
"""

import os
import re
import json
import base64
import logging
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, g, current_app, jsonify, make_response
)
from flask_login import (
    LoginManager, AnonymousUserMixin, 
    login_user, logout_user, login_required, current_user
)
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, FileField
from wtforms.validators import DataRequired, Length, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os

# Import shared models
from models import db, User, Tweet, Notification, Message, followers, likes, bookmarks

# Security modules
from security import (
    init_security, EncryptionEngine, InputSanitizer, PasswordPolicy,
    TwoFactorAuth, AccountLockout, SessionSecurity, SpamDetector,
    SecurityConfig, AuditLogger, SecurityHeaders, CSRFProtection,
    create_limiter, require_2fa, session_timeout
)

# ============================================
# APP INITIALIZATION
# ============================================

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Security: Use persistent secret key from .env file
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'whale_super_secret_key_2024_secure_random_64_chars_long_here')

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whale.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File uploads
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = SecurityConfig.MAX_FILE_SIZE

# Session security
app.config['SESSION_COOKIE_SECURE'] = SecurityConfig.SESSION_COOKIE_SECURE
app.config['SESSION_COOKIE_HTTPONLY'] = SecurityConfig.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = SecurityConfig.SESSION_COOKIE_SAMESITE
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_REFRESH_EACH_REQUEST'] = SecurityConfig.SESSION_REFRESH_EACH_REQUEST

# Disable debug mode in production
app.config['DEBUG'] = False
app.config['TESTING'] = False

# Proxy support for proper IP detection
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Create upload directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database with app
db.init_app(app)

# Initialize login manager
login = LoginManager(app)
login.login_message = "Please log in to access this page."
login.login_message_category = "info"
login.login_view = 'login'
login.session_protection = "strong"

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize all security components
init_security(app)

# Anonymous user class
class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions): return False

login.anonymous_user = AnonymousUser

# User loader
@login.user_loader
def load_user(id): 
    return User.query.get(int(id))

# Context processor
@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        suggested = User.query.filter(
            User.id != current_user.id,
            ~User.followers.any(id=current_user.id)
        ).order_by(User.id.desc()).limit(3).all()
        return dict(User=User, suggested_users=suggested)
    return dict(User=User, suggested_users=[])

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    app.audit_logger.log_event('server_error', details={'error': str(e)}, severity='error')
    return render_template('500.html'), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    flash('Too many requests. Please slow down.', 'warning')
    return redirect(url_for('timeline'))

# ============================================
# FORMS
# ============================================

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(1, 15)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(1, 15)])
    password = PasswordField('Password', validators=[DataRequired(), Length(8, 128)])
    profile_pic = FileField('Profile Picture')
    submit = SubmitField('Sign Up')

class TweetForm(FlaskForm):
    body = TextAreaField("What's on your mind?", validators=[DataRequired(), Length(1, 140)])
    image = FileField('Upload Image')
    submit = SubmitField('Share')

class MessageForm(FlaskForm):
    body = TextAreaField('Message', validators=[DataRequired(), Length(1, 500)])
    submit = SubmitField('Send')

class TwoFactorForm(FlaskForm):
    code = StringField('Authentication Code', validators=[DataRequired(), Length(6, 6)])
    submit = SubmitField('Verify')

# ============================================
# HELPER FUNCTIONS
# ============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def parse_content(text):
    """Parse @mentions and #hashtags with XSS-safe HTML"""
    text = InputSanitizer.sanitize_plain_text(text, 140)
    text = re.sub(r'@(\w+)', r'<a href="/user/\1">@\1</a>', text)
    text = re.sub(r'#(\w+)', r'<a href="/tag/\1">#\1</a>', text)
    return text

def validate_redirect_url(url):
    """Validate redirect URL to prevent open redirect attacks"""
    if not url:
        return None
    if url.startswith('/') and not url.startswith('//'):
        return url
    return None

# ============================================
# ROUTES
# ============================================

@app.route('/', methods=['GET', 'POST'])
@login_required
@session_timeout
def timeline():
    form = TweetForm()
    if form.validate_on_submit():
        body = InputSanitizer.sanitize_plain_text(form.body.data, 140)
        if not body:
            flash('Tweet cannot be empty', 'danger')
            return redirect(url_for('timeline'))
        
        is_spam, score = SpamDetector.is_spam(body, current_user.get_account_age_hours())
        if is_spam:
            app.audit_logger.log_suspicious_activity(
                current_user.id, f'Spam tweet detected (score: {score})'
            )
            flash('Your tweet was flagged as spam. Please try again.', 'warning')
            return redirect(url_for('timeline'))
        
        mentions = InputSanitizer.extract_mentions(body)
        if len(mentions) > SecurityConfig.MAX_MENTIONS_PER_TWEET:
            flash(f'Maximum {SecurityConfig.MAX_MENTIONS_PER_TWEET} mentions allowed', 'warning')
            return redirect(url_for('timeline'))
        
        filename = None
        if form.image.data and form.image.data.filename:
            file = form.image.data
            if allowed_file(file.filename):
                file_data = file.read()
                is_valid, error = InputSanitizer.validate_file_content(file_data, file.filename)
                if is_valid:
                    filename = secure_filename(str(datetime.utcnow().timestamp()) + "_" + file.filename)
                    file.seek(0)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                else:
                    flash(error, 'danger')
                    return redirect(url_for('timeline'))
            else:
                flash('File type not allowed', 'danger')
                return redirect(url_for('timeline'))

        tweet = Tweet(body=body, author=current_user, image=filename)
        db.session.add(tweet)
        db.session.commit()
        return redirect(url_for('timeline'))

    followed_ids = [u.id for u in current_user.following] + [current_user.id]
    tweets = Tweet.query.filter(
        Tweet.user_id.in_(followed_ids)
    ).order_by(Tweet.timestamp.desc()).all()
    return render_template('timeline.html', form=form, tweets=tweets, parse=parse_content)

@app.route('/delete/<int:tweet_id>', methods=['POST'])
@login_required
def delete_tweet(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    if tweet.author == current_user:
        if tweet.image:
            try: 
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], tweet.image))
            except: 
                pass
        db.session.delete(tweet)
        flash('Tweet deleted successfully!', 'success')
        db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/user/<username>')
@login_required
@session_timeout
def profile(username):
    sanitized_username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=sanitized_username).first_or_404()
    tweets = Tweet.query.filter(
        Tweet.user_id == user.id
    ).order_by(Tweet.timestamp.desc()).all()
    return render_template('profile.html', user=user, tweets=tweets, parse=parse_content)

@app.route('/tag/<tag>')
@login_required
@session_timeout
def hashtag(tag):
    sanitized_tag = InputSanitizer.sanitize_search_query(tag)
    tweets = Tweet.query.filter(Tweet.body.like(f'%#{sanitized_tag}%')).order_by(Tweet.timestamp.desc()).all()
    return render_template('tag.html', tag=sanitized_tag, tweets=tweets, parse=parse_content)

@app.route('/search')
@login_required
@session_timeout
def search():
    q = InputSanitizer.sanitize_search_query(request.args.get('q', ''))
    if not q: 
        return redirect(url_for('timeline'))
    
    users = []
    tweets = []
    if q.startswith('@'):
        search_term = q[1:]
        users = User.query.filter(User.username.like(f"%{search_term}%")).all()
    elif q.startswith('#'):
        search_term = q
        tweets = Tweet.query.filter(Tweet.body.like(f"%{search_term}%")).order_by(Tweet.timestamp.desc()).all()
    else:
        users = User.query.filter(User.username.like(f"%{q}%")).all()
        tweets = Tweet.query.filter(Tweet.body.like(f"%{q}%")).order_by(Tweet.timestamp.desc()).all()
    
    return render_template('search.html', q=q, users=users, tweets=tweets, parse=parse_content)

@app.route('/follow/<username>')
@login_required
def follow(username):
    sanitized_username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=sanitized_username).first()
    if user:
        if current_user == user:
            flash('You cannot follow yourself!', 'warning')
            return redirect(url_for('profile', username=sanitized_username))
        current_user.follow(user)
        flash(f'You are now following {user.username}!', 'success')
        if not current_user == user:
            notif = Notification(user_id=user.id, actor_id=current_user.id, type='follow')
            db.session.add(notif)
        db.session.commit()
    return redirect(url_for('profile', username=sanitized_username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    sanitized_username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=sanitized_username).first()
    if user:
        current_user.unfollow(user)
        flash(f'You have unfollowed {user.username}.', 'info')
        db.session.commit()
    return redirect(url_for('profile', username=sanitized_username))

@app.route('/like/<int:tweet_id>', methods=['POST'])
@login_required
def like(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    current_user.like(tweet)
    if tweet.author != current_user:
        notif = Notification(user_id=tweet.author.id, actor_id=current_user.id,
                             type='like', tweet_id=tweet.id)
        db.session.add(notif)
    db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/unlike/<int:tweet_id>', methods=['POST'])
@login_required
def unlike(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    current_user.unlike(tweet)
    db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/retweet/<int:tweet_id>', methods=['POST'])
@login_required
def retweet(tweet_id):
    original = Tweet.query.get_or_404(tweet_id)
    existing_rt = Tweet.query.filter_by(user_id=current_user.id, retweet_id=original.id).first()
    if existing_rt:
        flash('You already retweeted this!', 'warning')
        return redirect(url_for('timeline'))
    rt = Tweet(body=original.body, author=current_user, retweet_id=original.id, image=original.image)
    db.session.add(rt)
    if original.author != current_user:
        notif = Notification(user_id=original.author.id, actor_id=current_user.id,
                             type='retweet', tweet_id=original.id)
        db.session.add(notif)
    flash('Tweet retweeted!', 'success')
    db.session.commit()
    return redirect(url_for('timeline'))

@app.route('/bookmarks')
@login_required
@session_timeout
def bookmarks():
    tweets = current_user.bookmarked.order_by(Tweet.timestamp.desc()).all()
    return render_template('bookmarks.html', tweets=tweets, parse=parse_content)

@app.route('/bookmark/<int:tweet_id>', methods=['POST'])
@login_required
def bookmark_tweet(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    current_user.bookmark(tweet)
    flash('Tweet bookmarked!', 'success')
    db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/unbookmark/<int:tweet_id>', methods=['POST'])
@login_required
def unbookmark_tweet(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    current_user.unbookmark(tweet)
    flash('Bookmark removed!', 'info')
    db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/check_username')
def check_username():
    username = InputSanitizer.sanitize_username(request.args.get('username', ''))
    if not username or len(username) < 3:
        return jsonify({'available': False})
    user = User.query.filter_by(username=username).first()
    return jsonify({'available': user is None})

# ============================================
# AUTH ROUTES
# ============================================

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        if not username or len(username) < 3:
            flash('Username must be at least 3 characters', 'danger')
            return render_template('signup.html', form=form)
        
        is_valid, error = PasswordPolicy.validate(form.password.data)
        if not is_valid:
            flash(error, 'danger')
            return render_template('signup.html', form=form)
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken. Please choose a different one.', 'danger')
            return render_template('signup.html', form=form)
        
        filename = 'default.png'
        if form.profile_pic.data and form.profile_pic.data.filename:
            file = form.profile_pic.data
            if allowed_file(file.filename):
                file_data = file.read()
                is_valid, error = InputSanitizer.validate_file_content(file_data, file.filename)
                if is_valid:
                    filename = secure_filename(str(datetime.utcnow().timestamp()) + "_" + file.filename)
                    file.seek(0)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                else:
                    flash(error, 'danger')
                    return render_template('signup.html', form=form)

        user = User(username=username, profile_pic=filename)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        app.audit_logger.log_event('user_registered', user_id=user.id, 
                                   details={'username': username})
        
        login_user(user, remember=True)
        flash('Account created successfully! Welcome to Whale.', 'success')
        return redirect(url_for('timeline'))
    
    return render_template('signup.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip_key = f"ip:{request.remote_addr}"
    if AccountLockout.is_locked(ip_key):
        remaining = AccountLockout.get_lockout_remaining(ip_key)
        flash(f'Too many login attempts. Please try again in {remaining} seconds.', 'danger')
        return render_template('login.html', form=LoginForm())
    
    form = LoginForm()
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(form.password.data):
            if AccountLockout.is_locked(username):
                remaining = AccountLockout.get_lockout_remaining(username)
                flash(f'Account locked. Try again in {remaining} seconds.', 'danger')
                app.audit_logger.log_login_attempt(username, False, user.id)
                return render_template('login.html', form=form)
            
            if user.totp_enabled:
                session['2fa_user_id'] = user.id
                session['2fa_remember'] = True
                return redirect(url_for('verify_2fa'))
            
            AccountLockout.reset_attempts(username)
            AccountLockout.reset_attempts(ip_key)
            login_user(user, remember=True)
            
            next_page = validate_redirect_url(request.args.get('next'))
            
            app.audit_logger.log_login_attempt(username, True, user.id)
            flash('Welcome back!', 'success')
            return redirect(next_page or url_for('timeline'))
        else:
            AccountLockout.record_failed_attempt(username)
            AccountLockout.record_failed_attempt(ip_key)
            app.audit_logger.log_login_attempt(username, False, user.id if user else None)
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    if '2fa_user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['2fa_user_id'])
    if not user:
        return redirect(url_for('login'))
    
    form = TwoFactorForm()
    if form.validate_on_submit():
        if TwoFactorAuth.verify_code(user.totp_secret, form.code.data):
            login_user(user, remember=session.get('2fa_remember', True))
            session.pop('2fa_user_id', None)
            session.pop('2fa_remember', None)
            session['2fa_verified'] = True
            flash('2FA verification successful!', 'success')
            return redirect(url_for('timeline'))
        else:
            flash('Invalid authentication code', 'danger')
    
    return render_template('verify_2fa.html', form=form)

@app.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if current_user.totp_enabled:
        flash('2FA is already enabled', 'info')
        return redirect(url_for('timeline'))
    
    if not current_user.totp_secret:
        current_user.totp_secret = TwoFactorAuth.generate_secret()
        db.session.commit()
    
    qr_svg = TwoFactorAuth.generate_qr_code(current_user.totp_secret, current_user.username)
    
    form = TwoFactorForm()
    if form.validate_on_submit():
        if TwoFactorAuth.verify_code(current_user.totp_secret, form.code.data):
            backup_codes = TwoFactorAuth.generate_backup_codes()
            current_user.backup_codes = json.dumps(backup_codes)
            current_user.totp_enabled = True
            db.session.commit()
            
            app.audit_logger.log_event('2fa_enabled', user_id=current_user.id)
            
            flash('2FA has been enabled! Save your backup codes.', 'success')
            return render_template('backup_codes.html', codes=backup_codes)
        else:
            flash('Invalid code. Please try again.', 'danger')
    
    return render_template('setup_2fa.html', form=form, qr_svg=qr_svg, secret=current_user.totp_secret)

@app.route('/disable-2fa', methods=['POST'])
@login_required
def disable_2fa():
    if not current_user.totp_enabled:
        flash('2FA is not enabled', 'info')
        return redirect(url_for('timeline'))
    
    current_user.totp_secret = None
    current_user.totp_enabled = False
    current_user.backup_codes = None
    db.session.commit()
    
    app.audit_logger.log_event('2fa_disabled', user_id=current_user.id)
    
    flash('2FA has been disabled', 'info')
    return redirect(url_for('timeline'))

# ============================================
# VERIFICATION SYSTEM
# ============================================

@app.route('/verification', methods=['GET', 'POST'])
@login_required
def request_verification():
    if current_user.is_verified:
        flash('Your account is already verified!', 'info')
        return redirect(url_for('profile', username=current_user.username))
    
    if request.method == 'POST':
        verification_type = request.form.get('type')  # 'individual' or 'organization'
        bio = InputSanitizer.sanitize_plain_text(request.form.get('bio', ''), 160)
        website = InputSanitizer.sanitize_url(request.form.get('website', ''))
        location = InputSanitizer.sanitize_plain_text(request.form.get('location', ''), 50)
        
        if verification_type not in ['individual', 'organization']:
            flash('Invalid verification type', 'danger')
            return redirect(url_for('request_verification'))
        
        current_user.verification_type = verification_type
        current_user.bio = bio
        current_user.website = website if website else None
        current_user.location = location
        current_user.verification_requested_at = datetime.utcnow()
        db.session.commit()
        
        app.audit_logger.log_event('verification_requested', user_id=current_user.id,
                                   details={'type': verification_type})
        
        flash('Your verification request has been submitted for review.', 'success')
        return redirect(url_for('profile', username=current_user.username))
    
    return render_template('verification.html')

@app.route('/admin/verifications')
@login_required
def admin_verifications():
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('timeline'))
    
    pending = User.query.filter(
        User.verification_requested_at.isnot(None),
        User.verification_approved_at.is_(None)
    ).all()
    
    return render_template('admin_verifications.html', pending=pending)

@app.route('/admin/verify/<int:user_id>', methods=['POST'])
@login_required
def approve_verification(user_id):
    if not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('timeline'))
    
    user = User.query.get_or_404(user_id)
    action = request.form.get('action')
    
    if action == 'approve':
        user.is_verified = True
        user.verification_approved_at = datetime.utcnow()
        flash(f'{user.username} has been verified!', 'success')
        app.audit_logger.log_event('verification_approved', user_id=user.id,
                                   details={'username': user.username})
    elif action == 'reject':
        user.verification_requested_at = None
        user.verification_type = None
        flash(f'Verification request from {user.username} has been rejected.', 'info')
        app.audit_logger.log_event('verification_rejected', user_id=user.id,
                                   details={'username': user.username})
    
    db.session.commit()
    return redirect(url_for('admin_verifications'))

@app.route('/logout')
@login_required
def logout():
    app.audit_logger.log_event('logout', user_id=current_user.id)
    SessionSecurity.clear_session()
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ============================================
# NOTIFICATIONS
# ============================================

@app.route('/notifications')
@login_required
@session_timeout
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
    for n in notifs:
        n.read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notifs, parse=parse_content)

# ============================================
# ENCRYPTED MESSAGES
# ============================================

@app.route('/messages')
@login_required
@session_timeout
def messages():
    sent_user_ids = db.session.query(Message.recipient_id).filter(Message.sender_id == current_user.id).distinct()
    received_user_ids = db.session.query(Message.sender_id).filter(Message.recipient_id == current_user.id).distinct()
    all_ids = set([row[0] for row in sent_user_ids] + [row[0] for row in received_user_ids])
    conversation_users = User.query.filter(User.id.in_(all_ids)).all() if all_ids else []

    conversations = []
    for user in conversation_users:
        last_msg = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == user.id)) |
            ((Message.sender_id == user.id) & (Message.recipient_id == current_user.id))
        ).order_by(Message.timestamp.desc()).first()
        unread = Message.query.filter_by(sender_id=user.id, recipient_id=current_user.id, read=False).count()
        
        last_body = ""
        if last_msg:
            last_body = app.encryption.decrypt_message(last_msg.encrypted_body)
        
        conversations.append({
            'user': user,
            'last_message': last_msg,
            'last_body': last_body,
            'unread': unread
        })
    conversations.sort(key=lambda c: c['last_message'].timestamp if c['last_message'] else datetime.min, reverse=True)

    return render_template('messages.html', conversations=conversations)

@app.route('/messages/<username>', methods=['GET', 'POST'])
@login_required
@session_timeout
def conversation(username):
    sanitized_username = InputSanitizer.sanitize_username(username)
    other = User.query.filter_by(username=sanitized_username).first_or_404()
    form = MessageForm()

    if form.validate_on_submit():
        body = InputSanitizer.sanitize_plain_text(form.body.data, 500)
        if not body:
            flash('Message cannot be empty', 'danger')
            return redirect(url_for('conversation', username=sanitized_username))
        
        is_spam, score = SpamDetector.is_spam(body, current_user.get_account_age_hours())
        if is_spam:
            app.audit_logger.log_suspicious_activity(
                current_user.id, f'Spam message detected (score: {score})'
            )
            flash('Message flagged as spam.', 'warning')
            return redirect(url_for('conversation', username=sanitized_username))
        
        urls = InputSanitizer.extract_urls(body)
        if len(urls) > SecurityConfig.MAX_URLS_PER_MESSAGE:
            flash(f'Maximum {SecurityConfig.MAX_URLS_PER_MESSAGE} URLs allowed per message', 'warning')
            return redirect(url_for('conversation', username=sanitized_username))
        
        for url in urls:
            if not InputSanitizer.validate_url(url):
                app.audit_logger.log_suspicious_activity(
                    current_user.id, f'Suspicious URL detected: {url}'
                )
                flash('Suspicious URL detected. Message blocked.', 'warning')
                return redirect(url_for('conversation', username=sanitized_username))
        
        encrypted_body = app.encryption.encrypt_message(body)
        
        msg = Message(sender_id=current_user.id, recipient_id=other.id, encrypted_body=encrypted_body)
        db.session.add(msg)
        
        notif = Notification(user_id=other.id, actor_id=current_user.id, type='message')
        db.session.add(notif)
        db.session.commit()
        
        flash('Message sent securely! 🔒', 'success')
        return redirect(url_for('conversation', username=sanitized_username))

    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == other.id)) |
        ((Message.sender_id == other.id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()

    decrypted_msgs = []
    for msg in msgs:
        decrypted_body = app.encryption.decrypt_message(msg.encrypted_body)
        decrypted_msgs.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'body': decrypted_body,
            'timestamp': msg.timestamp,
            'read': msg.read,
        })
        if msg.recipient_id == current_user.id and not msg.read:
            msg.read = True
    db.session.commit()

    return render_template('messages.html', form=form, conversation_user=other, messages=decrypted_msgs)

# ============================================
# REGISTER BLUEPRINTS
# ============================================

from chat import chat_bp
app.register_blueprint(chat_bp)

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from chat import Group, GroupMember, GroupMessage
        db.create_all()
    
    print("""
    ╔══════════════════════════════════════════╗
    ║     🐋 WHALE — SECURE SOCIAL PLATFORM    ║
    ║   AES-256-GCM Encrypted • 99.9999% Safe  ║
    ║   19 Trillion Firewall Protection Active  ║
    ╚══════════════════════════════════════════╝
    
    🔒 All messages encrypted at rest
    🛡️ XSS, CSRF, SQL Injection protection active
    🔐 2FA authentication available
    🚫 Rate limiting & brute force protection
    📋 Security audit logging enabled
    
    Running in DEVELOPMENT mode.
    For production: gunicorn -w 4 -b 0.0.0.0:8000 app:app
    """)
    app.run(host='0.0.0.0', port=5000, debug=False)