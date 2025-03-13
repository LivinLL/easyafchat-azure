from flask import Blueprint, render_template_string, request, jsonify, Response, render_template
import os
from datetime import datetime
import csv
import io
import uuid

# Import connect_to_db from the database module
from database import connect_to_db

# Import document handler
from documents_handler import DocumentsHandler

# Import shared OpenAI and Pinecone clients from the main app
# This will be filled in when the blueprint is registered
openai_client = None
pinecone_client = None
DB_PATH = None
PINECONE_INDEX = None
document_handler = None

# Create Blueprint
admin_dashboard = Blueprint('admin_dashboard', __name__)

# HTML Template (updated with tabs and leads management)
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
        .nav-tabs { margin-bottom: 20px; }
        .badge { font-size: 85%; }
        .action-buttons { white-space: nowrap; }
        .filter-row { margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container mt-4">
        <h2>EasyAFChat Management Dashboard</h2>
        <div id="statusMessage" class="alert status-message"></div>
        
        <!-- Nav tabs -->
        <ul class="nav nav-tabs" id="dashboardTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="companies-tab" data-bs-toggle="tab" data-bs-target="#companies" type="button">Companies</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="leads-tab" data-bs-toggle="tab" data-bs-target="#leads" type="button">Leads</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="users-tab" data-bs-toggle="tab" data-bs-target="#users" type="button">Users</button>
            </li>
            <li class="nav-item" role="presentation">
                <a class="nav-link" href="/documents">Documents</a>
            </li>
            <li class="nav-item ms-auto">
                <button class="nav-link btn btn-warning" id="clearSessionBtn" type="button">
                    <i class="bi bi-x-circle"></i> Clear All Sessions
                </button>
            </li>
        </ul>

        <!-- Tab content -->
        <div class="tab-content">
            <!-- Companies Tab -->
            <div class="tab-pane fade show active" id="companies" role="tabpanel">
                <table id="companiesTable" class="table table-striped">
                    <thead>
                        <tr>
                            <th>Chatbot ID</th>
                            <th>URL</th>
                            <th>Namespace</th>
                            <th>Created At</th>
                            <th>Actions</th>
                            <th>Nuclear Option</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for record in records %}
                        <tr>
                            <td>{{ record[0] }}</td>
                            <td>{{ record[1] }}</td>
                            <td>{{ record[4] }}</td>
                            <td>{{ record[5] }}</td>
                            <td class="action-buttons">
                                <button class="btn btn-sm btn-primary" onclick="viewRecord('{{ record[0] }}')">View/Edit</button>
                                <button class="btn btn-sm btn-success" onclick="updatePinecone('{{ record[0] }}', '{{ record[4] }}')">Update Pinecone</button>
                                <button class="btn btn-sm btn-danger" onclick="deleteRecord('{{ record[0] }}')">Delete</button>
                            </td>
                            <td>
                                <button class="btn btn-sm btn-danger" style="background-color: #dc3545; border-color: #dc3545;" onclick="nuclearReset('{{ record[0] }}', '{{ record[1] }}')">
                                    ☢️ Nuclear Reset
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <!-- Leads Tab -->
            <div class="tab-pane fade" id="leads" role="tabpanel">
                <div class="row filter-row">
                    <div class="col-md-4">
                        <select id="companyFilter" class="form-select">
                            <option value="">All Companies</option>
                            {% for record in records %}
                            <option value="{{ record[0] }}">{{ record[1] }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-md-3">
                        <select id="statusFilter" class="form-select">
                            <option value="">All Statuses</option>
                            <option value="new">New</option>
                            <option value="contacted">Contacted</option>
                            <option value="qualified">Qualified</option>
                            <option value="converted">Converted</option>
                            <option value="closed">Closed</option>
                        </select>
                    </div>
                    <div class="col-md-5 text-end">
                        <button id="exportLeadsBtn" class="btn btn-success">
                            <i class="bi bi-download"></i> Export to CSV
                        </button>
                        <button id="refreshLeadsBtn" class="btn btn-primary">
                            <i class="bi bi-arrow-clockwise"></i> Refresh
                        </button>
                    </div>
                </div>
                
                <table id="leadsTable" class="table table-striped">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Company</th>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Phone</th>
                            <th>Date</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Leads will be loaded dynamically -->
                    </tbody>
                </table>
            </div>
            
            <!-- Users Tab -->
            <div class="tab-pane fade" id="users" role="tabpanel">
                <table id="usersTable" class="table table-striped">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Email</th>
                            <th>First Name</th>
                            <th>Last Name</th>
                            <th>Company</th>
                            <th>Created At</th>
                            <th>Last Login</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Users will be loaded dynamically -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Company Modal -->
    <div class="modal fade" id="recordModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Company Record Details</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="recordForm">
                        <input type="hidden" id="chatbotId">
                        <div class="mb-3">
                            <label class="form-label">Scraped Text</label>
                            <textarea class="form-control" id="scrapedText" rows="10"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Processed Content</label>
                            <textarea class="form-control" id="processedContent" rows="10"></textarea>
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

    <!-- Lead Modal -->
    <div class="modal fade" id="leadModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Lead Details</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="leadForm">
                        <input type="hidden" id="leadId">
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <label class="form-label">Name</label>
                                <input type="text" class="form-control" id="leadName" readonly>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Company</label>
                                <input type="text" class="form-control" id="leadCompany" readonly>
                            </div>
                        </div>
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <label class="form-label">Email</label>
                                <input type="email" class="form-control" id="leadEmail" readonly>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Phone</label>
                                <input type="tel" class="form-control" id="leadPhone" readonly>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Date Submitted</label>
                            <input type="text" class="form-control" id="leadDate" readonly>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Initial Question</label>
                            <textarea class="form-control" id="leadQuestion" rows="3" readonly></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Status</label>
                            <select class="form-select" id="leadStatus">
                                <option value="new">New</option>
                                <option value="contacted">Contacted</option>
                                <option value="qualified">Qualified</option>
                                <option value="converted">Converted</option>
                                <option value="closed">Closed</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Notes</label>
                            <textarea class="form-control" id="leadNotes" rows="4"></textarea>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" onclick="saveLead()">Save changes</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/datatables@1.10.18/media/js/jquery.dataTables.min.js"></script>
    <script>
        // Initialize DataTables and modals
        let companiesTable, leadsTable, usersTable;
        let companyUrlMap = {};

        $(document).ready(function() {
            // Initialize DataTables
            companiesTable = $('#companiesTable').DataTable({
                order: [[3, 'desc']]
            });
            
            leadsTable = $('#leadsTable').DataTable({
                order: [[5, 'desc']]
            });
            
            // Initialize Users DataTable
            usersTable = $('#usersTable').DataTable({
                order: [[5, 'desc']]
            });
            
            // Load users data
            loadUsers();
            
            // Create company-url mapping
            {% for record in records %}
            companyUrlMap['{{ record[0] }}'] = '{{ record[1] }}';
            {% endfor %}
            
            // Initial load of leads
            loadLeads();
            
            // Event listeners for filters
            $('#companyFilter, #statusFilter').change(function() {
                loadLeads();
            });
            
            // Refresh button
            $('#refreshLeadsBtn').click(function() {
                loadLeads();
            });
            
            // Export button
            $('#exportLeadsBtn').click(function() {
                exportLeads();
            });
            
            // Tab change event - reload leads when tab becomes active
            $('button[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {
                if (e.target.id === 'leads-tab') {
                    loadLeads();
                }
                if (e.target.id === 'users-tab') {
                    loadUsers();
                }
            });
        });

        // Modals
        const recordModal = new bootstrap.Modal(document.getElementById('recordModal'));
        const leadModal = new bootstrap.Modal(document.getElementById('leadModal'));

        function showStatus(message, type) {
            const status = document.getElementById('statusMessage');
            status.className = `alert alert-${type} status-message`;
            status.textContent = message;
            status.style.display = 'block';
            setTimeout(() => {
                status.style.display = 'none';
            }, 3000);
        }

        // Company functions
        async function viewRecord(id) {
            const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/record/${id}`);
            const data = await response.json();
            document.getElementById('chatbotId').value = id;
            document.getElementById('scrapedText').value = data.scraped_text;
            document.getElementById('processedContent').value = data.processed_content;
            recordModal.show();
        }

        async function saveRecord() {
            const id = document.getElementById('chatbotId').value;
            const data = {
                scraped_text: document.getElementById('scrapedText').value,
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

        // Leads functions
        async function loadLeads() {
            try {
                // Get filter values
                const company = $('#companyFilter').val();
                const status = $('#statusFilter').val();
                
                // Build URL with filters
                let url = '/admin-dashboard-08x7z9y2-yoursecretword/leads';
                if (company || status) {
                    url += '?';
                    if (company) url += `chatbot_id=${company}`;
                    if (company && status) url += '&';
                    if (status) url += `status=${status}`;
                }
                
                const response = await fetch(url);
                const data = await response.json();
                
                // Clear table
                leadsTable.clear();
                
                // Add data
                data.leads.forEach(lead => {
                    const companyUrl = companyUrlMap[lead.chatbot_id] || 'Unknown';
                    
                    // Format date
                    let leadDate = lead.created_at;
                    if (leadDate && leadDate.indexOf('T') > 0) {
                        leadDate = leadDate.replace('T', ' ').substring(0, 19);
                    }
                    
                    // Get badge class based on status
                    let statusClass = 'bg-secondary';
                    if (lead.status === 'new') statusClass = 'bg-primary';
                    if (lead.status === 'contacted') statusClass = 'bg-info';
                    if (lead.status === 'qualified') statusClass = 'bg-warning';
                    if (lead.status === 'converted') statusClass = 'bg-success';
                    if (lead.status === 'closed') statusClass = 'bg-dark';
                    
                    // Add row
                    leadsTable.row.add([
                        lead.lead_id,
                        companyUrl,
                        lead.name || '-',
                        lead.email || '-',
                        lead.phone || '-',
                        leadDate,
                        `<span class="badge ${statusClass}">${lead.status || 'unknown'}</span>`,
                        `<button class="btn btn-sm btn-primary" onclick="viewLead(${lead.lead_id})">View/Edit</button>`
                    ]);
                });
                
                leadsTable.draw();
                showStatus(`Loaded ${data.leads.length} leads`, 'info');
            } catch (error) {
                console.error('Error loading leads:', error);
                showStatus('Error loading leads', 'danger');
            }
        }

        // Load users data
        async function loadUsers() {
            try {
                const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/users');
                const data = await response.json();
                
                // Clear table
                usersTable.clear();
                
                // Add data
                data.users.forEach(user => {
                    // Format dates
                    let createdAt = user.created_at;
                    if (createdAt && createdAt.indexOf('T') > 0) {
                        createdAt = createdAt.replace('T', ' ').substring(0, 19);
                    }
                    
                    let lastLogin = user.last_login;
                    if (lastLogin && lastLogin.indexOf('T') > 0) {
                        lastLogin = lastLogin.replace('T', ' ').substring(0, 19);
                    }
                    
                    // Add row
                    usersTable.row.add([
                        user.user_id,
                        user.email,
                        user.first_name || '-',
                        user.last_name || '-',
                        user.company_name || '-',
                        createdAt,
                        lastLogin || '-'
                    ]);
                });
                
                usersTable.draw();
                showStatus(`Loaded ${data.users.length} users`, 'info');
            } catch (error) {
                console.error('Error loading users:', error);
                showStatus('Error loading users', 'danger');
            }
        }

        async function viewLead(id) {
            try {
                const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/lead/${id}`);
                const lead = await response.json();
                
                document.getElementById('leadId').value = lead.lead_id;
                document.getElementById('leadName').value = lead.name || '';
                document.getElementById('leadCompany').value = companyUrlMap[lead.chatbot_id] || '';
                document.getElementById('leadEmail').value = lead.email || '';
                document.getElementById('leadPhone').value = lead.phone || '';
                document.getElementById('leadDate').value = lead.created_at || '';
                document.getElementById('leadQuestion').value = lead.initial_question || '';
                document.getElementById('leadStatus').value = lead.status || 'new';
                document.getElementById('leadNotes').value = lead.notes || '';
                
                leadModal.show();
            } catch (error) {
                console.error('Error loading lead:', error);
                showStatus('Error loading lead', 'danger');
            }
        }

        async function saveLead() {
            const id = document.getElementById('leadId').value;
            const data = {
                status: document.getElementById('leadStatus').value,
                notes: document.getElementById('leadNotes').value
            };

            try {
                const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/lead/${id}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    showStatus('Lead updated successfully', 'success');
                    leadModal.hide();
                    loadLeads();
                } else {
                    showStatus('Error updating lead', 'danger');
                }
            } catch (error) {
                console.error('Error saving lead:', error);
                showStatus('Error updating lead', 'danger');
            }
        }

        async function exportLeads() {
            try {
                // Get filter values
                const company = $('#companyFilter').val();
                const status = $('#statusFilter').val();
                
                // Build URL with filters
                let url = '/admin-dashboard-08x7z9y2-yoursecretword/leads/export';
                if (company || status) {
                    url += '?';
                    if (company) url += `chatbot_id=${company}`;
                    if (company && status) url += '&';
                    if (status) url += `status=${status}`;
                }
                
                // Trigger download
                window.location.href = url;
                showStatus('Downloading leads...', 'info');
            } catch (error) {
                console.error('Error exporting leads:', error);
                showStatus('Error exporting leads', 'danger');
            }
        }

        async function nuclearReset(id, url) {
            if (confirm(`⚠️ DANGER! This will completely remove chatbot "${url}" from ALL systems.\n\nThis includes removing:\n- The chatbot and all its data\n- All documents associated with it\n- All leads generated from it\n- The user account if they only own this chatbot\n- All vectors from Pinecone\n\nThis action CANNOT be undone. Are you ABSOLUTELY sure?`)) {
                // Double confirm
                if (confirm("Last chance: Click OK to permanently DELETE this chatbot from all systems.")) {
                    try {
                        showStatus('Nuclear reset in progress...', 'warning');
                        
                        const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/nuclear-reset/${id}`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'}
                        });
                        
                        const result = await response.json();
                        
                        if (result.success) {
                            showStatus('Nuclear reset completed successfully! All traces of the chatbot have been removed.', 'success');
                            // Reload the page after a delay
                            setTimeout(() => location.reload(), 2000);
                        } else {
                            showStatus(`Error during nuclear reset: ${result.error}`, 'danger');
                        }
                    } catch (error) {
                        console.error('Error:', error);
                        showStatus('Failed to perform nuclear reset', 'danger');
                    }
                }
            }
        }

        // Clear all sessions
        document.getElementById('clearSessionBtn').addEventListener('click', async function() {
            if (confirm('This will clear ALL active sessions for ALL users. Users will need to log in again. Continue?')) {
                try {
                    showStatus('Clearing all sessions...', 'warning');
                    
                    const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/clear-sessions', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        showStatus('All sessions cleared successfully!', 'success');
                    } else {
                        showStatus(`Error clearing sessions: ${result.error}`, 'danger');
                    }
                } catch (error) {
                    console.error('Error:', error);
                    showStatus('Failed to clear sessions', 'danger');
                }
            }
        });
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
        'scraped_text': record[7] if record else '',  # scraped_text is 8th column (index 7)
        'processed_content': record[8] if record else ''  # processed_content is 9th column (index 8)
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
                SET scraped_text = %s, processed_content = %s, updated_at = %s
                WHERE chatbot_id = %s
            ''', (
                data['scraped_text'],
                data['processed_content'],
                now,
                id
            ))
        else:
            cursor.execute('''
                UPDATE companies 
                SET scraped_text = ?, processed_content = ?, updated_at = ?
                WHERE chatbot_id = ?
            ''', (
                data['scraped_text'],
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
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # First, check if this company has any documents
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # Delete all documents for this company
                cursor.execute('DELETE FROM documents WHERE chatbot_id = %s', (id,))
                
                # Delete all leads for this company
                cursor.execute('DELETE FROM leads WHERE chatbot_id = %s', (id,))
                
                # Delete the chatbot config if it exists
                cursor.execute('DELETE FROM chatbot_config WHERE chatbot_id = %s', (id,))
                
                # Finally delete the company record
                cursor.execute('DELETE FROM companies WHERE chatbot_id = %s', (id,))
            else:
                # Delete all documents for this company
                cursor.execute('DELETE FROM documents WHERE chatbot_id = ?', (id,))
                
                # Delete all leads for this company
                cursor.execute('DELETE FROM leads WHERE chatbot_id = ?', (id,))
                
                # Delete the chatbot config if it exists
                cursor.execute('DELETE FROM chatbot_config WHERE chatbot_id = ?', (id,))
                
                # Finally delete the company record
                cursor.execute('DELETE FROM companies WHERE chatbot_id = ?', (id,))
        
        # Also delete any vectors in Pinecone
        try:
            with connect_to_db() as conn:
                cursor = conn.cursor()
                
                if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                    cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = %s', (id,))
                else:
                    cursor.execute('SELECT pinecone_namespace FROM companies WHERE chatbot_id = ?', (id,))
                    
                row = cursor.fetchone()
                
                # If we found the namespace, delete all vectors
                if row and row[0]:
                    namespace = row[0]
                    index = pinecone_client.Index(PINECONE_INDEX)
                    index.delete(delete_all=True, namespace=namespace)
        except Exception as e:
            print(f"Warning: Could not delete Pinecone vectors: {e}")
            # Continue with the deletion process even if Pinecone cleanup fails
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting record: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': True})

# New routes for leads management

@admin_dashboard.route('/leads', methods=['GET'])
def get_leads():
    try:
        # Get filter parameters
        chatbot_id = request.args.get('chatbot_id')
        status = request.args.get('status')
        
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Build query based on filters
            query = "SELECT * FROM leads"
            params = []
            
            # Add WHERE clause if filters are provided
            where_clauses = []
            
            if chatbot_id:
                where_clauses.append("chatbot_id = ?")
                params.append(chatbot_id)
                
            if status:
                where_clauses.append("status = ?")
                params.append(status)
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
                
            # Add order by
            query += " ORDER BY created_at DESC"
            
            # Adjust placeholders for PostgreSQL if needed
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                query = query.replace('?', '%s')
            
            cursor.execute(query, params)
            leads_data = cursor.fetchall()
            
            # Get column names for result mapping
            columns = [desc[0] for desc in cursor.description]
            
            # Convert to list of dictionaries
            leads = []
            for lead in leads_data:
                lead_dict = dict(zip(columns, lead))
                leads.append(lead_dict)
            
            return jsonify({'leads': leads})
            
    except Exception as e:
        print(f"Error fetching leads: {e}")
        return jsonify({'error': str(e)}), 500

@admin_dashboard.route('/lead/<id>', methods=['GET'])
def get_lead(id):
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT * FROM leads WHERE lead_id = %s', (id,))
            else:
                cursor.execute('SELECT * FROM leads WHERE lead_id = ?', (id,))
                
            lead_data = cursor.fetchone()
            
            if not lead_data:
                return jsonify({'error': 'Lead not found'}), 404
                
            # Get column names for result mapping
            columns = [desc[0] for desc in cursor.description]
            
            # Convert to dictionary
            lead = dict(zip(columns, lead_data))
            
            return jsonify(lead)
            
    except Exception as e:
        print(f"Error fetching lead: {e}")
        return jsonify({'error': str(e)}), 500

@admin_dashboard.route('/lead/<id>', methods=['PUT'])
def update_lead(id):
    try:
        data = request.json
        status = data.get('status')
        notes = data.get('notes')
        
        if not status:
            return jsonify({'error': 'Status is required'}), 400
            
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    UPDATE leads
                    SET status = %s, notes = %s
                    WHERE lead_id = %s
                ''', (status, notes, id))
            else:
                cursor.execute('''
                    UPDATE leads
                    SET status = ?, notes = ?
                    WHERE lead_id = ?
                ''', (status, notes, id))
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error updating lead: {e}")
        return jsonify({'error': str(e)}), 500

@admin_dashboard.route('/leads/export', methods=['GET'])
def export_leads():
    try:
        # Get filter parameters
        chatbot_id = request.args.get('chatbot_id')
        status = request.args.get('status')
        
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Build query based on filters
            query = """
                SELECT l.lead_id, c.company_url, l.name, l.email, l.phone, 
                       l.initial_question, l.created_at, l.status, l.notes 
                FROM leads l
                LEFT JOIN companies c ON l.chatbot_id = c.chatbot_id
            """
            
            params = []
            
            # Add WHERE clause if filters are provided
            where_clauses = []
            
            if chatbot_id:
                where_clauses.append("l.chatbot_id = ?")
                params.append(chatbot_id)
                
            if status:
                where_clauses.append("l.status = ?")
                params.append(status)
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
                
            # Add order by
            query += " ORDER BY l.created_at DESC"
            
            # Adjust placeholders for PostgreSQL if needed
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                query = query.replace('?', '%s')
            
            cursor.execute(query, params)
            leads_data = cursor.fetchall()
            
            # Prepare CSV file
            output = io.StringIO()
            csv_writer = csv.writer(output)
            
            # Write header row
            csv_writer.writerow(['ID', 'Company URL', 'Name', 'Email', 'Phone', 
                                'Initial Question', 'Date Created', 'Status', 'Notes'])
            
            # Write data rows
            for lead in leads_data:
                csv_writer.writerow(lead)
            
            # Create response with CSV file
            output.seek(0)
            filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}'
                }
            )
            
    except Exception as e:
        print(f"Error exporting leads: {e}")
        return jsonify({'error': str(e)}), 500
    
@admin_dashboard.route('/users', methods=['GET'])
def get_users():
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
            users_data = cursor.fetchall()
            
            # Get column names for result mapping
            columns = [desc[0] for desc in cursor.description]
            
            # Convert to list of dictionaries
            users = []
            for user in users_data:
                user_dict = dict(zip(columns, user))
                users.append(user_dict)
            
            return jsonify({'users': users})
            
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({'error': str(e)}), 500

@admin_dashboard.route('/clear-sessions', methods=['POST'])
def clear_sessions():
    """
    Clear all sessions by removing the flask_session directory contents.
    """
    try:
        import shutil
        import glob
        from flask import session
        
        # Clear the current session
        session.clear()
        
        # Path to flask_session directory
        session_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'flask_session')
        
        if os.path.exists(session_dir):
            # Get all files in the directory
            session_files = glob.glob(os.path.join(session_dir, '*'))
            
            # Delete each session file
            for file_path in session_files:
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
            
            return jsonify({'success': True, 'message': f'Cleared {len(session_files)} session files'})
        else:
            return jsonify({'success': True, 'message': 'No session directory found'})
            
    except Exception as e:
        print(f"Error clearing sessions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# This function initializes the blueprint with the OpenAI and Pinecone clients
def init_admin_dashboard(app_openai_client, app_pinecone_client, app_db_path, app_pinecone_index):
    global openai_client, pinecone_client, DB_PATH, PINECONE_INDEX, document_handler
    openai_client = app_openai_client
    pinecone_client = app_pinecone_client
    DB_PATH = app_db_path
    PINECONE_INDEX = app_pinecone_index
    
    # Initialize document handler
    document_handler = DocumentsHandler(
        openai_client=openai_client,
        pinecone_client=pinecone_client,
        pinecone_index=PINECONE_INDEX
    )

# Add this function to admin_dashboard.py

@admin_dashboard.route('/nuclear-reset/<id>', methods=['POST'])
def nuclear_reset(id):
    """
    Complete nuclear reset of a chatbot - removes all traces from all tables.
    """
    try:
        # Store company info for potential re-use
        company_url = None
        namespace = None
        
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # First get the company info before deleting
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT company_url, pinecone_namespace FROM companies WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('SELECT company_url, pinecone_namespace FROM companies WHERE chatbot_id = ?', (id,))
                
            company_info = cursor.fetchone()
            if company_info:
                company_url = company_info[0]
                namespace = company_info[1]
                
            # START TRANSACTION - important for consistency
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('BEGIN')
            
            # 1. Delete all documents for this chatbot
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM documents WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM documents WHERE chatbot_id = ?', (id,))
                
            # 2. Delete all leads for this chatbot
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM leads WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM leads WHERE chatbot_id = ?', (id,))
                
            # 3. Delete any chatbot configurations
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM chatbot_config WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM chatbot_config WHERE chatbot_id = ?', (id,))
            
            # 4. Find any users who ONLY have this chatbot
            # (if you want to keep users who have multiple chatbots, you can skip this part)
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # Find user_id for this chatbot
                cursor.execute('SELECT user_id FROM companies WHERE chatbot_id = %s', (id,))
                user_row = cursor.fetchone()
                
                if user_row and user_row[0]:  # If there's a user associated
                    user_id = user_row[0]
                    
                    # Check if this user has other chatbots
                    cursor.execute('SELECT COUNT(*) FROM companies WHERE user_id = %s AND chatbot_id != %s', 
                                 (user_id, id))
                    other_chatbots = cursor.fetchone()[0]
                    
                    if other_chatbots == 0:
                        # User only has this chatbot, so delete the user
                        cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
            else:
                # Do the same for SQLite
                cursor.execute('SELECT user_id FROM companies WHERE chatbot_id = ?', (id,))
                user_row = cursor.fetchone()
                
                if user_row and user_row[0]:  # If there's a user associated
                    user_id = user_row[0]
                    
                    # Check if this user has other chatbots
                    cursor.execute('SELECT COUNT(*) FROM companies WHERE user_id = ? AND chatbot_id != ?', 
                                 (user_id, id))
                    other_chatbots = cursor.fetchone()[0]
                    
                    if other_chatbots == 0:
                        # User only has this chatbot, so delete the user
                        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            
            # 5. Finally delete the company record
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM companies WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM companies WHERE chatbot_id = ?', (id,))
            
            # COMMIT TRANSACTION
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('COMMIT')
        
        # Also delete any vectors in Pinecone
        if namespace:
            try:
                index = pinecone_client.Index(PINECONE_INDEX)
                index.delete(delete_all=True, namespace=namespace)
                print(f"Deleted all vectors for namespace: {namespace}")
            except Exception as e:
                print(f"Warning: Could not delete Pinecone vectors: {e}")
                # Continue with the deletion process even if Pinecone cleanup fails
        
        # Return the response
        result = {
            'success': True, 
            'message': 'Chatbot completely removed from all systems',
            'company_url': company_url  # Return the URL in case the frontend wants to use it
        }
        return jsonify(result)
    
    except Exception as e:
        print(f"Error in nuclear reset: {e}")
        # Try to rollback if possible
        try:
            if conn and os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('ROLLBACK')
        except:
            pass
            
        return jsonify({
            'success': False, 
            'error': str(e)
        }), 500