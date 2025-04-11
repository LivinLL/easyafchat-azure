from flask import Blueprint, jsonify, request, current_app
import os
from database import connect_to_db
import traceback
import json
import requests
import hashlib
from datetime import datetime
import time
from chat_handler import DEFAULT_SYSTEM_PROMPT  # Import the default prompt

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

def validate_webhook_url(url):
    """
    Validate if a webhook URL is from an allowed provider
    
    Args:
        url (str): The webhook URL to validate
        
    Returns:
        bool: True if the URL is valid, False otherwise
    """
    if not url:
        return False
        
    # List of allowed webhook providers
    allowed_domains = [
        'zapier.com',
        'make.com',
        'n8n.io',
        'pipedream.net',
        'zoho.com',
        'ifttt.com',
        'automate.io',
        'azure.com',  # Microsoft Power Automate
        'integromat.com',
        'slack.com',
        'automate.io',  # Generic domain
        'localhost',  # For local testing
        '127.0.0.1'   # For local testing
    ]
    
    # Domain patterns to match (e.g., *.app.n8n.cloud)
    domain_patterns = [
        '.app.n8n.cloud',  # Any n8n cloud domain
        '.n8n.io',         # Any n8n.io domain
        '.make.com',       # Any make.com domain
        '.zoho.com'        # Any zoho.com domain
    ]
    
    try:
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        
        # Extract domain from URL
        domain = parsed_url.netloc.lower()
        
        # Check if domain is in the exact allowed list
        if domain in allowed_domains:
            return True
            
        # Check for exact subdomain of allowed domains
        for allowed in allowed_domains:
            if domain.endswith('.' + allowed) or domain == allowed:
                return True
                
        # Check for pattern matches
        for pattern in domain_patterns:
            if domain.endswith(pattern):
                return True
        
        print(f"[webhook] URL validation failed for: {url}, domain: {domain}")
        return False
    except Exception as e:
        print(f"[webhook] Error validating webhook URL: {e}")
        return False

# Create a simple in-memory rate limiter for webhooks
webhook_rate_limits = {}

def check_rate_limit(webhook_url, max_calls=10, period_seconds=60):
    """
    Check if a webhook URL has exceeded its rate limit
    
    Args:
        webhook_url (str): The webhook URL to check
        max_calls (int): Maximum number of calls allowed in the period
        period_seconds (int): The period in seconds
        
    Returns:
        bool: True if rate limit is not exceeded, False otherwise
    """
    from time import time
    current_time = time()
    
    # Create an entry for this webhook if it doesn't exist
    if webhook_url not in webhook_rate_limits:
        webhook_rate_limits[webhook_url] = {
            'calls': [],
            'blocked_until': 0
        }
    
    rate_info = webhook_rate_limits[webhook_url]
    
    # Check if webhook is currently blocked
    if current_time < rate_info['blocked_until']:
        print(f"[webhook] Rate limit exceeded for {webhook_url}, blocked until {rate_info['blocked_until']}")
        return False
    
    # Remove calls that are outside the current period
    rate_info['calls'] = [timestamp for timestamp in rate_info['calls'] 
                         if timestamp > current_time - period_seconds]
    
    # Check if adding this call would exceed the limit
    if len(rate_info['calls']) >= max_calls:
        # Block this webhook for 5 minutes (adjust as needed)
        block_duration = 300  # 5 minutes in seconds
        rate_info['blocked_until'] = current_time + block_duration
        print(f"[webhook] Rate limit exceeded for {webhook_url}, blocking for {block_duration} seconds")
        return False
    
    # Add the current call time
    rate_info['calls'].append(current_time)
    return True

