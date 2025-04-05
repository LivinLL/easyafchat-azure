from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from pinecone import Pinecone
from datetime import datetime, UTC
from typing import List, Dict, Tuple, Optional
from chat_handler import ChatPromptHandler
from flask_cors import CORS
from db_leads import leads_blueprint, init_leads_blueprint
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message  # Add Flask-Mail imports
import time
import os
import validators
import trafilatura
import requests
import uuid
import re
import json
import vector_cache
from flask_session import Session
from auth import auth_bp
import sqlite3
import psycopg2
from psycopg2 import sql
from flask_wtf.csrf import CSRFProtect
from db_metrics import metrics_blueprint, init_metrics_blueprint, save_chat_message


# Import the admin dashboard blueprint
from admin_dashboard import admin_dashboard, init_admin_dashboard
from documents_blueprint import documents_blueprint, init_documents_blueprint

# Load environment variables from .env only in development
# Set ENVIRONMENT to production on Azure
if os.environ.get('ENVIRONMENT') != 'production':
    load_dotenv()

# Check for Google OAuth credentials
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print("WARNING: Google OAuth credentials not set. Google sign-in will not work.")
    print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")

# Check for Microsoft OAuth credentials
MS_AUTH_CLIENT_ID = os.environ.get('MS_AUTH_CLIENT_ID')
MS_AUTH_CLIENT_SECRET = os.environ.get('MS_AUTH_CLIENT_SECRET')
if not MS_AUTH_CLIENT_ID or not MS_AUTH_CLIENT_SECRET:
    print("WARNING: Microsoft OAuth credentials not set. Microsoft sign-in will not work.")
    print("Set MS_AUTH_CLIENT_ID and MS_AUTH_CLIENT_SECRET environment variables.")

# Import database initialization and connection functions
from database import initialize_database, connect_to_db

# Initialize the database
initialize_database(verbose=True)

# Initialize Flask app
app = Flask(__name__)

# Initialize Flask-Mail
mail = Mail()

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Add HTTPS configuration and ProxyFix
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Add rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window",  # Simple strategy that's effective for most cases
)

# Add reCAPTCHA configuration
app.config["CAPTCHA_SITE_KEY"] = os.environ.get("CAPTCHA_SITE_KEY", "")
app.config["CAPTCHA_SECRET_KEY"] = os.environ.get("CAPTCHA_SECRET_KEY", "")

# Configure server-side session
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(os.getcwd(), "flask_session")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-for-session")
Session(app)

# Email configuration for Flask-Mail
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.zoho.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', 'yes', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = ('GoEasyChat', os.environ.get('MAIL_USERNAME', 'agenteasy@goeasychat.com'))
mail.init_app(app)

# Check if mail credentials are configured
if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    print("WARNING: Email credentials not set. Email verification will not work.")
    print("Set MAIL_USERNAME and MAIL_PASSWORD environment variables.")

CORS(app)  # Add this line
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pinecone_client = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# Initialize and register the leads blueprint
init_leads_blueprint(openai_client, pinecone_client)
app.register_blueprint(leads_blueprint)

# Constants
PINECONE_INDEX = "all-companies"
PINECONE_HOST = "https://all-companies-6ctd3g7.svc.aped-4627-b74a.pinecone.io"
DB_PATH = os.getenv('DB_PATH', 'easyafchat.db')
APIFLASH_KEY = os.getenv('APIFLASH_ACCESS_KEY', '')  # Add this line


# Initialize and register the admin dashboard blueprint
init_admin_dashboard(openai_client, pinecone_client, DB_PATH, PINECONE_INDEX)
# Exempt admin dashboard from CSRF protection
csrf.exempt(admin_dashboard)
app.register_blueprint(admin_dashboard, url_prefix='/admin-dashboard-08x7z9y2-yoursecretword')

# Initialize and register the documents blueprint
init_documents_blueprint(openai_client, pinecone_client, PINECONE_INDEX)
app.register_blueprint(documents_blueprint, url_prefix='/documents')

# Database connection variables
DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
DB_HOST = os.getenv('DB_HOST', '')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'easychat')
DB_SSL = os.getenv('DB_SSL', '')
SQLITE_DB_NAME = "easyafchat.db"

# Register the authorization blueprint
app.register_blueprint(auth_bp, url_prefix='/auth')

# Register the db_metrics.py blueprint
app.register_blueprint(metrics_blueprint, url_prefix='/metrics')

# Dictionary to track processing status
processing_status = {}

# Initialize chat handlers dictionary
chat_handlers = {}

# Import the settings blueprint for use on dashboard.html
from settings_blueprint import settings_bp

# Register the settings blueprint with the app for use on dashboard.html
app.register_blueprint(settings_bp)

@app.before_request
def check_user_session():
    """Check user session and make user info available to templates"""
    if 'user_id' in session:
        g.user = {
            'user_id': session['user_id'],
            'email': session.get('email'),
            'name': session.get('name')
        }
    else:
        g.user = None
        
@app.context_processor
def inject_user():
    """Make user info available to all templates"""
    return dict(user=g.user)

# Function to get database connection for routes
def get_db_connection():
    """Get a database connection based on environment settings"""
    if DB_TYPE.lower() == 'postgresql':
        # PostgreSQL connection (for production)
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            sslmode=DB_SSL if DB_SSL else None
        )
        
        # Set the schema search path
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(
                sql.Identifier(DB_SCHEMA)
            ))
    else:
        # SQLite connection (for development)
        conn = sqlite3.connect(SQLITE_DB_NAME)
        
    return conn


def semantic_chunk_text(text, target_size=700, extended_size=1200):
    """
    Split text into chunks based on semantic boundaries rather than pure character count.
    Preserves structure, keeps URLs with their context, and maintains semantic coherence.
    
    Args:
        text (str): Text to be chunked
        target_size (int): Target size for chunks (default: 700 characters)
        extended_size (int): Extended size limit for special cases (default: 1200 characters)
    
    Returns:
        list: List of text chunks
    """
    # If the entire text is smaller than target_size, return it as a single chunk
    if len(text) <= target_size:
        return [text]
    
    # Split text into initial sections based on double line breaks
    sections = [s.strip() for s in text.split('\n\n') if s.strip()]
    
    chunks = []
    current_chunk = ""
    current_size = 0
    
    for section in sections:
        section_size = len(section)
        contains_url = ('http://' in section or 'https://' in section or 
                        'www.' in section or '.com' in section or '.org' in section)
        
        # Check for list patterns at the start of lines
        list_pattern = any(line.strip().startswith(('- ', '• ', '* ', '· ')) or 
                           (line.strip() and line.strip()[0].isdigit() and line.strip()[1:].startswith('. ')) 
                           for line in section.split('\n'))
        
        # Special handling for sections with URLs or list patterns
        is_special_section = contains_url or list_pattern
        
        # Identify section as a heading (likely to be shorter and be a title/subtitle)
        is_heading = (section_size < 100 and '\n' not in section and 
                      (section.isupper() or section.rstrip().endswith(':') or 
                       (len(section.split()) < 10 and section[-1] not in '.?!')))
        
        # Check if section would put current chunk over extended limit
        if current_size + section_size + 1 > extended_size and current_size > 0:
            # Add current chunk to list and reset
            chunks.append(current_chunk)
            current_chunk = ""
            current_size = 0
        
        # Check if section would fit within target size or deserves extended size
        if (current_size + section_size + 1 <= target_size or 
            (is_special_section and current_size + section_size + 1 <= extended_size) or
            current_size == 0):  # Always include at least one section in a chunk
            
            # Add a separator if not starting a new chunk
            if current_size > 0:
                current_chunk += "\n\n"
                current_size += 2
            
            current_chunk += section
            current_size += section_size
        else:
            # Section doesn't fit in current chunk, check if it needs further splitting
            if section_size > extended_size:
                # Split long section by sentences if possible
                sentences = []
                # Simple but relatively effective sentence splitting
                for sentence in section.replace('!', '.').replace('?', '.').split('.'):
                    if sentence.strip():
                        sentences.append(sentence.strip() + '.')
                
                # If we can't split by sentences, fall back to splitting by lines
                if not sentences:
                    sentences = [line.strip() for line in section.split('\n') if line.strip()]
                
                # Add current chunk if we have one
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                    current_size = 0
                
                # Process sentences to create new chunks
                temp_chunk = ""
                temp_size = 0
                
                for sentence in sentences:
                    if temp_size + len(sentence) + 1 <= extended_size or temp_size == 0:
                        if temp_size > 0:
                            temp_chunk += " "
                            temp_size += 1
                        temp_chunk += sentence
                        temp_size += len(sentence)
                    else:
                        chunks.append(temp_chunk)
                        temp_chunk = sentence
                        temp_size = len(sentence)
                
                if temp_chunk:
                    # If current_chunk is not empty, try to append temp_chunk to it
                    if current_chunk and current_size + temp_size + 2 <= extended_size:
                        current_chunk += "\n\n" + temp_chunk
                        current_size += temp_size + 2
                    else:
                        # Start a new chunk with temp_chunk
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = temp_chunk
                        current_size = temp_size
            else:
                # Section is too big for current chunk but not needing further splitting
                chunks.append(current_chunk)
                current_chunk = section
                current_size = section_size
    
    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def get_embeddings(text_chunks):
    """Get embeddings for text chunks using OpenAI's embedding model"""
    embeddings = []
    for chunk in text_chunks:
        response = openai_client.embeddings.create(
            input=chunk,
            model="text-embedding-ada-002"
        )
        embeddings.append(response.data[0].embedding)
    return embeddings

