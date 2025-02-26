from flask import Flask, render_template_string, request, jsonify
import sqlite3
from datetime import datetime
from openai import OpenAI
from pinecone import Pinecone
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pinecone_client = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# Constants
PINECONE_INDEX = "all-companies"

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
            const response = await fetch(`/record/${id}`);
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
                const response = await fetch(`/record/${id}`, {
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
                const response = await fetch(`/update_pinecone/${id}`, {
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
                    const response = await fetch(`/record/${id}`, {method: 'DELETE'});
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

def get_db():
    conn = sqlite3.connect('easyafchat.db')
    conn.row_factory = sqlite3.Row
    return conn

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
        vectors = [
            (f"{namespace}-{i}", embedding, {"text": chunk})
            for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings))
        ]
        index.upsert(vectors=vectors, namespace=namespace)
        return True
    except Exception as e:
        print(f"Error updating Pinecone: {e}")
        return False

@app.route('/')
def index():
    conn = get_db()
    records = conn.execute('SELECT * FROM companies').fetchall()
    return render_template_string(HTML, records=records)

@app.route('/record/<id>', methods=['GET'])
def get_record(id):
    conn = get_db()
    record = conn.execute('SELECT * FROM companies WHERE chatbot_id = ?', [id]).fetchone()
    return jsonify({
        'home_text': record['home_text'],
        'about_text': record['about_text'],
        'processed_content': record['processed_content']
    })

@app.route('/record/<id>', methods=['PUT'])
def update_record(id):
    data = request.json
    conn = get_db()
    conn.execute('''
        UPDATE companies 
        SET home_text = ?, about_text = ?, processed_content = ?, updated_at = ?
        WHERE chatbot_id = ?
    ''', [
        data['home_text'],
        data['about_text'],
        data['processed_content'],
        datetime.utcnow(),
        id
    ])
    conn.commit()
    return jsonify({'success': True})

@app.route('/update_pinecone/<id>', methods=['POST'])
def update_pinecone(id):
    try:
        conn = get_db()
        record = conn.execute('SELECT processed_content, pinecone_namespace FROM companies WHERE chatbot_id = ?', [id]).fetchone()
        
        chunks = chunk_text(record['processed_content'])
        embeddings = get_embeddings(chunks)
        
        success = update_pinecone_index(record['pinecone_namespace'], chunks, embeddings)
        
        return jsonify({'success': success})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False}), 500

@app.route('/record/<id>', methods=['DELETE'])
def delete_record(id):
    conn = get_db()
    conn.execute('DELETE FROM companies WHERE chatbot_id = ?', [id])
    conn.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5001)