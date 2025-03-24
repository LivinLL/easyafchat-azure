import os
from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app
from . import auth_bp
from .utils import generate_password_hash, check_password_hash, generate_token, generate_user_id, generate_google_state_token, is_token_valid
from datetime import datetime
import requests
import json
from urllib.parse import urlencode
import sqlite3
import psycopg2
from database import get_db_connection
from flask_wtf.csrf import validate_csrf

# Google OAuth Configuration
from dotenv import load_dotenv
load_dotenv()  # Load .env file directly in the module
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
print(f"AUTH ROUTES - Google Client ID: {GOOGLE_CLIENT_ID}")
print(f"AUTH ROUTES - Google Client Secret: {'[REDACTED]' if GOOGLE_CLIENT_SECRET else 'None'}")

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Microsoft OAuth Configuration
MS_AUTH_CLIENT_ID = os.environ.get('MS_AUTH_CLIENT_ID')
MS_AUTH_CLIENT_SECRET = os.environ.get('MS_AUTH_CLIENT_SECRET')
print(f"AUTH ROUTES - Microsoft Client ID: {MS_AUTH_CLIENT_ID}")
print(f"AUTH ROUTES - Microsoft Client Secret: {'[REDACTED]' if MS_AUTH_CLIENT_SECRET else 'None'}")

# Microsoft OAuth endpoints
MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_URL = "https://graph.microsoft.com/v1.0/me"

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

@auth_bp.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'GET':
        chatbot_id = request.args.get('chatbot_id')
        return render_template('auth/signin.html', chatbot_id=chatbot_id)
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        chatbot_id = request.form.get('chatbot_id')
        
        if not email or not password:
            flash('Email and password are required', 'error')
            return redirect(url_for('auth.signin', chatbot_id=chatbot_id))
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Check if using SQLite or PostgreSQL
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            else:
                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            
            user = cursor.fetchone()
            
            # Convert tuple to dict for easier access if user exists
            if user:
                columns = [desc[0] for desc in cursor.description]
                user_dict = dict(zip(columns, user))
                
                # Check password only if not a Google account
                if not user_dict.get('is_google_account') and check_password_hash(user_dict.get('password_hash', ''), password):
                    # Set session variables
                    session['user_id'] = user_dict.get('user_id')
                    session['email'] = user_dict.get('email')
                    session['name'] = user_dict.get('name')
                    flash('Login successful!', 'success')
                    
                    # If there's a chatbot_id, claim it and redirect to dashboard
                    if chatbot_id:
                        # Check if chatbot exists and isn't claimed
                        if os.environ.get('DB_TYPE') == 'postgresql':
                            cursor.execute("SELECT * FROM companies WHERE chatbot_id = %s", (chatbot_id,))
                        else:
                            cursor.execute("SELECT * FROM companies WHERE chatbot_id = ?", (chatbot_id,))
                            
                        chatbot = cursor.fetchone()
                        
                        if chatbot:
                            columns = [desc[0] for desc in cursor.description]
                            chatbot_dict = dict(zip(columns, chatbot))
                            
                            if chatbot_dict.get('user_id') and chatbot_dict.get('user_id') != session['user_id']:
                                flash('This chatbot has already been claimed by another user', 'error')
                            elif not chatbot_dict.get('user_id'):
                                # Update chatbot with user_id
                                if os.environ.get('DB_TYPE') == 'postgresql':
                                    cursor.execute(
                                        "UPDATE companies SET user_id = %s, updated_at = %s WHERE chatbot_id = %s",
                                        (session['user_id'], datetime.utcnow(), chatbot_id)
                                    )
                                else:
                                    cursor.execute(
                                        "UPDATE companies SET user_id = ?, updated_at = ? WHERE chatbot_id = ?",
                                        (session['user_id'], datetime.utcnow(), chatbot_id)
                                    )
                                conn.commit()
                                flash('Chatbot claimed successfully!', 'success')
                    
                    # Always redirect to dashboard after successful login
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid email or password', 'error')
            else:
                flash('Invalid email or password', 'error')
                
        except (sqlite3.Error, psycopg2.Error) as e:
            flash(f'Database error: {e}', 'error')
        finally:
            conn.close()
        
        return redirect(url_for('auth.signin', chatbot_id=chatbot_id))

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        chatbot_id = request.args.get('chatbot_id')
        website_url = request.args.get('website_url', '')
        return render_template('auth/signup.html', chatbot_id=chatbot_id, website_url=website_url)
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        company_name = request.form.get('company_name')
        chatbot_id = request.form.get('chatbot_id')
        
        if not email or not password or not name:
            flash('Name, email, and password are required', 'error')
            return redirect(url_for('auth.signup', chatbot_id=chatbot_id))
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Check if email already exists
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            else:
                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash('Email already registered', 'error')
                return redirect(url_for('auth.signup', chatbot_id=chatbot_id))
            
            # Create new user
            user_id = generate_user_id()
            password_hash = generate_password_hash(password)
            now = datetime.utcnow()
            
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute(
                    "INSERT INTO users (user_id, email, password_hash, is_google_account, name, company_name, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (user_id, email, password_hash, False, name, company_name, now, now)
                )
            else:
                cursor.execute(
                    "INSERT INTO users (user_id, email, password_hash, is_google_account, name, company_name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, email, password_hash, False, name, company_name, now, now)
                )
                
            conn.commit()
            
            # Set session variables
            session['user_id'] = user_id
            session['email'] = email
            session['name'] = name
            
            flash('Account created successfully!', 'success')
            
            # If there's a chatbot_id, claim it and redirect to dashboard
            if chatbot_id:
                # Check if chatbot exists and isn't claimed
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute("SELECT * FROM companies WHERE chatbot_id = %s", (chatbot_id,))
                else:
                    cursor.execute("SELECT * FROM companies WHERE chatbot_id = ?", (chatbot_id,))
                    
                chatbot = cursor.fetchone()
                
                if chatbot:
                    columns = [desc[0] for desc in cursor.description]
                    chatbot_dict = dict(zip(columns, chatbot))
                    
                    if not chatbot_dict.get('user_id'):
                        # Update chatbot with user_id
                        if os.environ.get('DB_TYPE') == 'postgresql':
                            cursor.execute(
                                "UPDATE companies SET user_id = %s, updated_at = %s WHERE chatbot_id = %s",
                                (user_id, datetime.utcnow(), chatbot_id)
                            )
                        else:
                            cursor.execute(
                                "UPDATE companies SET user_id = ?, updated_at = ? WHERE chatbot_id = ?",
                                (user_id, datetime.utcnow(), chatbot_id)
                            )
                        conn.commit()
                        flash('Chatbot claimed successfully!', 'success')
                
                return redirect(url_for('dashboard'))
            
            return redirect(url_for('home'))
            
        except (sqlite3.Error, psycopg2.Error) as e:
            conn.rollback()
            flash(f'Error creating account: {e}', 'error')
        finally:
            conn.close()
        
        return redirect(url_for('auth.signup', chatbot_id=chatbot_id))

