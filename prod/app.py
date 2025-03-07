from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from openai import OpenAI
from pinecone import Pinecone
from datetime import datetime, UTC
from typing import List, Dict, Tuple, Optional
from chat_handler import ChatPromptHandler
from flask_cors import CORS
from db_leads import leads_blueprint, init_leads_blueprint
import time
import os
import validators
import trafilatura
import requests
import uuid
import re
import json


# Import the admin dashboard blueprint
from admin_dashboard import admin_dashboard, init_admin_dashboard
from documents_blueprint import documents_blueprint, init_documents_blueprint

# Load environment variables from .env only in development
# Set ENVIRONMENT to production on Azure
if os.environ.get('ENVIRONMENT') != 'production':
    load_dotenv()

# Import database initialization and connection functions
from database import initialize_database, connect_to_db

# Initialize the database silently
initialize_database(verbose=False)

# Initialize Flask app
app = Flask(__name__)
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
app.register_blueprint(admin_dashboard, url_prefix='/admin-dashboard-08x7z9y2-yoursecretword')

# Initialize and register the documents blueprint
init_documents_blueprint(openai_client, pinecone_client, PINECONE_INDEX)
app.register_blueprint(documents_blueprint, url_prefix='/documents')

# Dictionary to track processing status
processing_status = {}

# Initialize chat handlers dictionary
chat_handlers = {}

def chunk_text(text, chunk_size=500):
    """Split text into smaller chunks for processing"""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        current_size += len(word) + 1
        if current_size > chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_size = len(word)
        else:
            current_chunk.append(word)
            
    if current_chunk:
        chunks.append(' '.join(current_chunk))
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', data)
        else:
            # SQLite uses ? placeholders
            cursor.execute('''
                INSERT INTO companies 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)

def get_existing_record(url):
    """Check if URL already exists in database and return its data"""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        # Normalize URL by converting to lowercase
        url_lower = url.lower()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                SELECT chatbot_id, pinecone_namespace
                FROM companies 
                WHERE LOWER(company_url) = %s
            ''', (url_lower,))
        else:
            cursor.execute('''
                SELECT chatbot_id, pinecone_namespace
                FROM companies 
                WHERE LOWER(company_url) = ?
            ''', (url_lower,))
            
        row = cursor.fetchone()
        return row

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

# Flask routes
@app.route('/chat-test')
def chat_test():
    return render_template('chat_test.html')

@app.route('/')
def home():
    return render_template('landing.html')

@app.route('/process-url-async', methods=['POST'])
def process_url_async():
    website_url = request.form.get('url')
    
    if not validators.url(website_url):
        return jsonify({"error": "Please enter a valid URL"}), 400
    
    # Check if URL already exists in the database
    existing_record = get_existing_record(website_url)
    
    if existing_record:
        chatbot_id = existing_record[0]
        namespace = existing_record[1]
    else:
        chatbot_id = generate_chatbot_id()
        namespace, _ = check_namespace(website_url)
    
    # Initialize processing status
    processing_status[chatbot_id] = {
        "namespace": namespace,
        "completed": False,
        "start_time": time.time(),
        "website_url": website_url
    }
    
    # Return chatbot_id immediately so frontend can start polling
    return jsonify({
        "status": "processing",
        "chatbot_id": chatbot_id
    })

@app.route('/process-url-execute/<chatbot_id>', methods=['GET'])
def process_url_execute(chatbot_id):
    """Execute URL processing in background while frontend polls for status"""
    if chatbot_id not in processing_status:
        return jsonify({"error": "Invalid chatbot ID"}), 404
    
    status_info = processing_status[chatbot_id]
    website_url = status_info["website_url"]
    namespace = status_info["namespace"]
    
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
        
    # Unpack the result - processed_content is the OpenAI response, full_prompt is what was sent to OpenAI
    processed_content, full_prompt = result
    
    # Store the about page text (if it was found)
    about_text = about_data.get("all_text", "About page not found") if about_data else "About page not found"
    
    # Combine into a single scraped_text field with clear sections
    scraped_text = f"""OpenAI Prompt
{full_prompt}

About Scrape
{about_text}"""
    
    # Chunk the content and create embeddings
    chunks = chunk_text(processed_content)
    embeddings = get_embeddings(chunks)
    
    if not update_pinecone_index(namespace, chunks, embeddings):
        processing_status[chatbot_id]["error"] = "Failed to update knowledge base"
        return jsonify({"error": "Failed to update knowledge base"}), 400

    now = datetime.now(UTC)
    data = (
        chatbot_id, website_url, PINECONE_HOST, PINECONE_INDEX,
        namespace, now, now, scraped_text, processed_content
    )

    try:
        if existing_record := get_existing_record(website_url):
            update_company_data(data, chatbot_id)
        else:
            insert_company_data(data)
    except Exception as e:
        print(f"Database error: {e}")
        processing_status[chatbot_id]["error"] = f"Failed to save company data: {str(e)}"
        return jsonify({"error": "Failed to save company data"}), 400

    # Generate APIFlash screenshot URL
    try:
        # Format the URL for APIFlash
        base_url = "https://api.apiflash.com/v1/urltoimage"
        
        screenshot_url = f"{base_url}?access_key={APIFLASH_KEY}&url={website_url}&format=jpeg&width=1600&height=1066"
        print(f"Screenshot URL generated: {screenshot_url}")
    except Exception as e:
        print(f"Error generating screenshot URL: {e}, but continuing")

    # Processing is successfully complete, update status to "waiting for pinecone"
    processing_status[chatbot_id]["status"] = "waiting_for_pinecone"
    
    return jsonify({"status": "success", "chatbot_id": chatbot_id})