def send_webhook(chatbot_id, event_type, payload_data):
    """
    Send a webhook notification if configured for the chatbot and event
    
    Args:
        chatbot_id (str): The chatbot ID
        event_type (str): The event type (e.g., "new_lead")
        payload_data (dict): The data to include in the payload
        
    Returns:
        bool: True if webhook was sent successfully, False otherwise
    """
    import requests
    import json
    from datetime import datetime
    
    try:
        # Get webhook configuration from database
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholders based on DB type
            placeholder = "%s" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "?"
            
            # Get webhook URL and triggers
            cursor.execute(f"""
                SELECT webhook_url, webhook_triggers
                FROM chatbot_config
                WHERE chatbot_id = {placeholder}
            """, (chatbot_id,))
            
            result = cursor.fetchone()
            
            if not result or not result[0] or not result[1]:
                # No webhook configured or no triggers set
                return False
                
            webhook_url, webhook_triggers = result
            
            # Check if the webhook URL is valid
            if not validate_webhook_url(webhook_url):
                print(f"[webhook] Invalid webhook URL for chatbot {chatbot_id}: {webhook_url}")
                return False
                
            # Parse the comma-separated triggers
            triggers = [t.strip() for t in webhook_triggers.split(',')]
            
            # Check if this event type is in the triggers
            if event_type not in triggers:
                print(f"[webhook] Event type {event_type} not in triggers for chatbot {chatbot_id}")
                return False
                
            # Check rate limit
            if not check_rate_limit(webhook_url):
                print(f"[webhook] Rate limit exceeded for chatbot {chatbot_id}")
                return False
                
            # Create the full payload with metadata
            full_payload = {
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                "chatbot_id": chatbot_id,
                **payload_data
            }
            
            # Send the webhook with retries
            for attempt in range(3):  # Try up to 3 times
                try:
                    response = requests.post(
                        webhook_url, 
                        json=full_payload,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'GoEasyChat-Webhook/1.0'
                        },
                        timeout=3  # 3 second timeout
                    )
                    
                    # Log the webhook attempt
                    print(f"[webhook] Sent {event_type} webhook for chatbot {chatbot_id} - Status: {response.status_code}")
                    
                    # Check if request was successful
                    if response.status_code >= 200 and response.status_code < 300:
                        return True, full_payload, response.status_code, response.text[:100]
                    
                    # If we get here, the request failed but didn't raise an exception
                    print(f"[webhook] Failed with status {response.status_code}: {response.text[:100]}")
                    error_data = {
                        "status_code": response.status_code,
                        "response": response.text[:100]
                    }
                    return False, full_payload, error_data
                    
                except requests.RequestException as e:
                    print(f"[webhook] Request failed on attempt {attempt+1}: {str(e)}")
                    
                # Wait before retrying (exponential backoff)
                if attempt < 2:  # Don't sleep after the last attempt
                    import time
                    time.sleep(2 ** attempt)  # 0, 2, 4 seconds
            
            # If we get here, all attempts failed
            print(f"[webhook] All attempts failed for chatbot {chatbot_id}")
            return False, full_payload, {"error": "All attempts failed"}
                
    except Exception as e:
        print(f"[webhook] Error sending webhook: {e}")
        import traceback
        print(traceback.format_exc())
        return False, None, {"error": str(e)}

