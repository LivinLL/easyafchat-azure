from flask import Blueprint, current_app
import requests
import time
from datetime import datetime
from database import connect_to_db
import os
import traceback

# Create the blueprint
webhook_blueprint = Blueprint('webhook', __name__)

# Dictionary to store rate limit information
webhook_rate_limits = {}

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
    current_time = time.time()
    
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
            
            if not result or not result[0]:
                # No webhook configured
                return False
                
            webhook_url, webhook_triggers = result
            
            # Check if the webhook URL is valid
            if not validate_webhook_url(webhook_url):
                print(f"[webhook] Invalid webhook URL for chatbot {chatbot_id}: {webhook_url}")
                return False
                
            # For "new_bot_claimed" events, bypass the trigger check - this is a system event
            if event_type != "new_bot_claimed":
                # For all other events, check if the event type is in the triggers list
                if not webhook_triggers:
                    print(f"[webhook] No webhook triggers configured for chatbot {chatbot_id}")
                    return False
                    
                # Parse the comma-separated triggers
                triggers = [t.strip() for t in webhook_triggers.split(',')]
                
                # Check if this specific event type is in the triggers
                if event_type not in triggers:
                    print(f"[webhook] Event type {event_type} not in triggers for chatbot {chatbot_id}")
                    return False
            else:
                print(f"[webhook] Processing special event type {event_type} - bypassing trigger check")
                
            # Check rate limit
            if not check_rate_limit(webhook_url):
                print(f"[webhook] Rate limit exceeded for chatbot {chatbot_id}")
                return False
                
            # Create the full payload with metadata
            full_payload = {
                "event_type": event_type,  # Include only the specific event type
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
                        return True
                    
                    # If we get here, the request failed but didn't raise an exception
                    print(f"[webhook] Failed with status {response.status_code}: {response.text[:100]}")
                    
                except requests.RequestException as e:
                    print(f"[webhook] Request failed on attempt {attempt+1}: {str(e)}")
                    
                # Wait before retrying (exponential backoff)
                if attempt < 2:  # Don't sleep after the last attempt
                    time.sleep(2 ** attempt)  # 0, 2, 4 seconds
            
            # If we get here, all attempts failed
            print(f"[webhook] All attempts failed for chatbot {chatbot_id}")
            return False
                
    except Exception as e:
        print(f"[webhook] Error sending webhook: {e}")
        print(traceback.format_exc())
        return False

# Initialization function to set up the blueprint
def init_webhook_blueprint():
    """
    Initialize the webhook blueprint.
    
    Returns:
        tuple: (Blueprint object, send_webhook function)
    """
    # Return both the blueprint and the function to allow direct access to send_webhook
    return webhook_blueprint, send_webhook
