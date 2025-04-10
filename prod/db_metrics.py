from flask import Blueprint, request, jsonify, current_app, g
from database import connect_to_db
import os
import json
import time
from datetime import date, timedelta, datetime
import traceback
from typing import Dict, Any, List, Optional, Tuple, Union
from decimal import Decimal, getcontext
import pytz 

# Set precision for Decimal calculations
getcontext().prec = 18  # Sufficient precision for cost calculations

# Constants for GPT-4o Pricing (adjust if necessary)
# Prices per 1 Million tokens
GPT4O_INPUT_COST_PER_MILLION_TOKENS = Decimal("5.00")
GPT4O_OUTPUT_COST_PER_MILLION_TOKENS = Decimal("15.00")

# Prices per token
GPT4O_INPUT_COST_PER_TOKEN = GPT4O_INPUT_COST_PER_MILLION_TOKENS / Decimal("1000000")
GPT4O_OUTPUT_COST_PER_TOKEN = GPT4O_OUTPUT_COST_PER_MILLION_TOKENS / Decimal("1000000")


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
                
                # Added debugging to see timestamps before conversion
                print(f"[DEBUG] Thread {thread['thread_id']} - Raw last_activity: {thread['last_activity']}, Type: {type(thread['last_activity'])}")
                
                # Convert datetime objects to strings if needed
                if isinstance(thread.get('started_at'), (datetime.datetime, datetime.date)):
                    # Debug original datetime before conversion
                    print(f"[DEBUG] Thread {thread['thread_id']} - started_at before: {thread['started_at']}, TZ info: {thread['started_at'].tzinfo}")
                    thread['started_at'] = thread['started_at'].isoformat()
                    print(f"[DEBUG] Thread {thread['thread_id']} - started_at after: {thread['started_at']}")
                
                if isinstance(thread.get('last_activity'), (datetime.datetime, datetime.date)):
                    # Debug original datetime before conversion
                    print(f"[DEBUG] Thread {thread['thread_id']} - last_activity before: {thread['last_activity']}, TZ info: {thread['last_activity'].tzinfo}")
                    thread['last_activity'] = thread['last_activity'].isoformat()
                    print(f"[DEBUG] Thread {thread['thread_id']} - last_activity after: {thread['last_activity']}")
                
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

