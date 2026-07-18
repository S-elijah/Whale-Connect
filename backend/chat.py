"""
WHALE CHAT SYSTEM — Encrypted Group Chat Module
AES-256-GCM encrypted group messaging with admin controls
"""

from datetime import datetime
from typing import Optional, List, Tuple
import json

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Length, Optional

from models import db, User
from security import (
    EncryptionEngine, InputSanitizer, SpamDetector, 
    SecurityConfig, AuditLogger, AccountLockout
)

# ============================================
# DATABASE MODELS
# ============================================

class Group(db.Model):
    """Chat group model"""
    __tablename__ = 'chat_group'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), default='')
    encrypted_key = db.Column(db.String(500), nullable=False)  # AES-256 key encrypted with master key
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_private = db.Column(db.Boolean, default=True)
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[creator_id])
    members = db.relationship('GroupMember', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('GroupMessage', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_member_count(self):
        return self.members.count()
    
    def is_member(self, user):
        return self.members.filter_by(user_id=user.id).count() > 0
    
    def is_admin(self, user):
        membership = self.members.filter_by(user_id=user.id).first()
        return membership and membership.role == 'admin'
    
    def get_last_message(self):
        return GroupMessage.query.filter_by(group_id=self.id).order_by(GroupMessage.timestamp.desc()).first()


class GroupMember(db.Model):
    """Group membership model"""
    __tablename__ = 'group_member'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('chat_group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member')  # 'admin' or 'member'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', foreign_keys=[user_id])


class GroupMessage(db.Model):
    """Encrypted group message model"""
    __tablename__ = 'group_message'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('chat_group.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    encrypted_body = db.Column(db.Text, nullable=False)  # AES-256-GCM encrypted
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    sender = db.relationship('User', foreign_keys=[sender_id])


# ============================================
# FORMS
# ============================================

class CreateGroupForm(FlaskForm):
    name = StringField('Group Name', validators=[DataRequired(), Length(1, 50)])
    description = StringField('Description', validators=[Optional(), Length(0, 200)])
    submit = SubmitField('Create Group')


class InviteMemberForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(1, 15)])
    submit = SubmitField('Invite')


class GroupMessageForm(FlaskForm):
    body = TextAreaField('Message', validators=[DataRequired(), Length(1, 500)])
    submit = SubmitField('Send')


# ============================================
# BLUEPRINT
# ============================================

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


# ============================================
# ROUTES
# ============================================

@chat_bp.route('/')
@login_required
def groups():
    """List all groups the current user is a member of"""
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    group_ids = [m.group_id for m in memberships]
    groups = Group.query.filter(Group.id.in_(group_ids)).order_by(Group.created_at.desc()).all() if group_ids else []
    
    # Get last message for each group
    group_data = []
    for group in groups:
        last_msg = group.get_last_message()
        group_data.append({
            'group': group,
            'last_message': last_msg,
            'member_count': group.get_member_count(),
        })
    
    return render_template('chat_groups.html', groups=group_data)


@chat_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_group():
    """Create a new encrypted group"""
    form = CreateGroupForm()
    
    if form.validate_on_submit():
        name = InputSanitizer.sanitize_plain_text(form.name.data, 50)
        description = InputSanitizer.sanitize_plain_text(form.description.data, 200)
        
        if not name:
            flash('Group name is required', 'danger')
            return render_template('create_group.html', form=form)
        
        # Generate group encryption key
        encryption = current_app.encryption
        group_key = encryption.generate_group_key()
        encrypted_key = encryption.encrypt_group_key(group_key)
        
        # Create group
        group = Group(
            name=name,
            description=description,
            encrypted_key=encrypted_key,
            creator_id=current_user.id,
        )
        db.session.add(group)
        db.session.flush()  # Get group ID
        
        # Add creator as admin
        membership = GroupMember(
            group_id=group.id,
            user_id=current_user.id,
            role='admin'
        )
        db.session.add(membership)
        db.session.commit()
        
        current_app.audit_logger.log_event(
            'group_created',
            user_id=current_user.id,
            details={'group_id': group.id, 'group_name': name}
        )
        
        flash(f'Group "{name}" created successfully!', 'success')
        return redirect(url_for('chat.group_chat', group_id=group.id))
    
    return render_template('create_group.html', form=form)


@chat_bp.route('/<int:group_id>', methods=['GET', 'POST'])
@login_required
def group_chat(group_id):
    """View and send messages in a group"""
    group = Group.query.get_or_404(group_id)
    
    # Check membership
    if not group.is_member(current_user):
        flash('You are not a member of this group', 'warning')
        return redirect(url_for('chat.groups'))
    
    form = GroupMessageForm()
    
    if form.validate_on_submit():
        body = InputSanitizer.sanitize_plain_text(form.body.data, 500)
        
        if not body:
            flash('Message cannot be empty', 'danger')
            return redirect(url_for('chat.group_chat', group_id=group_id))
        
        # Check for spam
        is_spam, score = SpamDetector.is_spam(body)
        if is_spam:
            current_app.audit_logger.log_suspicious_activity(
                current_user.id,
                f'Spam detected in group {group_id} (score: {score})'
            )
            flash('Message flagged as spam. Please try again.', 'warning')
            return redirect(url_for('chat.group_chat', group_id=group_id))
        
        # Encrypt the message
        encryption = current_app.encryption
        encrypted_body = encryption.encrypt_message(body)
        
        msg = GroupMessage(
            group_id=group.id,
            sender_id=current_user.id,
            encrypted_body=encrypted_body
        )
        db.session.add(msg)
        db.session.commit()
        
        return redirect(url_for('chat.group_chat', group_id=group_id))
    
    # Get messages (decrypted for display)
    messages = GroupMessage.query.filter_by(group_id=group.id).order_by(GroupMessage.timestamp.asc()).all()
    encryption = current_app.encryption
    
    decrypted_messages = []
    for msg in messages:
        decrypted_body = encryption.decrypt_message(msg.encrypted_body)
        decrypted_messages.append({
            'id': msg.id,
            'sender': msg.sender,
            'body': decrypted_body,
            'timestamp': msg.timestamp,
            'is_sender': msg.sender_id == current_user.id,
        })
    
    members = GroupMember.query.filter_by(group_id=group.id).all()
    
    return render_template('group_chat.html', 
                         group=group, 
                         messages=decrypted_messages, 
                         members=members,
                         form=form,
                         is_admin=group.is_admin(current_user))


@chat_bp.route('/<int:group_id>/invite', methods=['GET', 'POST'])
@login_required
def invite_member(group_id):
    """Invite a user to a group"""
    group = Group.query.get_or_404(group_id)
    
    # Check admin status
    if not group.is_admin(current_user):
        flash('Only group admins can invite members', 'warning')
        return redirect(url_for('chat.group_chat', group_id=group_id))
    
    form = InviteMemberForm()
    
    if form.validate_on_submit():
        username = InputSanitizer.sanitize_username(form.username.data)
        user = User.query.filter_by(username=username).first()
        
        if not user:
            flash('User not found', 'danger')
            return render_template('invite_member.html', form=form, group=group)
        
        if group.is_member(user):
            flash(f'{user.username} is already a member', 'warning')
            return render_template('invite_member.html', form=form, group=group)
        
        membership = GroupMember(
            group_id=group.id,
            user_id=user.id,
            role='member'
        )
        db.session.add(membership)
        db.session.commit()
        
        current_app.audit_logger.log_event(
            'member_invited',
            user_id=current_user.id,
            details={'group_id': group.id, 'invited_user_id': user.id}
        )
        
        flash(f'{user.username} has been added to the group!', 'success')
        return redirect(url_for('chat.group_chat', group_id=group.id))
    
    return render_template('invite_member.html', form=form, group=group)


@chat_bp.route('/<int:group_id>/remove/<int:user_id>')
@login_required
def remove_member(group_id, user_id):
    """Remove a member from a group"""
    group = Group.query.get_or_404(group_id)
    
    if not group.is_admin(current_user):
        flash('Only group admins can remove members', 'warning')
        return redirect(url_for('chat.group_chat', group_id=group_id))
    
    membership = GroupMember.query.filter_by(group_id=group.id, user_id=user_id).first()
    if not membership:
        flash('Member not found', 'danger')
        return redirect(url_for('chat.group_chat', group_id=group_id))
    
    if membership.role == 'admin' and membership.user_id != current_user.id:
        flash('Cannot remove another admin', 'warning')
        return redirect(url_for('chat.group_chat', group_id=group_id))
    
    db.session.delete(membership)
    db.session.commit()
    
    current_app.audit_logger.log_event(
        'member_removed',
        user_id=current_user.id,
        details={'group_id': group.id, 'removed_user_id': user_id}
    )
    
    flash('Member removed from group', 'info')
    return redirect(url_for('chat.group_chat', group_id=group_id))


@chat_bp.route('/<int:group_id>/leave')
@login_required
def leave_group(group_id):
    """Leave a group"""
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMember.query.filter_by(group_id=group.id, user_id=current_user.id).first()
    if not membership:
        flash('You are not a member of this group', 'warning')
        return redirect(url_for('chat.groups'))
    
    db.session.delete(membership)
    
    # If no members left, delete the group
    if group.get_member_count() <= 1:
        db.session.delete(group)
    
    db.session.commit()
    
    flash('You have left the group', 'info')
    return redirect(url_for('chat.groups'))


@chat_bp.route('/<int:group_id>/delete')
@login_required
def delete_group(group_id):
    """Delete a group (admin only)"""
    group = Group.query.get_or_404(group_id)
    
    if not group.is_admin(current_user):
        flash('Only group admins can delete the group', 'warning')
        return redirect(url_for('chat.group_chat', group_id=group_id))
    
    db.session.delete(group)
    db.session.commit()
    
    current_app.audit_logger.log_event(
        'group_deleted',
        user_id=current_user.id,
        details={'group_id': group.id, 'group_name': group.name}
    )
    
    flash('Group deleted', 'info')
    return redirect(url_for('chat.groups'))


@chat_bp.route('/api/search_users')
@login_required
def search_users():
    """API endpoint to search users for inviting"""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    
    users = User.query.filter(
        User.username.like(f'%{q}%'),
        User.id != current_user.id
    ).limit(10).all()
    
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'profile_pic': u.profile_pic
    } for u in users])