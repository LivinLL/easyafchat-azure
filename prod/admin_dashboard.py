from flask import Blueprint, render_template_string, request, jsonify
import os
from datetime import datetime

# Import connect_to_db from the database module
from database import connect_to_db

# Import shared OpenAI and Pinecone clients from the main app
# This will be filled in when the blueprint is registered
openai_client = None
pinecone_client = None
DB_PATH = None
PINECONE_INDEX = None

# Create Blueprint
admin_dashboard = Blueprint('admin_dashboard', __name__)

# HTML Template (unchanged from db_mgr.py)
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>EasyAFChat DB Manager</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/datatables@1.10.18/media/css/jquery.dataTables.min.css" rel="stylesheet">
    <style>
        .content-preview { max-height: 100px; overflow: hidden; }
        .modal-dialog { max-width: 80%; }
        .status-message { position: fixed; top: 20px; right: 20px; z-index: 1050; display: none; }
    </style>
</head>
<body>
    <div class="container mt-4">
        <h2>EasyAFChat Database Manager</h2>
        <div id="statusMessage" class="alert status-message"></div>
        <table id="records" class="table table-striped">
            <thead>
                <tr>
                    <th>Chatbot ID</th>
                    <th>URL</th>
                    <th>Namespace</th>
                    <th>Created At</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for record in records %}
                <tr>
                    <td>{{ record[0] }}</td>
                    <td>{{ record[1] }}</td>
                    <td>{{ record[4] }}</td>
                    <td>{{ record[5] }}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="viewRecord('{{ record[0] }}')">View/Edit</button>
                        <button class="btn btn-sm btn-success" onclick="updatePinecone('{{ record[0] }}', '{{ record[4] }}')">Update Pinecone</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteRecord('{{ record[0] }}')">Delete</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- Modal -->
    <div class="modal fade" id="recordModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Record Details</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="recordForm">
                        <input type="hidden" id="chatbotId">
                        <div class="mb-3">
                            <label class="form-label">Home Text</label>
                            <textarea class="form-control" id="homeText" rows="5"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">About Text</label>
                            <textarea class="form-control" id="aboutText" rows="5"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Processed Content</label>
                            <textarea class="form-control" id="processedContent" rows="5"></textarea>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" onclick="saveRecord()">Save changes</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/datatables@1.10.18/media/js/jquery.dataTables.min.js"></script>
    <script>
        $(document).ready(function() {
            $('#records').DataTable({
                order: [[3, 'desc']]
            });
        });

        const modal = new bootstrap.Modal(document.getElementById('recordModal'));

        function showStatus(message, type) {
            const status = document.getElementById('statusMessage');
            status.className = `alert alert-${type} status-message`;
            status.textContent = message;
            status.style.display = 'block';
            setTimeout(() => {
                status.style.display = 'none';
            }, 3000);
        }

        async function viewRecord(id) {
            const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/record/${id}`);
            const data = await response.json();
            document.getElementById('chatbotId').value = id;
            document.getElementById('homeText').value = data.home_text;
            document.getElementById('aboutText').value = data.about_text;
            document.getElementById('processedContent').value = data.processed_content;
            modal.show();
        }

        async function saveRecord() {
            const id = document.getElementById('chatbotId').value;
            const data = {
                home_text: document.getElementById('homeText').value,
                about_text: document.getElementById('aboutText').value,
                processed_content: document.getElementById('processedContent').value
            };

            try {
                const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/record/${id}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (response.ok) {
                    showStatus('Record updated successfully', 'success');
                    setTimeout(() => location.reload(), 1000);
                }
            } catch (error) {
                showStatus('Error updating record', 'danger');
            }
        }

        async function updatePinecone(id, namespace) {
            try {
                showStatus('Updating Pinecone...', 'info');
                const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/update_pinecone/${id}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({namespace: namespace})
                });
                
                if (response.ok) {
                    showStatus('Pinecone updated successfully', 'success');
                } else {
                    showStatus('Error updating Pinecone', 'danger');
                }
            } catch (error) {
                showStatus('Error updating Pinecone', 'danger');
            }
        }

        async function deleteRecord(id) {
            if (confirm('Are you sure you want to delete this record?')) {
                try {
                    const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/record/${id}`, {method: 'DELETE'});
                    if (response.ok) {
                        showStatus('Record deleted successfully', 'success');
                        setTimeout(() => location.reload(), 1000);
                    }
                } catch (error) {
                    showStatus('Error deleting record', 'danger');
                }
            }
        }
    </script>
