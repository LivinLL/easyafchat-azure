from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from openai import OpenAI
from pinecone import Pinecone
from datetime import datetime, UTC  # Add UTC here
from typing import List, Dict
from chat_handler import ChatPromptHandler
from flask_cors import CORS
import time
import os
import sqlite3
import validators
import trafilatura
import requests
import uuid
import re

# Import the admin dashboard blueprint
from admin_dashboard import admin_dashboard, init_admin_dashboard

# Load environment variables from .env only in development
# Set ENVIRONMENT to production on Azure
if os.environ.get('ENVIRONMENT') != 'production':
    load_dotenv()

# Import database initialization
from database import initialize_database

# Initialize the database silently
initialize_database(verbose=False)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Add this line
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pinecone_client = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# Constants
PINECONE_INDEX = "all-companies"
PINECONE_HOST = "https://all-companies-6ctd3g7.svc.aped-4627-b74a.pinecone.io"
DB_PATH = os.getenv('DB_PATH', 'easyafchat.db')

# Initialize and register the admin dashboard blueprint
init_admin_dashboard(openai_client, pinecone_client, DB_PATH, PINECONE_INDEX)
app.register_blueprint(admin_dashboard, url_prefix='/admin-dashboard-08x7z9y2-yoursecretword')

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
   try:
       index = pinecone_client.Index(PINECONE_INDEX)
       stats = index.describe_index_stats()
       
       # Clean URL to base namespace - convert to lowercase for consistency
       domain = url.split('//')[-1].split('/')[0].split('.')[0].lower()
       base = re.sub(r'[^a-zA-Z0-9-]', '', domain.replace('.', '-'))
       
       # Find existing namespaces
       pattern = f"^{base}-\\d+$"
       existing = [ns for ns in stats.namespaces.keys() if re.match(pattern, ns)]
       
       if not existing:
           return f"{base}-01", None
           
       # Return the existing namespace instead of creating a new one
       current = max(existing, key=lambda x: int(x.split('-')[-1]))
       return current, None
   except Exception as e:
       print(f"Error checking namespace: {e}")
       return f"{base}-01", None

def insert_company_data(data):
   conn = sqlite3.connect(DB_PATH)  # Using DB_PATH constant
   cursor = conn.cursor()
   cursor.execute('INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', data)
   conn.commit()
   conn.close()

def get_existing_record(url):
   """Check if URL already exists in database and return its data"""
   conn = sqlite3.connect(DB_PATH)  # Using DB_PATH constant
   cursor = conn.cursor()
   
   # Normalize URL by converting to lowercase
   url_lower = url.lower()
   
   cursor.execute('''
       SELECT chatbot_id, pinecone_namespace
       FROM companies 
       WHERE LOWER(company_url) = ?
   ''', (url_lower,))
   row = cursor.fetchone()
   conn.close()
   return row

def update_company_data(data, chatbot_id):
   """Update existing company record"""
   conn = sqlite3.connect(DB_PATH)  # Using DB_PATH constant
   cursor = conn.cursor()
   cursor.execute('''
       UPDATE companies 
       SET company_url=?, pinecone_host_url=?, pinecone_index=?, 
           pinecone_namespace=?, updated_at=?, home_text=?, 
           about_text=?, processed_content=?
       WHERE chatbot_id=?
   ''', (data[1], data[2], data[3], data[4], data[6], 
         data[7], data[8], data[9], chatbot_id))
   conn.commit()
   conn.close()

def scrape_page(url):
   try:
       downloaded = trafilatura.fetch_url(url)
       return trafilatura.extract(downloaded) if downloaded else None
   except Exception as e:
       print(f"Error scraping page: {e}")
       return None

def find_about_page(base_url):
   try:
       response = requests.get(base_url, timeout=10)
       soup = BeautifulSoup(response.text, 'html.parser')
       
       for link in soup.find_all('a', href=True):
           href = link['href'].lower()
           text = link.get_text(strip=True).lower()
           if 'about' in href or 'about' in text:
               return urljoin(base_url.rstrip('/'), link['href'])
       return None
   except Exception as e:
       print(f"Error finding About page: {e}")
       return None