@settings_bp.route('/generate-cloudinary-signature', methods=['GET'])
def generate_cloudinary_signature():
    """Generate a signature for Cloudinary uploads"""
    try:
        # Get Cloudinary credentials from environment
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
        api_key = os.environ.get('CLOUDINARY_API_KEY')
        api_secret = os.environ.get('CLOUDINARY_API_SECRET')
        
        # Check if credentials are available
        if not cloud_name or not api_key or not api_secret:
            return jsonify({
                "success": False,
                "error": "Cloudinary credentials not configured"
            }), 500
        
        # Create timestamp and transformation parameters
        timestamp = int(time.time())
        transformation = "w_600,c_limit,q_auto"
        folder = "GoEasyChat"
        
        # Build the string to sign (same format as your PHP implementation)
        signature_string = f"folder={folder}&timestamp={timestamp}&transformation={transformation}{api_secret}"
        
        print(f"[Cloudinary] Generating signature with folder: {folder}")
        print(f"[Cloudinary] Signature string: {signature_string}")

        # Generate SHA-256 signature
        signature = hashlib.sha256(signature_string.encode('utf-8')).hexdigest()
        
        # Return the necessary data for the frontend
        return jsonify({
            "success": True,
            "signature": signature,
            "timestamp": timestamp,
            "api_key": api_key,
            "folder": folder,
            "transformation": transformation,
            "cloud_name": cloud_name
        })
        
    except Exception as e:
        print(f"Error generating Cloudinary signature: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@settings_bp.route('/get-config/<chatbot_id>', methods=['GET'])
def get_chatbot_config(chatbot_id):
    """Get the configuration for a chatbot"""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholders based on DB type
            placeholder = "%s" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "?"
            
            # Get all config values
            cursor.execute(f"""
                SELECT 
                    system_prompt, 
                    chat_title, 
                    chat_subtitle, 
                    lead_form_title, 
                    primary_color, 
                    accent_color, 
                    icon_image_url, 
                    show_lead_form,
                    webhook_url,
                    webhook_triggers
                FROM chatbot_config
                WHERE chatbot_id = {placeholder}
            """, (chatbot_id,))
            
            result = cursor.fetchone()
            
            if not result:
                # Create default config if none exists
                # Use the imported default prompt instead of hardcoding it here
                default_system_prompt = DEFAULT_SYSTEM_PROMPT
                cursor.execute(f"""
                    INSERT INTO chatbot_config (
                        chatbot_id, 
                        system_prompt, 
                        chat_title, 
                        chat_subtitle, 
                        lead_form_title, 
                        primary_color, 
                        accent_color, 
                        show_lead_form
                    ) VALUES (
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}
                    )
                """, (
                    chatbot_id, 
                    default_system_prompt,
                    "Agent Easy",
                    "Hi there! 👋 How can I help you?",
                    "Want us to reach out? Need to keep this chat going? Just fill out the info below.",
                    "#0084ff",
                    "#ffffff",
                    "Yes"
                ))
                
                conn.commit()
                
                # Fetch the newly created config
                cursor.execute(f"""
                    SELECT 
                        system_prompt, 
                        chat_title, 
                        chat_subtitle, 
                        lead_form_title, 
                        primary_color, 
                        accent_color, 
                        icon_image_url, 
                        show_lead_form,
                        webhook_url,
                        webhook_triggers
                    FROM chatbot_config
                    WHERE chatbot_id = {placeholder}
                """, (chatbot_id,))
                
                result = cursor.fetchone()
            
            # Define default values to use when database values are NULL
            default_values = {
                # Use the imported default system prompt
                "system_prompt": DEFAULT_SYSTEM_PROMPT,
                "chat_title": "Agent Easy",
                "chat_subtitle": "Hi there! 👋 How can I help you?",
                "lead_form_title": "Want us to reach out? Need to keep this chat going? Just fill out the info below.",
                "primary_color": "#0084ff",
                "accent_color": "#ffffff",
                "show_lead_form": "Yes"
            }
            
            # Convert to dictionary with named keys, using defaults for NULL values
            config = {
                "system_prompt": result[0] if result[0] else default_values["system_prompt"],
                "chat_title": result[1] if result[1] else default_values["chat_title"],
                "chat_subtitle": result[2] if result[2] else default_values["chat_subtitle"],
                "lead_form_title": result[3] if result[3] else default_values["lead_form_title"],
                "primary_color": result[4] if result[4] else default_values["primary_color"],
                "accent_color": result[5] if result[5] else default_values["accent_color"],
                "icon_image_url": result[6] or "",
                "show_lead_form": result[7] if result[7] else default_values["show_lead_form"],
                "webhook_url": result[8] or "",
                "webhook_triggers": result[9] or ""
            }
            
            return jsonify({"success": True, "config": config})
            
    except Exception as e:
        print(f"Error getting chatbot config: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@settings_bp.route('/update/<chatbot_id>', methods=['POST'])
def update_chatbot_config(chatbot_id):
    """Update a specific configuration setting for a chatbot"""
    try:
        data = request.json
        
        if not data or 'setting' not in data or 'value' not in data:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
            
        setting = data['setting']
        value = data['value']
        
        # Validate settings
        if setting == 'webhook_url' and value:
            if not validate_webhook_url(value):
                return jsonify({
                    "success": False, 
                    "error": "Invalid webhook URL. Please use a URL from a supported integration provider."
                }), 400
        
        # List of allowed settings to update
        allowed_settings = [
            'system_prompt', 
            'chat_title', 
            'chat_subtitle', 
            'lead_form_title', 
            'primary_color', 
            'accent_color', 
            'icon_image_url', 
            'show_lead_form',
            'webhook_url',
            'webhook_triggers'
        ]
        
        if setting not in allowed_settings:
            return jsonify({"success": False, "error": f"Setting '{setting}' cannot be updated"}), 400
            
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholders based on DB type
            placeholder = "%s" if os.getenv('DB_TYPE', '').lower() == 'postgresql' else "?"
            
            # Check if config exists
            cursor.execute(f"""
                SELECT COUNT(*) FROM chatbot_config WHERE chatbot_id = {placeholder}
            """, (chatbot_id,))
            
            if cursor.fetchone()[0] == 0:
                # Create default config if none exists
                default_system_prompt = (
                    "You are a helpful AI assistant for the website. Your name is d-A-v-I-d (pronounced David). "
                    "You are friendly, respectful, and provide concise responses. If you don't know something, "
                    "admit it rather than making up information. Answer the user's questions based on the website content "
                    "when possible. If the user asks for personal information or tries to make a purchase, offer to "
                    "collect their contact information using the lead form so a human can follow up with them."
                )
                
                cursor.execute(f"""
                    INSERT INTO chatbot_config (
                        chatbot_id, 
                        system_prompt, 
                        chat_title, 
                        chat_subtitle, 
                        lead_form_title, 
                        primary_color, 
                        accent_color, 
                        show_lead_form
                    ) VALUES (
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}
                    )
                """, (
                    chatbot_id, 
                    default_system_prompt,
                    "Agent Easy",
                    "Hi there! 👋 How can I help you?",
                    "Want us to reach out? Need to keep this chat going? Just fill out the info below.",
                    "#0084ff",
                    "#ffffff",
                    "Yes"
                ))
                
                conn.commit()
            
            # Update the specific setting
            cursor.execute(f"""
                UPDATE chatbot_config 
                SET {setting} = {placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE chatbot_id = {placeholder}
            """, (value, chatbot_id))
            
            conn.commit()
            
            return jsonify({"success": True})
            
    except Exception as e:
        print(f"Error updating chatbot config: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@settings_bp.route('/test-webhook/<chatbot_id>', methods=['POST'])
def test_webhook(chatbot_id):
    """Test a webhook by sending a dummy lead payload"""
    try:
        # Create a dummy lead payload
        dummy_payload = {
            "lead": {
                "name": "Test User",
                "email": "test@example.com",
                "phone": "555-123-4567",
                "message": "This is a test lead from GoEasyChat webhook testing."
            }
        }
        
        # Send the test webhook
        success, payload, response_data, *_ = send_webhook(chatbot_id, "new_lead", dummy_payload)
        
        if success:
            return jsonify({
                "success": True,
                "message": "Webhook test was successful",
                "payload": payload,
                "response": response_data
            })
        else:
            return jsonify({
                "success": False,
                "error": "Webhook test failed",
                "payload": payload,
                "details": response_data
            }), 400
            
    except Exception as e:
        print(f"Error testing webhook: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
