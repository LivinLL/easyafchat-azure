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

# ============================================================================
# Email verification utility functions
# 
# These functions support the email verification flow that occurs after
# OAuth authentication but before granting access to the dashboard.
# This ensures users verify ownership of their email address before
# being able to manage chatbots.
# ============================================================================

def generate_verification_token():
    """Generate a random token for email verification"""
    import secrets
    return secrets.token_urlsafe(32)

def get_verification_link(token, external=True):
    """Generate a full verification URL with token."""
    from flask import current_app, url_for
    
    # Use _external=True to generate a full URL with domain
    return url_for('auth.verify_email', token=token, _external=external)

def send_verification_email(email, name, token):
    """Send verification email to the user."""
    from flask import current_app
    from flask_mail import Message
    from app import mail
    
    verification_link = get_verification_link(token)
    
    # Create the email
    subject = "Verify Your GoEasyChat Account"
    
    # Create simple text-based email
    body = f"""Hello {name},

Thank you for creating your GoEasyChat account. Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you did not create this account, please ignore this email.

Thanks,
The GoEasyChat Team
"""
    
    msg = Message(
        subject=subject,
        recipients=[email],
        body=body
    )
    
    # Send the email
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending verification email: {e}")
        return False

def is_token_expired(timestamp, expiry_hours=24):
    """Check if a token has expired based on its creation timestamp."""
    from datetime import datetime, timedelta
    
    if not timestamp:
        return True
        
    # Get current time
    now = datetime.utcnow()
    
    # Convert timestamp to datetime if it's not already
    if isinstance(timestamp, str):
        try:
            # Try parsing the string timestamp
            timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            try:
                # Try alternate format without microseconds
                timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # If parsing fails, consider it expired
                return True
    
    # Calculate expiration time
    expiry_time = timestamp + timedelta(hours=expiry_hours)
    
    # Return True if token has expired
    return now > expiry_time