@auth_bp.route('/google', methods=['GET'])
def google_login():
    # Create a state token to prevent CSRF
    state = generate_google_state_token()
    session['google_state'] = state
    
    # Store chatbot_id in session if provided
    chatbot_id = request.args.get('chatbot_id')
    if chatbot_id:
        session['chatbot_id'] = chatbot_id
    
    # Always use HTTPS for production environments
    if os.environ.get('ENVIRONMENT') == 'production':
        base_url = f"https://{request.host}"
        redirect_uri = f"{base_url}/auth/google/callback"
    else:
        # For local development
        redirect_uri = f"{request.host_url.rstrip('/')}/auth/google/callback"
    
    # Debug logging
    print(f"Google Client ID: {GOOGLE_CLIENT_ID}")
    print(f"Redirect URI: {redirect_uri}")
    
    # Google OAuth request parameters
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'response_type': 'code',
        'scope': 'openid email profile',
        'redirect_uri': redirect_uri,
        'state': state,
        'prompt': 'select_account'
    }
    
    # Debug the full URL
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    print(f"Auth URL: {auth_url}")
    
    # Redirect to Google's OAuth 2.0 server
    return redirect(auth_url)

@auth_bp.route('/microsoft', methods=['GET'])
def microsoft_login():
    # Create a state token to prevent CSRF
    state = generate_google_state_token()  # Reuse the same function for state token
    session['microsoft_state'] = state
    
    # Store chatbot_id in session if provided
    chatbot_id = request.args.get('chatbot_id')
    if chatbot_id:
        session['chatbot_id'] = chatbot_id
    
    # Always use HTTPS for production environments
    if os.environ.get('ENVIRONMENT') == 'production':
        base_url = f"https://{request.host}"
        redirect_uri = f"{base_url}/auth/microsoft/callback"
    else:
        # For local development
        redirect_uri = f"{request.host_url.rstrip('/')}/auth/microsoft/callback"
    
    # Debug logging
    print(f"Microsoft Client ID: {MS_AUTH_CLIENT_ID}")
    print(f"Redirect URI: {redirect_uri}")
    
    # Microsoft OAuth request parameters
    params = {
        'client_id': MS_AUTH_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': 'openid profile email User.Read',
        'state': state,
        'response_mode': 'query',
        'prompt': 'select_account'
    }
    
    # Debug the full URL
    auth_url = f"{MS_AUTH_URL}?{urlencode(params)}"
    print(f"Auth URL: {auth_url}")
    
    # Redirect to Microsoft's OAuth server
    return redirect(auth_url)