</body>
</html>
'''

def chunk_text(text, chunk_size=500):
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
    embeddings = []
    for chunk in text_chunks:
        response = openai_client.embeddings.create(
            input=chunk,
            model="text-embedding-ada-002"
        )
        embeddings.append(response.data[0].embedding)
    return embeddings

def update_pinecone_index(namespace, text_chunks, embeddings):
    try:
        index = pinecone_client.Index(PINECONE_INDEX)
        
        # First, delete all vectors in the namespace
        index.delete(delete_all=True, namespace=namespace)
        
        vectors = [
            (f"{namespace}-{i}", embedding, {"text": chunk})
            for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings))
        ]
        index.upsert(vectors=vectors, namespace=namespace)
        return True
    except Exception as e:
        print(f"Error updating Pinecone: {e}")
        return False

@admin_dashboard.route('/')
def index():
    with connect_to_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM companies')
        records = cursor.fetchall()
    return render_template_string(HTML, records=records)

@admin_dashboard.route('/record/<id>', methods=['GET'])
def get_record(id):
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('SELECT * FROM companies WHERE chatbot_id = %s', (id,))
        else:
            cursor.execute('SELECT * FROM companies WHERE chatbot_id = ?', (id,))
            
        record = cursor.fetchone()
        
    # For PostgreSQL compatibility, access by index instead of by name
    return jsonify({
        'home_text': record[7] if record else '',  # home_text is 8th column (index 7)
        'about_text': record[8] if record else '',  # about_text is 9th column (index 8)
        'processed_content': record[9] if record else ''  # processed_content is 10th column (index 9)
    })

@admin_dashboard.route('/record/<id>', methods=['PUT'])
def update_record(id):
    data = request.json
    now = datetime.utcnow()
    
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                UPDATE companies 
                SET home_text = %s, about_text = %s, processed_content = %s, updated_at = %s
                WHERE chatbot_id = %s
            ''', (
                data['home_text'],
                data['about_text'],
                data['processed_content'],
                now,
                id
            ))
        else:
            cursor.execute('''
                UPDATE companies 
                SET home_text = ?, about_text = ?, processed_content = ?, updated_at = ?
                WHERE chatbot_id = ?
            ''', (
                data['home_text'],
                data['about_text'],
                data['processed_content'],
                now,
                id
            ))
    
    return jsonify({'success': True})

@admin_dashboard.route('/update_pinecone/<id>', methods=['POST'])
def update_pinecone(id):
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT processed_content, pinecone_namespace FROM companies WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('SELECT processed_content, pinecone_namespace FROM companies WHERE chatbot_id = ?', (id,))
                
            record = cursor.fetchone()
            
            # Access by index for PostgreSQL compatibility
            processed_content = record[0] if record else ''
            pinecone_namespace = record[1] if record else ''
        
        chunks = chunk_text(processed_content)
        embeddings = get_embeddings(chunks)
        
        success = update_pinecone_index(pinecone_namespace, chunks, embeddings)
        
        return jsonify({'success': success})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False}), 500

@admin_dashboard.route('/record/<id>', methods=['DELETE'])
def delete_record(id):
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('DELETE FROM companies WHERE chatbot_id = %s', (id,))
        else:
            cursor.execute('DELETE FROM companies WHERE chatbot_id = ?', (id,))
    
    return jsonify({'success': True})

# This function initializes the blueprint with the OpenAI and Pinecone clients
def init_admin_dashboard(app_openai_client, app_pinecone_client, app_db_path, app_pinecone_index):
    global openai_client, pinecone_client, DB_PATH, PINECONE_INDEX
    openai_client = app_openai_client
    pinecone_client = app_pinecone_client
    DB_PATH = app_db_path
    PINECONE_INDEX = app_pinecone_index