def process_and_update_pinecone(processed_content, namespace):
    """
    Process content into semantic chunks and update Pinecone with embeddings.
    This ensures content is chunked based on meaning rather than arbitrary character limits.
    
    Args:
        processed_content (str): The processed content to chunk and vectorize
        namespace (str): The Pinecone namespace to store vectors in
        
    Returns:
        bool: Success status of the operation
    """
    try:
        # Use semantic chunking to preserve content structure and relationships
        text_chunks = semantic_chunk_text(processed_content)
        
        # Log chunk stats for monitoring
        print(f"Created {len(text_chunks)} semantic chunks from content")
        print(f"Average chunk size: {sum(len(chunk) for chunk in text_chunks) / len(text_chunks)}")
        
        # Create embeddings for the chunks
        embeddings = get_embeddings(text_chunks)
        print(f"Generated {len(embeddings)} embeddings")
        
        # Add to the in-memory cache for immediate use
        vector_cache.add_to_cache(namespace, embeddings, text_chunks, expiry_seconds=60)
        print(f"Added vectors to in-memory cache for namespace '{namespace}'")
        
        # Update Pinecone index with the new vectors
        index = pinecone_client.Index(PINECONE_INDEX)
        
        # Check if namespace exists before trying to delete
        existing_stats = index.describe_index_stats()
        if namespace in existing_stats.namespaces:
            # Delete all vectors in the current namespace if it exists
            index.delete(delete_all=True, namespace=namespace)
            print(f"Cleared existing vectors for namespace '{namespace}'")
        
        # Upload vectors to the namespace
        vectors = [(f"{namespace}-{i}", embedding, {"text": chunk}) 
                  for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings))]
        
        index.upsert(vectors=vectors, namespace=namespace)
        print(f"Successfully uploaded {len(vectors)} vectors to Pinecone namespace '{namespace}'")
        
        return True
    except Exception as e:
        print(f"Error in process_and_update_pinecone: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def update_pinecone_index(namespace, text_chunks, embeddings, old_namespace=None):
    """Update Pinecone index with new vectors"""
    try:
        index = pinecone_client.Index(PINECONE_INDEX)
        
        # Check if namespace exists before trying to delete from it
        existing_stats = index.describe_index_stats()
        if namespace in existing_stats.namespaces:
            # Delete all vectors in the current namespace if it exists
            index.delete(delete_all=True, namespace=namespace)
        
        # Upload vectors to the namespace
        vectors = [(f"{namespace}-{i}", embedding, {"text": chunk}) 
                  for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings))]
        index.upsert(vectors=vectors, namespace=namespace)
        
        return True
    except Exception as e:
        print(f"Error in Pinecone update: {e}")
        return False

def check_pinecone_status(namespace, expected_count=None):
    """Check if Pinecone has processed vectors for a namespace"""
    try:
        index = pinecone_client.Index(PINECONE_INDEX)
        stats = index.describe_index_stats()
        
        # Simply check if namespace exists and has any vectors
        if namespace in stats.namespaces:
            # Different Pinecone versions might have different response structures
            # Try both possible structures to be safe
            try:
                # First try accessing as an object with vector_count property
                vector_exists = hasattr(stats.namespaces[namespace], 'vector_count') and stats.namespaces[namespace].vector_count > 0
            except:
                # If that fails, try treating it as a direct count
                vector_exists = stats.namespaces[namespace] > 0
                
            print(f"Namespace {namespace} found in Pinecone with vectors: {vector_exists}")
            return vector_exists
        else:
            print(f"Namespace {namespace} not found in Pinecone")
            return False
    except Exception as e:
        print(f"Error checking Pinecone status: {e}")
        return False

def generate_chatbot_id():
    return str(uuid.uuid4()).replace('-', '')[:20]

def check_namespace(url):
    """
    Find an appropriate namespace based on the main domain of the URL.
    Handles subdomains and common TLDs appropriately.
    """
    try:
        index = pinecone_client.Index(PINECONE_INDEX)
        stats = index.describe_index_stats()
        
        # Extract the domain from the URL
        domain = url.split('//')[-1].split('/')[0].lower()
        
        # Split the domain into parts
        parts = domain.split('.')
        
        # Common TLDs and second-level domains we want to exclude
        common_tlds = {'com', 'org', 'net', 'edu', 'gov', 'io', 'co', 'us', 'info', 'biz', 'app', 'dev'}
        second_level_domains = {'co.uk', 'com.au', 'co.nz', 'co.jp', 'or.jp', 'ne.jp', 'ac.uk', 'gov.uk', 'org.uk', 'co.za'}
        
        # Check if we have a second-level domain
        if len(parts) >= 3 and '.'.join(parts[-2:]) in second_level_domains:
            # For domains like example.co.uk, use 'example'
            main_domain = parts[-3]
        elif len(parts) >= 2:
            # For typical domains like example.com or subdomain.example.com
            # Check if it's a subdomain structure
            if len(parts) > 2 and parts[0] == 'www':
                # Handle www.example.com -> use 'example'
                main_domain = parts[-2]
            elif parts[-1] in common_tlds:
                # Handle example.com -> use 'example'
                main_domain = parts[-2]
            else:
                # Fallback to second part for unknown patterns
                main_domain = parts[1] if len(parts) > 1 else parts[0]
        else:
            # Fallback for unusual domains
            main_domain = parts[0]
        
        # Clean the main domain to remove any invalid characters
        base = re.sub(r'[^a-zA-Z0-9-]', '', main_domain)
        
        # Find existing namespaces with this base
        pattern = f"^{base}-\\d+$"
        existing = [ns for ns in stats.namespaces.keys() if re.match(pattern, ns)]
        
        if not existing:
            return f"{base}-01", None
            
        # Return the existing namespace instead of creating a new one
        current = max(existing, key=lambda x: int(x.split('-')[-1]))
        return current, None
    except Exception as e:
        print(f"Error checking namespace: {e}")
        # Fallback in case of error
        base = re.sub(r'[^a-zA-Z0-9-]', '', domain.replace('.', '-'))
        return f"{base}-01", None