@auth_bp.route('/microsoft/callback', methods=['GET'])
def microsoft_callback():
    # Verify state token to prevent CSRF
    state = request.args.get('state')
    session_state = session.pop('microsoft_state', None)
    
    if not state or state != session_state:
        flash('Authentication failed: Invalid state', 'error')
        return redirect(url_for('auth.signin'))
    
    # Get authorization code from request
    code = request.args.get('code')
    if not code:
        flash('Authentication failed: No authorization code received', 'error')
        return redirect(url_for('auth.signin'))
    
    # Get chatbot_id from session if present
    chatbot_id = session.get('chatbot_id')
    
    # Exchange authorization code for tokens
    if os.environ.get('ENVIRONMENT') == 'production':
        base_url = f"https://{request.host}"
        redirect_uri = f"{base_url}/auth/microsoft/callback"
    else:
        # For local development
        redirect_uri = f"{request.host_url.rstrip('/')}/auth/microsoft/callback"
        
    token_data = {
        'client_id': MS_AUTH_CLIENT_ID,
        'client_secret': MS_AUTH_CLIENT_SECRET,
        'code': code,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    try:
        token_response = requests.post(MS_TOKEN_URL, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
        
        # Get user info with access token
        userinfo_response = requests.get(
            MS_GRAPH_URL,
            headers={'Authorization': f'Bearer {tokens["access_token"]}'}
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
        
        # Extract user details
        microsoft_id = userinfo.get('id')
        email = userinfo.get('userPrincipalName') or userinfo.get('mail')
        name = userinfo.get('displayName')
        
        if not microsoft_id or not email:
            flash('Authentication failed: Insufficient user info', 'error')
            return redirect(url_for('auth.signin'))
        
        # Check if user exists or create new account
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # First, check if user exists by Microsoft ID
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE microsoft_id = %s", (microsoft_id,))
            else:
                cursor.execute("SELECT * FROM users WHERE microsoft_id = ?", (microsoft_id,))
                
            user = cursor.fetchone()
            
            # If not found by Microsoft ID, check by email
            if not user:
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                else:
                    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                    
                user = cursor.fetchone()
            
            now = datetime.utcnow()
            
            if user:
                # User exists, update Microsoft info if needed
                columns = [desc[0] for desc in cursor.description]
                user_dict = dict(zip(columns, user))
                user_id = user_dict.get('user_id')
                
                # Update Microsoft ID and other info if it's missing
                if not user_dict.get('microsoft_id'):
                    if os.environ.get('DB_TYPE') == 'postgresql':
                        cursor.execute(
                            "UPDATE users SET microsoft_id = %s, is_microsoft_account = %s, name = %s, updated_at = %s WHERE user_id = %s",
                            (microsoft_id, True, name, now, user_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE users SET microsoft_id = ?, is_microsoft_account = ?, name = ?, updated_at = ? WHERE user_id = ?",
                            (microsoft_id, True, name, now, user_id)
                        )
                    conn.commit()
            else:
                # Create new user
                user_id = generate_user_id()
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute(
                        "INSERT INTO users (user_id, email, microsoft_id, is_microsoft_account, name, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (user_id, email, microsoft_id, True, name, now, now)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO users (user_id, email, microsoft_id, is_microsoft_account, name, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (user_id, email, microsoft_id, True, name, now, now)
                    )
                conn.commit()
            
            # Set session variables
            session['user_id'] = user_id
            session['email'] = email
            session['name'] = name
            
            flash('Microsoft login successful!', 'success')
            
            # If there's a chatbot_id, claim it and redirect to dashboard
            if chatbot_id:
                # Check if chatbot exists and isn't claimed
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute("SELECT * FROM companies WHERE chatbot_id = %s", (chatbot_id,))
                else:
                    cursor.execute("SELECT * FROM companies WHERE chatbot_id = ?", (chatbot_id,))
                    
                chatbot = cursor.fetchone()
                
                if chatbot:
                    columns = [desc[0] for desc in cursor.description]
                    chatbot_dict = dict(zip(columns, chatbot))
                    
                    if chatbot_dict.get('user_id') and chatbot_dict.get('user_id') != user_id:
                        flash('This chatbot has already been claimed by another user', 'error')
                    elif not chatbot_dict.get('user_id'):
                        # Update chatbot with user_id
                        if os.environ.get('DB_TYPE') == 'postgresql':
                            cursor.execute(
                                "UPDATE companies SET user_id = %s, updated_at = %s WHERE chatbot_id = %s",
                                (user_id, datetime.utcnow(), chatbot_id)
                            )
                        else:
                            cursor.execute(
                                "UPDATE companies SET user_id = ?, updated_at = ? WHERE chatbot_id = ?",
                                (user_id, datetime.utcnow(), chatbot_id)
                            )
                        conn.commit()
                        flash('Chatbot claimed successfully!', 'success')
                
                # Clear chatbot_id from session
                session.pop('chatbot_id', None)
            
            # Always redirect to dashboard after successful authentication
            return redirect(url_for('dashboard'))
            
        except (sqlite3.Error, psycopg2.Error) as e:
            conn.rollback()
            flash(f'Database error: {e}', 'error')
        finally:
            conn.close()
            
    except requests.RequestException as e:
        flash(f'Authentication failed: {e}', 'error')
    
    return redirect(url_for('auth.signin'))


@auth_bp.route('/google/callback', methods=['GET'])
def google_callback():
    # Verify state token to prevent CSRF
    state = request.args.get('state')
    session_state = session.pop('google_state', None)
    
    if not state or state != session_state:
        flash('Authentication failed: Invalid state', 'error')
        return redirect(url_for('auth.signin'))
    
    # Get authorization code from request
    code = request.args.get('code')
    if not code:
        flash('Authentication failed: No authorization code received', 'error')
        return redirect(url_for('auth.signin'))
    
    # Get chatbot_id from session if present
    chatbot_id = session.get('chatbot_id')
    
    # Exchange authorization code for tokens
    if os.environ.get('ENVIRONMENT') == 'production':
        base_url = f"https://{request.host}"
        redirect_uri = f"{base_url}/auth/google/callback"
    else:
        # For local development
        redirect_uri = f"{request.host_url.rstrip('/')}/auth/google/callback"
        
    token_data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    try:
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
        
        # Get user info with access token
        userinfo_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {tokens["access_token"]}'}
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
        
        # Extract user details
        google_id = userinfo.get('sub')
        email = userinfo.get('email')
        name = userinfo.get('name')
        
        if not google_id or not email:
            flash('Authentication failed: Insufficient user info', 'error')
            return redirect(url_for('auth.signin'))
        
        # Check if user exists or create new account
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # First, check if user exists by Google ID
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE google_id = %s", (google_id,))
            else:
                cursor.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
                
            user = cursor.fetchone()
            
            # If not found by Google ID, check by email
            if not user:
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                else:
                    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                    
                user = cursor.fetchone()
            
            now = datetime.utcnow()
            
            if user:
                # User exists, update Google info if needed
                columns = [desc[0] for desc in cursor.description]
                user_dict = dict(zip(columns, user))
                user_id = user_dict.get('user_id')
                
                # Update Google ID and other info if it's missing
                if not user_dict.get('google_id'):
                    if os.environ.get('DB_TYPE') == 'postgresql':
                        cursor.execute(
                            "UPDATE users SET google_id = %s, is_google_account = %s, name = %s, updated_at = %s WHERE user_id = %s",
                            (google_id, True, name, now, user_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE users SET google_id = ?, is_google_account = ?, name = ?, updated_at = ? WHERE user_id = ?",
                            (google_id, True, name, now, user_id)
                        )
                    conn.commit()
            else:
                # Create new user
                user_id = generate_user_id()
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute(
                        "INSERT INTO users (user_id, email, google_id, is_google_account, name, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (user_id, email, google_id, True, name, now, now)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO users (user_id, email, google_id, is_google_account, name, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (user_id, email, google_id, True, name, now, now)
                    )
                conn.commit()
            
            # Set session variables
            session['user_id'] = user_id
            session['email'] = email
            session['name'] = name
            
            flash('Google login successful!', 'success')
            
            # If there's a chatbot_id, claim it and redirect to dashboard
            if chatbot_id:
                # Check if chatbot exists and isn't claimed
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute("SELECT * FROM companies WHERE chatbot_id = %s", (chatbot_id,))
                else:
                    cursor.execute("SELECT * FROM companies WHERE chatbot_id = ?", (chatbot_id,))
                    
                chatbot = cursor.fetchone()
                
                if chatbot:
                    columns = [desc[0] for desc in cursor.description]
                    chatbot_dict = dict(zip(columns, chatbot))
                    
                    if chatbot_dict.get('user_id') and chatbot_dict.get('user_id') != user_id:
                        flash('This chatbot has already been claimed by another user', 'error')
                    elif not chatbot_dict.get('user_id'):
                        # Update chatbot with user_id
                        if os.environ.get('DB_TYPE') == 'postgresql':
                            cursor.execute(
                                "UPDATE companies SET user_id = %s, updated_at = %s WHERE chatbot_id = %s",
                                (user_id, datetime.utcnow(), chatbot_id)
                            )
                        else:
                            cursor.execute(
                                "UPDATE companies SET user_id = ?, updated_at = ? WHERE chatbot_id = ?",
                                (user_id, datetime.utcnow(), chatbot_id)
                            )
                        conn.commit()
                        flash('Chatbot claimed successfully!', 'success')
                
                # Clear chatbot_id from session
                session.pop('chatbot_id', None)
            
            # Always redirect to dashboard after successful authentication
            return redirect(url_for('dashboard'))
            
        except (sqlite3.Error, psycopg2.Error) as e:
            conn.rollback()
            flash(f'Database error: {e}', 'error')
        finally:
            conn.close()
            
    except requests.RequestException as e:
        flash(f'Authentication failed: {e}', 'error')
    
    return redirect(url_for('auth.signin'))

@auth_bp.route('/logout', methods=['GET'])
def logout():
    # Clear session
    session.pop('user_id', None)
    session.pop('email', None)
    session.pop('name', None)
    
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('auth/reset_password.html')
    
    if request.method == 'POST':
        email = request.form.get('email')
        
        if not email:
            flash('Email is required', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        # Generate reset token and store with user
        reset_token = generate_token()
        now = datetime.utcnow()
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Check if user exists
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            else:
                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                
            user = cursor.fetchone()
            
            if user:
                # Update user with reset token
                columns = [desc[0] for desc in cursor.description]
                user_dict = dict(zip(columns, user))
                
                if os.environ.get('DB_TYPE') == 'postgresql':
                    cursor.execute(
                        "UPDATE users SET reset_token = %s, reset_token_created_at = %s, updated_at = %s WHERE user_id = %s",
                        (reset_token, now, now, user_dict.get('user_id'))
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET reset_token = ?, reset_token_created_at = ?, updated_at = ? WHERE user_id = ?",
                        (reset_token, now, now, user_dict.get('user_id'))
                    )
                conn.commit()
                
                # TODO: Send email with reset link
                # For now, just display the token (in production you would email this)
                reset_url = url_for('auth.reset_password', token=reset_token, _external=True)
                flash(f'Password reset link: {reset_url}', 'info')
            else:
                # Still show success to prevent email enumeration
                flash('If your email is registered, you will receive a password reset link', 'info')
                
        except (sqlite3.Error, psycopg2.Error) as e:
            conn.rollback()
            flash(f'Error processing request: {e}', 'error')
        finally:
            conn.close()
            
        return redirect(url_for('auth.forgot_password'))

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'GET':
        # Check if token is valid
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE reset_token = %s", (token,))
            else:
                cursor.execute("SELECT * FROM users WHERE reset_token = ?", (token,))
                
            user = cursor.fetchone()
            
            if not user:
                flash('Invalid or expired reset token', 'error')
                return redirect(url_for('auth.signin'))
            
            columns = [desc[0] for desc in cursor.description]
            user_dict = dict(zip(columns, user))
            
            # Check if token is still valid (24 hours)
            token_created_at = user_dict.get('reset_token_created_at')
            if not is_token_valid(token_created_at, 24):
                flash('Reset token has expired', 'error')
                return redirect(url_for('auth.signin'))
                
            return render_template('auth/reset_password.html', token=token, reset_mode=True)
            
        except (sqlite3.Error, psycopg2.Error) as e:
            flash(f'Error processing request: {e}', 'error')
        finally:
            conn.close()
            
        return redirect(url_for('auth.signin'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Both password fields are required', 'error')
            return redirect(url_for('auth.reset_password', token=token))
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('auth.reset_password', token=token))
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE reset_token = %s", (token,))
            else:
                cursor.execute("SELECT * FROM users WHERE reset_token = ?", (token,))
                
            user = cursor.fetchone()
            
            if not user:
                flash('Invalid or expired reset token', 'error')
                return redirect(url_for('auth.signin'))
            
            columns = [desc[0] for desc in cursor.description]
            user_dict = dict(zip(columns, user))
            
            # Check if token is still valid
            token_created_at = user_dict.get('reset_token_created_at')
            if not is_token_valid(token_created_at, 24):
                flash('Reset token has expired', 'error')
                return redirect(url_for('auth.signin'))
            
            # Update password
            password_hash = generate_password_hash(password)
            now = datetime.utcnow()
            
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute(
                    "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_created_at = NULL, updated_at = %s "
                    "WHERE user_id = %s",
                    (password_hash, now, user_dict.get('user_id'))
                )
            else:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_created_at = NULL, updated_at = ? "
                    "WHERE user_id = ?",
                    (password_hash, now, user_dict.get('user_id'))
                )
            conn.commit()
            
            flash('Password has been reset successfully!', 'success')
            return redirect(url_for('auth.signin'))
            
        except (sqlite3.Error, psycopg2.Error) as e:
            conn.rollback()
            flash(f'Error processing request: {e}', 'error')
        finally:
            conn.close()
            
        return redirect(url_for('auth.reset_password', token=token))

@auth_bp.route('/claim-chatbot/<chatbot_id>', methods=['POST'])
def claim_chatbot(chatbot_id):
    # Check for CSRF Token
    if request.is_json and not current_app.config.get('TESTING'):
        # For API/AJAX requests, check the X-CSRFToken header
        csrf_token = request.headers.get('X-CSRFToken')
        if not csrf_token or not validate_csrf(csrf_token):
            return jsonify({'success': False, 'message': 'CSRF token missing or invalid'}), 400
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'You must be logged in to claim a chatbot'}), 401
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Check if chatbot exists and isn't claimed
        if os.environ.get('DB_TYPE') == 'postgresql':
            cursor.execute("SELECT * FROM companies WHERE chatbot_id = %s", (chatbot_id,))
        else:
            cursor.execute("SELECT * FROM companies WHERE chatbot_id = ?", (chatbot_id,))
            
        chatbot = cursor.fetchone()
        
        if not chatbot:
            return jsonify({'success': False, 'message': 'Chatbot not found'}), 404
        
        columns = [desc[0] for desc in cursor.description]
        chatbot_dict = dict(zip(columns, chatbot))
        
        if chatbot_dict.get('user_id') and chatbot_dict.get('user_id') != user_id:
            return jsonify({'success': False, 'message': 'This chatbot is already claimed by another user'}), 403
        
        if chatbot_dict.get('user_id') == user_id:
            return jsonify({'success': True, 'message': 'This chatbot is already yours'})
        
        # Update chatbot with user_id
        if os.environ.get('DB_TYPE') == 'postgresql':
            cursor.execute(
                "UPDATE companies SET user_id = %s, updated_at = %s WHERE chatbot_id = %s",
                (user_id, datetime.utcnow(), chatbot_id)
            )
        else:
            cursor.execute(
                "UPDATE companies SET user_id = ?, updated_at = ? WHERE chatbot_id = ?",
                (user_id, datetime.utcnow(), chatbot_id)
            )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Chatbot claimed successfully'})
        
    except (sqlite3.Error, psycopg2.Error) as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()
