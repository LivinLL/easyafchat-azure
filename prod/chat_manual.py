from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from datetime import datetime, UTC
from flask_cors import CORS
import os
import re
import sqlite3
import uuid
import time

# Import functions from app.py
from app import (
    openai_client,
    pinecone_client,
    DB_PATH,
    PINECONE_INDEX,
    PINECONE_HOST,
    chunk_text,
    get_embeddings,
    check_namespace,
    update_pinecone_index,
    insert_company_data,
    update_company_data,
    get_existing_record
)

# Import ChatPromptHandler from chat_handler.py
from chat_handler import ChatPromptHandler

# Load environment variables
load_dotenv()

# Initialize Flask app with proper template path
# This ensures we use the same templates folder as the main app
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")
CORS(app)  # Enable CORS for all routes

# Dictionary to track processing status
processing_status = {}

def generate_chatbot_id():
    """Generate a unique chatbot ID"""
    return str(uuid.uuid4()).replace('-', '')[:20]

def clean_company_name(name):
    """Clean company name for use in namespace"""
    # Remove special characters and convert to lowercase
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
    # Ensure it's not empty
    if not cleaned:
        cleaned = "company"
    return cleaned

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

@app.route('/chat-manual', methods=['GET', 'POST'])
def manual_entry():
    """Handle manual knowledge base entry"""
    if request.method == 'POST':
        # Get form data
        company_name = request.form.get('company_name')
        knowledge_text = request.form.get('knowledge_text')
        
        # Validate input
        if not company_name or not knowledge_text:
            flash("Both company name and knowledge base text are required", "danger")
            return redirect(url_for('manual_entry'))
        
        # Clean company name for namespace
        clean_name = clean_company_name(company_name)
        
        # Create a dummy URL from company name for namespace generation
        dummy_url = f"http://{clean_name}.com"
        
        # Check if company already exists
        existing_record = get_existing_record(dummy_url)
        
        if existing_record:
            chatbot_id = existing_record[0]
            old_namespace = existing_record[1]
            new_namespace, _ = check_namespace(dummy_url)
        else:
            chatbot_id = generate_chatbot_id()
            new_namespace, old_namespace = check_namespace(dummy_url)
        
        # Chunk the content and create embeddings
        chunks = chunk_text(knowledge_text)
        embeddings = get_embeddings(chunks)
        
        # Update Pinecone index
        if not update_pinecone_index(new_namespace, chunks, embeddings, old_namespace):
            flash("Failed to update knowledge base", "danger")
            return redirect(url_for('manual_entry'))
        
        # Current time in UTC
        now = datetime.now(UTC)
        
        # Prepare data for database
        data = (
            chatbot_id, dummy_url, PINECONE_HOST, PINECONE_INDEX,
            new_namespace, now, now, 
            # Include knowledge text as both home_text and processed_content
            knowledge_text, "", knowledge_text
        )
        
        try:
            if existing_record:
                update_company_data(data, chatbot_id)
            else:
                insert_company_data(data)
        except Exception as e:
            print(f"Database error: {e}")
            flash(f"Failed to save company data: {e}", "danger")
            return redirect(url_for('manual_entry'))
        
        # Initialize processing status
        processing_status[chatbot_id] = {
            "namespace": new_namespace,
            "completed": False,
            "start_time": time.time()
        }
        
        # Prepare result data to pass to template
        result = {
            "company_name": company_name,
            "chatbot_id": chatbot_id,
            "namespace": new_namespace,
            "text_length": len(knowledge_text),
            "chunks": len(chunks),
            "status": "Processing"  # Changed from "Success" to "Processing"
        }
        
        flash("Knowledge base processing initiated!", "success")
        return render_template('chat_manual.html', result=result)
    
    # GET request - show empty form
    return render_template('chat_manual.html')

@app.route('/check-processing/<chatbot_id>', methods=['GET'])
def check_processing(chatbot_id):
    """Check if processing is complete for a chatbot"""
    if chatbot_id not in processing_status:
        return jsonify({"status": "error", "message": "Chatbot ID not found"}), 404
    
    status_info = processing_status[chatbot_id]
    
    # If already marked as completed, return success
    if status_info["completed"]:
        return jsonify({"status": "complete"})
    
    # Check Pinecone status
    is_complete = check_pinecone_status(
        status_info["namespace"]
    )
    
    # If complete, update status
    if is_complete:
        status_info["completed"] = True
        processing_time = time.time() - status_info["start_time"]
        print(f"Processing completed for {chatbot_id} in {processing_time:.2f} seconds")
        return jsonify({"status": "complete"})
    
    # If still processing, return in-progress status
    elapsed_time = time.time() - status_info["start_time"]
    return jsonify({
        "status": "processing", 
        "elapsed_seconds": int(elapsed_time)
    })

# Initialize chat handlers dictionary
chat_handlers = {}

@app.route('/')
def root():
    """Redirect from root to chat-manual page"""
    return redirect(url_for('manual_entry'))

@app.route('/embed-chat', methods=['POST'])
def embed_chat():
    """Handle chat requests from the embedded chatbot"""
    try:
        data = request.json
        print("Received chat request:", data)  # Debug log
        chatbot_id = data.get("chatbot_id")
        user_message = data.get("message")

        if not chatbot_id or not user_message:
            print(f"Missing fields - chatbot_id: {chatbot_id}, message: {user_message}")
            return jsonify({"error": "Missing chatbot_id or message"}), 400

        # Get namespace from the database
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
        print(f"Found namespace: {namespace} for chatbot_id: {chatbot_id}")  # Debug log
        
        # Initialize chat handler if it doesn't exist
        if chatbot_id not in chat_handlers:
            chat_handlers[chatbot_id] = ChatPromptHandler(openai_client, pinecone_client)
            # Reset conversation to ensure system prompt is included
            chat_handlers[chatbot_id].reset_conversation()

        handler = chat_handlers[chatbot_id]
        messages = handler.format_messages(user_message, namespace=namespace)
        
        # Log the messages being sent to OpenAI for debugging
        print(f"Sending messages to OpenAI: {messages}")
        
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
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route('/embed-reset-chat', methods=['POST'])
def reset_chat():
    """Reset the chat history for a chatbot"""
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))  # Different port from main app
    app.run(host='0.0.0.0', port=port, debug=True)
