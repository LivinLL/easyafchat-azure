from flask import Blueprint, render_template, request, jsonify
import os
from datetime import datetime
import uuid

# Import connect_to_db from the database module
from database import connect_to_db

# Import documents handler
from documents_handler import DocumentsHandler

# Import shared OpenAI and Pinecone clients from the main app
# This will be filled in when the blueprint is registered
openai_client = None
pinecone_client = None
PINECONE_INDEX = None
documents_handler = None

# Create Blueprint
documents_blueprint = Blueprint('documents', __name__)

@documents_blueprint.route('/')
def documents():
    """View and manage documents for all companies"""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        # Get all companies
        cursor.execute('SELECT chatbot_id, company_url FROM companies ORDER BY company_url')
        companies = [{'chatbot_id': row[0], 'company_url': row[1]} for row in cursor.fetchall()]
        
        # Get all documents
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                SELECT doc_id, chatbot_id, doc_name, doc_type, created_at, updated_at, 
                       vectors_count, LEFT(content, 1000) as content_preview
                FROM documents ORDER BY created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT doc_id, chatbot_id, doc_name, doc_type, created_at, updated_at, 
                       vectors_count, substr(content, 1, 1000) as content_preview
                FROM documents ORDER BY created_at DESC
            ''')
            
        documents = []
        for row in cursor.fetchall():
            documents.append({
                'doc_id': row[0],
                'chatbot_id': row[1],
                'doc_name': row[2],
                'doc_type': row[3],
                'created_at': row[4],
                'updated_at': row[5],
                'vectors_count': row[6],
                'content': row[7]
            })
    
    return render_template('admin_documents.html', companies=companies, documents=documents)

@documents_blueprint.route('/document/<doc_id>', methods=['GET'])
def get_document(doc_id):
    """Get a single document's content"""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('SELECT * FROM documents WHERE doc_id = %s', (doc_id,))
        else:
            cursor.execute('SELECT * FROM documents WHERE doc_id = ?', (doc_id,))
            
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': 'Document not found'}), 404
            
        # Get column names for result mapping
        columns = [desc[0] for desc in cursor.description]
        
        # Convert to dictionary
        document = dict(zip(columns, row))
        
        return jsonify(document)

@documents_blueprint.route('/document/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Delete a document and its vectors from Pinecone"""
    try:
        data = request.json
        chatbot_id = data.get('chatbot_id')
        
        if not chatbot_id:
            return jsonify({'error': 'Missing chatbot_id'}), 400
            
        # Get namespace for this company
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = %s', (chatbot_id,))
            else:
                cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = ?', (chatbot_id,))
                
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Company not found'}), 404
                
            namespace = row[0]
            
            # Delete vectors from Pinecone
            success = documents_handler.delete_document_vectors(namespace, doc_id)
            
            if not success:
                return jsonify({'error': 'Failed to delete vectors from Pinecone'}), 500
                
            # Delete document from database
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM documents WHERE doc_id = %s', (doc_id,))
            else:
                cursor.execute('DELETE FROM documents WHERE doc_id = ?', (doc_id,))
                
            return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting document: {e}")
        return jsonify({'error': str(e)}), 500

@documents_blueprint.route('/upload-document', methods=['POST'])
def upload_document():
    """Upload and process a new document"""
    try:
        # Get form data
        chatbot_id = request.form.get('chatbot_id')
        document_file = request.files.get('document')
        
        if not chatbot_id or not document_file:
            return jsonify({'error': 'Missing required fields'}), 400
            
        # Get namespace for this company
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = %s', (chatbot_id,))
            else:
                cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = ?', (chatbot_id,))
                
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Company not found'}), 404
                
            namespace = row[0]
            
            # Read file data
            file_data = document_file.read()
            filename = document_file.filename
            
            # Process document
            doc_result = documents_handler.process_document(
                file_data=file_data,
                filename=filename,
                chatbot_id=chatbot_id,
                namespace=namespace
            )
            
            # Save document to database
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    INSERT INTO documents
                    (doc_id, chatbot_id, doc_name, doc_type, created_at, updated_at, content, vectors_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    doc_result['doc_id'],
                    doc_result['chatbot_id'],
                    doc_result['doc_name'],
                    doc_result['doc_type'],
                    doc_result['created_at'],
                    doc_result['updated_at'],
                    doc_result['content'],
                    doc_result['vectors_count']
                ))
            else:
                cursor.execute('''
                    INSERT INTO documents
                    (doc_id, chatbot_id, doc_name, doc_type, created_at, updated_at, content, vectors_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    doc_result['doc_id'],
                    doc_result['chatbot_id'],
                    doc_result['doc_name'],
                    doc_result['doc_type'],
                    doc_result['created_at'],
                    doc_result['updated_at'],
                    doc_result['content'],
                    doc_result['vectors_count']
                ))
                
            return jsonify({'success': True, 'doc_id': doc_result['doc_id']})
    except Exception as e:
        print(f"Error uploading document: {e}")
        return jsonify({'error': str(e)}), 500

