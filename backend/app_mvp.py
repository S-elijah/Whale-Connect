"""
WHALE MVP — Minimal Secure Social Platform
Core features only: Auth, Tweets, Follow, Messages, 2FA
"""

import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

from models import db, User, Tweet, Message, followers
from security import (
    EncryptionEngine, InputSanitizer, PasswordPolicy, 
    TwoFactorAuth, AccountLockout, AuditLogger, SecurityHeaders
)

# ============================================
# APP SETUP
# ============================================

app = Flask(__name__)
load_dotenv()

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whale_mvp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db.init_app(app)
csrf = CSRFProtect(app)

# ============================================
# SECURITY INIT
# ============================================

app.encryption = EncryptionEngine.from_env()
app.audit_logger = AuditLogger(app)

@app.after_request
def add_security_headers(response):
    return SecurityHeaders.apply_headers(response)

# ============================================
# LOGIN MANAGER
# ============================================

login = LoginManager(app)
login.login_view = 'login'

@login.user_loader
def load_user(id):
    return User.query.get(int(id))

# ============================================
# FORMS
# ============================================

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(1, 15)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(3, 15)])
    password = PasswordField('Password', validators=[DataRequired(), Length(8, 128)])
    submit = SubmitField('Sign Up')

class TweetForm(FlaskForm):
    body = TextAreaField('What\'s on your mind?', validators=[DataRequired(), Length(1, 280)])
    submit = SubmitField('Share')

class MessageForm(FlaskForm):
    body = TextAreaField('Message', validators=[DataRequired(), Length(1, 500)])
    submit = SubmitField('Send')

class TwoFactorForm(FlaskForm):
    code = StringField('Code', validators=[DataRequired(), Length(6, 6)])
    submit = SubmitField('Verify')