def insert_company_data(data):
    """Insert new company data into database"""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            # PostgreSQL uses %s placeholders
            cursor.execute('''
                INSERT INTO companies 
                (chatbot_id, company_url, pinecone_host_url, pinecone_index, pinecone_namespace, 
                created_at, updated_at, scraped_text, processed_content, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', data + (None,))  # Add None for user_id
        else:
            # SQLite uses ? placeholders
            cursor.execute('''
                INSERT INTO companies 
                (chatbot_id, company_url, pinecone_host_url, pinecone_index, pinecone_namespace, 
                created_at, updated_at, scraped_text, processed_content, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data + (None,))  # Add None for user_id

def get_existing_record(url):
    """Check if URL already exists in database and return its data.
    Uses normalized domain to find matches regardless of protocol, subdomains, or case."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        # Normalize URL for comparison
        normalized_domain = normalize_domain_for_comparison(url)
        print(f"[get_existing_record] Original URL: {url}, Normalized domain: {normalized_domain}")
        
        # Extract main parts for partial matching
        domain_parts = normalized_domain.split('.')
        if len(domain_parts) >= 2:
            main_domain = domain_parts[-2]  # e.g., 'example' from 'example.com'
        else:
            main_domain = domain_parts[0]
            
        # Get all potential matching records first
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            # PostgreSQL - use ILIKE for case-insensitive matching
            cursor.execute('''
                SELECT chatbot_id, pinecone_namespace, company_url
                FROM companies
                WHERE company_url ILIKE %s
            ''', (f'%{main_domain}%',))
        else:
            # SQLite - it doesn't have ILIKE, but LIKE is case-insensitive by default
            cursor.execute('''
                SELECT chatbot_id, pinecone_namespace, company_url
                FROM companies
                WHERE company_url LIKE ?
            ''', (f'%{main_domain}%',))
            
        # Then filter the smaller set of results for exact normalized matches
        candidates = cursor.fetchall()
        for row in candidates:
            company_url = row[2]
            company_normalized = normalize_domain_for_comparison(company_url)
            print(f"[get_existing_record] Comparing: '{normalized_domain}' with '{company_normalized}'")
            
            # Case-insensitive comparison using lower() on both sides
            if company_normalized.lower() == normalized_domain.lower():
                print(f"[get_existing_record] Match found: {row[0]}")
                return (row[0], row[1])  # Return chatbot_id and namespace
        
        # If we get here, no match was found
        print(f"[get_existing_record] No match found for {normalized_domain}")
        return None

def normalize_domain_for_comparison(url):
    """Extract and normalize the core domain from a URL for comparison purposes.
    Removes protocols, www prefixes, and handles subdomains."""
    try:
        # Add protocol if missing for proper parsing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        # Extract the domain from the URL
        domain = url.split('//')[-1].split('/')[0].lower()
        
        # Split the domain into parts
        parts = domain.split('.')
        
        # Common TLDs and second-level domains we want to exclude
        common_tlds = {'com', 'org', 'net', 'edu', 'gov', 'io', 'co', 'us', 'info', 'biz', 'app', 'dev'}
        second_level_domains = {'co.uk', 'com.au', 'co.nz', 'co.jp', 'or.jp', 'ne.jp', 'ac.uk', 'gov.uk', 'org.uk', 'co.za'}
        
        # Check if we have a second-level domain
        if len(parts) >= 3 and '.'.join(parts[-2:]) in second_level_domains:
            # For domains like example.co.uk, use 'example'
            main_domain = parts[-3]
        elif len(parts) >= 2:
            # For typical domains like example.com or subdomain.example.com
            if parts[-1] in common_tlds:
                # Handle example.com -> use 'example'
                main_domain = parts[-2]
            else:
                # Fallback to second part for unknown patterns
                main_domain = parts[1] if len(parts) > 1 else parts[0]
        else:
            # Fallback for unusual domains
            main_domain = parts[0]
        
        # For consistency in matching, we'll include the TLD in the normalized form
        if len(parts) >= 2:
            tld = parts[-1]
            normalized = f"{main_domain}.{tld}"
        else:
            normalized = main_domain
            
        return normalized.lower()
    except Exception as e:
        print(f"Error normalizing domain: {e}")
        # In case of any error, return the lowercased input as fallback
        return url.lower()

def update_company_data(data, chatbot_id):
    """Update existing company record"""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                UPDATE companies 
                SET company_url=%s, pinecone_host_url=%s, pinecone_index=%s, 
                    pinecone_namespace=%s, updated_at=%s, scraped_text=%s, 
                    processed_content=%s
                WHERE chatbot_id=%s
            ''', (data[1], data[2], data[3], data[4], data[6], 
                data[7], data[8], chatbot_id))
        else:
            cursor.execute('''
                UPDATE companies 
                SET company_url=?, pinecone_host_url=?, pinecone_index=?, 
                    pinecone_namespace=?, updated_at=?, scraped_text=?, 
                    processed_content=?
                WHERE chatbot_id=?
            ''', (data[1], data[2], data[3], data[4], data[6], 
                data[7], data[8], chatbot_id))

def extract_all_text(html_content):
    """Extract all visible text from HTML while maintaining minimal structure"""
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements that contain no visible text
    for element in soup(['script', 'style', 'noscript']):
        element.decompose()
    
    # Get text from all remaining elements
    text = soup.get_text(separator=' ', strip=True)
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text

def extract_meta_tags(html_content):
    """Extract relevant meta tags from HTML"""
    meta_info = {
        "title": "",
        "description": ""
    }
    
    if not html_content:
        return meta_info
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract page title
    title_tag = soup.find('title')
    if title_tag:
        meta_info["title"] = title_tag.text.strip()
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={"name": "description"})
    if meta_desc:
        meta_info["description"] = meta_desc.get('content', '')
    
    return meta_info

def simple_scrape_page(url):
    """Simplified scraper that extracts all visible text from a page"""
    try:
        # Use requests to get the full HTML with enhanced headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
            "Cache-Control": "no-cache"
        }
        response = requests.get(url, timeout=10, headers=headers)
        html_content = response.text
        
        # Extract all visible text
        all_text = extract_all_text(html_content)
        
        # Extract basic meta information
        meta_info = extract_meta_tags(html_content)
        
        return {
            "all_text": all_text,
            "meta_info": meta_info
        }
    except Exception as e:
        print(f"Error in simple scraping: {e}")
        return {"all_text": "", "meta_info": {"title": "", "description": ""}}

def scrape_page(url):
    """Original scrape_page function maintained for compatibility"""
    try:
        # Use the simplified scraper but return just the main content for backward compatibility
        result = simple_scrape_page(url)
        return result["all_text"]
    except Exception as e:
        print(f"Error scraping page: {e}")
        return None

def find_about_page(base_url):
    """Find the About page URL"""
    try:
        response = requests.get(base_url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Common about page indicators
        about_keywords = ['about', 'about us', 'about-us', 'aboutus', 'our story', 'our-story', 'ourstory', 'who we are', 'company']
        
        # Check all links
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            text = link.get_text(strip=True).lower()
            if any(keyword in href for keyword in about_keywords) or any(keyword in text for keyword in about_keywords):
                return urljoin(base_url.rstrip('/'), link['href'])
                
        # If still not found, try common about page patterns
        common_about_paths = ['/about', '/about-us', '/aboutus', '/about_us', '/our-story', '/company']
        for path in common_about_paths:
            about_url = urljoin(base_url.rstrip('/'), path)
            try:
                about_response = requests.head(about_url, timeout=5)
                if about_response.status_code == 200:
                    return about_url
            except:
                continue
                
        return None
    except Exception as e:
        print(f"Error finding About page: {e}")
        return None

def process_simple_content(home_data, about_data):
    """Process the scraped content with OpenAI and return both prompt and response"""
    try:
        # Create a comprehensive prompt with all the text data
        prompt = f"""
        Create a comprehensive knowledge base document from this website content. Include clear section headings for all relevant business information such as Company Overview:, Primary Products/Services:, Secondary Products/Services:, Pricing:, Contact Details:, Calls to Action:,  etc:

        HOME PAGE TITLE:
        {home_data['meta_info']['title']}

        HOME PAGE DESCRIPTION:
        {home_data['meta_info']['description']}

        HOME PAGE CONTENT:
        {home_data['all_text']}

        """
        
        # Add about page content if available
        if about_data and about_data.get('all_text'):
            prompt += f"""
            ABOUT PAGE TITLE:
            {about_data['meta_info']['title']}

            ABOUT PAGE DESCRIPTION:
            {about_data['meta_info']['description']}

            ABOUT PAGE CONTENT:
            {about_data['all_text']}
            """
        else:
            prompt += "\nABOUT PAGE: Not found or no content available."
            
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Return both the response and the prompt
        return response.choices[0].message.content, prompt
    except Exception as e:
        print(f"Error processing with OpenAI: {e}")
        # In case of error, return None
        return None

def verify_recaptcha(token, remote_ip):
    """Verify reCAPTCHA token with Google with enhanced debugging"""
    print(f"[reCAPTCHA] Starting verification for IP: {remote_ip}")
    print(f"[reCAPTCHA] Token present: {bool(token)}")
    print(f"[reCAPTCHA] Token length: {len(token) if token else 0}")
    
    if not token:
        print("[reCAPTCHA] No token provided, verification failed")
        return False
    
    # During development/debugging, you can bypass verification
    # Uncomment the next line to bypass reCAPTCHA during testing
    # return True
    
    try:
        print(f"[reCAPTCHA] Using site key: {app.config.get('CAPTCHA_SITE_KEY', 'Not set')}")
        print(f"[reCAPTCHA] Using secret key (length): {len(app.config.get('CAPTCHA_SECRET_KEY', '')) if app.config.get('CAPTCHA_SECRET_KEY') else 0}")
        
        data = {
            'secret': app.config.get("CAPTCHA_SECRET_KEY", ""),
            'response': token,
            'remoteip': remote_ip
        }
        
        print("[reCAPTCHA] Sending verification request to Google")
        response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data, timeout=5)
        print(f"[reCAPTCHA] Response status code: {response.status_code}")
        print(f"[reCAPTCHA] Response content: {response.text[:200]}...")  # Log first 200 chars
        
        result = response.json()
        
        print(f"[reCAPTCHA] Verification response: {result}")
        success = result.get('success', False)
        score = result.get('score', 0)
        error_codes = result.get('error-codes', [])
        
        print(f"[reCAPTCHA] Verification result - Success: {success}, Score: {score}")
        if error_codes:
            print(f"[reCAPTCHA] Error codes: {error_codes}")
        
        return success
    except requests.exceptions.Timeout:
        print(f"[reCAPTCHA] Verification timeout after 5 seconds")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[reCAPTCHA] Request error: {str(e)}")
        return False
    except ValueError as e:
        print(f"[reCAPTCHA] JSON parsing error: {str(e)}")
        print(f"[reCAPTCHA] Raw response: {response.text}")
        return False
    except Exception as e:
        print(f"[reCAPTCHA] Verification error: {str(e)}")
        import traceback
        print(f"[reCAPTCHA] Error trace: {traceback.format_exc()}")
        return False

def validate_website_url(url, recaptcha_token, remote_ip, honeypot_value=None):
    """
    Comprehensive validation of website URL before processing.
    Returns dictionary with validation results.
    """
    print(f"[validate_website_url] Starting validation for URL: {url}")
    
    # Results dictionary to track validation results
    result = {
        "is_valid": False,
        "message": "",
        "status_code": 400,
        "existing_record": None,
        "chatbot_id": None,
        "namespace": None,
        "validated_url": url  # Initialize with original URL
    }
    
    # Check 4: Honeypot check (bot detection)
    if honeypot_value:
        print(f"[validate_website_url] Honeypot field filled, likely bot activity")
        # Silently succeed but mark as invalid for processing
        result["is_valid"] = False
        result["status_code"] = 200  # Appear successful to bots
        result["message"] = "Validation successful"  # Misleading message for bots
        fake_chatbot_id = str(uuid.uuid4()).replace('-', '')[:20]
        result["chatbot_id"] = fake_chatbot_id
        return result
    
    # Auto-correct URLs without protocol (needed for validation and processing)
    if url and not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        result["validated_url"] = url
        print(f"[validate_website_url] Auto-corrected URL to: {url}")
    
    # Check 5: reCAPTCHA verification
    print(f"[validate_website_url] Verifying reCAPTCHA token")
    if not verify_recaptcha(recaptcha_token, remote_ip):
        print(f"[validate_website_url] reCAPTCHA verification failed")
        result["message"] = "reCAPTCHA verification failed. Please try again."
        return result
    
    # Check 6: URL validity check
    print(f"[validate_website_url] Checking URL validity")
    if not validators.url(url):
        print(f"[validate_website_url] Invalid URL format: {url}")
        result["message"] = "Please enter a valid URL that includes a domain name."
        return result
    
    # Check 7: Blocked domain check
    print(f"[validate_website_url] Checking for blocked domain")
    from blocked_domains import is_domain_blocked
    if is_domain_blocked(url):
        print(f"[validate_website_url] Blocked domain detected: {url}")
        result["message"] = "Sorry, we can't process this website. Please try a different domain."
        result["status_code"] = 403
        return result
    
    # Check 8: Domain accessibility check
    print(f"[validate_website_url] Checking domain accessibility")
    try:
        response = requests.head(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        })
        if response.status_code >= 400:
            print(f"[validate_website_url] Domain not accessible: HTTP {response.status_code}")
            result["message"] = f"We couldn't access this website (HTTP {response.status_code}). Please check the URL and try again."
            return result
    except requests.exceptions.RequestException as e:
        print(f"[validate_website_url] Error accessing domain: {e}")
        result["message"] = "We couldn't connect to this website. Please check the URL and try again."
        return result
    
    # Check 10: Existing record check
    print(f"[validate_website_url] Checking for existing record")
    existing_record = get_existing_record(url)
    if existing_record:
        print(f"[validate_website_url] Found existing record: {existing_record}")
        result["existing_record"] = existing_record
        result["chatbot_id"] = existing_record[0]
        result["namespace"] = existing_record[1]
    else:
        # Generate new IDs for new records
        print(f"[validate_website_url] No existing record, generating new IDs")
        result["chatbot_id"] = generate_chatbot_id()
        result["namespace"], _ = check_namespace(url)
        print(f"[validate_website_url] New chatbot_id: {result['chatbot_id']}, namespace: {result['namespace']}")
    
    # All checks passed
    print(f"[validate_website_url] All validation checks passed")
    result["is_valid"] = True
    result["message"] = "Validation successful"
    result["status_code"] = 200
    
    return result

@app.errorhandler(429)
def ratelimit_handler(e):
    """Custom handler for rate limit exceeded errors"""
    # Log the rate limit exceeded event
    print(f"[RATE LIMIT] Rate limit exceeded for IP: {request.remote_addr}")
    
    # Extract chatbot_id from the request if available
    chatbot_id = None
    try:
        # Check if this was from embed-chat endpoint
        if request.path == '/embed-chat' and request.is_json:
            data = request.get_json(silent=True)
            if data and isinstance(data, dict):
                chatbot_id = data.get('chatbot_id')
                
                if chatbot_id:
                    # Log the incident and update active_status
                    log_chatbot_incident(
                        chatbot_id=chatbot_id,
                        incident_type='rate_limit_exceeded',
                        incident_details=f"Rate limit exceeded for endpoint: {request.path}",
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string if request.user_agent else None
                    )
                    
                    # Update active_status to 'paused'
                    with connect_to_db() as conn:
                        cursor = conn.cursor()
                        
                        # Different placeholder based on database type
                        placeholder = '%s' if os.getenv('DB_TYPE', '').lower() == 'postgresql' else '?'
                        table_name = 'companies' if os.getenv('DB_TYPE', '').lower() != 'postgresql' else f"{DB_SCHEMA}.companies"
                        
                        query = f"""
                            UPDATE {table_name}
                            SET active_status = 'paused'
                            WHERE chatbot_id = {placeholder}
                        """
                        
                        cursor.execute(query, (chatbot_id,))
                        conn.commit()
                        
                        print(f"[RATE LIMIT] Chatbot {chatbot_id} paused due to rate limit violation")
    except Exception as incident_error:
        print(f"[RATE LIMIT] Error handling rate limit incident: {str(incident_error)}")
    
    # Check if it's an AJAX/JSON request
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # For AJAX requests, return a JSON response
        return jsonify({
            "error": "Too many requests. This chatbot has been paused due to excessive usage.",
            "rate_limit_exceeded": True,
            "chatbot_paused": chatbot_id is not None
        }), 429
    else:
        # For regular form submissions, flash a message and redirect
        flash("Too many requests. Please try again later.")
        return redirect(url_for('home'))

def log_chatbot_incident(chatbot_id, incident_type, incident_details=None, ip_address=None, user_agent=None):
    """
    Log an incident for a chatbot in the chatbot_incidents table
    
    Args:
        chatbot_id (str): The ID of the affected chatbot
        incident_type (str): Type of incident (e.g., 'rate_limit_exceeded')
        incident_details (str, optional): Additional details about the incident
        ip_address (str, optional): IP address associated with the incident
        user_agent (str, optional): User agent string associated with the incident
    
    Returns:
        bool: True if logging was successful, False otherwise
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different syntax based on database type
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute("""
                    INSERT INTO chatbot_incidents 
                    (chatbot_id, incident_type, incident_details, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s)
                """, (chatbot_id, incident_type, incident_details, ip_address, user_agent))
            else:
                cursor.execute("""
                    INSERT INTO chatbot_incidents 
                    (chatbot_id, incident_type, incident_details, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?)
                """, (chatbot_id, incident_type, incident_details, ip_address, user_agent))
            
            print(f"[INCIDENT] Logged {incident_type} incident for chatbot {chatbot_id}")
            return True
    except Exception as e:
        print(f"[INCIDENT] Error logging incident: {str(e)}")
        return False

# Flask routes
@app.route('/chat-test')
def chat_test():
    return render_template('chat_test.html')

@app.route('/')
def home():
    return render_template('landing.html')

@app.route('/validate-url', methods=['POST'])
@limiter.limit("5 per minute")
def validate_url():
    """Validate URL without starting processing"""
    print(f"[validate_url] Starting validation at {datetime.now().isoformat()}")
    print(f"[validate_url] Form data: {request.form}")
    website_url = request.form.get('url')
    print(f"[validate_url] Original URL: {website_url}")
    
    # Get reCAPTCHA token and honeypot value
    recaptcha_token = request.form.get('g-recaptcha-response')
    honeypot_value = request.form.get('contact_email')
    
    # Use the validation function to comprehensively validate the URL
    validation_result = validate_website_url(website_url, recaptcha_token, request.remote_addr, honeypot_value)
    
    # If validation failed, return appropriate error response
    if not validation_result["is_valid"]:
        print(f"[validate_url] Validation failed: {validation_result['message']}")
        return jsonify({"error": validation_result["message"]}), validation_result["status_code"]
    
    # If validation succeeded, return success with chatbot ID and other info
    print(f"[validate_url] Validation successful for {website_url}")
    return jsonify({
        "status": "success",
        "message": "URL validation successful",
        "chatbot_id": validation_result["chatbot_id"],
        "namespace": validation_result["namespace"],
        "validated_url": validation_result.get("validated_url", website_url)
    })

@app.route('/process-url-async', methods=['POST'])
@limiter.limit("2 per minute; 4 per hour")
def process_url_async():
    print(f"[process_url_async] Starting at {datetime.now().isoformat()}")
    print(f"[process_url_async] Form data: {request.form}")
    website_url = request.form.get('url')
    print(f"[process_url_async] Original URL: {website_url}")
    
    # Get reCAPTCHA token, honeypot value, and pre-validated flag
    recaptcha_token = request.form.get('g-recaptcha-response')
    honeypot_value = request.form.get('contact_email')
    pre_validated = request.form.get('pre_validated') == 'true'
    
    # Skip validation if pre-validated flag is true
    if pre_validated:
        print(f"[process_url_async] URL is pre-validated, skipping validation checks")
        # We still need chatbot_id and namespace
        chatbot_id = request.form.get('chatbot_id')
        namespace = request.form.get('namespace')
        
        if not chatbot_id or not namespace:
            print(f"[process_url_async] Missing required fields for pre-validated request")
            return jsonify({"error": "Missing chatbot_id or namespace for pre-validated request"}), 400
            
        print(f"[process_url_async] Using pre-validated data: chatbot_id={chatbot_id}, namespace={namespace}")
    else:
        # Use the validation function to comprehensively validate the URL
        validation_result = validate_website_url(website_url, recaptcha_token, request.remote_addr, honeypot_value)
        
        # If validation failed, return appropriate error response
        if not validation_result["is_valid"]:
            print(f"[process_url_async] Validation failed: {validation_result['message']}")
            return jsonify({"error": validation_result["message"]}), validation_result["status_code"]
        
        # Get validated data from validation result
        chatbot_id = validation_result["chatbot_id"]
        namespace = validation_result["namespace"]
        website_url = validation_result.get("validated_url", website_url)  # Use validated URL if available
        
        print(f"[process_url_async] Validation successful. Using chatbot_id: {chatbot_id}, namespace: {namespace}")
    
    # Generate APIFlash screenshot URL immediately
    screenshot_url = ""
    try:
        base_url = "https://api.apiflash.com/v1/urltoimage"
        screenshot_url = f"{base_url}?access_key={APIFLASH_KEY}&url={website_url}&format=jpeg&width=1600&height=1066"
        print(f"[process_url_async] Screenshot URL generated: {screenshot_url}")
        
        # Make an HTTP request to trigger APIFlash to generate and cache the screenshot
        try:
            print("[process_url_async] Triggering APIFlash screenshot generation")
            response = requests.get(screenshot_url, timeout=2, stream=True)
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    break
            response.close()
            print("[process_url_async] APIFlash screenshot generation triggered successfully")
        except requests.exceptions.Timeout:
            print("[process_url_async] APIFlash request timed out, but screenshot generation was triggered")
        except Exception as api_e:
            print(f"[process_url_async] Error making APIFlash request: {api_e}, but continuing")
            
    except Exception as e:
        print(f"[process_url_async] Error generating screenshot URL: {e}, but continuing")
    
    # Initialize processing status
    processing_status[chatbot_id] = {
        "namespace": namespace,
        "completed": False,
        "start_time": time.time(),
        "website_url": website_url,
        "screenshot_url": screenshot_url
    }
    
    print(f"[process_url_async] Processing status initialized for {chatbot_id}")
    print(f"[process_url_async] Current processing_status keys: {list(processing_status.keys())}")
    
    # Start the processing in the background
    try:
        print(f"[process_url_async] Starting processing execution for {chatbot_id}")
        
        # Simplified scraping of the website and its About page
        home_data = simple_scrape_page(website_url)
        about_url = find_about_page(website_url)
        about_data = simple_scrape_page(about_url) if about_url else None
        
        if not home_data.get("all_text"):
            processing_status[chatbot_id]["error"] = "Failed to scrape website content"
            return jsonify({"error": "Failed to scrape website content"}), 400

        # Process the content with OpenAI - returns both content and prompt
        result = process_simple_content(home_data, about_data)
        if not result:
            processing_status[chatbot_id]["error"] = "Failed to process content"
            return jsonify({"error": "Failed to process content"}), 400
            
        # Unpack the result
        processed_content, full_prompt = result
        
        # Store the about page text (if it was found)
        about_text = about_data.get("all_text", "About page not found") if about_data else "About page not found"
        
        # Combine into a single scraped_text field with clear sections
        scraped_text = f"""OpenAI Prompt
{full_prompt}

About Scrape
{about_text}"""
        
        # OLD CHUNKING METHOD (COMMENTED OUT)
        # chunks = chunk_text(processed_content)
        # embeddings = get_embeddings(chunks)
        # update_pinecone_index(namespace, chunks, embeddings)
        
        # NEW SEMANTIC CHUNKING METHOD
        success = process_and_update_pinecone(processed_content, namespace)
        if not success:
            processing_status[chatbot_id]["error"] = "Failed to process and update Pinecone"
            return jsonify({"error": "Failed to process and update Pinecone"}), 400
        
        now = datetime.now(UTC)
        data = (
            chatbot_id, website_url, PINECONE_HOST, PINECONE_INDEX,
            namespace, now, now, scraped_text, processed_content
        )

        try:
            # If this is a pre-validated request, we need to check explicitly
            if pre_validated:
                existing_record = get_existing_record(website_url)
                if existing_record and existing_record[0] == chatbot_id:
                    update_company_data(data, chatbot_id)
                else:
                    insert_company_data(data)
            else:
                # Use validation result to determine if record exists
                if validation_result["existing_record"]:
                    update_company_data(data, chatbot_id)
                else:
                    insert_company_data(data)
        except Exception as e:
            processing_status[chatbot_id]["error"] = f"Failed to save company data: {str(e)}"
            return jsonify({"error": "Failed to save company data"}), 400

        # Processing is complete - update status to ready
        processing_status[chatbot_id]["completed"] = True
        processing_time = time.time() - processing_status[chatbot_id]["start_time"]
        print(f"[process_url_async] Processing completed for {chatbot_id} in {processing_time:.2f} seconds")
    
    except Exception as e:
        print(f"[process_url_async] Error during processing: {e}")
        import traceback
        print(f"[process_url_async] Error traceback: {traceback.format_exc()}")
        processing_status[chatbot_id]["error"] = f"Processing error: {str(e)}"
    
    # Return chatbot_id immediately so frontend can start polling
    print(f"[process_url_async] Returning to client - chatbot_id: {chatbot_id}")
    return jsonify({
        "status": "processing",
        "chatbot_id": chatbot_id
    })

@app.route('/process-url-execute/<chatbot_id>', methods=['GET'])
def process_url_execute(chatbot_id):
    """Execute URL processing in background while frontend polls for status"""
    print(f"[process_url_execute] Starting for chatbot_id: {chatbot_id}")
    
    if chatbot_id not in processing_status:
        print(f"[process_url_execute] Chatbot ID not found in processing_status")
        return jsonify({"error": "Invalid chatbot ID"}), 404
    
    status_info = processing_status[chatbot_id]
    website_url = status_info["website_url"]
    namespace = status_info["namespace"]
    
    print(f"[process_url_execute] Processing URL: {website_url}, namespace: {namespace}")
    
    # Simplified scraping of the website and its About page
    print(f"[process_url_execute] Starting website scraping")
    home_data = simple_scrape_page(website_url)
    print(f"[process_url_execute] Home page scraped, content length: {len(home_data.get('all_text', ''))}")
    
    about_url = find_about_page(website_url)
    print(f"[process_url_execute] About page URL: {about_url}")
    
    about_data = simple_scrape_page(about_url) if about_url else None
    print(f"[process_url_execute] About page scraped: {about_data is not None}")
    
    if not home_data.get("all_text"):
        processing_status[chatbot_id]["error"] = "Failed to scrape website content"
        print(f"[process_url_execute] Failed to scrape website content")
        return jsonify({"error": "Failed to scrape website content"}), 400

    # Process the content with OpenAI - returns both content and prompt
    print(f"[process_url_execute] Processing content with OpenAI")
    result = process_simple_content(home_data, about_data)
    if not result:
        processing_status[chatbot_id]["error"] = "Failed to process content"
        print(f"[process_url_execute] Failed to process content with OpenAI")
        return jsonify({"error": "Failed to process content"}), 400
        
    # Unpack the result - processed_content is the OpenAI response, full_prompt is what was sent to OpenAI
    processed_content, full_prompt = result
    print(f"[process_url_execute] OpenAI processing complete, content length: {len(processed_content)}")
    
    # Store the about page text (if it was found)
    about_text = about_data.get("all_text", "About page not found") if about_data else "About page not found"
    
    # Combine into a single scraped_text field with clear sections
    scraped_text = f"""OpenAI Prompt
{full_prompt}

About Scrape
{about_text}"""
    
    # OLD CHUNKING METHOD (COMMENTED OUT)
    # print(f"[process_url_execute] Chunking content and creating embeddings")
    # chunks = chunk_text(processed_content)
    # print(f"[process_url_execute] Created {len(chunks)} chunks")
    
    # embeddings = get_embeddings(chunks)
    # print(f"[process_url_execute] Created {len(embeddings)} embeddings")
    
    # Add to the in-memory cache first (60 seconds expiration by default)
    # vector_cache.add_to_cache(namespace, embeddings, chunks, expiry_seconds=60)
    # print(f"[process_url_execute] Added vectors to in-memory cache for namespace '{namespace}'")
    
    # Update Pinecone in background (will continue while user is redirected to demo)
    # update_pinecone_task = update_pinecone_index(namespace, chunks, embeddings)
    # print(f"[process_url_execute] Pinecone update started: {update_pinecone_task}")
    
    # NEW SEMANTIC CHUNKING METHOD
    success = process_and_update_pinecone(processed_content, namespace)
    if not success:
        processing_status[chatbot_id]["error"] = "Failed to process and update Pinecone"
        print(f"[process_url_execute] Failed to process and update Pinecone")
        return jsonify({"error": "Failed to process and update Pinecone"}), 400
    
    now = datetime.now(UTC)
    data = (
        chatbot_id, website_url, PINECONE_HOST, PINECONE_INDEX,
        namespace, now, now, scraped_text, processed_content
    )

    try:
        print(f"[process_url_execute] Updating database for chatbot_id: {chatbot_id}")
        if existing_record := get_existing_record(website_url):
            print(f"[process_url_execute] Updating existing record")
            update_company_data(data, chatbot_id)
        else:
            print(f"[process_url_execute] Inserting new record")
            insert_company_data(data)
    except Exception as e:
        print(f"[process_url_execute] Database error: {e}")
        processing_status[chatbot_id]["error"] = f"Failed to save company data: {str(e)}"
        return jsonify({"error": "Failed to save company data"}), 400

    # Processing is complete - update status to ready
    # No need to wait for Pinecone since we're using the cache
    processing_status[chatbot_id]["completed"] = True
    processing_time = time.time() - status_info["start_time"]
    print(f"[process_url_execute] Processing completed for {chatbot_id} in {processing_time:.2f} seconds")
    
    return jsonify({
        "status": "success", 
        "chatbot_id": chatbot_id,
        "cache_status": vector_cache.get_cache_status(namespace)
    })

@app.route('/check-processing/<chatbot_id>', methods=['GET'])
def check_processing(chatbot_id):
    """Check if processing is complete for a chatbot"""
    print(f"[check_processing] Checking status for chatbot_id: {chatbot_id}")
    print(f"[check_processing] Available processing_status keys: {list(processing_status.keys())}")
    
    if chatbot_id not in processing_status:
        print(f"[check_processing] Chatbot ID not found in processing_status")
        return jsonify({"status": "error", "message": "Chatbot ID not found"}), 404
    
    status_info = processing_status[chatbot_id]
    print(f"[check_processing] Status info: {status_info}")
    
    # If already marked as completed, return success
    if status_info.get("completed", False):
        print(f"[check_processing] Processing complete for {chatbot_id}")
        return jsonify({
            "status": "complete",
            "chatbot_id": chatbot_id,
            "website_url": status_info.get("website_url", ""),
            "screenshot_url": status_info.get("screenshot_url", "")  # Include screenshot URL
        })
    
    # If there was an error during processing
    if "error" in status_info:
        print(f"[check_processing] Error for {chatbot_id}: {status_info['error']}")
        return jsonify({
            "status": "error",
            "message": status_info["error"]
        }), 400
    
    # If we're still in the initial processing phase
    elapsed_time = time.time() - status_info["start_time"]
    print(f"[check_processing] Still processing {chatbot_id}, elapsed: {int(elapsed_time)}s")
    return jsonify({
        "status": "processing",
        "phase": "content",
        "elapsed_seconds": int(elapsed_time)
    })

@app.route('/', methods=['POST'])
@limiter.limit("2 per minute; 4 per hour")
def process_url():
    """Simplified catch-all route for direct form submissions when JavaScript is disabled"""
    print(f"[process_url] Received direct form submission - JavaScript might be disabled")
    
    # Flash a friendly message explaining JavaScript is required
    flash("JavaScript is required to create a chatbot. Please enable JavaScript in your browser settings and try again.", "error")
    
    # Redirect back to the home page (landing.html)
    return redirect(url_for('home'))

@app.route('/demo/<session_id>')
def demo(session_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Get company info
        if DB_TYPE.lower() == 'postgresql':
            cursor.execute(f"SELECT * FROM {DB_SCHEMA}.companies WHERE chatbot_id = %s", (session_id,))
        else:
            cursor.execute("SELECT * FROM companies WHERE chatbot_id = ?", (session_id,))
            
        result = cursor.fetchone()
        
        if not result:
            flash('Chatbot not found', 'error')
            return redirect(url_for('home'))
        
        # Convert to dictionary for easier access
        columns = [desc[0] for desc in cursor.description]
        chatbot_dict = dict(zip(columns, result))
        
        # Check if the chatbot is claimed and by who
        is_claimed = chatbot_dict.get('user_id') is not None
        owner_id = chatbot_dict.get('user_id')
        
        # Get the website URL
        website_url = chatbot_dict.get('company_url')
        
        # Check if we have a cached screenshot URL in the processing status
        screenshot_url = ""
        if session_id in processing_status and "screenshot_url" in processing_status[session_id]:
            screenshot_url = processing_status[session_id]["screenshot_url"]
        else:
            # Generate APIFlash screenshot URL if we don't have one cached
            try:
                base_url = "https://api.apiflash.com/v1/urltoimage"
                screenshot_url = f"{base_url}?access_key={APIFLASH_KEY}&url={website_url}&format=jpeg&width=1600&height=1066"
            except Exception as e:
                print(f"Error generating screenshot URL: {e}")
                screenshot_url = ""
        
        return render_template('demo.html', 
                               chatbot_id=session_id, 
                               website_url=website_url, 
                               screenshot_url=screenshot_url,
                               is_claimed=is_claimed,
                               owner_id=owner_id)
    except Exception as e:
        app.logger.error(f"Error in demo route: {e}")
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('home'))
    finally:
        conn.close()

# Modify the /embed-chat route to save message data
@app.route('/embed-chat', methods=['POST'])
@limiter.limit("10 per minute")
def embed_chat():
    try:
        data = request.json
        print("Received chat request:", data)  # Keep existing debug log
        chatbot_id = data.get("chatbot_id")
        user_message = data.get("message")
        thread_id = data.get("thread_id")  # Get the thread_id from the request
        model_settings = data.get("model_settings", {})  # Get custom model settings if provided

        # Get IP address and user agent for metrics - Updated approach
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')  # Direct access from headers
        
        # Log the user agent for debugging
        print(f"Captured user agent: {user_agent}")

        if not chatbot_id or not user_message:
            print(f"Missing fields - chatbot_id: {chatbot_id}, message: {user_message}")
            return jsonify({"error": "Missing chatbot_id or message"}), 400

        # Get namespace BEFORE initializing chat handler
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT pinecone_namespace, c.chatbot_id
                    FROM companies c
                    WHERE c.chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT pinecone_namespace, c.chatbot_id
                    FROM companies c 
                    WHERE c.chatbot_id = ?
                ''', (chatbot_id,))
                
            row = cursor.fetchone()

        if not row:
            print(f"Chatbot ID {chatbot_id} not found in database")
            return jsonify({"error": "Chatbot ID not found"}), 404

        namespace = row[0]
        
        # Check if this is a support bot request (thread_id starting with "support_")
        is_support_bot = thread_id and thread_id.startswith("support_")
        if is_support_bot:
            print(f"Support bot request detected - using namespace: {namespace}")
        
        # Get system prompt from chatbot_config if it exists
        system_prompt = None
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT system_prompt, chat_model, temperature, max_tokens
                    FROM chatbot_config
                    WHERE chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT system_prompt, chat_model, temperature, max_tokens
                    FROM chatbot_config
                    WHERE chatbot_id = ?
                ''', (chatbot_id,))
                
            config_row = cursor.fetchone()
            
            if config_row:
                system_prompt = config_row[0]
                # Override model settings from frontend if not provided
                if not model_settings:
                    model_settings = {
                        "model": config_row[1] or "gpt-4o",
                        "temperature": float(config_row[2]) if config_row[2] is not None else 0.7,
                        "max_tokens": int(config_row[3]) if config_row[3] is not None else 500
                    }
        
        # Initialize chat handler with namespace if it doesn't exist
        if chatbot_id not in chat_handlers:
            chat_handlers[chatbot_id] = ChatPromptHandler(openai_client, pinecone_client)
            # Ensure first message includes system prompt by forcing conversation reset
            chat_handlers[chatbot_id].reset_conversation()
            
            # Always set the thread_id in the handler to the one provided by frontend
            if thread_id:
                # Ensure we're using the frontend-provided thread_id
                chat_handlers[chatbot_id].thread_id = thread_id
                print(f"Using frontend-provided thread_id: {thread_id}")
            else:
                # Log a warning if no thread_id was provided
                print(f"Warning: No thread_id provided in request, using generated: {chat_handlers[chatbot_id].thread_id}")

        handler = chat_handlers[chatbot_id]
        
        # If a custom system prompt is provided, override the default one
        if system_prompt:
            print(f"Using custom system prompt for chatbot {chatbot_id}")
            handler.SYSTEM_PROMPT = system_prompt
        
        # Ensure handler is using the frontend thread_id for every message in the conversation
        if thread_id and handler.thread_id != thread_id:
            print(f"Thread ID mismatch - Request: {thread_id}, Handler: {handler.thread_id}")
            # Always use the frontend-provided thread_id for consistency
            handler.thread_id = thread_id
            print(f"Updated handler thread_id to match request: {thread_id}")
        
        messages = handler.format_messages(user_message, namespace=namespace)
        
        # Extract model settings from the request or use defaults
        chat_model = model_settings.get("model", "gpt-4o")
        temperature = model_settings.get("temperature", 0.7)
        max_tokens = model_settings.get("max_tokens", 500)
        
        # Log the model settings being used
        print(f"Using model settings - model: {chat_model}, temperature: {temperature}, max_tokens: {max_tokens}")
        
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )

        assistant_response = response.choices[0].message.content
        handler.add_to_history("user", user_message)
        handler.add_to_history("assistant", assistant_response)

        # Get the current conversation state for the frontend
        conversation_state = handler.get_conversation_state()
        
        # Debugging information
        print(f"Conversation state: {conversation_state}")
        
        # Extract token usage from OpenAI response
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        
        # Check if usage information is available in the response
        if hasattr(response, 'usage') and response.usage:
            try:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens
                print(f"Token usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
            except Exception as token_error:
                print(f"Error extracting token usage: {str(token_error)}")
        
        # Save message to database - ALWAYS use the frontend-provided thread_id
        try:
            # Always use the thread_id from request if available
            current_thread_id = thread_id or handler.thread_id
            
            # Save the message exchange
            save_result = save_chat_message(
                chatbot_id=chatbot_id,
                thread_id=current_thread_id,  # Use consistent thread_id
                user_message=user_message,
                assistant_response=assistant_response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            if not save_result:
                print(f"Warning: Failed to save chat message to database")
        except Exception as save_error:
            print(f"Error saving chat message: {str(save_error)}")
            # Continue with response even if saving fails
        
        # Return the same thread_id that was provided in the request
        return jsonify({
            "response": assistant_response,
            "thread_id": thread_id or handler.thread_id,  # Return consistent thread_id
            "is_first_interaction": conversation_state["is_first_interaction"],
            "message_count": conversation_state["message_count"],
            "initial_question": conversation_state.get("initial_question")
        })

    except Exception as e:
        print(f"Detailed error in embed-chat: {str(e)}")  # Enhanced error logging
        return jsonify({"error": "Internal server error"}), 500
    

@app.route('/embed-reset-chat', methods=['POST'])
@limiter.limit("2 per minute")
def reset_chat():
    try:
        data = request.json
        chatbot_id = data.get('chatbot_id')
        
        if not chatbot_id:
            return jsonify({'error': 'Missing chatbot ID'}), 400
            
        if chatbot_id in chat_handlers:
            chat_handlers[chatbot_id].reset_conversation()
            
        return jsonify({'status': 'success', 'message': 'Chat history reset'})
    except Exception as e:
        print(f"Error resetting chat: {e}")
        return jsonify({"error": "Internal server error"}), 500

# DIGITAL OCEAN SPECIFIC - GIVES US ABILITY TO SEE WHAT'S INSIDE
@app.route('/db-check')
def db_check():
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('SELECT * FROM companies')
        else:
            cursor.execute('SELECT * FROM companies')
            
        rows = cursor.fetchall()
        
        return jsonify([{
            'chatbot_id': row[0],
            'company_url': row[1],
            'pinecone_host_url': row[2],
            'pinecone_index': row[3],
            'pinecone_namespace': row[4],
            'created_at': row[5],
            'updated_at': row[6]
            # Omitting text fields for brevity
        } for row in rows])

#@app.route('/standalone-test')
#def standalone_test():
#    return render_template('standalone_test.html')

@app.route('/standalone-test')
def standalone_test():
    # Default route without chatbot ID - use a default test ID
    default_chatbot_id = "4c0487935a8745bc86da"  # Keep the original default ID
    return render_template('standalone_test.html', chatbot_id=default_chatbot_id)

@app.route('/standalone-test/<session_id>')
def standalone_test_with_id(session_id):
    # Fetch the company URL for the given chatbot ID
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                SELECT company_url
                FROM companies
                WHERE chatbot_id = %s
            ''', (session_id,))
        else:
            cursor.execute('''
                SELECT company_url
                FROM companies
                WHERE chatbot_id = ?
            ''', (session_id,))
            
        row = cursor.fetchone()

    if not row:
        flash("Invalid session ID")
        return redirect(url_for('home'))

    website_url = row[0]
    
    # Pass the chatbot ID to the template
    return render_template('standalone_test.html', chatbot_id=session_id, website_url=website_url)

# user dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access your dashboard', 'error')
        return redirect(url_for('auth.signin'))
    
    try:
        print(f"Dashboard access - user_id: {session.get('user_id')}")
        
        # Get user's chatbots
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # First verify the user exists
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (session['user_id'],))
            else:
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (session['user_id'],))
                
            user = cursor.fetchone()
            if not user:
                print(f"User not found in database: {session['user_id']}")
                flash('User account not found', 'error')
                return redirect(url_for('home'))
                
            # Get user's chatbots
            if os.environ.get('DB_TYPE') == 'postgresql':
                cursor.execute(
                    "SELECT * FROM companies WHERE user_id = %s ORDER BY created_at DESC",
                    (session['user_id'],)
                )
            else:
                cursor.execute(
                    "SELECT * FROM companies WHERE user_id = ? ORDER BY created_at DESC",
                    (session['user_id'],)
                )
                
            chatbots = cursor.fetchall()
            print(f"Found {len(chatbots)} chatbots for user")
            
            # Convert to list of dicts for easier access in template
            chatbot_list = []
            for chatbot in chatbots:
                columns = [desc[0] for desc in cursor.description]
                chatbot_dict = dict(zip(columns, chatbot))
                
                # Convert string timestamps to datetime objects for use with strftime in template
                if 'created_at' in chatbot_dict and chatbot_dict['created_at']:
                    try:
                        # Handle different timestamp formats
                        if isinstance(chatbot_dict['created_at'], str):
                            # Try common formats
                            formats_to_try = [
                                '%Y-%m-%d %H:%M:%S',  # 2023-01-01 12:34:56
                                '%Y-%m-%dT%H:%M:%S',  # 2023-01-01T12:34:56
                                '%Y-%m-%d %H:%M:%S.%f'  # 2023-01-01 12:34:56.789
                            ]
                            
                            for fmt in formats_to_try:
                                try:
                                    chatbot_dict['created_at'] = datetime.strptime(
                                        chatbot_dict['created_at'].split('.')[0],  # Remove microseconds if present
                                        fmt
                                    )
                                    break
                                except ValueError:
                                    continue
                    except Exception as e:
                        print(f"Error converting timestamp: {e}")
                        # If conversion fails, keep as string
                
                chatbot_list.append(chatbot_dict)
            
            return render_template('dashboard.html', 
                               chatbots=chatbot_list, 
                               user_name=session.get('name', ''),
                               user_email=session.get('email', ''))
        
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"Database error in dashboard: {str(e)}")
            flash(f'Error loading dashboard: {e}', 'error')
            return redirect(url_for('home'))
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        print(f"Unexpected error in dashboard: {str(e)}")
        print(traceback.format_exc())
        flash('An unexpected error occurred', 'error')
        return redirect(url_for('home'))

@app.route('/check-processing-latest', methods=['GET'])
def check_processing_latest():
    """Return the ID of the most recently created chatbot process"""
    print(f"[check_processing_latest] Checking for latest chatbot")
    
    if not processing_status:
        print(f"[check_processing_latest] No processing status entries found")
        return jsonify({"status": "error", "message": "No processing found"}), 404
    
    # Get the most recent chatbot_id based on start_time
    latest_chatbot_id = None
    latest_start_time = 0
    
    for chatbot_id, status_info in processing_status.items():
        if status_info.get("start_time", 0) > latest_start_time:
            latest_start_time = status_info.get("start_time", 0)
            latest_chatbot_id = chatbot_id
    
    if not latest_chatbot_id:
        print(f"[check_processing_latest] No valid chatbot found")
        return jsonify({"status": "error", "message": "No valid processing found"}), 404
    
    print(f"[check_processing_latest] Found latest chatbot: {latest_chatbot_id}")
    return jsonify({
        "status": "success",
        "chatbot_id": latest_chatbot_id
    })

@app.route('/verify-domain', methods=['POST'])
def verify_domain():
    """Verify if a domain is authorized to use a specific chatbot"""
    try:
        data = request.json
        chatbot_id = data.get('chatbot_id')
        domain = data.get('domain')
        
        print(f"[verify-domain] Received request: chatbot_id={chatbot_id}, domain={domain}")
        
        if not chatbot_id or not domain:
            print(f"[verify-domain] Missing required fields: chatbot_id={chatbot_id}, domain={domain}")
            return jsonify({'error': 'Missing chatbot_id or domain', 'authorized': False}), 400
            
        # Get the company URL for this chatbot
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT company_url
                    FROM companies
                    WHERE chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT company_url
                    FROM companies
                    WHERE chatbot_id = ?
                ''', (chatbot_id,))
                
            row = cursor.fetchone()
            
        if not row:
            print(f"[verify-domain] Chatbot not found: {chatbot_id}")
            return jsonify({'error': 'Chatbot not found', 'authorized': False}), 404
            
        company_url = row[0]
        print(f"[verify-domain] Found company_url: {company_url}")
        
        # Extract domain from company URL
        try:
            # Handle malformed URLs by adding protocol if missing
            if not company_url.startswith(('http://', 'https://')):
                company_url = 'https://' + company_url
                print(f"[verify-domain] Added protocol to URL: {company_url}")
                
            # Parse URL components
            parsed_url = urlparse(company_url)
            company_domain = parsed_url.netloc.lower()
            
            # Handle empty netloc by trying to use path as domain
            if not company_domain and parsed_url.path:
                company_domain = parsed_url.path.split('/')[0].lower()
                print(f"[verify-domain] Using path as domain: {company_domain}")
                
            # Remove www. prefix if present
            if company_domain.startswith('www.'):
                company_domain = company_domain[4:]
                print(f"[verify-domain] Removed www prefix: {company_domain}")
                
            # Clean up request domain
            request_domain = domain.lower()
            if request_domain.startswith('www.'):
                request_domain = request_domain[4:]
                
            print(f"[verify-domain] Comparing domains: request={request_domain}, company={company_domain}")
                
            # Check if domains match exactly or if request domain is a subdomain of company domain
            is_authorized = (request_domain == company_domain or 
                            request_domain.endswith('.' + company_domain))
            
            # Also check the reverse - allow main domain to use bots created for subdomains
            if not is_authorized and '.' in company_domain:
                main_company_domain = '.'.join(company_domain.split('.')[-2:])
                is_authorized = request_domain == main_company_domain
                
            print(f"[verify-domain] Authorization result: {is_authorized}")
            
            return jsonify({'authorized': is_authorized})
            
        except Exception as e:
            import traceback
            print(f"[verify-domain] Error parsing domain: {e}")
            print(f"[verify-domain] Traceback: {traceback.format_exc()}")
            print(f"[verify-domain] Company URL: {company_url}, Request domain: {domain}")
            return jsonify({'error': f'Invalid domain format: {str(e)}', 'authorized': False}), 400
            
    except Exception as e:
        import traceback
        print(f"[verify-domain] Unhandled error: {e}")
        print(f"[verify-domain] Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Server error: {str(e)}', 'authorized': False}), 500

@app.route('/verify-support-domain', methods=['POST'])
@limiter.limit("10 per minute")
def verify_support_domain():
    """Verify if a domain is authorized to use the support chatbot"""
    try:
        data = request.json
        domain = data.get('domain')
        
        print(f"[verify-support-domain] Received request: domain={domain}")
        
        if not domain:
            print(f"[verify-support-domain] Missing required field: domain={domain}")
            return jsonify({'error': 'Missing domain', 'authorized': False}), 400
            
        # List of authorized domains for the support chatbot
        authorized_domains = [
            'localhost',
            '127.0.0.1',
            'easyafchat-v3-epbzeabngbb5dcek.centralus-01.azurewebsites.net',
            'goeasychat.com',
            'www.goeasychat.com'
            # Add any other domains you want to authorize here
        ]
        
        # Clean up request domain
        request_domain = domain.lower()
        if request_domain.startswith('www.'):
            request_domain = request_domain[4:]
                
        print(f"[verify-support-domain] Checking domain: {request_domain}")
        
        # Check if domain is in authorized list
        is_authorized = request_domain in authorized_domains
        
        # Also check if it's a local development domain with common ports
        if not is_authorized and (request_domain.startswith('localhost:') or request_domain.startswith('127.0.0.1:')):
            base_domain = request_domain.split(':')[0]
            is_authorized = base_domain in authorized_domains
            
        print(f"[verify-support-domain] Authorization result: {is_authorized}")
        
        return jsonify({'authorized': is_authorized})
            
    except Exception as e:
        import traceback
        print(f"[verify-support-domain] Unhandled error: {e}")
        print(f"[verify-support-domain] Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Server error: {str(e)}', 'authorized': False}), 500

@app.route('/debug-url')
def debug_url():
    from flask import request
    print(f"request.url_root: {request.url_root}")
    print(f"request.host_url: {request.host_url}")
    print(f"request.base_url: {request.base_url}")
    print(f"request.url: {request.url}")
    print(f"request headers: {dict(request.headers)}")
    return f"""
    URL Root: {request.url_root}
    Host URL: {request.host_url}
    Base URL: {request.base_url}
    """

# Exempt chatbot endpoints from CSRF protection after they're defined
chatbot_endpoints = [
    'embed_chat', 
    'embed_reset_chat', 
    'reset_chat', 
    'verify_domain', 
    'verify_support_domain'
]

# Exempt function names in app.view_functions
for endpoint in chatbot_endpoints:
    if endpoint in app.view_functions:
        csrf.exempt(app.view_functions[endpoint])

# Exempt lead-related routes in the leads_blueprint
if 'leads.handle_lead_submission' in app.view_functions:
    csrf.exempt(app.view_functions['leads.handle_lead_submission'])

# Also exempt lead form config endpoint
if 'leads.get_lead_form_config' in app.view_functions:
    csrf.exempt(app.view_functions['leads.get_lead_form_config'])

@app.route('/config/chatbot/<chatbot_id>', methods=['GET'])
def get_chatbot_config(chatbot_id):
    """
    Get chatbot configuration for the specified chatbot ID.
    This includes the icon_image_url and other settings.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Determine placeholder style based on database type
            # SQLite uses ? while PostgreSQL uses %s
            db_type = os.getenv('DB_TYPE', 'sqlite')
            placeholder = '?' if db_type.lower() == 'sqlite' else '%s'
            
            # Query the chatbot_config table for the specified chatbot_id
            query = f"""
                SELECT 
                    config_id, chatbot_id, chat_model, temperature, max_tokens,
                    system_prompt, chat_title, chat_subtitle, lead_form_title, 
                    primary_color, accent_color, icon_image_url, show_lead_form
                FROM chatbot_config
                WHERE chatbot_id = {placeholder}
            """
            
            cursor.execute(query, (chatbot_id,))
            config = cursor.fetchone()
            
            # If no config found, return a default configuration
            if not config:
                return jsonify({
                    'status': 'default',
                    'icon_image_url': None,
                    'chat_title': None,
                    'chat_subtitle': None
                }), 200
            
            # Convert the row to a dictionary
            columns = [desc[0] for desc in cursor.description]
            config_dict = dict(zip(columns, config))
            
            # Add a status field to indicate successful retrieval
            config_dict['status'] = 'success'
            
            return jsonify(config_dict), 200
            
    except Exception as e:
        import traceback
        print(f"Error fetching chatbot config: {e}")
        print(traceback.format_exc())  # Print full stack trace
        return jsonify({
            'status': 'error',
            'message': f'Failed to fetch chatbot configuration: {str(e)}',
            'icon_image_url': None,
            'chat_title': None,
            'chat_subtitle': None
        }), 500
    
# Zoho SMTP Email Test
@app.route('/test-email', methods=['GET'])
def test_email():
    try:
        recipient = request.args.get('to', 'david@lluniversity.com')
        
        msg = Message(
            subject="GoEasyChat - Test Email",
            recipients=[recipient],
            body=f"""
Hello,

This is a test email from GoEasyChat to verify that our email system is working correctly.

The time is now: {datetime.now()}

Thanks,
The GoEasyChat Team
            """
        )
        
        mail.send(msg)
        return f"Test email sent to {recipient}. Please check your inbox."
    except Exception as e:
        return f"Error sending email: {str(e)}"

@app.route('/check-active-status/<chatbot_id>', methods=['GET'])
@limiter.limit("10 per minute")
def check_active_status(chatbot_id):
    """Check if a chatbot is active and can be displayed"""
    try:
        # Get database connection
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder based on database type
            placeholder = '%s' if os.getenv('DB_TYPE', '').lower() == 'postgresql' else '?'
            
            # Query to get active_status from companies table
            query = f"""
                SELECT active_status
                FROM {'companies' if os.getenv('DB_TYPE', '').lower() != 'postgresql' else DB_SCHEMA + '.companies'}
                WHERE chatbot_id = {placeholder}
            """
            
            cursor.execute(query, (chatbot_id,))
            result = cursor.fetchone()
            
            if not result:
                print(f"[check_active_status] Chatbot ID not found: {chatbot_id}")
                return jsonify({
                    "active": False,
                    "status": "not_found",
                    "message": "Chatbot not found"
                }), 404
            
            active_status = result[0]
            print(f"[check_active_status] Chatbot {chatbot_id} status: {active_status}")
            
            # Only consider 'live' as active
            is_active = active_status == 'live'
            
            return jsonify({
                "active": is_active,
                "status": active_status
            })
            
    except Exception as e:
        import traceback
        print(f"[check_active_status] Error checking status: {e}")
        print(traceback.format_exc())
        return jsonify({
            "active": False,
            "status": "error",
            "message": "Internal server error"
        }), 500


def validate_webhook_url(url):
    """
    Validate if a webhook URL is from an allowed provider
    
    Args:
        url (str): The webhook URL to validate
        
    Returns:
        bool: True if the URL is valid, False otherwise
    """
    if not url:
        return False
        
    # List of allowed webhook providers
    allowed_domains = [
        'hooks.zapier.com',
        'hook.us1.make.com',
        'hook.eu1.make.com',
        'hook.make.com',
        'cloud.n8n.io',
        'endpoint.pipedream.net',
        'maker.ifttt.com',
        'wh.automate.io',
        'logic.azure.com',  # Microsoft Power Automate
        'hook.integromat.com',
        'api.webhookrelay.com',
        'flowservice.realm.io',
        'hooks.slack.com',
        'api.platformable.com',
        'webhooks.data8.app',
        'automate.io',  # Generic domain
        'workflow.adalo.com',
        'dsl.pipedream.net',
        'chatflow.io',
        'sendymail.com',
        'localhost',  # For local testing
        '127.0.0.1'   # For local testing
    ]
    
    # Domain patterns to match (e.g., *.app.n8n.cloud)
    domain_patterns = [
        '.app.n8n.cloud',  # Any n8n cloud domain
        '.n8n.io'          # Any n8n.io domain
    ]
    
    try:
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        
        # Extract domain from URL
        domain = parsed_url.netloc.lower()
        
        # Check if domain is in the exact allowed list
        if domain in allowed_domains:
            return True
            
        # Check for exact subdomain of allowed domains
        for allowed in allowed_domains:
            if domain.endswith('.' + allowed) or domain == allowed:
                return True
                
        # Check for pattern matches
        for pattern in domain_patterns:
            if domain.endswith(pattern):
                return True
        
        print(f"[webhook] URL validation failed for: {url}, domain: {domain}")
        return False
    except Exception as e:
        print(f"[webhook] Error validating webhook URL: {e}")
        return False

# Create a simple in-memory rate limiter for webhooks
webhook_rate_limits = {}

def check_rate_limit(webhook_url, max_calls=10, period_seconds=60):
    """
    Check if a webhook URL has exceeded its rate limit
    
    Args:
        webhook_url (str): The webhook URL to check
        max_calls (int): Maximum number of calls allowed in the period
        period_seconds (int): The period in seconds
        
    Returns:
        bool: True if rate limit is not exceeded, False otherwise
    """
    from time import time
    current_time = time()
    
    # Create an entry for this webhook if it doesn't exist
    if webhook_url not in webhook_rate_limits:
        webhook_rate_limits[webhook_url] = {
            'calls': [],
            'blocked_until': 0
        }
    
    rate_info = webhook_rate_limits[webhook_url]
    
    # Check if webhook is currently blocked
    if current_time < rate_info['blocked_until']:
        print(f"[webhook] Rate limit exceeded for {webhook_url}, blocked until {rate_info['blocked_until']}")
        return False
    
    # Remove calls that are outside the current period
    rate_info['calls'] = [timestamp for timestamp in rate_info['calls'] 
                         if timestamp > current_time - period_seconds]
    
    # Check if adding this call would exceed the limit
    if len(rate_info['calls']) >= max_calls:
        # Block this webhook for 5 minutes (adjust as needed)
        block_duration = 300  # 5 minutes in seconds
        rate_info['blocked_until'] = current_time + block_duration
        print(f"[webhook] Rate limit exceeded for {webhook_url}, blocking for {block_duration} seconds")
        return False
    
    # Add the current call time
    rate_info['calls'].append(current_time)
    return True


def send_webhook(chatbot_id, event_type, payload_data):
    """
    Send a webhook notification if configured for the chatbot and event
    
    Args:
        chatbot_id (str): The chatbot ID
        event_type (str): The event type (e.g., "new_lead")
        payload_data (dict): The data to include in the payload
        
    Returns:
        bool: True if webhook was sent successfully, False otherwise
    """
    import requests
    import json
    from datetime import datetime
    
    try:
        # Get webhook configuration from database
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholders based on DB type
            placeholder = "%s" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "?"
            
            # Get webhook URL and triggers
            cursor.execute(f"""
                SELECT webhook_url, webhook_triggers
                FROM chatbot_config
                WHERE chatbot_id = {placeholder}
            """, (chatbot_id,))
            
            result = cursor.fetchone()
            
            if not result or not result[0] or not result[1]:
                # No webhook configured or no triggers set
                return False
                
            webhook_url, webhook_triggers = result
            
            # Check if the webhook URL is valid
            if not validate_webhook_url(webhook_url):
                print(f"[webhook] Invalid webhook URL for chatbot {chatbot_id}: {webhook_url}")
                return False
                
            # Parse the comma-separated triggers
            triggers = [t.strip() for t in webhook_triggers.split(',')]
            
            # Check if this event type is in the triggers
            if event_type not in triggers:
                print(f"[webhook] Event type {event_type} not in triggers for chatbot {chatbot_id}")
                return False
                
            # Check rate limit
            if not check_rate_limit(webhook_url):
                print(f"[webhook] Rate limit exceeded for chatbot {chatbot_id}")
                return False
                
            # Create the full payload with metadata
            full_payload = {
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                "chatbot_id": chatbot_id,
                **payload_data
            }
            
            # Send the webhook with retries
            for attempt in range(3):  # Try up to 3 times
                try:
                    response = requests.post(
                        webhook_url, 
                        json=full_payload,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'GoEasyChat-Webhook/1.0'
                        },
                        timeout=3  # 3 second timeout
                    )
                    
                    # Log the webhook attempt
                    print(f"[webhook] Sent {event_type} webhook for chatbot {chatbot_id} - Status: {response.status_code}")
                    
                    # Check if request was successful
                    if response.status_code >= 200 and response.status_code < 300:
                        return True
                    
                    # If we get here, the request failed but didn't raise an exception
                    print(f"[webhook] Failed with status {response.status_code}: {response.text[:100]}")
                    
                except requests.RequestException as e:
                    print(f"[webhook] Request failed on attempt {attempt+1}: {str(e)}")
                    
                # Wait before retrying (exponential backoff)
                if attempt < 2:  # Don't sleep after the last attempt
                    import time
                    time.sleep(2 ** attempt)  # 0, 2, 4 seconds
            
            # If we get here, all attempts failed
            print(f"[webhook] All attempts failed for chatbot {chatbot_id}")
            return False
                
    except Exception as e:
        print(f"[webhook] Error sending webhook: {e}")
        import traceback
        print(traceback.format_exc())
        return False

# Initialize webhook function in leads blueprint
try:
    from db_leads import init_webhook_function
    init_webhook_function(send_webhook)
    print("Webhook function initialized in leads blueprint")
except ImportError:
    print("Warning: Could not initialize webhook function in leads blueprint")
except Exception as e:
    print(f"Error initializing webhook function: {e}")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))  # Digital Ocean needs this
    app.run(host='0.0.0.0', port=port, debug=False)  # Listen on all interfaces