def process_content(home_text, about_text):
   try:
       prompt = f"""
       Create a knowledge base document from this website content:

       HOME PAGE:
       {home_text}

       ABOUT PAGE:
       {about_text}
       """
       response = openai_client.chat.completions.create(
           model="gpt-4o",
           messages=[{"role": "user", "content": prompt}]
       )
       return response.choices[0].message.content
   except Exception as e:
       print(f"Error processing with OpenAI: {e}")
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
    
    # Scrape the website and its About page
    home_text = scrape_page(website_url)
    about_url = find_about_page(website_url)
    about_text = scrape_page(about_url) if about_url else "About page not found"

    if not home_text:
        processing_status[chatbot_id]["error"] = "Failed to scrape website content"
        return jsonify({"error": "Failed to scrape website content"}), 400

    # Process the scraped content with OpenAI
    processed_content = process_content(home_text, about_text)
    if not processed_content:
        processing_status[chatbot_id]["error"] = "Failed to process content"
        return jsonify({"error": "Failed to process content"}), 400

    # Chunk the content and create embeddings
    chunks = chunk_text(processed_content)
    embeddings = get_embeddings(chunks)
    
    if not update_pinecone_index(namespace, chunks, embeddings):
        processing_status[chatbot_id]["error"] = "Failed to update knowledge base"
        return jsonify({"error": "Failed to update knowledge base"}), 400

    now = datetime.now(UTC)
    data = (
        chatbot_id, website_url, PINECONE_HOST, PINECONE_INDEX,
        namespace, now, now, home_text, about_text, processed_content
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

    # Prefetch the Thum.io screenshot
    base_thumio_url = "https://image.thum.io/get/auth/73147-easyafchat-thumio/width/800/crop/1200"
    screenshot_url = f"{base_thumio_url}/{website_url}"

    # Make a GET request to force the screenshot to be generated
    try:
        response = requests.get(screenshot_url, timeout=10)
        if response.status_code != 200:
            print("Failed to generate screenshot, but continuing")
    except Exception as e:
        print(f"Error generating screenshot: {e}, but continuing")

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

    # Scrape the website and its About page
    home_text = scrape_page(website_url)
    about_url = find_about_page(website_url)
    about_text = scrape_page(about_url) if about_url else "About page not found"

    if not home_text:
        flash("Failed to scrape website content")
        return redirect(url_for('home'))

    # Process the scraped content with OpenAI
    processed_content = process_content(home_text, about_text)
    if not processed_content:
        flash("Failed to process content")
        return redirect(url_for('home'))

    # Chunk the content and create embeddings
    chunks = chunk_text(processed_content)
    embeddings = get_embeddings(chunks)
    
    if not update_pinecone_index(namespace, chunks, embeddings):
        flash("Failed to update knowledge base")
        return redirect(url_for('home'))

    now = datetime.now(UTC)
    data = (
        chatbot_id, website_url, PINECONE_HOST, PINECONE_INDEX,
        namespace, now, now, home_text, about_text, processed_content
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

    # Prefetch the Thum.io screenshot
    base_thumio_url = "https://image.thum.io/get/auth/73147-easyafchat-thumio/width/800/crop/1200"
    screenshot_url = f"{base_thumio_url}/{website_url}"

    # Make a GET request to force the screenshot to be generated
    try:
        response = requests.get(screenshot_url, timeout=10)
        if response.status_code != 200:
            flash("Failed to generate screenshot")
            return redirect(url_for('home'))
    except Exception as e:
        print(f"Error generating screenshot: {e}")
        flash("Failed to generate screenshot")
        return redirect(url_for('home'))

    # Optional delay to ensure the screenshot is fully cached
    time.sleep(2)

    # Redirect to the demo page with the session_id
    return redirect(url_for('demo', session_id=chatbot_id))


@app.route('/demo/<session_id>')
def demo(session_id):
    # Fetch the company URL for the given chatbot ID
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT company_url, home_text, about_text, processed_content
            FROM companies
            WHERE chatbot_id = ?
        ''', (session_id,))
        row = cursor.fetchone()

    if not row:
        flash("Invalid session ID")
        return redirect(url_for('home'))

    website_url, home_text, about_text, processed_content = row
    
    # Generate the screenshot URL dynamically
    base_thumio_url = "https://image.thum.io/get/auth/73147-easyafchat-thumio/width/800/crop/800"
    screenshot_url = f"{base_thumio_url}/{website_url}"

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

       if not chatbot_id or not user_message:
           print(f"Missing fields - chatbot_id: {chatbot_id}, message: {user_message}")
           return jsonify({"error": "Missing chatbot_id or message"}), 400

       # Get namespace BEFORE initializing chat handler
       with sqlite3.connect(DB_PATH) as conn:
           cursor = conn.cursor()
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

       return jsonify({"response": assistant_response})

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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM companies')
    rows = cursor.fetchall()
    conn.close()
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

if __name__ == '__main__':
   port = int(os.getenv('PORT', 8080))  # Digital Ocean needs this
   app.run(host='0.0.0.0', port=port, debug=False)  # Listen on all interfaces
