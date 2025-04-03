from flask import Blueprint, request, jsonify, current_app, g
from database import connect_to_db
import os
import json
import time
import datetime
import traceback
from typing import Dict, Any, List, Optional, Tuple, Union

# Create the blueprint
metrics_blueprint = Blueprint('metrics', __name__)

# Global variables
DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'easychat')

def init_metrics_blueprint():
    """Initialize the metrics blueprint"""
    print("[db_metrics] Initializing metrics blueprint")
    return metrics_blueprint

def save_chat_message(
    chatbot_id: str, 
    thread_id: str, 
    user_message: str, 
    assistant_response: str, 
    prompt_tokens: int = 0, 
    completion_tokens: int = 0, 
    total_tokens: int = 0,
    ip_address: str = None, 
    user_agent: str = None
) -> bool:
    """
    Save a chat message exchange to the database
    
    Args:
        chatbot_id: The ID of the chatbot
        thread_id: The thread ID for this conversation
        user_message: The message sent by the user
        assistant_response: The response from the assistant
        prompt_tokens: Number of tokens in the prompt
        completion_tokens: Number of tokens in the completion/response
        total_tokens: Total tokens used (prompt + completion)
        ip_address: User's IP address (optional)
        user_agent: User's browser user agent (optional)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"[db_metrics] Saving chat message for chatbot {chatbot_id}, thread {thread_id}")
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder style based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                query = f"""
                    INSERT INTO {DB_SCHEMA}.chat_messages 
                    (chatbot_id, thread_id, user_message, assistant_response, 
                     prompt_tokens, completion_tokens, total_tokens, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
            else:
                # SQLite uses ? placeholders
                query = """
                    INSERT INTO chat_messages 
                    (chatbot_id, thread_id, user_message, assistant_response, 
                     prompt_tokens, completion_tokens, total_tokens, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            
            # Execute the query with parameters
            cursor.execute(query, (
                chatbot_id, 
                thread_id, 
                user_message, 
                assistant_response, 
                prompt_tokens, 
                completion_tokens, 
                total_tokens,
                ip_address, 
                user_agent
            ))
            
            conn.commit()
            print(f"[db_metrics] Chat message saved successfully for {chatbot_id}")
            return True
            
    except Exception as e:
        print(f"[db_metrics] Error saving chat message: {str(e)}")
        print(traceback.format_exc())
        return False

def update_user_feedback(message_id: int, feedback: str) -> bool:
    """
    Update the user feedback for a specific message
    
    Args:
        message_id: The ID of the message to update
        feedback: The feedback value (e.g., "positive", "negative")
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"[db_metrics] Updating feedback for message {message_id} to '{feedback}'")
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder style based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                query = f"""
                    UPDATE {DB_SCHEMA}.chat_messages 
                    SET user_feedback = %s
                    WHERE message_id = %s
                """
            else:
                # SQLite uses ? placeholders
                query = """
                    UPDATE chat_messages 
                    SET user_feedback = ?
                    WHERE message_id = ?
                """
            
            # Execute the query with parameters
            cursor.execute(query, (feedback, message_id))
            
            # Check if any rows were affected
            if conn.total_changes > 0:
                conn.commit()
                print(f"[db_metrics] Feedback updated successfully for message {message_id}")
                return True
            else:
                print(f"[db_metrics] No message found with ID {message_id}")
                return False
            
    except Exception as e:
        print(f"[db_metrics] Error updating user feedback: {str(e)}")
        print(traceback.format_exc())
        return False

