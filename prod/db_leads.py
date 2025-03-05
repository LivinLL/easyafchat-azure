from flask import Blueprint, request, jsonify, send_file, Response
import os
import uuid
import csv
import io
from datetime import datetime
from contextlib import closing
from database import connect_to_db

# Create Blueprint for leads management
leads_blueprint = Blueprint('leads', __name__)

# Global variable to store references to OpenAI and Pinecone clients
openai_client = None
pinecone_client = None

def init_leads_blueprint(app_openai_client, app_pinecone_client):
    """Initialize the blueprint with the OpenAI and Pinecone clients"""
    global openai_client, pinecone_client
    openai_client = app_openai_client
    pinecone_client = app_pinecone_client
    return leads_blueprint

def save_lead(chatbot_id, thread_id, name, email, phone, initial_question):
    """
    Save lead information to the database
    
    Args:
        chatbot_id: The ID of the chatbot that captured the lead
        thread_id: The conversation thread ID
        name: User's name (optional)
        email: User's email (optional)
        phone: User's phone number (optional)
        initial_question: First question asked by the user
        
    Returns:
        lead_id: The ID of the newly created lead
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            
            # Use appropriate placeholders based on database type
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    INSERT INTO leads 
                    (chatbot_id, thread_id, name, email, phone, initial_question, created_at, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING lead_id
                ''', (chatbot_id, thread_id, name, email, phone, initial_question, now, 'new'))
                lead_id = cursor.fetchone()[0]
            else:
                cursor.execute('''
                    INSERT INTO leads 
                    (chatbot_id, thread_id, name, email, phone, initial_question, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (chatbot_id, thread_id, name, email, phone, initial_question, now, 'new'))
                lead_id = cursor.lastrowid
                
            return lead_id
    except Exception as e:
        print(f"Error saving lead: {e}")
        return None

def get_leads_by_chatbot(chatbot_id, status=None, limit=100, offset=0):
    """
    Get leads for a specific chatbot with optional filtering by status
    
    Args:
        chatbot_id: The ID of the chatbot
        status: Filter by status (optional)
        limit: Maximum number of leads to return
        offset: Number of leads to skip for pagination
        
    Returns:
        List of lead records
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Build query based on whether status filter is provided
            query = "SELECT * FROM leads WHERE chatbot_id = "
            params = [chatbot_id]
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                query += "%s"
                if status:
                    query += " AND status = %s"
                    params.append(status)
                query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
            else:
                query += "?"
                if status:
                    query += " AND status = ?"
                    params.append(status)
                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor.execute(query, params)
            leads = cursor.fetchall()
            
            # Get column names
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                columns = [desc[0] for desc in cursor.description]
            else:
                columns = [desc[0] for desc in cursor.description]
            
            # Convert to list of dictionaries
            result = []
            for lead in leads:
                lead_dict = dict(zip(columns, lead))
                result.append(lead_dict)
                
            return result
    except Exception as e:
        print(f"Error getting leads: {e}")
        return []