@documents_blueprint.route('/create-initial-document/<chatbot_id>', methods=['POST'])
def create_initial_document(chatbot_id):
    """Create initial document from website content"""
    try:
        # Get company data
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT pinecone_namespace, processed_content
                    FROM companies WHERE chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT pinecone_namespace, processed_content
                    FROM companies WHERE chatbot_id = ?
                ''', (chatbot_id,))
                
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Company not found'}), 404
                
            namespace = row[0]
            processed_content = row[1]
            
            # Check if initial document already exists
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT doc_id FROM documents 
                    WHERE chatbot_id = %s AND doc_type = 'scraped_content'
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT doc_id FROM documents 
                    WHERE chatbot_id = ? AND doc_type = 'scraped_content'
                ''', (chatbot_id,))
                
            if cursor.fetchone():
                return jsonify({'error': 'Initial document already exists'}), 400
            
            # Create document
            doc_result = documents_handler.create_initial_document_from_website(
                chatbot_id=chatbot_id,
                namespace=namespace,
                processed_content=processed_content
            )
            
            # Save document to database
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    INSERT INTO documents
                    (doc_id, chatbot_id, doc_name, doc_type, created_at, updated_at, content, vectors_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    doc_result['doc_id'],
                    doc_result['chatbot_id'],
                    doc_result['doc_name'],
                    doc_result['doc_type'],
                    doc_result['created_at'],
                    doc_result['updated_at'],
                    doc_result['content'],
                    doc_result['vectors_count']
                ))
            else:
                cursor.execute('''
                    INSERT INTO documents
                    (doc_id, chatbot_id, doc_name, doc_type, created_at, updated_at, content, vectors_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    doc_result['doc_id'],
                    doc_result['chatbot_id'],
                    doc_result['doc_name'],
                    doc_result['doc_type'],
                    doc_result['created_at'],
                    doc_result['updated_at'],
                    doc_result['content'],
                    doc_result['vectors_count']
                ))
                
            return jsonify({'success': True, 'doc_id': doc_result['doc_id']})
    except Exception as e:
        print(f"Error creating initial document: {e}")
        return jsonify({'error': str(e)}), 500

# This function initializes the blueprint with the OpenAI and Pinecone clients
def init_documents_blueprint(app_openai_client, app_pinecone_client, app_pinecone_index):
    global openai_client, pinecone_client, PINECONE_INDEX, documents_handler
    openai_client = app_openai_client
    pinecone_client = app_pinecone_client
    PINECONE_INDEX = app_pinecone_index
    
    # Initialize documents handler
    documents_handler = DocumentsHandler(
        openai_client=openai_client,
        pinecone_client=pinecone_client,
        pinecone_index=PINECONE_INDEX
    )