def get_chatbot_message_count(chatbot_id: str) -> int:
    """
    Get the total number of messages for a specific chatbot
    
    Args:
        chatbot_id: The ID of the chatbot
        
    Returns:
        int: Total message count
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder style based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                query = f"""
                    SELECT COUNT(*) 
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s
                """
            else:
                # SQLite uses ? placeholders
                query = """
                    SELECT COUNT(*) 
                    FROM chat_messages 
                    WHERE chatbot_id = ?
                """
            
            # Execute the query with parameters
            cursor.execute(query, (chatbot_id,))
            
            # Fetch the result
            result = cursor.fetchone()
            return result[0] if result else 0
            
    except Exception as e:
        print(f"[db_metrics] Error getting message count: {str(e)}")
        return 0

def get_thread_messages(thread_id: str) -> List[Dict[str, Any]]:
    """
    Get all messages for a specific thread
    
    Args:
        thread_id: The thread ID
        
    Returns:
        List[Dict]: List of message objects
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder style based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                query = f"""
                    SELECT message_id, chatbot_id, thread_id, user_message, 
                           assistant_response, prompt_tokens, completion_tokens, 
                           total_tokens, user_feedback, created_at
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE thread_id = %s
                    ORDER BY created_at ASC
                """
            else:
                # SQLite uses ? placeholders
                query = """
                    SELECT message_id, chatbot_id, thread_id, user_message, 
                           assistant_response, prompt_tokens, completion_tokens, 
                           total_tokens, user_feedback, created_at
                    FROM chat_messages 
                    WHERE thread_id = ?
                    ORDER BY created_at ASC
                """
            
            # Execute the query with parameters
            cursor.execute(query, (thread_id,))
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = [column[0] for column in cursor.description]
            messages = []
            
            for row in rows:
                message = dict(zip(columns, row))
                
                # Convert datetime object to string if needed
                if isinstance(message.get('created_at'), (datetime.datetime, datetime.date)):
                    message['created_at'] = message['created_at'].isoformat()
                
                messages.append(message)
                
            return messages
            
    except Exception as e:
        print(f"[db_metrics] Error getting thread messages: {str(e)}")
        print(traceback.format_exc())
        return []

def get_chatbot_threads(chatbot_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Get all threads for a specific chatbot
    
    Args:
        chatbot_id: The ID of the chatbot
        limit: Maximum number of threads to return
        offset: Offset for pagination
        
    Returns:
        List[Dict]: List of thread objects with summary info
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder style based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                query = f"""
                    SELECT thread_id, 
                           MIN(created_at) as started_at,
                           MAX(created_at) as last_activity,
                           COUNT(*) as message_count
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s
                    GROUP BY thread_id
                    ORDER BY last_activity DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (chatbot_id, limit, offset))
            else:
                # SQLite uses ? placeholders
                query = """
                    SELECT thread_id, 
                           MIN(created_at) as started_at,
                           MAX(created_at) as last_activity,
                           COUNT(*) as message_count
                    FROM chat_messages 
                    WHERE chatbot_id = ?
                    GROUP BY thread_id
                    ORDER BY last_activity DESC
                    LIMIT ? OFFSET ?
                """
                cursor.execute(query, (chatbot_id, limit, offset))
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = [column[0] for column in cursor.description]
            threads = []
            
            for row in rows:
                thread = dict(zip(columns, row))
                
                # Convert datetime objects to strings if needed
                if isinstance(thread.get('started_at'), (datetime.datetime, datetime.date)):
                    thread['started_at'] = thread['started_at'].isoformat()
                
                if isinstance(thread.get('last_activity'), (datetime.datetime, datetime.date)):
                    thread['last_activity'] = thread['last_activity'].isoformat()
                
                threads.append(thread)
                
            return threads
            
    except Exception as e:
        print(f"[db_metrics] Error getting chatbot threads: {str(e)}")
        print(traceback.format_exc())
        return []

def get_chatbot_token_usage(chatbot_id: str, days: int = 30) -> Dict[str, int]:
    """
    Get token usage statistics for a chatbot over the specified number of days
    
    Args:
        chatbot_id: The ID of the chatbot
        days: Number of days to look back
        
    Returns:
        Dict: Token usage statistics
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Calculate the date cutoff
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL date calculation
                query = f"""
                    SELECT 
                        SUM(prompt_tokens) as total_prompt_tokens,
                        SUM(completion_tokens) as total_completion_tokens,
                        SUM(total_tokens) as total_tokens
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s
                    AND created_at >= NOW() - INTERVAL '{days} days'
                """
                cursor.execute(query, (chatbot_id,))
            else:
                # SQLite date calculation
                query = """
                    SELECT 
                        SUM(prompt_tokens) as total_prompt_tokens,
                        SUM(completion_tokens) as total_completion_tokens,
                        SUM(total_tokens) as total_tokens
                    FROM chat_messages 
                    WHERE chatbot_id = ?
                    AND created_at >= datetime('now', ?)
                """
                cursor.execute(query, (chatbot_id, f'-{days} days'))
            
            # Fetch the result
            result = cursor.fetchone()
            
            if result:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, result))
            else:
                return {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0
                }
            
    except Exception as e:
        print(f"[db_metrics] Error getting token usage: {str(e)}")
        print(traceback.format_exc())
        return {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0
        }

