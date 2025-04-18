from flask import Blueprint, render_template_string, request, jsonify, Response, render_template
import os
from datetime import datetime, UTC, date, timedelta
import time
import csv
import io
import uuid
from db_metrics import aggregate_usage_for_date
from db_metrics import get_usage_metrics_for_range

# Import connect_to_db from the database module
from database import connect_to_db

# Import document handler
from documents_handler import DocumentsHandler

# Needed for the new manual add route
from flask import request

# Import from app_utils.py
from app_utils import (
    generate_chatbot_id, 
    check_namespace, 
    chunk_text, 
    get_existing_record,
    process_simple_content
)

PINECONE_HOST = "https://all-companies-6ctd3g7.svc.aped-4627-b74a.pinecone.io"

# Import shared OpenAI and Pinecone clients from the main app
# This will be filled in when the blueprint is registered
openai_client = None
pinecone_client = None
DB_PATH = None
PINECONE_INDEX = None

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
        <button class="nav-link" id="db-management-tab" data-bs-toggle="tab" data-bs-target="#db-management" type="button">DB Management</button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="manual-add-tab" data-bs-toggle="tab" data-bs-target="#manual-add" type="button">Manual Add</button>
    </li>
    <!-- New Usage Metrics Tab -->
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="usage-metrics-tab" data-bs-toggle="tab" data-bs-target="#usage-metrics" type="button">Usage Metrics</button>
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
                    <th>Name</th>
                    <th>Account Type</th>
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
                                
                                <hr class="my-3">
                                
                                <p>This will <strong>DROP and RECREATE</strong> the companies table with the correct schema.</p>
                                <p><strong>Warning:</strong> This will rebuild the companies table schema. Your data will be preserved, but this fixes any schema issues.</p>
                                <button id="cleanCompaniesTableBtn" class="btn btn-danger">
                                    <i class="bi bi-exclamation-octagon"></i> Rebuild Companies Table
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

                    <div class="col-md-4 mb-3">
                        <div class="card">
                            <div class="card-header bg-danger">
                                <h6 class="mb-0 text-white">Chatbot Config Table</h6>
                            </div>
                            <div class="card-body">
                                <p>This will <strong>DROP and RECREATE</strong> the chatbot config table with the correct schema.</p>
                                <p><strong>Warning:</strong> This will rebuild the chatbot config table schema. Your data will be preserved, but this fixes any schema issues.</p>
                                <button id="cleanConfigTableBtn" class="btn btn-danger">
                                    <i class="bi bi-exclamation-octagon"></i> Rebuild Config Table
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

        <!-- Table Truncation Tools -->
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-danger text-white">
                        <h5 class="mb-0">Table Truncation Tools</h5>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-warning">
                            <strong>Warning:</strong> These buttons will delete ALL records from their respective tables. This action cannot be undone!
                        </div>
                        
                        <div class="row">
                            <div class="col-md-4 mb-3">
                                <div class="card">
                                    <div class="card-header bg-danger">
                                        <h6 class="mb-0 text-white">Companies Table</h6>
                                    </div>
                                    <div class="card-body">
                                        <p>Delete all company records.</p>
                                        <button id="truncateCompaniesBtn" class="btn btn-danger">
                                            <i class="bi bi-trash"></i> Empty Companies Table
                                        </button>
                                    </div>
                                </div>
                            </div>
                           
                            <div class="col-md-4 mb-3">
                                <div class="card">
                                    <div class="card-header bg-danger">
                                        <h6 class="mb-0 text-white">Leads Table</h6>
                                    </div>
                                    <div class="card-body">
                                        <p>Delete all lead records.</p>
                                        <button id="truncateLeadsBtn" class="btn btn-danger">
                                            <i class="bi bi-trash"></i> Empty Leads Table
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-4 mb-3">
                                <div class="card">
                                    <div class="card-header bg-danger">
                                        <h6 class="mb-0 text-white">Users Table</h6>
                                    </div>
                                    <div class="card-body">
                                        <p>Delete all user accounts.</p>
                                        <button id="truncateUsersBtn" class="btn btn-danger">
                                            <i class="bi bi-trash"></i> Empty Users Table
                                        </button>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="col-md-4 mb-3">
                                <div class="card">
                                    <div class="card-header bg-danger">
                                        <h6 class="mb-0 text-white">Chatbot Config Table</h6>
                                    </div>
                                    <div class="card-body">
                                        <p>Delete all chatbot configurations.</p>
                                        <button id="truncateConfigBtn" class="btn btn-danger">
                                            <i class="bi bi-trash"></i> Empty Config Table
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                            <div id="truncateResultsAlert" class="alert d-none">
                                <!-- Truncation results will be displayed here -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    
    <!-- Manual Add Tab -->
    <div class="tab-pane fade" id="manual-add" role="tabpanel">
        <div class="card">
            <div class="card-header bg-success text-white">
                <h5 class="mb-0">Manual Company/Chatbot Addition</h5>
            </div>
            <div class="card-body">
                <form id="manualCompanyAddForm">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label for="websiteUrl" class="form-label">Website URL <span class="text-danger">*</span></label>
                            <input type="url" class="form-control" id="websiteUrl" name="website_url" required 
                                placeholder="https://example.com" pattern="https?://.*">
                            <div class="form-text">Full URL of the website</div>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label for="skipOpenaiProcessing" class="form-label">Skip OpenAI Processing?</label>
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="skipOpenaiProcessing" name="skip_openai_processing">
                                <label class="form-check-label" for="skipOpenaiProcessing">
                                    Provide pre-processed content
                                </label>
                            </div>
                            <div class="form-text">If checked, you must provide processed content below</div>
                        </div>
                    </div>

                    <div class="mb-3">
                        <label for="scrapedText" class="form-label">Scraped Text <span class="text-danger">*</span></label>
                        <textarea class="form-control" id="scrapedText" name="scraped_text" rows="6" required 
                                placeholder="Paste the raw text scraped from the website"></textarea>
                        <div class="form-text">Raw text content from the website. This will be processed by OpenAI unless skipped.</div>
                    </div>

                    <div id="processedContentGroup" class="mb-3" style="display:none;">
                        <label for="processedContent" class="form-label">Processed Content</label>
                        <textarea class="form-control" id="processedContent" name="processed_content" rows="6"
                                placeholder="Paste pre-processed content if skipping OpenAI processing"></textarea>
                        <div class="form-text">Required when skipping OpenAI processing</div>
                    </div>

                    <div class="d-grid">
                        <button type="submit" class="btn btn-success">
                            <i class="bi bi-plus-circle"></i> Add Company/Chatbot
                        </button>
                    </div>
                </form>

                <div id="manualAddResults" class="mt-3">
                    <!-- Results or error messages will be displayed here -->
                </div>
            </div>
        </div>
    </div>

    <!-- Usage Metrics Tab -->
    <div class="tab-pane fade" id="usage-metrics" role="tabpanel">
        <h4>Usage Metrics Aggregation and Reporting</h4>
        <div class="card mb-3">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p>Click the button below to aggregate usage data from the `chat_messages` table for **yesterday** and store it in the `usage_metrics` table. If data for yesterday already exists, it will be updated.</p>
                        <button id="aggregateYesterdayBtn" class="btn btn-primary">
                            <i class="bi bi-calculator"></i> Aggregate Yesterday's Metrics
                        </button>
                    </div>
                    <div class="col-md-6">
                        <p>Click the button below to view the aggregated usage metrics stored in the `usage_metrics` table for the **past 7 days**.</p>
                        <button id="viewLast7DaysBtn" class="btn btn-info">
                            <i class="bi bi-calendar-week"></i> View Last 7 Days Metrics
                        </button>
                    </div>
                </div>
                <div id="serverTimeInfo" class="mt-3 text-muted" style="font-size: 0.9em;">
                    <!-- Server time will be loaded here -->
                </div>
                <div id="metricsStatus" class="mt-3 alert d-none">
                    <!-- Status messages will appear here -->
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header bg-secondary text-white">
                <h5 class="mb-0">Metrics Report</h5>
            </div>
            <div class="card-body">
                <div id="metricsReportContainer" class="table-responsive">
                    <!-- Report table will be rendered here by JavaScript -->
                    <p>Click one of the buttons above to generate or view a report.</p>
                </div>
            </div>
        </div>
    </div>
    <!-- End Usage Metrics Tab -->

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
                            <textarea class="form-control" id="modalScrapedText" rows="10"></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Processed Content</label>
                            <textarea class="form-control" id="modalProcessedContent" rows="10"></textarea>
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
            document.getElementById('modalScrapedText').value = data.scraped_text;
            document.getElementById('modalProcessedContent').value = data.processed_content;
            recordModal.show();
        }

        async function saveRecord() {
            const id = document.getElementById('chatbotId').value;
            const data = {
                scraped_text: document.getElementById('modalScrapedText').value,
                processed_content: document.getElementById('modalProcessedContent').value
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
                    
                    // Determine account type
                    const accountType = user.is_google_account ? 
                        '<span class="badge bg-primary">Google</span>' : 
                        '<span class="badge bg-secondary">Regular</span>';
                    
                    // Add row
                    usersTable.row.add([
                        user.user_id,
                        user.email,
                        user.name || '-',
                        accountType,
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

        document.getElementById('cleanCompaniesTableBtn').addEventListener('click', async function() {
            if (confirm('WARNING! This will rebuild the companies table schema. Your data will be preserved, but this is a significant operation that fixes schema issues. Continue?')) {
                if (confirm('FINAL WARNING: The companies table will be dropped and recreated. Type "REBUILD" in the next prompt to proceed.')) {
                    const confirmation = prompt('Type "REBUILD" to proceed with rebuilding the companies table:');
                    
                    if (confirmation === 'REBUILD') {
                        try {
                            const resultsDiv = document.getElementById('dbOperationResults');
                            
                            resultsDiv.className = 'alert alert-info';
                            resultsDiv.innerHTML = 'Rebuilding companies table... This may take a moment.';
                            resultsDiv.classList.remove('d-none');
                            
                            const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/clean-companies-table', {
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

        document.getElementById('cleanConfigTableBtn').addEventListener('click', async function() {
            if (confirm('WARNING! This will rebuild the chatbot config table schema. Your configurations will be preserved, but this is a significant operation that fixes schema issues. Continue?')) {
                if (confirm('FINAL WARNING: The chatbot config table will be dropped and recreated. Type "REBUILD" in the next prompt to proceed.')) {
                    const confirmation = prompt('Type "REBUILD" to proceed with rebuilding the config table:');
                    
                    if (confirmation === 'REBUILD') {
                        try {
                            const resultsDiv = document.getElementById('dbOperationResults');
                            
                            resultsDiv.className = 'alert alert-info';
                            resultsDiv.innerHTML = 'Rebuilding chatbot config table... This may take a moment.';
                            resultsDiv.classList.remove('d-none');
                            
                            const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/clean-config-table', {
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

        // Helper function to handle table truncation
        async function truncateTable(tableName) {
            if (confirm(`⚠️ WARNING! This will DELETE ALL RECORDS from the ${tableName} table!\n\nThis action CANNOT be undone. Are you sure?`)) {
                if (confirm(`FINAL WARNING: All ${tableName} data will be permanently lost.\nType "DELETE" in the next prompt to proceed.`)) {
                    const confirmation = prompt(`Type "DELETE" to empty the ${tableName} table:`);
                    
                    if (confirmation === "DELETE") {
                        try {
                            const resultsAlert = document.getElementById('truncateResultsAlert');
                            resultsAlert.className = 'alert alert-info';
                            resultsAlert.innerHTML = `<strong>Processing:</strong> Emptying the ${tableName} table...`;
                            resultsAlert.classList.remove('d-none');
                            
                            const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/truncate-table/${tableName}`, {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'}
                            });
                            
                            const result = await response.json();
                            
                            if (result.success) {
                                resultsAlert.className = 'alert alert-success';
                                resultsAlert.innerHTML = `<strong>Success!</strong> ${result.message}`;
                            } else {
                                resultsAlert.className = 'alert alert-danger';
                                resultsAlert.innerHTML = `<strong>Error!</strong> ${result.message}`;
                            }
                        } catch (error) {
                            console.error('Error:', error);
                            const resultsAlert = document.getElementById('truncateResultsAlert');
                            resultsAlert.className = 'alert alert-danger';
                            resultsAlert.innerHTML = `<strong>Error!</strong> Failed to empty the ${tableName} table: ${error.message}`;
                            resultsAlert.classList.remove('d-none');
                        }
                    } else {
                        alert('Operation cancelled.');
                    }
                }
            }
        }

        // Add event listeners for each truncate button
        document.getElementById('truncateCompaniesBtn').addEventListener('click', function() {
            truncateTable('companies');
        });

        document.getElementById('truncateLeadsBtn').addEventListener('click', function() {
            truncateTable('leads');
        });

        document.getElementById('truncateUsersBtn').addEventListener('click', function() {
            truncateTable('users');
        });

        document.getElementById('truncateConfigBtn').addEventListener('click', function() {
            truncateTable('chatbot_config');
        });

        function loadCompanies() {
            // Reload the page to refresh the companies table
            location.reload();
        }

        // Function to display the report table (Updated for Company column and shorter headers)
        function displayMetricsReport(data, serverTimeInfo) {
            console.log('[Admin JS] displayMetricsReport called with data:', data);
            const reportContainer = document.getElementById('metricsReportContainer');
            const serverTimeDiv = document.getElementById('serverTimeInfo');
            reportContainer.innerHTML = ''; // Clear previous report
            serverTimeDiv.textContent = serverTimeInfo || ''; // Display server time info

            if (!data || data.length === 0) {
                reportContainer.innerHTML = '<p>No usage metrics found for the selected period.</p>';
                console.log('[Admin JS] No data to display in report.');
                return;
            }

            // Group data by date for subtotals
            const groupedData = data.reduce((acc, row) => {
                // Ensure date is just the date part (YYYY-MM-DD)
                const dateKey = row.date.substring(0, 10);
                if (!acc[dateKey]) {
                    acc[dateKey] = [];
                }
                acc[dateKey].push(row);
                return acc;
            }, {});

            console.log('[Admin JS] Data grouped by date:', groupedData);

            // Create table structure with updated headers
            let tableHTML = '<table class="table table-striped table-bordered table-sm">';
            tableHTML += `
                <thead class="table-light">
                    <tr>
                        <th>Date</th>
                        <th>Chatbot ID</th>
                        <th>Company</th>
                        <th>Cvs</th>
                        <th>Msgs</th>
                        <th>Tokens</th>
                        <th>Costs ($)</th>
                        <th>+F</th>
                        <th>-F</th>
                    </tr>
                </thead>
                <tbody>
            `;

            let grandTotalConversations = 0;
            let grandTotalMessages = 0;
            let grandTotalTokens = 0;
            let grandTotalCosts = 0; // Use number for summing
            let grandTotalPositive = 0;
            let grandTotalNegative = 0;

            // Sort dates chronologically
            const sortedDates = Object.keys(groupedData).sort();

            sortedDates.forEach(dateKey => {
                const dayData = groupedData[dateKey];
                let daySubtotalConversations = 0;
                let daySubtotalMessages = 0;
                let daySubtotalTokens = 0;
                let daySubtotalCosts = 0; // Use number for summing
                let daySubtotalPositive = 0;
                let daySubtotalNegative = 0;

                // Add rows for the current day, including company namespace
                dayData.forEach(row => {
                    // Safely parse cost, default to 0 if invalid
                    let costValue = 0;
                    try {
                        costValue = parseFloat(row.costs);
                        if (isNaN(costValue)) costValue = 0;
                    } catch {
                        costValue = 0;
                    }

                    // Ensure company_namespace exists, default to '-'
                    const companyNamespace = row.company_namespace || '-';

                    tableHTML += `
                        <tr>
                            <td>${dateKey}</td>
                            <td>${row.chatbot_id || '-'}</td>
                            <td>${companyNamespace}</td>
                            <td>${row.conversations || 0}</td>
                            <td>${row.messages || 0}</td>
                            <td>${row.tokens || 0}</td>
                            <td class="text-end">${costValue.toFixed(6)}</td>
                            <td>${row.positive_feedback || 0}</td>
                            <td>${row.negative_feedback || 0}</td>
                        </tr>
                    `;
                    // Accumulate daily subtotals
                    daySubtotalConversations += parseInt(row.conversations || 0);
                    daySubtotalMessages += parseInt(row.messages || 0);
                    daySubtotalTokens += parseInt(row.tokens || 0);
                    daySubtotalCosts += costValue;
                    daySubtotalPositive += parseInt(row.positive_feedback || 0);
                    daySubtotalNegative += parseInt(row.negative_feedback || 0);
                });

                // Add subtotal row for the day, adjusting colspan
                tableHTML += `
                    <tr class="table-info fw-bold">
                        <td colspan="3" class="text-end">Subtotal for ${dateKey}:</td>
                        <td>${daySubtotalConversations}</td>
                        <td>${daySubtotalMessages}</td>
                        <td>${daySubtotalTokens}</td>
                        <td class="text-end">${daySubtotalCosts.toFixed(6)}</td>
                        <td>${daySubtotalPositive}</td>
                        <td>${daySubtotalNegative}</td>
                    </tr>
                `;

                // Accumulate grand totals
                grandTotalConversations += daySubtotalConversations;
                grandTotalMessages += daySubtotalMessages;
                grandTotalTokens += daySubtotalTokens;
                grandTotalCosts += daySubtotalCosts;
                grandTotalPositive += daySubtotalPositive;
                grandTotalNegative += daySubtotalNegative;
            });

            tableHTML += `</tbody>`;

            // Add Grand Total footer, adjusting colspan
            tableHTML += `
                <tfoot class="table-dark fw-bold">
                    <tr>
                        <td colspan="3" class="text-end">Grand Total:</td>
                        <td>${grandTotalConversations}</td>
                        <td>${grandTotalMessages}</td>
                        <td>${grandTotalTokens}</td>
                        <td class="text-end">${grandTotalCosts.toFixed(6)}</td>
                        <td>${grandTotalPositive}</td>
                        <td>${grandTotalNegative}</td>
                    </tr>
                </tfoot>
            `;

            tableHTML += '</table>';
            reportContainer.innerHTML = tableHTML;
            console.log('[Admin JS] Report table rendered with Company column.');
        }

        // Function to fetch and display metrics for the last N days
        async function fetchAndDisplayLastNDays(days) {
            console.log(`[Admin JS] fetchAndDisplayLastNDays called for ${days} days.`);
            const statusDiv = document.getElementById('metricsStatus');
            const reportContainer = document.getElementById('metricsReportContainer');
            statusDiv.className = 'alert alert-info';
            statusDiv.textContent = `Fetching metrics for the last ${days} days...`;
            statusDiv.classList.remove('d-none');
            reportContainer.innerHTML = '<div class="spinner-border text-info" role="status"><span class="visually-hidden">Loading...</span></div>'; // Show spinner

            try {
                // ** NOTE: Need to create this route '/get-usage-metrics' next **
                const response = await fetch(`/admin-dashboard-08x7z9y2-yoursecretword/get-usage-metrics?days=${days}`);
                const result = await response.json();
                console.log('[Admin JS] Received response from /get-usage-metrics:', result);

                if (response.ok && result.success) {
                    statusDiv.className = 'alert alert-success';
                    statusDiv.textContent = `Successfully fetched metrics for the last ${days} days.`;
                    displayMetricsReport(result.data, `Report for Last ${days} Days`);
                } else {
                    statusDiv.className = 'alert alert-danger';
                    statusDiv.textContent = `Error fetching metrics: ${result.message || 'Unknown error'}`;
                    reportContainer.innerHTML = `<p class="text-danger">Could not load metrics: ${result.message || response.statusText}</p>`;
                }
            } catch (error) {
                console.error('[Admin JS] Error fetching last N days metrics:', error);
                statusDiv.className = 'alert alert-danger';
                statusDiv.textContent = `Network or server error fetching metrics: ${error.message}`;
                reportContainer.innerHTML = `<p class="text-danger">An error occurred while fetching the report.</p>`;
            }
            // Hide status message after a few seconds unless it was an error
            if (!statusDiv.classList.contains('alert-danger')) {
                setTimeout(() => { statusDiv.classList.add('d-none'); }, 3000);
            }
        }
       

        // Add event listener for the "Aggregate Yesterday" button
        document.getElementById('aggregateYesterdayBtn').addEventListener('click', async function() {
            console.log('[Admin JS] "Aggregate Yesterday" button clicked.');
            const statusDiv = document.getElementById('metricsStatus');
            const reportContainer = document.getElementById('metricsReportContainer');
            this.disabled = true; // Disable button during processing
            statusDiv.className = 'alert alert-info';
            statusDiv.textContent = 'Aggregating yesterdays metrics... Please wait.';
            statusDiv.classList.remove('d-none');
            reportContainer.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>'; // Show spinner

            try {
                const response = await fetch('/admin-dashboard-08x7z9y2-yoursecretword/aggregate-yesterday-metrics', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        // Add CSRF token if needed, depends on how CSRF is handled for POST via JS
                        // 'X-CSRFToken': '{{ csrf_token() }}' // Example if using Flask-WTF CSRF in template context
                    }
                });
                const result = await response.json();
                console.log('[Admin JS] Received response from /aggregate-yesterday-metrics:', result);

                if (response.ok && result.success) {
                    statusDiv.className = 'alert alert-success';
                    statusDiv.textContent = `Aggregation successful! ${result.message || ''}`;
                    // Display the newly aggregated data
                    displayMetricsReport(result.aggregated_data, result.server_time_info);
                } else {
                    statusDiv.className = 'alert alert-danger';
                    statusDiv.textContent = `Aggregation failed: ${result.message || 'Unknown error'} ${result.errors ? JSON.stringify(result.errors) : ''}`;
                    reportContainer.innerHTML = `<p class="text-danger">Aggregation failed. See status message above.</p>`;
                    document.getElementById('serverTimeInfo').textContent = result.server_time_info || ''; // Show server time even on failure
                }
            } catch (error) {
                console.error('[Admin JS] Error during aggregation fetch:', error);
                statusDiv.className = 'alert alert-danger';
                statusDiv.textContent = `Network or server error during aggregation: ${error.message}`;
                reportContainer.innerHTML = `<p class="text-danger">An error occurred while contacting the server.</p>`;
            } finally {
                this.disabled = false; // Re-enable button
                // Hide status message after a few seconds unless it was an error
                if (!statusDiv.classList.contains('alert-danger')) {
                    setTimeout(() => { statusDiv.classList.add('d-none'); }, 5000);
                }
            }
        });


        // Add event listener for the "View Last 7 Days" button
        document.getElementById('viewLast7DaysBtn').addEventListener('click', function() {
            console.log('[Admin JS] "View Last 7 Days" button clicked.');
            fetchAndDisplayLastNDays(7);
        });

        // Optional: Add event listener for when the Usage Metrics tab is shown
        const usageMetricsTab = document.getElementById('usage-metrics-tab');
        if (usageMetricsTab) {
            usageMetricsTab.addEventListener('shown.bs.tab', function (event) {
                console.log('[Admin JS] Usage Metrics tab shown.');
                // Clear any previous status messages or reports when tab becomes active
                document.getElementById('metricsStatus').classList.add('d-none');
                document.getElementById('metricsReportContainer').innerHTML = '<p>Click one of the buttons above to generate or view a report.</p>';
                document.getElementById('serverTimeInfo').textContent = ''; // Clear server time info
                // Potentially auto-load last 7 days? Or leave it manual. Current setup is manual.
                // fetchAndDisplayLastNDays(7); // Uncomment to auto-load
            });
        }

    </script>

    <script>
    document.addEventListener('DOMContentLoaded', function() {
        const skipProcessingCheckbox = document.getElementById('skipOpenaiProcessing');
        const processedContentGroup = document.getElementById('processedContentGroup');
        const processedContentInput = document.getElementById('processedContent');
        const manualCompanyAddForm = document.getElementById('manualCompanyAddForm');
        const resultsDiv = document.getElementById('manualAddResults');

        // Toggle processed content visibility based on checkbox
        skipProcessingCheckbox.addEventListener('change', function() {
            processedContentGroup.style.display = this.checked ? 'block' : 'none';
            processedContentInput.required = this.checked;
        });

        // Form submission handler
        manualCompanyAddForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Create FormData object
            const formData = new FormData(manualCompanyAddForm);
            
            // Show loading state
            resultsDiv.innerHTML = `
                <div class="alert alert-info">
                    <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                    Processing... Please wait.
                </div>
            `;

            // Send AJAX request
            fetch('/admin-dashboard-08x7z9y2-yoursecretword/manual-add-company', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    resultsDiv.innerHTML = `
                        <div class="alert alert-success">
                            <strong>Success!</strong> 
                            Company added. Chatbot ID: ${data.chatbot_id}<br>
                            Namespace: ${data.namespace}<br>
                            Website: ${data.website_url}
                        </div>
                    `;
                    // Optional: Reload companies table or perform other actions
                    loadCompanies(); // Assuming you have a function to reload companies
                } else {
                    resultsDiv.innerHTML = `
                        <div class="alert alert-danger">
                            <strong>Error!</strong> ${data.error}
                        </div>
                    `;
                }
            })
            .catch(error => {
                resultsDiv.innerHTML = `
                    <div class="alert alert-danger">
                        <strong>Network Error!</strong> ${error.message}
                    </div>
                `;
            });
        });
    });
    </script>

</body>
</html>
'''

def get_embeddings(text_chunks):
    embeddings = []
    for chunk in text_chunks:
        response = openai_client.embeddings.create(
            input=chunk,
            model="text-embedding-ada-002"
        )
        embeddings.append(response.data[0].embedding)
    return embeddings

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
                    # Drop users table if it exists
                    cursor.execute("DROP TABLE IF EXISTS users CASCADE")
                    
                    # Create users table with TEXT id (not INTEGER)
                    cursor.execute("""
                    CREATE TABLE users (
                        user_id TEXT PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT,
                        is_google_account BOOLEAN DEFAULT FALSE,
                        google_id TEXT UNIQUE,
                        name TEXT,
                        company_name TEXT,
                        
                        /* Password Reset (existing fields) */
                        reset_token TEXT,
                        reset_token_created_at TIMESTAMP,
                        
                        /* Email Verification */
                        email_verify_token TEXT,
                        email_verify_status BOOLEAN DEFAULT FALSE,
                        
                        /* Login Security */
                        login_failed_attempts INTEGER DEFAULT 0,
                        login_failed_last TIMESTAMP,
                        login_locked_until TIMESTAMP,
                        
                        /* Two-Factor Authentication */
                        totp_secret TEXT,
                        totp_enabled BOOLEAN DEFAULT FALSE,
                        
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP
                    )
                    """)
                    
                    return {
                        'success': True,
                        'message': "PostgreSQL users table recreated successfully with security fields"
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
                    
                    # Create new users table with TEXT id (not INTEGER)
                    cursor.execute('''
                    CREATE TABLE users (
                        user_id TEXT PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT,
                        is_google_account INTEGER DEFAULT 0,
                        google_id TEXT UNIQUE,
                        name TEXT,
                        company_name TEXT,
                        
                        /* Password Reset (existing fields) */
                        reset_token TEXT,
                        reset_token_created_at DATETIME,
                        
                        /* Email Verification */
                        email_verify_token TEXT,
                        email_verify_status INTEGER DEFAULT 0,
                        
                        /* Login Security */
                        login_failed_attempts INTEGER DEFAULT 0,
                        login_failed_last DATETIME,
                        login_locked_until DATETIME,
                        
                        /* Two-Factor Authentication */
                        totp_secret TEXT,
                        totp_enabled INTEGER DEFAULT 0,
                        
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_login DATETIME
                    )
                    ''')
                    
                    return {
                        'success': True,
                        'message': "SQLite users table recreated successfully with security fields"
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

def clean_companies_table():
    """Clean up the companies table and recreate it with the correct schema."""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # PostgreSQL cleanup
                try:
                    # Store existing data
                    cursor.execute("""
                        SELECT 
                            chatbot_id, company_url, pinecone_host_url, pinecone_index, 
                            pinecone_namespace, created_at, updated_at, scraped_text, 
                            processed_content, user_id 
                        FROM companies
                    """)
                    existing_data = cursor.fetchall()
                    
                    # Drop companies table if it exists
                    cursor.execute("DROP TABLE IF EXISTS companies CASCADE")
                    
                    # Create companies table with TEXT user_id
                    cursor.execute("""
                    CREATE TABLE companies (
                        chatbot_id TEXT PRIMARY KEY,
                        company_url TEXT NOT NULL,
                        pinecone_host_url TEXT,
                        pinecone_index TEXT,
                        pinecone_namespace TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        scraped_text TEXT,
                        processed_content TEXT,
                        user_id TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                    )
                    """)
                    
                    # Restore data with proper type conversion
                    for row in existing_data:
                        # If user_id is not NULL and not already a TEXT, convert it
                        user_id = row[9]
                        if user_id is not None and not isinstance(user_id, str):
                            user_id = str(user_id)
                            
                        cursor.execute("""
                            INSERT INTO companies (
                                chatbot_id, company_url, pinecone_host_url, pinecone_index, 
                                pinecone_namespace, created_at, updated_at, scraped_text, 
                                processed_content, user_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            row[0], row[1], row[2], row[3], row[4], row[5], 
                            row[6], row[7], row[8], user_id
                        ))
                    
                    return {
                        'success': True,
                        'message': f"PostgreSQL companies table recreated successfully with {len(existing_data)} records restored"
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
                    # Store existing data
                    cursor.execute("""
                        SELECT 
                            chatbot_id, company_url, pinecone_host_url, pinecone_index, 
                            pinecone_namespace, created_at, updated_at, scraped_text, 
                            processed_content, user_id 
                        FROM companies
                    """)
                    existing_data = cursor.fetchall()
                    
                    # Create a backup of the companies table first
                    cursor.execute("CREATE TABLE IF NOT EXISTS companies_backup AS SELECT * FROM companies")
                    
                    # Drop companies table
                    cursor.execute("DROP TABLE IF EXISTS companies")
                    
                    # Create new companies table with correct schema
                    cursor.execute('''
                    CREATE TABLE companies (
                        chatbot_id TEXT PRIMARY KEY,
                        company_url TEXT NOT NULL,
                        pinecone_host_url TEXT,
                        pinecone_index TEXT,
                        pinecone_namespace TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        scraped_text TEXT,
                        processed_content TEXT,
                        user_id TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                    )
                    ''')
                    
                    # Restore data with proper type conversion
                    for row in existing_data:
                        # If user_id is not NULL and not already a TEXT, convert it
                        user_id = row[9]
                        if user_id is not None and not isinstance(user_id, str):
                            user_id = str(user_id)
                            
                        cursor.execute("""
                            INSERT INTO companies (
                                chatbot_id, company_url, pinecone_host_url, pinecone_index, 
                                pinecone_namespace, created_at, updated_at, scraped_text, 
                                processed_content, user_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            row[0], row[1], row[2], row[3], row[4], row[5], 
                            row[6], row[7], row[8], user_id
                        ))
                    
                    return {
                        'success': True,
                        'message': f"SQLite companies table recreated successfully with {len(existing_data)} records restored"
                    }
                
                except Exception as e:
                    print(f"SQLite Error: {e}")
                    conn.rollback()
                    return {
                        'success': False,
                        'message': f"SQLite Error: {str(e)}"
                    }
    
    except Exception as e:
        print(f"Error cleaning companies table: {e}")
        return {
            'success': False,
            'message': f"Error: {str(e)}"
        }

def clean_chatbot_config_table():
    """Clean up the chatbot_config table and recreate it with the correct schema."""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # PostgreSQL cleanup
                try:
                    # Drop chatbot_config table if it exists
                    cursor.execute("DROP TABLE IF EXISTS chatbot_config CASCADE")
                    
                    # Create new chatbot_config table
                    cursor.execute("""
                    CREATE TABLE chatbot_config (
                        config_id SERIAL PRIMARY KEY,
                        chatbot_id TEXT UNIQUE REFERENCES companies(chatbot_id),
                        chat_model TEXT DEFAULT 'gpt-4o',
                        temperature NUMERIC(3,2) DEFAULT 0.7,
                        max_tokens INTEGER DEFAULT 500,
                        system_prompt TEXT,
                        chat_title TEXT,
                        chat_subtitle TEXT,
                        lead_form_title TEXT DEFAULT 'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
                        primary_color TEXT DEFAULT '#0084ff',
                        accent_color TEXT DEFAULT '#e9ecef',
                        icon_image_url TEXT DEFAULT NULL,
                        show_lead_form TEXT DEFAULT 'Yes',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """)
                    
                    return {
                        'success': True,
                        'message': "PostgreSQL chatbot_config table recreated successfully"
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
                    # Drop chatbot_config table
                    cursor.execute("DROP TABLE IF EXISTS chatbot_config")
                    
                    # Create new chatbot_config table with correct schema
                    cursor.execute('''
                    CREATE TABLE chatbot_config (
                        config_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chatbot_id TEXT UNIQUE REFERENCES companies(chatbot_id),
                        chat_model TEXT DEFAULT 'gpt-4o',
                        temperature NUMERIC(3,2) DEFAULT 0.7,
                        max_tokens INTEGER DEFAULT 500,
                        system_prompt TEXT,
                        chat_title TEXT,
                        chat_subtitle TEXT,
                        lead_form_title TEXT DEFAULT 'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
                        primary_color TEXT DEFAULT '#0084ff',
                        accent_color TEXT DEFAULT '#e9ecef',
                        icon_image_url TEXT DEFAULT NULL,
                        show_lead_form TEXT DEFAULT 'Yes',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    
                    return {
                        'success': True,
                        'message': "SQLite chatbot_config table recreated successfully"
                    }
                
                except Exception as e:
                    print(f"SQLite Error: {e}")
                    conn.rollback()
                    return {
                        'success': False,
                        'message': f"SQLite Error: {str(e)}"
                    }
    
    except Exception as e:
        print(f"Error cleaning chatbot_config table: {e}")
        return {
            'success': False,
            'message': f"Error: {str(e)}"
        }

# Add a new route to handle clean config table
@admin_dashboard.route('/clean-config-table', methods=['POST'])
def rebuild_config_table():
    """Rebuild the chatbot_config table with the correct schema."""
    result = clean_chatbot_config_table()
    return jsonify(result)

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
            cursor.execute('SELECT scraped_text, processed_content FROM companies WHERE chatbot_id = %s', (id,))
        else:
            cursor.execute('SELECT scraped_text, processed_content FROM companies WHERE chatbot_id = ?', (id,))
            
        record = cursor.fetchone()
        
        if record:
            return jsonify({
                'scraped_text': record[0] or '',
                'processed_content': record[1] or ''
            })
        else:
            return jsonify({
                'scraped_text': '',
                'processed_content': ''
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

@admin_dashboard.route('/clean-companies-table', methods=['POST'])
def rebuild_companies_table():
    """Rebuild the companies table with the correct schema."""
    result = clean_companies_table()
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

@admin_dashboard.route('/truncate-table/<table_name>', methods=['POST'])
def truncate_table(table_name):
    """
    Delete all records from the specified table.
    """
    allowed_tables = ['companies', 'documents', 'leads', 'users', 'chatbot_config']
    
    if table_name not in allowed_tables:
        return jsonify({
            'success': False,
            'message': f"Invalid table name: {table_name}"
        }), 400
    
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Start transaction
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('BEGIN')
            
            # Special handling for users table - handle foreign key constraints first
            if table_name == 'users':
                # First, NULL out all user_id references in the companies table
                cursor.execute("UPDATE companies SET user_id = NULL")
                print("Cleared all user_id references in the companies table")
            
            # Get record count first
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            # Delete all records
            cursor.execute(f"DELETE FROM {table_name}")
            
            # For SQLite, we need to reset the auto-increment counter for tables with INTEGER PRIMARY KEY
            if os.getenv('DB_TYPE', '').lower() != 'postgresql':
                # Check if table has an autoincrement primary key
                if table_name in ['leads']:  # Add other tables with autoincrement as needed
                    cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}'")
            
            # Commit transaction
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('COMMIT')
            
            # If this is the companies table, also clean up Pinecone
            if table_name == 'companies':
                try:
                    # Get all namespaces from another query connection to avoid transaction issues
                    namespaces = []
                    with connect_to_db() as namespace_conn:
                        namespace_cursor = namespace_conn.cursor()
                        namespace_cursor.execute("SELECT pinecone_namespace FROM companies_backup WHERE pinecone_namespace IS NOT NULL")
                        namespaces = [row[0] for row in namespace_cursor.fetchall()]
                    
                    # Delete vectors from Pinecone for each namespace
                    index = pinecone_client.Index(PINECONE_INDEX)
                    for namespace in namespaces:
                        if namespace:
                            try:
                                index.delete(delete_all=True, namespace=namespace)
                                print(f"Deleted all vectors for namespace: {namespace}")
                            except Exception as e:
                                print(f"Warning: Error deleting Pinecone vectors for namespace {namespace}: {e}")
                except Exception as e:
                    print(f"Warning: Error cleaning up Pinecone: {e}")
            
            return jsonify({
                'success': True,
                'message': f"Successfully deleted {count} records from the {table_name} table."
            })
            
    except Exception as e:
        print(f"Error truncating table {table_name}: {e}")
        # Try to rollback if possible
        try:
            if conn and os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('ROLLBACK')
        except:
            pass
            
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
    
@admin_dashboard.route('/nuclear-reset/<id>', methods=['POST'])
def nuclear_reset(id):
    """
    Complete nuclear reset of a chatbot - removes all traces from all tables.
    """
    try:
        # Store company info for potential re-use
        company_url = None
        namespace = None
        user_id = None
        
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # First get the company info before deleting
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('SELECT company_url, pinecone_namespace, user_id FROM companies WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('SELECT company_url, pinecone_namespace, user_id FROM companies WHERE chatbot_id = ?', (id,))
                
            company_info = cursor.fetchone()
            if company_info:
                company_url = company_info[0]
                namespace = company_info[1]
                user_id = company_info[2]
                
            # START TRANSACTION - important for consistency
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('BEGIN')
            
            # 1. Delete all chat messages for this chatbot (added this step)
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM chat_messages WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM chat_messages WHERE chatbot_id = ?', (id,))
            
            # 2. Delete all documents for this chatbot
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM documents WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM documents WHERE chatbot_id = ?', (id,))
                
            # 3. Delete all leads for this chatbot
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM leads WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM leads WHERE chatbot_id = ?', (id,))
                
            # 4. Delete any chatbot configurations
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM chatbot_config WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM chatbot_config WHERE chatbot_id = ?', (id,))
            
            # 5. Delete any chatbot incidents
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM chatbot_incidents WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM chatbot_incidents WHERE chatbot_id = ?', (id,))
                
            # 6. Delete any usage metrics records for this chatbot
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM usage_metrics WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM usage_metrics WHERE chatbot_id = ?', (id,))
            
            # 7. Remove the company record (break the foreign key relationship)
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('DELETE FROM companies WHERE chatbot_id = %s', (id,))
            else:
                cursor.execute('DELETE FROM companies WHERE chatbot_id = ?', (id,))
            
            # 8. Now see if we need to delete the user (if they don't have any other chatbots)
            if user_id:
                if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                    # Check if this user has other chatbots
                    cursor.execute('SELECT COUNT(*) FROM companies WHERE user_id = %s', (user_id,))
                    other_chatbots = cursor.fetchone()[0]
                    
                    if other_chatbots == 0:
                        # User has no other chatbots, so delete the user
                        cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
                else:
                    # Do the same for SQLite
                    cursor.execute('SELECT COUNT(*) FROM companies WHERE user_id = ?', (user_id,))
                    other_chatbots = cursor.fetchone()[0]
                    
                    if other_chatbots == 0:
                        # User has no other chatbots, so delete the user
                        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            
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
    
# Add the manual company addition route
@admin_dashboard.route('/manual-add-company', methods=['POST'])
def manual_add_company():
    """
    Manually add a new company/chatbot to the system.
    This route handler uses the add_manual_company utility function.
    """
    try:
        # Extract form data
        website_url = request.form.get('website_url')
        scraped_text = request.form.get('scraped_text')
        skip_openai_processing = request.form.get('skip_openai_processing') == 'on'
        processed_content = request.form.get('processed_content', '')

        # Call the utility function from app_utils
        from app_utils import add_manual_company
        
        result = add_manual_company(
            website_url=website_url,
            scraped_text=scraped_text,
            skip_openai_processing=skip_openai_processing,
            processed_content=processed_content,
            openai_client=openai_client,
            pinecone_client=pinecone_client,
            pinecone_index=PINECONE_INDEX,
            pinecone_host=PINECONE_HOST
        )
        
        # Return the result with appropriate status code
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception as e:
        # Catch any unexpected errors
        print(f"Unexpected error in manual company addition route: {e}")
        return jsonify({
            'success': False, 
            'error': f'Unexpected error: {str(e)}'
        }), 500
    
@admin_dashboard.route('/aggregate-yesterday-metrics', methods=['POST'])
def handle_aggregate_yesterday():
    """
    API endpoint called by the admin dashboard to trigger the aggregation
    of yesterday's usage metrics.
    After successful aggregation, it re-fetches the data for yesterday
    using get_usage_metrics_for_range to include company namespace for display.
    """
    print("[admin_dashboard] Received request to aggregate yesterday's metrics.")
    try:
        # Determine yesterday's date based on server's local time
        today_local = date.today()
        # *** CORRECTION: yesterday is timedelta(days=1) ***
        yesterday_local = today_local - timedelta(days=1)
        print(f"[admin_dashboard] Calculated yesterday's date (local): {yesterday_local.isoformat()}")

        # Get current server time and timezone for display
        now_local = datetime.now()
        try:
            current_tz_name = time.tzname[now_local.dst()] if now_local.dst() else time.tzname[0]
            server_time_str = now_local.strftime(f'%Y-%m-%d %H:%M:%S {current_tz_name}')
        except Exception:
            server_time_str = now_local.strftime('%Y-%m-%d %H:%M:%S %Z%z')

        print(f"[admin_dashboard] Current server time for display: {server_time_str}")

        # Call the aggregation function from db_metrics
        aggregation_result = aggregate_usage_for_date(yesterday_local)

        # Default response data in case aggregation fails or returns no data
        response_data = {
            "success": aggregation_result.get("success", False),
            "message": aggregation_result.get("message", "Aggregation status unknown."),
            "errors": aggregation_result.get("errors", []),
            "aggregated_data": [], # Start with empty data
            "server_time_info": f"Server Time at Aggregation: {server_time_str}"
        }
        status_code = 500 if not aggregation_result.get("success") else 200

        if aggregation_result.get("success"):
            print("[admin_dashboard] Aggregation successful. Re-fetching yesterday's data for display.")
            # Aggregation succeeded, now fetch yesterday's data using the updated function
            # which includes the company namespace.
            yesterdays_data_with_namespace = get_usage_metrics_for_range(yesterday_local, yesterday_local)

            # Update the response data with the fetched metrics
            response_data["aggregated_data"] = yesterdays_data_with_namespace
            # Keep the original success message from the aggregation process
            response_data["message"] = aggregation_result.get("message", "Aggregation successful.")

            print(f"[admin_dashboard] Fetched {len(yesterdays_data_with_namespace)} records for yesterday's report.")
            return jsonify(response_data)
        else:
            print(f"[admin_dashboard] Aggregation failed: {aggregation_result.get('message')}")
            # Return the error details from the aggregation attempt
            return jsonify(response_data), status_code

    except Exception as e:
        print(f"[admin_dashboard] FATAL ERROR during aggregation trigger: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # Use the server time calculated earlier if available, otherwise generate new one
        final_server_time = server_time_str if 'server_time_str' in locals() else datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z%z')
        return jsonify({
            "success": False,
            "message": "An unexpected server error occurred during the aggregation process.",
            "errors": [str(e)],
            "aggregated_data": [],
            "server_time_info": final_server_time # Provide time even on failure
        }), 500
    
    
@admin_dashboard.route('/get-usage-metrics', methods=['GET'])
def get_usage_metrics_report():
    """
    API endpoint to fetch aggregated usage metrics for a specified number of past days.
    """
    print("[admin_dashboard] Received request for usage metrics report.")
    try:
        # Get 'days' parameter from query string, default to 7
        try:
            days_param = request.args.get('days', '7')
            days = int(days_param)
            if days < 1:
                days = 1 # Minimum 1 day
            elif days > 90: # Add a reasonable upper limit
                days = 90
        except ValueError:
            print(f"[admin_dashboard] Invalid 'days' parameter: {days_param}. Defaulting to 7.")
            days = 7

        print(f"[admin_dashboard] Fetching metrics for the last {days} days.")

        # Calculate start and end dates using imported date and timedelta
        today_local = date.today()
        end_date = today_local # Include today if needed, or use today - 1 day for "up to yesterday"
        start_date = today_local - timedelta(days=days - 1) # N days includes today

        print(f"[admin_dashboard] Date range: {start_date.isoformat()} to {end_date.isoformat()}")

        # Call the function from db_metrics to get data
        metrics_data = get_usage_metrics_for_range(start_date, end_date)

        # Check if data was retrieved (function returns empty list on error)
        # Note: An empty list is also valid if no metrics exist for the range.
        # The success status here indicates the route itself executed ok.
        # We rely on the frontend to display "no data" if metrics_data is empty.

        return jsonify({
            "success": True,
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "data": metrics_data # This list might be empty
        })

    except Exception as e:
        print(f"[admin_dashboard] FATAL ERROR fetching usage metrics report: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": "An unexpected server error occurred while fetching the report.",
            "errors": [str(e)]
        }), 500