def update_lead_status(lead_id, status, notes=None):
    """
    Update the status and notes for a lead
    
    Args:
        lead_id: The ID of the lead to update
        status: New status value
        notes: Optional notes to add
        
    Returns:
        Boolean indicating success
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                if notes:
                    cursor.execute('''
                        UPDATE leads
                        SET status = %s, notes = %s, updated_at = %s
                        WHERE lead_id = %s
                    ''', (status, notes, datetime.now(), lead_id))
                else:
                    cursor.execute('''
                        UPDATE leads
                        SET status = %s, updated_at = %s
                        WHERE lead_id = %s
                    ''', (status, datetime.now(), lead_id))
            else:
                if notes:
                    cursor.execute('''
                        UPDATE leads
                        SET status = ?, notes = ?, updated_at = ?
                        WHERE lead_id = ?
                    ''', (status, notes, datetime.now(), lead_id))
                else:
                    cursor.execute('''
                        UPDATE leads
                        SET status = ?, updated_at = ?
                        WHERE lead_id = ?
                    ''', (status, datetime.now(), lead_id))
            
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating lead status: {e}")
        return False

def export_leads_to_csv(chatbot_id, status=None):
    """
    Export leads for a chatbot to CSV format
    
    Args:
        chatbot_id: The ID of the chatbot
        status: Optional status filter
        
    Returns:
        CSV content as string
    """
    try:
        # Get leads
        leads = get_leads_by_chatbot(chatbot_id, status, limit=1000)
        
        if not leads:
            return None
            
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        header = ['ID', 'Name', 'Email', 'Phone', 'Initial Question', 'Date', 'Status', 'Notes']
        writer.writerow(header)
        
        # Write data rows
        for lead in leads:
            # Format date for better readability
            created_at = lead.get('created_at')
            if isinstance(created_at, datetime):
                formatted_date = created_at.strftime('%Y-%m-%d %H:%M:%S')
            else:
                formatted_date = str(created_at)
            
            row = [
                lead.get('lead_id'),
                lead.get('name', ''),
                lead.get('email', ''),
                lead.get('phone', ''),
                lead.get('initial_question', ''),
                formatted_date,
                lead.get('status', ''),
                lead.get('notes', '')
            ]
            writer.writerow(row)
        
        return output.getvalue()
    except Exception as e:
        print(f"Error exporting leads to CSV: {e}")
        return None

def get_chatbot_config(chatbot_id):
    """
    Get chatbot configuration, including lead form settings
    
    Args:
        chatbot_id: The ID of the chatbot
    
    Returns:
        Dictionary with chatbot configuration
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # First check if a config exists
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                cursor.execute('''
                    SELECT * FROM chatbot_config
                    WHERE chatbot_id = %s
                ''', (chatbot_id,))
            else:
                cursor.execute('''
                    SELECT * FROM chatbot_config
                    WHERE chatbot_id = ?
                ''', (chatbot_id,))
                
            row = cursor.fetchone()
            
            # If no configuration exists, create default one
            if not row:
                # Create a default configuration
                if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                    cursor.execute('''
                        INSERT INTO chatbot_config
                        (chatbot_id, lead_form_title, created_at, updated_at)
                        VALUES (%s, %s, %s, %s)
                        RETURNING *
                    ''', (
                        chatbot_id,
                        'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
                        datetime.now(),
                        datetime.now()
                    ))
                    row = cursor.fetchone()
                else:
                    cursor.execute('''
                        INSERT INTO chatbot_config
                        (chatbot_id, lead_form_title, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        chatbot_id,
                        'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
                        datetime.now(),
                        datetime.now()
                    ))
                    
                    # Get the newly created config
                    cursor.execute('''
                        SELECT * FROM chatbot_config
                        WHERE chatbot_id = ?
                    ''', (chatbot_id,))
                    row = cursor.fetchone()
            
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            
            # Convert to dictionary
            config = dict(zip(columns, row)) if row else {}
            
            return config
    except Exception as e:
        print(f"Error getting chatbot config: {e}")
        return {
            'lead_form_title': 'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
            'show_lead_form': 'Yes'
        }

# Routes for the leads blueprint
@leads_blueprint.route('/embed-save-lead', methods=['POST'])
def handle_lead_submission():
    """
    API endpoint to handle lead form submissions from the chatbot
    """
    try:
        data = request.json
        chatbot_id = data.get('chatbot_id')
        thread_id = data.get('thread_id')
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        initial_question = data.get('initial_question')
        
        if not chatbot_id or not thread_id:
            return jsonify({"error": "Missing required fields"}), 400
            
        lead_id = save_lead(chatbot_id, thread_id, name, email, phone, initial_question)
        
        if lead_id:
            return jsonify({
                "success": True,
                "lead_id": lead_id
            })
        else:
            return jsonify({"error": "Failed to save lead"}), 500
    except Exception as e:
        print(f"Error in lead submission: {e}")
        return jsonify({"error": "Internal server error"}), 500

@leads_blueprint.route('/leads/export/<chatbot_id>', methods=['GET'])
def export_leads(chatbot_id):
    """
    API endpoint to export leads to CSV
    """
    try:
        status = request.args.get('status')
        filename = f"leads_{chatbot_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        
        csv_content = export_leads_to_csv(chatbot_id, status)
        
        if not csv_content:
            return jsonify({"error": "No leads found or error generating CSV"}), 404
        
        # Create a response with CSV content
        response = Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
        
        return response
    except Exception as e:
        print(f"Error exporting leads: {e}")
        return jsonify({"error": "Internal server error"}), 500

@leads_blueprint.route('/leads/<chatbot_id>', methods=['GET'])
def get_leads(chatbot_id):
    """
    API endpoint to get leads for a chatbot
    """
    try:
        status = request.args.get('status')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        leads = get_leads_by_chatbot(chatbot_id, status, limit, offset)
        
        return jsonify({
            "leads": leads,
            "count": len(leads)
        })
    except Exception as e:
        print(f"Error getting leads: {e}")
        return jsonify({"error": "Internal server error"}), 500

@leads_blueprint.route('/leads/<lead_id>', methods=['PUT'])
def update_lead(lead_id):
    """
    API endpoint to update lead status and notes
    """
    try:
        data = request.json
        status = data.get('status')
        notes = data.get('notes')
        
        if not status:
            return jsonify({"error": "Status is required"}), 400
            
        success = update_lead_status(lead_id, status, notes)
        
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to update lead or lead not found"}), 404
    except Exception as e:
        print(f"Error updating lead: {e}")
        return jsonify({"error": "Internal server error"}), 500

@leads_blueprint.route('/config/lead-form/<chatbot_id>', methods=['GET'])
def get_lead_form_config(chatbot_id):
    """
    API endpoint to get lead form configuration
    """
    try:
        config = get_chatbot_config(chatbot_id)
        
        # Return only lead form related configuration
        lead_form_config = {
            'lead_form_title': config.get('lead_form_title', 'Want us to reach out? Need to keep this chat going? Just fill out the info below.')
        }
        
        return jsonify(lead_form_config)
    except Exception as e:
        print(f"Error getting lead form config: {e}")
        return jsonify({"error": "Internal server error"}), 500