@app.route('/check-processing/<chatbot_id>', methods=['GET'])
def check_processing(chatbot_id):
    """Check if processing is complete for a chatbot"""
    if chatbot_id not in processing_status:
        return jsonify({"status": "error", "message": "Chatbot ID not found"}), 404
    
    status_info = processing_status[chatbot_id]
    
    # If already marked as completed, return success
    if status_info.get("completed", False):
        return jsonify({
            "status": "complete",
            "chatbot_id": chatbot_id,
            "website_url": status_info.get("website_url", "")
        })
    
    # If there was an error during processing
    if "error" in status_info:
        return jsonify({
            "status": "error",
            "message": status_info["error"]
        }), 400
    
    # If we're still in the initial processing phase
    if "status" not in status_info or status_info["status"] != "waiting_for_pinecone":
        elapsed_time = time.time() - status_info["start_time"]
        return jsonify({
            "status": "processing",
            "phase": "content",
            "elapsed_seconds": int(elapsed_time)
        })
    
    # At this point, we're waiting for Pinecone to finish indexing
    # Check Pinecone status
    is_complete = check_pinecone_status(status_info["namespace"])
    
    # If complete, update status
    if is_complete:
        status_info["completed"] = True
        processing_time = time.time() - status_info["start_time"]
        print(f"Processing completed for {chatbot_id} in {processing_time:.2f} seconds")
        return jsonify({
            "status": "complete", 
            "chatbot_id": chatbot_id,
            "website_url": status_info.get("website_url", "")
        })
    
    # If still processing, return in-progress status
    elapsed_time = time.time() - status_info["start_time"]
    return jsonify({
        "status": "processing",
        "phase": "pinecone", 
        "elapsed_seconds": int(elapsed_time)
    })

@app.route('/', methods=['POST'])
def process_url():
    website_url = request.form.get('url')
    
    if not validators.url(website_url):
        flash("Please enter a valid URL")
        return redirect(url_for('home'))
    
    # Check if URL already exists in the database
    existing_record = get_existing_record(website_url)
    
    if existing_record:
        chatbot_id = existing_record[0]
        namespace = existing_record[1]
    else:
        chatbot_id = generate_chatbot_id()
        namespace, _ = check_namespace(website_url)

    # Simplified scraping of the website and its About page
    home_data = simple_scrape_page(website_url)
    about_url = find_about_page(website_url)
    about_data = simple_scrape_page(about_url) if about_url else None
    
    if not home_data.get("all_text"):
        flash("Failed to scrape website content")
        return redirect(url_for('home'))

    # Process the content with OpenAI - returns both content and prompt
    result = process_simple_content(home_data, about_data)
    if not result:
        flash("Failed to process content")
        return redirect(url_for('home'))
        
    # Unpack the result - processed_content is the OpenAI response, full_prompt is what was sent to OpenAI
    processed_content, full_prompt = result
    
    # Store the about page text (if it was found)
    about_text = about_data.get("all_text", "About page not found") if about_data else "About page not found"
    
    # Combine into a single scraped_text field with clear sections
    scraped_text = f"""OpenAI Prompt
{full_prompt}

About Scrape
{about_text}"""
    
    # Chunk the content and create embeddings
    chunks = chunk_text(processed_content)
    embeddings = get_embeddings(chunks)
    
    if not update_pinecone_index(namespace, chunks, embeddings):
        flash("Failed to update knowledge base")
        return redirect(url_for('home'))

    now = datetime.now(UTC)
    data = (
        chatbot_id, website_url, PINECONE_HOST, PINECONE_INDEX,
        namespace, now, now, scraped_text, processed_content
    )

    try:
        if existing_record:
            update_company_data(data, chatbot_id)
        else:
            insert_company_data(data)
    except Exception as e:
        print(f"Database error: {e}")
        flash("Failed to save company data")
        return redirect(url_for('home'))

    # Generate APIFlash screenshot URL
    try:
        # Format the URL for APIFlash
        base_url = "https://api.apiflash.com/v1/urltoimage"
        
        screenshot_url = f"{base_url}?access_key={APIFLASH_KEY}&url={website_url}&format=jpeg&width=1600&height=1066"
        print(f"Screenshot URL generated: {screenshot_url}")
    except Exception as e:
        print(f"Error generating screenshot URL: {e}")
        flash("Failed to generate screenshot URL")
        return redirect(url_for('home'))

