from flask import Blueprint, render_template_string, request, jsonify, session
import os
from datetime import datetime
import uuid
import vector_cache

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

# HTML Template for Documents Management
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>EasyAFChat - Document Management</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/datatables@1.10.18/media/css/jquery.dataTables.min.css" rel="stylesheet">
    <style>
        .content-preview { max-height: 100px; overflow: hidden; text-overflow: ellipsis; }
        .status-message { position: fixed; top: 20px; right: 20px; z-index: 1050; display: none; }
        .action-buttons { white-space: nowrap; }
    </style>
</head>
<body>
    <div class="container mt-4">
        <h2>Document Management</h2>
        <div id="statusMessage" class="alert status-message"></div>
        
        <div class="row mb-3">
            <div class="col-md-6">
                <select id="companyFilter" class="form-select">
                    <option value="">All Companies</option>
                    {% for company in companies %}
                    <option value="{{ company.chatbot_id }}">{{ company.company_url }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-6 text-end">
                <button id="uploadDocumentBtn" class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#uploadDocumentModal">
                    <i class="bi bi-upload"></i> Upload Document
                </button>
            </div>
        </div>
        
        <table id="documentsTable" class="table table-striped">
            <thead>
                <tr>
                    <th>Document Name</th>
                    <th>Company</th>
                    <th>Type</th>
                    <th>Created At</th>
                    <th>Vectors</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for doc in documents %}
                <tr>
                    <td>{{ doc.doc_name }}</td>
                    <td>{{ doc.company_url or 'N/A' }}</td>
                    <td>{{ doc.doc_type }}</td>
                    <td>{{ doc.created_at }}</td>
                    <td>{{ doc.vectors_count }}</td>
                    <td class="action-buttons">
                        <button class="btn btn-sm btn-info" onclick="viewDocument('{{ doc.doc_id }}')">View</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteDocument('{{ doc.doc_id }}', '{{ doc.chatbot_id }}')">Delete</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- Upload Document Modal -->
    <div class="modal fade" id="uploadDocumentModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Upload Document</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="uploadDocumentForm">
                        <div class="mb-3">
                            <label class="form-label">Select Company</label>
                            <select id="uploadCompany" class="form-select" required>
                                <option value="">Choose Company</option>
                                {% for company in companies %}
                                <option value="{{ company.chatbot_id }}">{{ company.company_url }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Document File</label>
                            <input type="file" id="documentFile" class="form-control" required>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" onclick="uploadDocument()">Upload</button>
                </div>
            </div>
        </div>
    </div>

    <!-- View Document Modal -->
    <div class="modal fade" id="viewDocumentModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Document Details</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <strong>Document Name:</strong>
                            <p id="viewDocName"></p>
                        </div>
                        <div class="col-md-6">
                            <strong>Document Type:</strong>
                            <p id="viewDocType"></p>
                        </div>
                    </div>
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <strong>Created At:</strong>
                            <p id="viewDocCreatedAt"></p>
                        </div>
                        <div class="col-md-6">
                            <strong>Vectors Count:</strong>
                            <p id="viewDocVectorsCount"></p>
                        </div>
                    </div>
                    <div class="mb-3">
                        <strong>Content Preview:</strong>
                        <pre id="viewDocContent" class="border p-2" style="max-height: 400px; overflow-y: auto;"></pre>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/datatables@1.10.18/media/js/jquery.dataTables.min.js"></script>
    <script>
        let documentsTable;

        $(document).ready(function() {
            // Initialize DataTable
            documentsTable = $('#documentsTable').DataTable({
                order: [[3, 'desc']]
            });

            // Company filter
            $('#companyFilter').change(function() {
                const companyId = $(this).val();
                documentsTable.column(1).search(companyId ? companyId : '').draw();
            });
        });

        function showStatus(message, type) {
            const status = document.getElementById('statusMessage');
            status.className = `alert alert-${type} status-message`;
            status.textContent = message;
            status.style.display = 'block';
            setTimeout(() => {
                status.style.display = 'none';
            }, 3000);
        }

        function viewDocument(docId) {
            fetch(`/documents/document/${docId}`)
                .then(response => response.json())
                .then(doc => {
                    document.getElementById('viewDocName').textContent = doc.doc_name;
                    document.getElementById('viewDocType').textContent = doc.doc_type;
                    document.getElementById('viewDocCreatedAt').textContent = doc.created_at;
                    document.getElementById('viewDocVectorsCount').textContent = doc.vectors_count;
                    document.getElementById('viewDocContent').textContent = doc.content;
                    
                    new bootstrap.Modal(document.getElementById('viewDocumentModal')).show();
                })
                .catch(error => {
                    console.error('Error:', error);
                    showStatus('Error fetching document', 'danger');
                });
        }

        function deleteDocument(docId, chatbotId) {
            fetch(`/documents/document/${docId}`, {  // ✅ Corrected URL
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ chatbot_id: chatbotId })
            })
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => { throw new Error(text); });
                }
                return response.json();
            })
            .then(result => {
                if (result.success) {
                    showStatus('Document deleted successfully', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showStatus(`Error deleting document: ${result.error}`, 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showStatus(`Error deleting document: ${error.message}`, 'danger');
            });
        }



        function uploadDocument() {
            const company = document.getElementById('uploadCompany').value;
            const file = document.getElementById('documentFile').files[0];

            if (!company || !file) {
                showStatus('Please select a company and file', 'danger');
                return;
            }

            const formData = new FormData();
            formData.append('chatbot_id', company);
            formData.append('document', file);

            fetch('/documents/upload-document', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    showStatus('Document uploaded successfully', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showStatus('Error uploading document', 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showStatus('Error uploading document', 'danger');
            });
        }
    </script>
</body>
</html>
'''

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
                SELECT d.doc_id, d.chatbot_id, d.doc_name, d.doc_type, d.created_at, d.updated_at, 
                       d.vectors_count, LEFT(d.content, 1000) as content_preview, c.company_url
                FROM documents d
                LEFT JOIN companies c ON d.chatbot_id = c.chatbot_id
                ORDER BY d.created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT d.doc_id, d.chatbot_id, d.doc_name, d.doc_type, d.created_at, d.updated_at, 
                       d.vectors_count, substr(d.content, 1, 1000) as content_preview, c.company_url
                FROM documents d
                LEFT JOIN companies c ON d.chatbot_id = c.chatbot_id
                ORDER BY d.created_at DESC
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
                'content': row[7],
                'company_url': row[8] if len(row) > 8 else None
            })
    
    return render_template_string(HTML, companies=companies, documents=documents)

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
    """Delete a document from the database and its vectors from Pinecone (if applicable)."""
    try:
        data = request.json
        chatbot_id = data.get('chatbot_id')

        if not chatbot_id:
            return jsonify({'error': 'Missing chatbot_id'}), 400

        namespace = None
        vectors_count = 0

        # Try to get the namespace if the company exists
        with connect_to_db() as conn:
            cursor = conn.cursor()
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = %s', (chatbot_id,))
            else:
                cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = ?', (chatbot_id,))

            row = cursor.fetchone()
            if row:
                namespace = row[0]  # Get the namespace if the company still exists

            # Get the number of vectors for this document
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT vectors_count FROM documents WHERE doc_id = %s', (doc_id,))
            else:
                cursor.execute('SELECT vectors_count FROM documents WHERE doc_id = ?', (doc_id,))

            vectors_row = cursor.fetchone()
            if vectors_row:
                vectors_count = vectors_row[0] or 0  # Default to 0 if None

        # If namespace exists, delete all Pinecone vectors for this document
        if namespace and vectors_count > 0:
            try:
                pinecone_index = pinecone_client.Index(PINECONE_INDEX)
                
                # Construct all vector IDs for deletion
                vector_ids = [f"{namespace}-{doc_id}-{i}" for i in range(vectors_count)]
                
                # Perform batch deletion
                pinecone_index.delete(ids=vector_ids, namespace=namespace)
                
                print(f"Deleted {vectors_count} vectors for doc_id {doc_id} in namespace {namespace}")

            except Exception as e:
                print(f"Warning: Pinecone deletion failed - {e}")

        # Delete the document from the database (always do this)
        with connect_to_db() as conn:
            cursor = conn.cursor()
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

@documents_blueprint.route('/user-documents', methods=['GET'])
def user_documents():
    """Get documents for the current user's chatbots"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
        
    user_id = session['user_id']
    
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Get all chatbots for this user
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT chatbot_id FROM companies WHERE user_id = %s', (user_id,))
            else:
                cursor.execute('SELECT chatbot_id FROM companies WHERE user_id = ?', (user_id,))
                
            user_chatbots = [row[0] for row in cursor.fetchall()]
            
            if not user_chatbots:
                return jsonify({'documents': []})
                
            # Format the list for SQL IN clause
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                chatbot_ids_str = ','.join([f"'{chatbot_id}'" for chatbot_id in user_chatbots])
                
                # Get all documents for these chatbots
                cursor.execute(f'''
                    SELECT d.doc_id, d.chatbot_id, d.doc_name, d.doc_type, d.created_at, d.updated_at, 
                           d.vectors_count, LEFT(d.content, 1000) as content_preview, c.company_url
                    FROM documents d
                    LEFT JOIN companies c ON d.chatbot_id = c.chatbot_id
                    WHERE d.chatbot_id IN ({chatbot_ids_str})
                    ORDER BY d.created_at DESC
                ''')
            else:
                # SQLite uses ? placeholders
                placeholders = ','.join(['?'] * len(user_chatbots))
                
                # Get all documents for these chatbots
                cursor.execute(f'''
                    SELECT d.doc_id, d.chatbot_id, d.doc_name, d.doc_type, d.created_at, d.updated_at, 
                           d.vectors_count, substr(d.content, 1, 1000) as content_preview, c.company_url
                    FROM documents d
                    LEFT JOIN companies c ON d.chatbot_id = c.chatbot_id
                    WHERE d.chatbot_id IN ({placeholders})
                    ORDER BY d.created_at DESC
                ''', user_chatbots)
                
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
                    'content': row[7],
                    'company_url': row[8] if len(row) > 8 else None
                })
                
            return jsonify({'documents': documents})
    except Exception as e:
        print(f"Error getting user documents: {e}")
        return jsonify({'error': str(e)}), 500

@documents_blueprint.route('/processing-status/<doc_id>', methods=['GET'])
def document_processing_status(doc_id):
    """Check if a document's processing is complete"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
        
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # First verify that this document belongs to one of the user's chatbots
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT d.vectors_count
                    FROM documents d
                    JOIN companies c ON d.chatbot_id = c.chatbot_id
                    WHERE d.doc_id = %s AND c.user_id = %s
                ''', (doc_id, session['user_id']))
            else:
                cursor.execute('''
                    SELECT d.vectors_count
                    FROM documents d
                    JOIN companies c ON d.chatbot_id = c.chatbot_id
                    WHERE d.doc_id = ? AND c.user_id = ?
                ''', (doc_id, session['user_id']))
                
            result = cursor.fetchone()
            
            if not result:
                return jsonify({'error': 'Document not found or access denied'}), 404
                
            # If vectors_count is > 0, processing is complete
            vectors_count = result[0] or 0
            
            return jsonify({
                'completed': vectors_count > 0,
                'vectors_count': vectors_count
            })
    except Exception as e:
        print(f"Error checking document processing status: {e}")
        return jsonify({'error': str(e)}), 500

@documents_blueprint.route('/retrain-agent/<chatbot_id>', methods=['POST'])
def retrain_agent(chatbot_id):
    """Retrain the agent for a specific chatbot by refreshing vectors"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
        
    try:
        # First, verify the user owns this chatbot
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT pinecone_namespace, processed_content
                    FROM companies
                    WHERE chatbot_id = %s AND user_id = %s
                ''', (chatbot_id, session['user_id']))
            else:
                cursor.execute('''
                    SELECT pinecone_namespace, processed_content
                    FROM companies
                    WHERE chatbot_id = ? AND user_id = ?
                ''', (chatbot_id, session['user_id']))
                
            company = cursor.fetchone()
            
            if not company:
                return jsonify({'error': 'Chatbot not found or access denied'}), 404
                
            namespace = company[0]
            processed_content = company[1]
            
            # Get all documents for this chatbot
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT doc_id, content
                    FROM documents
                    WHERE chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT doc_id, content
                    FROM documents
                    WHERE chatbot_id = ?
                ''', (chatbot_id,))
                
            documents = cursor.fetchall()
            
            # Combine all text content
            all_content = processed_content if processed_content else ""
            
            for doc in documents:
                if doc[1]:  # If document has content
                    all_content += "\n\n" + doc[1]
            
            # Check if there's any content to process
            if not all_content.strip():
                return jsonify({'error': 'No content available for retraining'}), 400
                
            # Chunk the content and create embeddings
            chunks = documents_handler.chunk_text(all_content)
            embeddings = documents_handler.get_embeddings(chunks)
            
            # Update Pinecone
            index = pinecone_client.Index(PINECONE_INDEX)
            
            # First delete all existing vectors
            try:
                index.delete(delete_all=True, namespace=namespace)
            except Exception as e:
                print(f"Warning: Error clearing vectors from namespace {namespace}: {e}")
            
            # Upload new vectors
            vectors = []
            
            # Add vectors for the main content
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                vectors.append((
                    f"{namespace}-{i}",
                    embedding,
                    {"text": chunk}
                ))
            
            # Upsert vectors in batches of 100
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i+batch_size]
                index.upsert(vectors=batch, namespace=namespace)
            
            return jsonify({'success': True, 'vectors_count': len(vectors)})
    except Exception as e:
        print(f"Error retraining agent: {e}")
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