def get_daily_token_usage(chatbot_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get daily token usage for a chatbot over the specified number of days
    
    Args:
        chatbot_id: The ID of the chatbot
        days: Number of days to look back
        
    Returns:
        List[Dict]: Daily token usage statistics
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL date functions
                query = f"""
                    SELECT 
                        DATE(created_at) as date,
                        SUM(prompt_tokens) as prompt_tokens,
                        SUM(completion_tokens) as completion_tokens,
                        SUM(total_tokens) as total_tokens,
                        COUNT(*) as message_count
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s
                    AND created_at >= NOW() - INTERVAL '{days} days'
                    GROUP BY DATE(created_at)
                    ORDER BY DATE(created_at) ASC
                """
                cursor.execute(query, (chatbot_id,))
            else:
                # SQLite date functions
                query = """
                    SELECT 
                        DATE(created_at) as date,
                        SUM(prompt_tokens) as prompt_tokens,
                        SUM(completion_tokens) as completion_tokens,
                        SUM(total_tokens) as total_tokens,
                        COUNT(*) as message_count
                    FROM chat_messages 
                    WHERE chatbot_id = ?
                    AND created_at >= datetime('now', ?)
                    GROUP BY DATE(created_at)
                    ORDER BY DATE(created_at) ASC
                """
                cursor.execute(query, (chatbot_id, f'-{days} days'))
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = [column[0] for column in cursor.description]
            daily_usage = []
            
            for row in rows:
                usage = dict(zip(columns, row))
                daily_usage.append(usage)
                
            return daily_usage
            
    except Exception as e:
        print(f"[db_metrics] Error getting daily token usage: {str(e)}")
        print(traceback.format_exc())
        return []

def get_message_by_id(message_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a specific message by ID
    
    Args:
        message_id: The ID of the message
        
    Returns:
        Dict or None: Message data if found, None otherwise
    """
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholder style based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                query = f"""
                    SELECT message_id, chatbot_id, thread_id, user_message, 
                           assistant_response, prompt_tokens, completion_tokens, 
                           total_tokens, user_feedback, created_at
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE message_id = %s
                """
            else:
                # SQLite uses ? placeholders
                query = """
                    SELECT message_id, chatbot_id, thread_id, user_message, 
                           assistant_response, prompt_tokens, completion_tokens, 
                           total_tokens, user_feedback, created_at
                    FROM chat_messages 
                    WHERE message_id = ?
                """
            
            # Execute the query with parameters
            cursor.execute(query, (message_id,))
            
            # Fetch the result
            row = cursor.fetchone()
            
            if row:
                # Convert row to dictionary
                columns = [column[0] for column in cursor.description]
                message = dict(zip(columns, row))
                
                # Convert datetime object to string if needed
                if isinstance(message.get('created_at'), (datetime.datetime, datetime.date)):
                    message['created_at'] = message['created_at'].isoformat()
                
                return message
            else:
                return None
            
    except Exception as e:
        print(f"[db_metrics] Error getting message by ID: {str(e)}")
        print(traceback.format_exc())
        return None

# Route for submitting user feedback on a message
@metrics_blueprint.route('/message-feedback', methods=['POST'])
def handle_message_feedback():
    """API endpoint to handle message feedback submission"""
    try:
        data = request.json
        
        # Validate required fields
        if not data or 'message_id' not in data or 'feedback' not in data:
            return jsonify({
                "status": "error",
                "message": "Missing required fields: message_id and feedback"
            }), 400
            
        message_id = data['message_id']
        feedback = data['feedback']
        
        # Validate feedback value
        valid_feedback = ['positive', 'negative', 'neutral']
        if feedback not in valid_feedback:
            return jsonify({
                "status": "error",
                "message": f"Invalid feedback value. Must be one of: {', '.join(valid_feedback)}"
            }), 400
            
        # Get message to verify it exists
        message = get_message_by_id(message_id)
        if not message:
            return jsonify({
                "status": "error",
                "message": f"Message with ID {message_id} not found"
            }), 404
            
        # Update the feedback
        success = update_user_feedback(message_id, feedback)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Feedback recorded successfully"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to record feedback"
            }), 500
            
    except Exception as e:
        print(f"[db_metrics] Error handling message feedback: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500

# Route for getting basic metrics for a chatbot
@metrics_blueprint.route('/chatbot-metrics/<chatbot_id>', methods=['GET'])
def get_chatbot_metrics(chatbot_id):
    """API endpoint to get basic metrics for a chatbot"""
    try:
        # Get token usage for the last 30 days
        token_usage = get_chatbot_token_usage(chatbot_id)
        
        # Get message count
        message_count = get_chatbot_message_count(chatbot_id)
        
        # Get thread count (unique thread_ids)
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different query based on database type
            if DB_TYPE.lower() == 'postgresql':
                query = f"""
                    SELECT COUNT(DISTINCT thread_id) 
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s
                """
                cursor.execute(query, (chatbot_id,))
            else:
                query = """
                    SELECT COUNT(DISTINCT thread_id) 
                    FROM chat_messages 
                    WHERE chatbot_id = ?
                """
                cursor.execute(query, (chatbot_id,))
            
            thread_count = cursor.fetchone()[0]
        
        # Get feedback counts
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different query based on database type
            if DB_TYPE.lower() == 'postgresql':
                query = f"""
                    SELECT user_feedback, COUNT(*) 
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s AND user_feedback IS NOT NULL
                    GROUP BY user_feedback
                """
                cursor.execute(query, (chatbot_id,))
            else:
                query = """
                    SELECT user_feedback, COUNT(*) 
                    FROM chat_messages 
                    WHERE chatbot_id = ? AND user_feedback IS NOT NULL
                    GROUP BY user_feedback
                """
                cursor.execute(query, (chatbot_id,))
            
            feedback_rows = cursor.fetchall()
            
            feedback_counts = {
                "positive": 0,
                "negative": 0,
                "neutral": 0
            }
            
            for row in feedback_rows:
                feedback_type, count = row
                if feedback_type in feedback_counts:
                    feedback_counts[feedback_type] = count
        
        # Compile all metrics into response
        metrics = {
            "chatbot_id": chatbot_id,
            "total_messages": message_count,
            "total_threads": thread_count,
            "token_usage": token_usage,
            "feedback": feedback_counts
        }
        
        return jsonify({
            "status": "success",
            "data": metrics
        })
        
    except Exception as e:
        print(f"[db_metrics] Error getting chatbot metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500

# Route for getting chatbot threads with time filter
@metrics_blueprint.route('/chatbot-threads/<chatbot_id>', methods=['GET'])
def get_chatbot_threads_route(chatbot_id):
    """API endpoint to get threads for a chatbot with optional time filter"""
    try:
        # Get query parameters
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        since = request.args.get('since', None)
        
        # Parse the since parameter (30d, 7d, etc.)
        days_cutoff = 30  # Default to 30 days
        if since:
            if since.endswith('d'):
                try:
                    days_cutoff = int(since[:-1])
                except ValueError:
                    pass
        
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different query based on database type
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL query with date filtering
                query = f"""
                    SELECT thread_id, 
                           MIN(created_at) as started_at,
                           MAX(created_at) as last_activity,
                           COUNT(*) as message_count
                    FROM {DB_SCHEMA}.chat_messages 
                    WHERE chatbot_id = %s
                    AND created_at >= NOW() - INTERVAL '{days_cutoff} days'
                    GROUP BY thread_id
                    ORDER BY last_activity DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (chatbot_id, limit, offset))
            else:
                # SQLite query with date filtering
                query = """
                    SELECT thread_id, 
                           MIN(created_at) as started_at,
                           MAX(created_at) as last_activity,
                           COUNT(*) as message_count
                    FROM chat_messages 
                    WHERE chatbot_id = ?
                    AND created_at >= datetime('now', ?)
                    GROUP BY thread_id
                    ORDER BY last_activity DESC
                    LIMIT ? OFFSET ?
                """
                cursor.execute(query, (chatbot_id, f'-{days_cutoff} days', limit, offset))
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = [column[0] for column in cursor.description]
            threads = []
            
            for row in rows:
                thread = dict(zip(columns, row))
                
                # Convert datetime objects to strings if needed
                if isinstance(thread.get('started_at'), (datetime.datetime, datetime.date)):
                    thread['started_at'] = thread['started_at'].isoformat()
                
                if isinstance(thread.get('last_activity'), (datetime.datetime, datetime.date)):
                    thread['last_activity'] = thread['last_activity'].isoformat()
                
                threads.append(thread)
            
            return jsonify({
                "status": "success",
                "threads": threads
            })
            
    except Exception as e:
        print(f"[db_metrics] Error getting chatbot threads: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": "Error retrieving threads",
            "error": str(e)
        }), 500