@app.route('/demo/<session_id>')
def demo(session_id):
    # Fetch the company URL for the given chatbot ID
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                SELECT company_url, scraped_text, processed_content
                FROM companies
                WHERE chatbot_id = %s
            ''', (session_id,))
        else:
            cursor.execute('''
                SELECT company_url, scraped_text, processed_content
                FROM companies
                WHERE chatbot_id = ?
            ''', (session_id,))
            
        row = cursor.fetchone()

    if not row:
        flash("Invalid session ID")
        return redirect(url_for('home'))

    website_url, scraped_text, processed_content = row
    
    # Generate APIFlash screenshot URL dynamically
    try:
        # Format the URL for APIFlash
        base_url = "https://api.apiflash.com/v1/urltoimage"
        
        screenshot_url = f"{base_url}?access_key={APIFLASH_KEY}&url={website_url}&format=jpeg&width=1600&height=1066"
    except Exception as e:
        print(f"Error generating screenshot URL: {e}")
        screenshot_url = ""  # Empty URL if there's an error

    # Pass the screenshot URL and other data to the template
    return render_template(
        'demo.html',
        website_url=website_url,
        chatbot_id=session_id,
        screenshot_url=screenshot_url
    )

@app.route('/embed-chat', methods=['POST'])
def embed_chat():
    try:
        data = request.json
        print("Received chat request:", data)  # Keep existing debug log
        chatbot_id = data.get("chatbot_id")
        user_message = data.get("message")
        thread_id = data.get("thread_id")  # Get the thread_id from the request

        if not chatbot_id or not user_message:
            print(f"Missing fields - chatbot_id: {chatbot_id}, message: {user_message}")
            return jsonify({"error": "Missing chatbot_id or message"}), 400

        # Get namespace BEFORE initializing chat handler
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT pinecone_namespace
                    FROM companies
                    WHERE chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT pinecone_namespace
                    FROM companies
                    WHERE chatbot_id = ?
                ''', (chatbot_id,))
                
            row = cursor.fetchone()

        if not row:
            print(f"Chatbot ID {chatbot_id} not found in database")
            return jsonify({"error": "Chatbot ID not found"}), 404

        namespace = row[0]
        
        # Initialize chat handler with namespace if it doesn't exist
        if chatbot_id not in chat_handlers:
            chat_handlers[chatbot_id] = ChatPromptHandler(openai_client, pinecone_client)
            # Ensure first message includes system prompt by forcing conversation reset
            chat_handlers[chatbot_id].reset_conversation()
            
            # If a thread_id was provided, set it in the handler
            if thread_id:
                chat_handlers[chatbot_id].thread_id = thread_id

        handler = chat_handlers[chatbot_id]
        messages = handler.format_messages(user_message, namespace=namespace)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        assistant_response = response.choices[0].message.content
        handler.add_to_history("user", user_message)
        handler.add_to_history("assistant", assistant_response)

        # Get the current conversation state for the frontend
        conversation_state = handler.get_conversation_state()
        
        # Debugging information - add this to see what's happening
        print(f"Conversation state: {conversation_state}")

        return jsonify({
            "response": assistant_response,
            "thread_id": conversation_state["thread_id"],
            "is_first_interaction": conversation_state["is_first_interaction"],
            "message_count": conversation_state["message_count"],
            "initial_question": conversation_state.get("initial_question")
        })

    except Exception as e:
        print(f"Detailed error in embed-chat: {str(e)}")  # Enhanced error logging
        return jsonify({"error": "Internal server error"}), 500
    

@app.route('/embed-reset-chat', methods=['POST'])
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

@app.route('/standalone-test')
def standalone_test():
    return render_template('standalone_test.html')

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))  # Digital Ocean needs this
    app.run(host='0.0.0.0', port=port, debug=False)  # Listen on all interfaces