# USAGE METRICS FUNCTION NEW 04/10/2025
def aggregate_usage_for_date(target_date: date) -> Dict[str, Any]:
    """
    Aggregates usage metrics from chat_messages for a specific date
    and inserts/updates records in the usage_metrics table.

    Args:
        target_date: The specific date (datetime.date object) to aggregate for.

    Returns:
        A dictionary containing the status and aggregated data or errors.
    """
    print(f"[db_metrics] Starting aggregation for date: {target_date.isoformat()}")
    results = {"success": True, "aggregated_data": [], "errors": []}
    processed_chatbots = 0
    updated_records = 0
    inserted_records = 0

    # First, import the time class from datetime module
    from datetime import time as dt_time
    
    start_timestamp_dt = datetime.combine(target_date, dt_time.min)
    end_timestamp_dt = datetime.combine(target_date, dt_time.max)

    # Convert to UTC if created_at is timezone-naive UTC
    # If your DB stores naive UTC timestamps:
    try:
        # Check if system timezone is UTC, otherwise convert
        is_utc = time.tzname[0] == 'UTC'
        if not is_utc:
            # This conversion might need adjustment based on server environment
             # Assuming target_date is local, convert to UTC start/end
            local_tz = datetime.now().astimezone().tzinfo
            utc_tz = pytz.utc

            local_start = local_tz.localize(start_timestamp_dt)
            local_end = local_tz.localize(end_timestamp_dt)

            start_timestamp_utc = local_start.astimezone(utc_tz)
            end_timestamp_utc = local_end.astimezone(utc_tz)
            print(f"[db_metrics] Aggregating between UTC: {start_timestamp_utc} and {end_timestamp_utc}")
        else:
             # Server is already UTC
             start_timestamp_utc = start_timestamp_dt
             end_timestamp_utc = end_timestamp_dt
             print(f"[db_metrics] Server is UTC. Aggregating between: {start_timestamp_utc} and {end_timestamp_utc}")

    except Exception as tz_err:
         print(f"[db_metrics] Timezone conversion error: {tz_err}. Falling back to naive comparison.")
         # Fallback to naive comparison if timezone libraries fail
         start_timestamp_utc = start_timestamp_dt
         end_timestamp_utc = end_timestamp_dt


    # Use the determined UTC start/end times for queries
    start_timestamp_str = start_timestamp_utc.strftime('%Y-%m-%d %H:%M:%S')
    end_timestamp_str = end_timestamp_utc.strftime('%Y-%m-%d %H:%M:%S')

    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()

            # 1. Get all active chatbot IDs
            if DB_TYPE.lower() == 'postgresql':
                cursor.execute(f"SELECT chatbot_id FROM {DB_SCHEMA}.companies")
            else:
                cursor.execute("SELECT chatbot_id FROM companies")
            chatbot_ids = [row[0] for row in cursor.fetchall()]
            print(f"[db_metrics] Found {len(chatbot_ids)} chatbots to process.")

            if not chatbot_ids:
                results["message"] = "No chatbots found in the companies table."
                return results

            # 2. Loop through each chatbot ID
            for chatbot_id in chatbot_ids:
                print(f"[db_metrics] Processing chatbot_id: {chatbot_id}")
                try:
                    # Query chat_messages for this chatbot and date range (using UTC timestamps)
                    if DB_TYPE.lower() == 'postgresql':
                        msg_query = f"""
                            SELECT
                                COUNT(DISTINCT thread_id) as conversations,
                                COUNT(*) as messages,
                                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                                COALESCE(SUM(total_tokens), 0) as total_tokens,
                                COUNT(CASE WHEN user_feedback = 'positive' THEN 1 END) as positive_feedback,
                                COUNT(CASE WHEN user_feedback = 'negative' THEN 1 END) as negative_feedback
                            FROM {DB_SCHEMA}.chat_messages
                            WHERE chatbot_id = %s
                              AND created_at >= %s::timestamp
                              AND created_at <= %s::timestamp
                        """
                        cursor.execute(msg_query, (chatbot_id, start_timestamp_str, end_timestamp_str))
                    else:
                        msg_query = """
                            SELECT
                                COUNT(DISTINCT thread_id) as conversations,
                                COUNT(*) as messages,
                                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                                COALESCE(SUM(total_tokens), 0) as total_tokens,
                                COUNT(CASE WHEN user_feedback = 'positive' THEN 1 END) as positive_feedback,
                                COUNT(CASE WHEN user_feedback = 'negative' THEN 1 END) as negative_feedback
                            FROM chat_messages
                            WHERE chatbot_id = ?
                              AND created_at >= ?
                              AND created_at <= ?
                        """
                        cursor.execute(msg_query, (chatbot_id, start_timestamp_str, end_timestamp_str))

                    metrics = cursor.fetchone()

                    if not metrics or metrics[1] == 0: # Check if messages count is 0
                        print(f"[db_metrics] No messages found for {chatbot_id} on {target_date}. Skipping.")
                        continue

                    conversations = metrics[0]
                    messages_count = metrics[1]
                    prompt_tokens = metrics[2]
                    completion_tokens = metrics[3]
                    total_tokens = metrics[4]
                    positive_feedback = metrics[5]
                    negative_feedback = metrics[6]

                    # Calculate cost
                    cost = (Decimal(prompt_tokens) * GPT4O_INPUT_COST_PER_TOKEN) + \
                           (Decimal(completion_tokens) * GPT4O_OUTPUT_COST_PER_TOKEN)

                    # Format cost to a reasonable number of decimal places for storage
                    cost = cost.quantize(Decimal("0.000001")) # E.g., $0.001234
                    
                    # Convert Decimal to float for SQLite compatibility
                    cost_value = float(cost) if DB_TYPE.lower() != 'postgresql' else cost

                    print(f"[db_metrics] Aggregated for {chatbot_id}: Msgs={messages_count}, Tokens={total_tokens}, Cost=${cost:.6f}")

                    # Check if record exists in usage_metrics for this chatbot and date
                    if DB_TYPE.lower() == 'postgresql':
                        check_query = f"""
                            SELECT usage_metric_id FROM {DB_SCHEMA}.usage_metrics
                            WHERE chatbot_id = %s AND date = %s
                        """
                        cursor.execute(check_query, (chatbot_id, target_date))
                    else:
                        check_query = """
                            SELECT usage_metric_id FROM usage_metrics
                            WHERE chatbot_id = ? AND date = ?
                        """
                        cursor.execute(check_query, (chatbot_id, target_date.isoformat()))

                    existing_record = cursor.fetchone()

                    metric_data = {
                        "chatbot_id": chatbot_id,
                        "date": target_date,
                        "conversations": conversations,
                        "messages": messages_count,
                        "tokens": total_tokens,
                        "costs": cost_value,
                        "positive_feedback": positive_feedback,
                        "negative_feedback": negative_feedback
                    }

                    if existing_record:
                        # Update existing record
                        usage_metric_id = existing_record[0]
                        print(f"[db_metrics] Updating existing record ID: {usage_metric_id}")
                        if DB_TYPE.lower() == 'postgresql':
                            update_query = f"""
                                UPDATE {DB_SCHEMA}.usage_metrics SET
                                    conversations = %s, messages = %s, tokens = %s, costs = %s,
                                    positive_feedback = %s, negative_feedback = %s,
                                    created_at = NOW()
                                WHERE usage_metric_id = %s
                            """
                            cursor.execute(update_query, (
                                conversations, messages_count, total_tokens, cost_value,
                                positive_feedback, negative_feedback, usage_metric_id
                            ))
                        else:
                            update_query = """
                                UPDATE usage_metrics SET
                                    conversations = ?, messages = ?, tokens = ?, costs = ?,
                                    positive_feedback = ?, negative_feedback = ?,
                                    created_at = CURRENT_TIMESTAMP
                                WHERE usage_metric_id = ?
                            """
                            cursor.execute(update_query, (
                                conversations, messages_count, total_tokens, cost_value,
                                positive_feedback, negative_feedback, usage_metric_id
                            ))
                        updated_records += 1
                        metric_data["usage_metric_id"] = usage_metric_id # Add id for reference
                        results["aggregated_data"].append(metric_data)

                    else:
                        # Insert new record
                        print(f"[db_metrics] Inserting new record for {chatbot_id} on {target_date}")
                        if DB_TYPE.lower() == 'postgresql':
                            insert_query = f"""
                                INSERT INTO {DB_SCHEMA}.usage_metrics
                                (chatbot_id, date, conversations, messages, tokens, costs, positive_feedback, negative_feedback)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                RETURNING usage_metric_id
                            """
                            cursor.execute(insert_query, (
                                chatbot_id, target_date, conversations, messages_count, total_tokens, cost_value,
                                positive_feedback, negative_feedback
                            ))
                            new_id = cursor.fetchone()[0]
                        else:
                            insert_query = """
                                INSERT INTO usage_metrics
                                (chatbot_id, date, conversations, messages, tokens, costs, positive_feedback, negative_feedback)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """
                            cursor.execute(insert_query, (
                                chatbot_id, target_date.isoformat(), conversations, messages_count, total_tokens, cost_value,
                                positive_feedback, negative_feedback
                            ))
                            new_id = cursor.lastrowid

                        inserted_records += 1
                        metric_data["usage_metric_id"] = new_id # Add id for reference
                        results["aggregated_data"].append(metric_data)

                    processed_chatbots += 1

                except Exception as e:
                    error_msg = f"Failed to process chatbot_id {chatbot_id}: {str(e)}"
                    print(f"[db_metrics] ERROR: {error_msg}")
                    print(traceback.format_exc())
                    results["success"] = False
                    results["errors"].append(error_msg)
                    conn.rollback() # Rollback transaction for this specific chatbot if needed, or handle errors globally

            # Commit all successful operations if no major errors occurred or handled per-chatbot
            if not results["errors"]: # Or adjust based on desired error handling
                conn.commit()
            else:
                # Decide if partial success is okay or if all should be rolled back
                print("[db_metrics] Rolling back due to errors during processing.")
                conn.rollback()


        results["message"] = (f"Aggregation complete for {target_date.isoformat()}. "
                              f"Processed: {processed_chatbots} chatbots. "
                              f"Inserted: {inserted_records} records. "
                              f"Updated: {updated_records} records.")
        if results["errors"]:
             results["message"] += f" Encountered {len(results['errors'])} errors."

        print(f"[db_metrics] {results['message']}")
        return results

    except Exception as e:
        error_msg = f"Major error during aggregation for {target_date.isoformat()}: {str(e)}"
        print(f"[db_metrics] FATAL ERROR: {error_msg}")
        print(traceback.format_exc())
        results["success"] = False
        results["errors"].append(error_msg)
        results["message"] = error_msg
        return results