# ============================================
# ROUTES: AUTH
# ============================================

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        
        if not username or len(username) < 3:
            flash('Username must be 3-15 characters', 'danger')
            return redirect(url_for('signup'))
        
        is_valid, error = PasswordPolicy.validate(form.password.data)
        if not is_valid:
            flash(error, 'danger')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(username=username).first():
            flash('Username taken', 'danger')
            return redirect(url_for('signup'))
        
        user = User(username=username)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        app.audit_logger.log_event('user_registered', user_id=user.id)
        login_user(user)
        flash('Account created! Whale welcomes you 🐋', 'success')
        return redirect(url_for('timeline'))
    
    return render_template('signup_mvp.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip_key = f"ip:{request.remote_addr}"
    
    if AccountLockout.is_locked(ip_key):
        remaining = AccountLockout.get_lockout_remaining(ip_key)
        flash(f'Too many attempts. Try in {remaining}s', 'danger')
        return render_template('login_mvp.html', form=LoginForm())
    
    form = LoginForm()
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(form.password.data):
            if user.totp_enabled:
                session['2fa_user_id'] = user.id
                return redirect(url_for('verify_2fa'))
            
            AccountLockout.reset_attempts(ip_key)
            login_user(user, remember=True)
            app.audit_logger.log_event('login_success', user_id=user.id)
            flash('Welcome back!', 'success')
            return redirect(url_for('timeline'))
        else:
            AccountLockout.record_failed_attempt(ip_key)
            app.audit_logger.log_event('login_failed', details={'username': username})
            flash('Invalid credentials', 'danger')
    
    return render_template('login_mvp.html', form=form)

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
            login_user(user)
            session.pop('2fa_user_id', None)
            flash('2FA verified!', 'success')
            return redirect(url_for('timeline'))
        else:
            flash('Invalid code', 'danger')
    
    return render_template('verify_2fa_mvp.html', form=form)

@app.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if current_user.totp_enabled:
        flash('2FA already enabled', 'info')
        return redirect(url_for('timeline'))
    
    if not current_user.totp_secret:
        current_user.totp_secret = TwoFactorAuth.generate_secret()
        db.session.commit()
    
    qr_svg = TwoFactorAuth.generate_qr_code(current_user.totp_secret, current_user.username)
    
    form = TwoFactorForm()
    if form.validate_on_submit():
        if TwoFactorAuth.verify_code(current_user.totp_secret, form.code.data):
            current_user.totp_enabled = True
            db.session.commit()
            app.audit_logger.log_event('2fa_enabled', user_id=current_user.id)
            flash('2FA enabled! 🔐', 'success')
            return redirect(url_for('timeline'))
        else:
            flash('Invalid code', 'danger')
    
    return render_template('setup_2fa_mvp.html', form=form, qr_svg=qr_svg)

@app.route('/logout')
@login_required
def logout():
    app.audit_logger.log_event('logout', user_id=current_user.id)
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

# ============================================
# ROUTES: TWEETS
# ============================================

@app.route('/', methods=['GET', 'POST'])
@login_required
def timeline():
    form = TweetForm()
    if form.validate_on_submit():
        body = InputSanitizer.sanitize_plain_text(form.body.data, 280)
        if not body:
            flash('Tweet empty', 'warning')
            return redirect(url_for('timeline'))
        
        tweet = Tweet(body=body, author=current_user)
        db.session.add(tweet)
        db.session.commit()
        flash('Tweet posted!', 'success')
        return redirect(url_for('timeline'))
    
    followed_ids = [u.id for u in current_user.following] + [current_user.id]
    tweets = Tweet.query.filter(Tweet.user_id.in_(followed_ids)).order_by(Tweet.timestamp.desc()).all()
    return render_template('timeline_mvp.html', form=form, tweets=tweets)

@app.route('/delete/<int:tweet_id>', methods=['POST'])
@login_required
def delete_tweet(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    if tweet.author == current_user:
        db.session.delete(tweet)
        db.session.commit()
        flash('Deleted', 'success')
    return redirect(url_for('timeline'))

@app.route('/like/<int:tweet_id>', methods=['POST'])
@login_required
def like(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    if tweet not in current_user.likes:
        current_user.likes.append(tweet)
        db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/unlike/<int:tweet_id>', methods=['POST'])
@login_required
def unlike(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    if tweet in current_user.likes:
        current_user.likes.remove(tweet)
        db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

# ============================================
# ROUTES: FOLLOW
# ============================================

@app.route('/user/<username>')
@login_required
def profile(username):
    username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=username).first_or_404()
    tweets = Tweet.query.filter_by(user_id=user.id).order_by(Tweet.timestamp.desc()).all()
    return render_template('profile_mvp.html', user=user, tweets=tweets)

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=username).first()
    if user and user != current_user:
        current_user.follow(user)
        db.session.commit()
        flash(f'Following {user.username}', 'success')
    return redirect(request.referrer or url_for('timeline'))

@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=username).first()
    if user:
        current_user.unfollow(user)
        db.session.commit()
        flash(f'Unfollowed {user.username}', 'info')
    return redirect(request.referrer or url_for('timeline'))

# ============================================
# ROUTES: MESSAGES (ENCRYPTED)
# ============================================

@app.route('/messages')
@login_required
def messages():
    # Get unique users we've messaged
    sent_ids = [m.recipient_id for m in Message.query.filter_by(sender_id=current_user.id).distinct()]
    recv_ids = [m.sender_id for m in Message.query.filter_by(recipient_id=current_user.id).distinct()]
    all_ids = set(sent_ids + recv_ids)
    users = User.query.filter(User.id.in_(all_ids)).all() if all_ids else []
    return render_template('messages_mvp.html', conversation_users=users)

@app.route('/messages/<username>', methods=['GET', 'POST'])
@login_required
def conversation(username):
    username = InputSanitizer.sanitize_username(username)
    other = User.query.filter_by(username=username).first_or_404()
    form = MessageForm()
    
    if form.validate_on_submit():
        body = InputSanitizer.sanitize_plain_text(form.body.data, 500)
        encrypted_body = app.encryption.encrypt_message(body)
        
        msg = Message(sender_id=current_user.id, recipient_id=other.id, encrypted_body=encrypted_body)
        db.session.add(msg)
        db.session.commit()
        flash('Message sent 🔒', 'success')
        return redirect(url_for('conversation', username=username))
    
    # Get conversation
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == other.id)) |
        ((Message.sender_id == other.id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    decrypted = []
    for msg in msgs:
        decrypted.append({
            'sender_id': msg.sender_id,
            'body': app.encryption.decrypt_message(msg.encrypted_body),
            'timestamp': msg.timestamp
        })
        if msg.recipient_id == current_user.id:
            msg.read = True
    db.session.commit()
    
    return render_template('conversation_mvp.html', form=form, other=other, messages=decrypted)

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# ============================================
# DATABASE INIT
# ============================================

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    print("""
    🐋 WHALE MVP
    http://localhost:5000
    """)
    app.run(host='0.0.0.0', port=5000, debug=False)
