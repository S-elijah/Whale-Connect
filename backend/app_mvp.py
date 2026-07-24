"""
WHALE MVP — Minimal Secure Social Platform
Core: User Auth + Tweets + Follow
"""

import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

from models import db, User, Tweet, followers
from security import InputSanitizer, PasswordPolicy, AccountLockout, SecurityHeaders

app = Flask(__name__)
load_dotenv()

# Config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whale.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db.init_app(app)
csrf = CSRFProtect(app)

@app.after_request
def add_security_headers(response):
    return SecurityHeaders.apply_headers(response)

# Auth
login = LoginManager(app)
login.login_view = 'login'

@login.user_loader
def load_user(id):
    return User.query.get(int(id))

# Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(3, 15)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(3, 15)])
    password = PasswordField('Password', validators=[DataRequired(), Length(8, 128)])
    submit = SubmitField('Sign Up')

class TweetForm(FlaskForm):
    body = TextAreaField("What's on your mind?", validators=[DataRequired(), Length(1, 280)])
    submit = SubmitField('Tweet')

# Routes
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        
        if not username or len(username) < 3:
            flash('Username 3-15 chars', 'danger')
            return redirect(url_for('signup'))
        
        valid, error = PasswordPolicy.validate(form.password.data)
        if not valid:
            flash(error, 'danger')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(username=username).first():
            flash('Username taken', 'danger')
            return redirect(url_for('signup'))
        
        user = User(username=username)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Welcome to Whale! 🐋', 'success')
        return redirect(url_for('timeline'))
    
    return render_template('signup.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip_key = f"ip:{request.remote_addr}"
    
    if AccountLockout.is_locked(ip_key):
        remaining = AccountLockout.get_lockout_remaining(ip_key)
        flash(f'Too many attempts. Try in {remaining}s', 'danger')
        return redirect(url_for('login'))
    
    form = LoginForm()
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(form.password.data):
            AccountLockout.reset_attempts(ip_key)
            login_user(user, remember=True)
            return redirect(url_for('timeline'))
        else:
            AccountLockout.record_failed_attempt(ip_key)
            flash('Invalid credentials', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def timeline():
    form = TweetForm()
    if form.validate_on_submit():
        body = InputSanitizer.sanitize_plain_text(form.body.data, 280)
        tweet = Tweet(body=body, author=current_user)
        db.session.add(tweet)
        db.session.commit()
        flash('Tweet posted!', 'success')
        return redirect(url_for('timeline'))
    
    followed_ids = [u.id for u in current_user.following] + [current_user.id]
    tweets = Tweet.query.filter(Tweet.user_id.in_(followed_ids)).order_by(Tweet.timestamp.desc()).all()
    return render_template('timeline.html', form=form, tweets=tweets)

@app.route('/user/<username>')
@login_required
def profile(username):
    username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=username).first_or_404()
    tweets = Tweet.query.filter_by(user_id=user.id).order_by(Tweet.timestamp.desc()).all()
    return render_template('profile.html', user=user, tweets=tweets)

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=username).first()
    if user and user != current_user:
        current_user.follow(user)
        db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    username = InputSanitizer.sanitize_username(username)
    user = User.query.filter_by(username=username).first()
    if user:
        current_user.unfollow(user)
        db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

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

@app.route('/delete/<int:tweet_id>', methods=['POST'])
@login_required
def delete(tweet_id):
    tweet = Tweet.query.get_or_404(tweet_id)
    if tweet.author == current_user:
        db.session.delete(tweet)
        db.session.commit()
    return redirect(request.referrer or url_for('timeline'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