# END USAGE METRICS FUNCTION

# BEGIN GET USAGE METRICS FOR RANGE
def get_usage_metrics_for_range(start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """
    Retrieves aggregated usage metrics from the usage_metrics table for a given date range.

    Args:
        start_date: The start date of the range (inclusive).
        end_date: The end date of the range (inclusive).

    Returns:
        A list of dictionaries, where each dictionary represents a row
        from the usage_metrics table for the specified range.
    """
    print(f"[db_metrics] Fetching usage metrics from {start_date.isoformat()} to {end_date.isoformat()}")
    metrics_data = []
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()

            # Prepare query based on DB type
            if DB_TYPE.lower() == 'postgresql':
                query = f"""
                    SELECT
                        usage_metric_id, chatbot_id, date, conversations, messages,
                        tokens, costs, positive_feedback, negative_feedback, created_at
                    FROM {DB_SCHEMA}.usage_metrics
                    WHERE date >= %s AND date <= %s
                    ORDER BY date ASC, chatbot_id ASC
                """
                cursor.execute(query, (start_date, end_date))
            else:
                # SQLite stores dates as strings typically
                query = """
                    SELECT
                        usage_metric_id, chatbot_id, date, conversations, messages,
                        tokens, costs, positive_feedback, negative_feedback, created_at
                    FROM usage_metrics
                    WHERE date >= ? AND date <= ?
                    ORDER BY date ASC, chatbot_id ASC
                """
                cursor.execute(query, (start_date.isoformat(), end_date.isoformat()))

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            for row in rows:
                row_dict = dict(zip(columns, row))
                # Ensure cost is a string representation of a float for JSON compatibility
                if isinstance(row_dict.get('costs'), Decimal):
                     row_dict['costs'] = f"{row_dict['costs']:.6f}" # Format as string with 6 decimals
                elif isinstance(row_dict.get('costs'), (int, float)):
                     row_dict['costs'] = f"{row_dict['costs']:.6f}"
                # Ensure date is in ISO format string
                if isinstance(row_dict.get('date'), date):
                    row_dict['date'] = row_dict['date'].isoformat()
                # Ensure created_at is ISO format string
                if isinstance(row_dict.get('created_at'), datetime):
                    row_dict['created_at'] = row_dict['created_at'].isoformat()

                metrics_data.append(row_dict)

            print(f"[db_metrics] Found {len(metrics_data)} usage metric records.")
            return metrics_data

    except Exception as e:
        print(f"[db_metrics] Error fetching usage metrics for range: {str(e)}")
        print(traceback.format_exc())
        return [] # Return empty list on error
# END GET USAGE METRICS FOR RANGE

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
    """API endpoint to get threads for a chatbot with optional time filter
       Gets a max of 50 threads and not older than 30 days ago"""
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
