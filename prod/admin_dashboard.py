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
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="db-management-tab" data-bs-toggle="tab" data-bs-target="#db-management" type="button">DB Management</button>
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

            <!-- DB Management Tab -->
            <div class="tab-pane fade" id="db-management" role="tabpanel">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h5 class="mb-0">Database Management Tools</h5>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-info">
                            <strong>Current Database:</strong> {{ db_info.type }} {% if db_info.type == "PostgreSQL" %}({{ db_info.host }}/{{ db_info.name }}){% else %}({{ db_info.name }}){% endif %}
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6">
                                <div class="card mb-3">
                                    <div class="card-header bg-warning">
                                        <h5 class="mb-0">Companies Table Management</h5>
                                    </div>
                                    <div class="card-body">
                                        <p>This will clear all user associations from companies (set user_id to NULL).</p>
                                        <p><strong>Use case:</strong> When you need to "unclaim" all chatbots from users.</p>
                                        <button id="clearCompanyUsersBtn" class="btn btn-warning">
                                            <i class="bi bi-exclamation-triangle"></i> Clear All User IDs from Companies
                                        </button>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="col-md-6">
                                <div class="card mb-3">
                                    <div class="card-header bg-danger">
                                        <h5 class="mb-0">Users Table Management</h5>
                                    </div>
                                    <div class="card-body">
                                        <p>This will <strong>DROP and RECREATE</strong> the users table with the correct schema.</p>
                                        <p><strong>Warning:</strong> This will delete all user accounts! Only use when fixing database schema issues.</p>
                                        <button id="cleanUsersTableBtn" class="btn btn-danger">
                                            <i class="bi bi-exclamation-octagon"></i> Rebuild Users Table (DANGER!)
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card mt-3">
                            <div class="card-header bg-secondary text-white">
                                <h5 class="mb-0">Operation Results</h5>
                            </div>
                            <div class="card-body">
                                <div id="dbOperationResults" class="alert d-none">
                                    <!-- Results will be displayed here -->
                                </div>
                                <div id="chatbotsContainer" class="mt-3 d-none">
                                    <h6>Affected Chatbots:</h6>
                                    <div class="table-responsive">
                                        <table class="table table-sm table-hover">
                                            <thead>
                                                <tr>
                                                    <th>Chatbot ID</th>
                                                    <th>URL</th>
                                                </tr>
                                            </thead>
                                            <tbody id="chatbotsList">
                                                <!-- Chatbots will be listed here -->
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="row mt-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-info text-white">
                            <h5 class="mb-0">Database Structure Inspector</h5>
                        </div>
                        <div class="card-body">
                            <p>This will generate a detailed report of your database structure, including tables, schemas, foreign keys, and sample data.</p>
                            <button id="inspectDatabaseBtn" class="btn btn-info">
                                <i class="bi bi-database-check"></i> Inspect Database Structure
                            </button>
                            
                            <div id="databaseReportContainer" class="mt-3 d-none">
                                <div class="card">
                                    <div class="card-header bg-light">
                                        <h6 class="mb-0">Database Inspection Report</h6>
                                    </div>
                                    <div class="card-body p-0">
                                        <pre id="databaseReport" class="p-3 bg-light" style="max-height: 600px; overflow-y: auto; font-size: 12px; font-family: monospace; white-space: pre-wrap;"></pre>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
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

        // DB Management tab functionality
        document.getElementById('clearCompanyUsersBtn').addEventListener('click', async function() {
            if (confirm('This will clear all user associations from companies. Users will need to reclaim their chatbots. Continue?')) {
                try {
                    const resultsDiv = document.getElementById('dbOperationResults');
                    const chatbotsContainer = document.getElementById('chatbotsContainer');
                    const chatbotsList = document.getElementById('chatbotsList');
                    
                    resultsDiv.className = 'alert alert-info';
                    resultsDiv.innerHTML = 'Processing request...';
                    resultsDiv.classList.remove('d-none');
                    chatbotsContainer.classList.add('d-none');
                    
                    const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/clear-company-users', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        resultsDiv.className = 'alert alert-success';
                        resultsDiv.innerHTML = `<strong>Success!</strong> ${result.message}`;
                        
                        // Display affected chatbots if available
                        if (result.chatbots && result.chatbots.length > 0) {
                            chatbotsList.innerHTML = '';
                            result.chatbots.forEach(chatbot => {
                                chatbotsList.innerHTML += `
                                    <tr>
                                        <td>${chatbot.id}</td>
                                        <td>${chatbot.url}</td>
                                    </tr>
                                `;
                            });
                            chatbotsContainer.classList.remove('d-none');
                        }
                    } else {
                        resultsDiv.className = 'alert alert-danger';
                        resultsDiv.innerHTML = `<strong>Error!</strong> ${result.message}`;
                    }
                } catch (error) {
                    console.error('Error:', error);
                    const resultsDiv = document.getElementById('dbOperationResults');
                    resultsDiv.className = 'alert alert-danger';
                    resultsDiv.innerHTML = `<strong>Error!</strong> Failed to execute operation: ${error.message}`;
                    resultsDiv.classList.remove('d-none');
                }
            }
        });

        document.getElementById('cleanUsersTableBtn').addEventListener('click', async function() {
            if (confirm('WARNING! This will DELETE ALL USER ACCOUNTS and recreate the users table! This cannot be undone. Are you ABSOLUTELY sure?')) {
                if (confirm('FINAL WARNING: All user data will be lost. Type "CONFIRM" in the next prompt to proceed.')) {
                    const confirmation = prompt('Type "CONFIRM" to proceed with deleting all users:');
                    
                    if (confirmation === 'CONFIRM') {
                        try {
                            const resultsDiv = document.getElementById('dbOperationResults');
                            
                            resultsDiv.className = 'alert alert-info';
                            resultsDiv.innerHTML = 'Rebuilding users table... This may take a moment.';
                            resultsDiv.classList.remove('d-none');
                            
                            const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/clean-users-table', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'}
                            });
                            
                            const result = await response.json();
                            
                            if (result.success) {
                                resultsDiv.className = 'alert alert-success';
                                resultsDiv.innerHTML = `<strong>Success!</strong> ${result.message}`;
                            } else {
                                resultsDiv.className = 'alert alert-danger';
                                resultsDiv.innerHTML = `<strong>Error!</strong> ${result.message}`;
                            }
                        } catch (error) {
                            console.error('Error:', error);
                            const resultsDiv = document.getElementById('dbOperationResults');
                            resultsDiv.className = 'alert alert-danger';
                            resultsDiv.innerHTML = `<strong>Error!</strong> Failed to execute operation: ${error.message}`;
                            resultsDiv.classList.remove('d-none');
                        }
                    } else {
                        alert('Operation cancelled.');
                    }
                }
            }
        });

        document.getElementById('inspectDatabaseBtn').addEventListener('click', async function() {
            try {
                const reportContainer = document.getElementById('databaseReportContainer');
                const reportElement = document.getElementById('databaseReport');
                const inspectBtn = document.getElementById('inspectDatabaseBtn');
                
                // Show loading state
                inspectBtn.disabled = true;
                inspectBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Inspecting Database...';
                reportElement.textContent = 'Generating report, please wait...';
                reportContainer.classList.remove('d-none');
                
                const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/inspect-database', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });
                
                const result = await response.json();
                
                if (result.success) {
                    reportElement.textContent = result.report;
                } else {
                    reportElement.textContent = `Error generating report: ${result.message}`;
                }
            } catch (error) {
                console.error('Error:', error);
                const reportContainer = document.getElementById('databaseReportContainer');
                const reportElement = document.getElementById('databaseReport');
                
                reportContainer.classList.remove('d-none');
                reportElement.textContent = `Error: Failed to inspect database: ${error.message}`;
            } finally {
                // Reset button state
                const inspectBtn = document.getElementById('inspectDatabaseBtn');
                inspectBtn.disabled = false;
                inspectBtn.innerHTML = '<i class="bi bi-database-check"></i> Inspect Database Structure';
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

def clear_user_id_from_companies():
    """Clear all user_id values in the companies table."""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # First check how many records will be affected
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute("SELECT COUNT(*) FROM companies WHERE user_id IS NOT NULL")
            else:
                cursor.execute("SELECT COUNT(*) FROM companies WHERE user_id IS NOT NULL")
                
            count = cursor.fetchone()[0]
            
            # Now update all records
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute("UPDATE companies SET user_id = NULL")
            else:
                cursor.execute("UPDATE companies SET user_id = NULL")
                
            # Also get all chatbots for log
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute("SELECT chatbot_id, company_url FROM companies")
            else:
                cursor.execute("SELECT chatbot_id, company_url FROM companies")
                
            chatbots = cursor.fetchall()
            
            return {
                'success': True,
                'message': f"Cleared user_id from {count} companies",
                'chatbots': [{'id': c[0], 'url': c[1]} for c in chatbots]
            }
    
    except Exception as e:
        print(f"Error clearing user IDs: {e}")
        return {
            'success': False,
            'message': f"Error: {str(e)}"
        }

def clean_users_table():
    """Clean up the users table and recreate it with the correct schema."""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # PostgreSQL cleanup
                try:
                    # First, check the data type of user_id in the companies table
                    cursor.execute("""
                        SELECT data_type 
                        FROM information_schema.columns 
                        WHERE table_schema = %s 
                        AND table_name = 'companies' 
                        AND column_name = 'user_id'
                    """, (os.getenv('DB_SCHEMA', 'easychat'),))
                    
                    company_user_id_type = cursor.fetchone()
                    user_id_type = "TEXT"  # Default type for new users table
                    
                    if company_user_id_type and company_user_id_type[0].upper() == 'INTEGER':
                        # If companies.user_id is INTEGER, we need to make users.user_id INTEGER too
                        user_id_type = "INTEGER"
                    
                    # Drop users table if it exists
                    cursor.execute("DROP TABLE IF EXISTS users CASCADE")
                    
                    # Create users table with appropriate user_id type
                    if user_id_type == "INTEGER":
                        cursor.execute("""
                        CREATE TABLE users (
                            user_id INTEGER PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            password_hash TEXT,
                            is_google_account BOOLEAN DEFAULT FALSE,
                            google_id TEXT UNIQUE,
                            name TEXT,
                            company_name TEXT,
                            reset_token TEXT,
                            reset_token_created_at TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """)
                    else:
                        cursor.execute("""
                        CREATE TABLE users (
                            user_id TEXT PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            password_hash TEXT,
                            is_google_account BOOLEAN DEFAULT FALSE,
                            google_id TEXT UNIQUE,
                            name TEXT,
                            company_name TEXT,
                            reset_token TEXT,
                            reset_token_created_at TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """)
                    
                    # Update foreign key constraint in companies table
                    cursor.execute("""
                    ALTER TABLE companies 
                    DROP CONSTRAINT IF EXISTS companies_user_id_fkey;
                    """)
                    
                    cursor.execute("""
                    ALTER TABLE companies 
                    ADD CONSTRAINT companies_user_id_fkey 
                    FOREIGN KEY (user_id) REFERENCES users(user_id);
                    """)
                    
                    return {
                        'success': True,
                        'message': f"PostgreSQL users table recreated successfully with user_id type: {user_id_type}"
                    }
                
                except Exception as e:
                    print(f"PostgreSQL Error: {e}")
                    conn.rollback()
                    return {
                        'success': False,
                        'message': f"PostgreSQL Error: {str(e)}"
                    }
            
            else:
                # SQLite cleanup
                try:
                    # Check if users_old table exists and drop it
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_old'")
                    if cursor.fetchone():
                        cursor.execute("DROP TABLE users_old")
                    
                    # Check if users table exists and drop it
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                    if cursor.fetchone():
                        cursor.execute("DROP TABLE users")
                    
                    # Create new users table with correct schema
                    cursor.execute('''
                    CREATE TABLE users (
                        user_id TEXT PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT,
                        is_google_account INTEGER DEFAULT 0,
                        google_id TEXT UNIQUE,
                        name TEXT,
                        company_name TEXT,
                        reset_token TEXT,
                        reset_token_created_at DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    
                    # Check if temporary tables exist and drop them
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_temp'")
                    if cursor.fetchone():
                        cursor.execute("DROP TABLE users_temp")
                    
                    return {
                        'success': True,
                        'message': "SQLite users table recreated successfully"
                    }
                
                except Exception as e:
                    print(f"SQLite Error: {e}")
                    conn.rollback()
                    return {
                        'success': False,
                        'message': f"SQLite Error: {str(e)}"
                    }
    
    except Exception as e:
        print(f"Error cleaning users table: {e}")
        return {
            'success': False,
            'message': f"Error: {str(e)}"
        }

def inspect_database():
    """Inspect all tables in the database and generate a report."""
    output_lines = []
    
    # Helper function to add lines to output
    def add_line(message=""):
        output_lines.append(message)
    
    # Get database type and connection info
    add_line("=" * 80)
    add_line(f"DATABASE INSPECTION REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add_line("=" * 80)
    
    db_type = "PostgreSQL" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "SQLite"
    add_line(f"Database Type: {db_type}")
    
    if os.getenv('DB_TYPE', '').lower() == 'postgresql':
        add_line(f"Host: {os.getenv('DB_HOST', '')}")
        add_line(f"Database: {os.getenv('DB_NAME', '')}")
        add_line(f"Schema: {os.getenv('DB_SCHEMA', '')}")
    else:
        add_line(f"Database File: {os.getenv('DB_PATH', 'easyafchat.db')}")
    add_line("")
    
    # Get all tables
    tables = []
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            # PostgreSQL query to get tables
            cursor.execute(f"""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = '{os.getenv('DB_SCHEMA', 'easychat')}'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cursor.fetchall()]
        else:
            # SQLite query to get tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
    
    add_line(f"Found {len(tables)} tables: {', '.join(tables)}")
    add_line("")
    
    # Examine each table
    for table_name in tables:
        add_line("-" * 80)
        add_line(f"TABLE: {table_name}")
        add_line("-" * 80)
        
        # Get schema
        columns = []
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # PostgreSQL query to get column information
                cursor.execute(f"""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_schema = '{os.getenv('DB_SCHEMA', 'easychat')}' 
                    AND table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        'name': row[0],
                        'type': row[1],
                        'nullable': row[2]
                    })
            else:
                # SQLite query to get column information
                cursor.execute(f"PRAGMA table_info({table_name})")
                
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        'name': row[1],
                        'type': row[2],
                        'nullable': "YES" if row[3] == 0 else "NO"
                    })
        
        add_line("SCHEMA:")
        for col in columns:
            nullable = "NULL" if col['nullable'] == "YES" else "NOT NULL"
            add_line(f"  {col['name']} ({col['type']}) {nullable}")
        add_line("")
        
        # Get foreign keys
        foreign_keys = []
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # PostgreSQL query to get foreign keys
                cursor.execute(f"""
                    SELECT
                        kcu.column_name, 
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM 
                        information_schema.table_constraints AS tc 
                        JOIN information_schema.key_column_usage AS kcu
                          ON tc.constraint_name = kcu.constraint_name
                          AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu 
                          ON ccu.constraint_name = tc.constraint_name
                          AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY' 
                    AND tc.table_schema = '{os.getenv('DB_SCHEMA', 'easychat')}'
                    AND tc.table_name = %s
                """, (table_name,))
                
                for row in cursor.fetchall():
                    foreign_keys.append({
                        'column_name': row[0],
                        'foreign_table_name': row[1],
                        'foreign_column_name': row[2]
                    })
            else:
                # SQLite query to get foreign keys
                cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                
                # Format to match PostgreSQL output
                for row in cursor.fetchall():
                    foreign_keys.append({
                        'column_name': row[3],
                        'foreign_table_name': row[2],
                        'foreign_column_name': row[4]
                    })
                    
        if foreign_keys:
            add_line("FOREIGN KEYS:")
            for fk in foreign_keys:
                add_line(f"  {fk['column_name']} -> {fk['foreign_table_name']}.{fk['foreign_column_name']}")
            add_line("")
        
        # Count records
        record_count = 0
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                query = f'SELECT COUNT(*) FROM "{table_name}"'
                cursor.execute(query)
            else:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                
            record_count = cursor.fetchone()[0]
            
        add_line(f"RECORD COUNT: {record_count}")
        add_line("")
        
        # Get sample records
        if record_count > 0:
            add_line("SAMPLE RECORDS (up to 5):")
            
            with connect_to_db() as conn:
                cursor = conn.cursor()
                
                if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                    cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 5')
                else:
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                    
                records = cursor.fetchall()
                
                # Get column names
                column_names = [desc[0] for desc in cursor.description]
                
                # Print column headers
                header = " | ".join(column_names)
                add_line(f"  {header}")
                add_line(f"  {'-' * len(header)}")
                
                # Print records
                for record in records:
                    formatted_row = []
                    for i, value in enumerate(record):
                        # Handle text fields - truncate if too long
                        if isinstance(value, str) and len(value) > 50:
                            formatted_row.append(f"{value[:47]}...")
                        else:
                            formatted_row.append(str(value))
                    add_line("  " + " | ".join(formatted_row))
            add_line("")
        
        add_line("")
    
    add_line("=" * 80)
    add_line("End of report")
    add_line("=" * 80)
    
    return "\n".join(output_lines)

@admin_dashboard.route('/')
def index():
    with connect_to_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM companies')
        records = cursor.fetchall()
    
    # Add db_info for the DB Management tab
    db_type = "PostgreSQL" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "SQLite"
    
    return render_template_string(HTML, 
                                 records=records,
                                 active_tab="companies",
                                 db_info={
                                     'type': db_type,
                                     'host': os.getenv('DB_HOST', 'local'),
                                     'name': os.getenv('DB_NAME', 'easyafchat.db')
                                 })

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

@admin_dashboard.route('/db-management', methods=['GET'])
def db_management():
    """Display the database management interface."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM companies')
        records = cursor.fetchall()
        
    db_type = "PostgreSQL" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "SQLite"
    
    return render_template_string(HTML, 
                                 records=records, 
                                 active_tab="db_management",
                                 db_info={
                                     'type': db_type,
                                     'host': os.getenv('DB_HOST', 'local'),
                                     'name': os.getenv('DB_NAME', 'easyafchat.db')
                                 })

@admin_dashboard.route('/clear-company-users', methods=['POST'])
def clear_company_users():
    """Clear all user_id references in the companies table."""
    result = clear_user_id_from_companies()
    return jsonify(result)

@admin_dashboard.route('/clean-users-table', methods=['POST'])
def rebuild_users_table():
    """Rebuild the users table with the correct schema."""
    result = clean_users_table()
    return jsonify(result)

@admin_dashboard.route('/inspect-database', methods=['POST'])
def run_database_inspection():
    """Run the database inspection and return the report."""
    try:
        report = inspect_database()
        return jsonify({
            'success': True,
            'report': report
        })
    except Exception as e:
        print(f"Error inspecting database: {e}")
        return jsonify({
            'success': False,
            'message': f"Error: {str(e)}"
        }), 500

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