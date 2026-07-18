"""
WHALE — Database Models
Shared models for app.py and chat.py
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# Association tables
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('tweet_id', db.Integer, db.ForeignKey('tweet.id'))
)

bookmarks = db.Table('bookmarks',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('tweet_id', db.Integer, db.ForeignKey('tweet.id'))
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200))
    profile_pic = db.Column(db.String(200), default='default.png')
    totp_secret = db.Column(db.String(32), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False)
    backup_codes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Verification system
    is_verified = db.Column(db.Boolean, default=False)
    verification_type = db.Column(db.String(20))  # 'individual' or 'organization'
    verification_requested_at = db.Column(db.DateTime)
    verification_approved_at = db.Column(db.DateTime)
    bio = db.Column(db.String(160))
    website = db.Column(db.String(100))
    location = db.Column(db.String(50))
    
    tweets = db.relationship('Tweet', backref='author', lazy=True)
    liked = db.relationship('Tweet', secondary=likes, backref=db.backref('likers', lazy='dynamic'))
    bookmarked = db.relationship('Tweet', secondary=bookmarks, backref=db.backref('bookmarkers', lazy='dynamic'))
    following = db.relationship('User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic',
        foreign_keys='Notification.user_id')
    sent_messages = db.relationship('Message', backref='sender', lazy='dynamic',
        foreign_keys='Message.sender_id')
    received_messages = db.relationship('Message', backref='recipient', lazy='dynamic',
        foreign_keys='Message.recipient_id')

    def set_password(self, password): 
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:600000')
    
    def check_password(self, password): 
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)
    
    def follow(self, user):
        if not self.is_following(user): self.following.append(user)
    def unfollow(self, user):
        if self.is_following(user): self.following.remove(user)
    def is_following(self, user): 
        return self.following.filter(followers.c.followed_id == user.id).count() > 0
    def like(self, tweet):
        if not self.has_liked(tweet): self.liked.append(tweet)
    def unlike(self, tweet):
        if self.has_liked(tweet): self.liked.remove(tweet)
    def has_liked(self, tweet): 
        return self.liked.filter(likes.c.tweet_id == tweet.id).count() > 0
    def bookmark(self, tweet):
        if not self.has_bookmarked(tweet): self.bookmarked.append(tweet)
    def unbookmark(self, tweet):
        if self.has_bookmarked(tweet): self.bookmarked.remove(tweet)
    def has_bookmarked(self, tweet): 
        return self.bookmarked.filter(bookmarks.c.tweet_id == tweet.id).count() > 0
    def unread_notifications_count(self):
        return Notification.query.filter_by(user_id=self.id, read=False).count()
    def unread_messages_count(self):
        return Message.query.filter_by(recipient_id=self.id, read=False).count()
    def get_account_age_hours(self):
        return (datetime.utcnow() - self.created_at).total_seconds() / 3600


class Tweet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140), nullable=False)
    image = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    retweet_id = db.Column(db.Integer, db.ForeignKey('tweet.id'), nullable=True)
    retweet = db.relationship('Tweet', remote_side=[id])


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    tweet_id = db.Column(db.Integer, db.ForeignKey('tweet.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    actor = db.relationship('User', foreign_keys=[actor_id])
    tweet_ref = db.relationship('Tweet', foreign_keys=[tweet_id])


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    encrypted_body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)