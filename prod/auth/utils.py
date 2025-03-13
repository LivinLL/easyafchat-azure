import secrets
import hashlib
from flask import current_app
from datetime import datetime, timedelta
import uuid
import bcrypt

def generate_password_hash(password):
    """Generate a bcrypt hash for the given password"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def check_password_hash(stored_hash, provided_password):
    """Check if the provided password matches the stored hash"""
    stored_bytes = stored_hash.encode('utf-8')
    provided_bytes = provided_password.encode('utf-8')
    return bcrypt.checkpw(provided_bytes, stored_bytes)

def generate_token():
    """Generate a secure random token for password reset or email verification"""
    return secrets.token_urlsafe(32)

def generate_user_id():
    """Generate a unique user ID"""
    return str(uuid.uuid4())

def generate_google_state_token():
    """Generate a state token for OAuth to prevent CSRF"""
    return secrets.token_hex(16)

def is_token_valid(token_created_at, expiry_hours=24):
    """Check if a token is still valid based on creation time"""
    if not token_created_at:
        return False
    
    expiry_time = token_created_at + timedelta(hours=expiry_hours)
    return datetime.utcnow() < expiry_time