# Route for getting messages for a specific thread
# Used on dashboard for Chat Logs tab
@metrics_blueprint.route('/thread-messages/<thread_id>', methods=['GET'])
def get_thread_messages_route(thread_id):
    """API endpoint to get messages for a specific thread"""
    try:
        # Get query parameters
        limit = request.args.get('limit', None, type=int)
        
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different query based on database type and limit
            if DB_TYPE.lower() == 'postgresql':
                # PostgreSQL query
                if limit:
                    query = f"""
                        SELECT message_id, chatbot_id, thread_id, user_message, 
                               assistant_response, prompt_tokens, completion_tokens, 
                               total_tokens, user_feedback, created_at
                        FROM {DB_SCHEMA}.chat_messages 
                        WHERE thread_id = %s
                        ORDER BY created_at ASC
                        LIMIT %s
                    """
                    cursor.execute(query, (thread_id, limit))
                else:
                    query = f"""
                        SELECT message_id, chatbot_id, thread_id, user_message, 
                               assistant_response, prompt_tokens, completion_tokens, 
                               total_tokens, user_feedback, created_at
                        FROM {DB_SCHEMA}.chat_messages 
                        WHERE thread_id = %s
                        ORDER BY created_at ASC
                    """
                    cursor.execute(query, (thread_id,))
            else:
                # SQLite query
                if limit:
                    query = """
                        SELECT message_id, chatbot_id, thread_id, user_message, 
                               assistant_response, prompt_tokens, completion_tokens, 
                               total_tokens, user_feedback, created_at
                        FROM chat_messages 
                        WHERE thread_id = ?
                        ORDER BY created_at ASC
                        LIMIT ?
                    """
                    cursor.execute(query, (thread_id, limit))
                else:
                    query = """
                        SELECT message_id, chatbot_id, thread_id, user_message, 
                               assistant_response, prompt_tokens, completion_tokens, 
                               total_tokens, user_feedback, created_at
                        FROM chat_messages 
                        WHERE thread_id = ?
                        ORDER BY created_at ASC
                    """
                    cursor.execute(query, (thread_id,))
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = [column[0] for column in cursor.description]
            messages = []
            
            for row in rows:
                message = dict(zip(columns, row))
                
                # Convert datetime object to string if needed
                if isinstance(message.get('created_at'), (datetime.datetime, datetime.date)):
                    message['created_at'] = message['created_at'].isoformat()
                
                messages.append(message)
            
            return jsonify({
                "status": "success",
                "thread_id": thread_id,
                "messages": messages
            })
            
    except Exception as e:
        print(f"[db_metrics] Error getting thread messages: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": "Error retrieving messages",
            "error": str(e)
        }), 500

# Route for getting daily usage over time
@metrics_blueprint.route('/daily-metrics/<chatbot_id>', methods=['GET'])
def get_daily_metrics(chatbot_id):
    """API endpoint to get daily metrics for a chatbot"""
    try:
        # Get days parameter (default 30 days)
        days = request.args.get('days', 30, type=int)
        
        # Validate days parameter
        if days < 1 or days > 365:
            return jsonify({
                "status": "error",
                "message": "Days parameter must be between 1 and 365"
            }), 400
        
        # Get daily token usage
        daily_usage = get_daily_token_usage(chatbot_id, days)
        
        return jsonify({
            "status": "success",
            "data": daily_usage
        })
        
    except Exception as e:
        print(f"[db_metrics] Error getting daily metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500
