"""
Test script for the Nuclear Reset functionality.
This script tests the reset process for a specific chatbot by URL.
Works with both local SQLite and Azure PostgreSQL environments.

Usage:
python nuclear_reset_test.py [chatbot_url]

All of these would work to find a chatbot for "example.com":
    python nuclear_reset_test.py EXAMPLE.COM
    python nuclear_reset_test.py https://example.com/
    python nuclear_reset_test.py example.com
    python nuclear_reset_test.py example
"""

import sys
import requests
import sqlite3
import os
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_TYPE = os.getenv('DB_TYPE', 'sqlite')  # Default to sqlite if not specified
DB_HOST = os.getenv('DB_HOST', '')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'easychat')
DB_SSL = os.getenv('DB_SSL', '')

# SQLite specific settings
SQLITE_DB_PATH = '.'
SQLITE_DB_NAME = os.path.join(SQLITE_DB_PATH, "easyafchat.db")

# API settings - detect environment
if DB_TYPE.lower() == 'postgresql':
    API_URL = os.getenv('AZURE_APP_URL', 'https://easyafchat-v3.azurewebsites.net')
else:
    API_URL = os.getenv('LOCAL_API_URL', 'http://127.0.0.1:8080')

@contextmanager
def connect_to_db():
    """
    Connect to the database (either SQLite or PostgreSQL) 
    based on environment variables.
    """
    conn = None
    try:
        if DB_TYPE.lower() == 'postgresql':
            # Set SSL mode if specified
            ssl_mode = None
            if DB_SSL.lower() == 'require':
                ssl_mode = 'require'
            
            # Connect to PostgreSQL
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                sslmode=ssl_mode
            )
            
            # Set the schema search path
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL("SET search_path TO {}").format(
                    sql.Identifier(DB_SCHEMA)
                ))
        else:
            # Default to SQLite
            conn = sqlite3.connect(SQLITE_DB_NAME)
        
        yield conn
        
        if conn is not None:
            conn.commit()
    except Exception as e:
        if conn is not None:
            conn.rollback()
        raise e
    finally:
        if conn is not None:
            conn.close()

def get_chatbot_id_from_url(url):
    """Get the chatbot ID from a URL by checking the database with case-insensitive matching."""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Normalize the URL for comparison by removing protocol and making lowercase
            normalized_url = url.lower()
            if normalized_url.startswith('http://'):
                normalized_url = normalized_url[7:]
            elif normalized_url.startswith('https://'):
                normalized_url = normalized_url[8:]
            
            # Remove trailing slash if present
            if normalized_url.endswith('/'):
                normalized_url = normalized_url[:-1]
                
            # Get all companies
            cursor.execute('SELECT chatbot_id, company_url FROM companies')
            all_companies = cursor.fetchall()
            
            # Find matching URL with case-insensitive comparison
            for chatbot_id, company_url in all_companies:
                db_url = company_url.lower()
                if db_url.startswith('http://'):
                    db_url = db_url[7:]
                elif db_url.startswith('https://'):
                    db_url = db_url[8:]
                    
                if db_url.endswith('/'):
                    db_url = db_url[:-1]
                    
                if normalized_url == db_url or normalized_url in db_url or db_url in normalized_url:
                    print(f"Found matching chatbot with URL: {company_url}")
                    return chatbot_id
            
            print(f"No chatbot found for URL: {url}")
            print("Available URLs in database:")
            for _, company_url in all_companies:
                print(f"  - {company_url}")
                
            return None
    except Exception as e:
        print(f"Error accessing database: {e}")
        return None

def check_tables_for_chatbot(chatbot_id):
    """Check if the chatbot exists in any tables and print the results."""
    try:
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            # Different placeholders for SQLite and PostgreSQL
            placeholder = '%s' if DB_TYPE.lower() == 'postgresql' else '?'
            
            # Check companies table
            cursor.execute(f'SELECT COUNT(*) FROM companies WHERE chatbot_id = {placeholder}', (chatbot_id,))
            companies_count = cursor.fetchone()[0]
            
            documents_count = 0
            leads_count = 0
            config_count = 0
            
            # Check if tables exist before querying
            if DB_TYPE.lower() == 'postgresql':
                # For PostgreSQL, check if tables exist in schema
                for table in ['documents', 'leads', 'chatbot_config']:
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = %s AND table_name = %s
                        )
                    """, (DB_SCHEMA, table))
                    
                    if cursor.fetchone()[0]:
                        cursor.execute(f'SELECT COUNT(*) FROM {table} WHERE chatbot_id = %s', (chatbot_id,))
                        count = cursor.fetchone()[0]
                        
                        if table == 'documents':
                            documents_count = count
                        elif table == 'leads':
                            leads_count = count
                        elif table == 'chatbot_config':
                            config_count = count
            else:
                # For SQLite, use a simpler approach
                try:
                    cursor.execute('SELECT COUNT(*) FROM documents WHERE chatbot_id = ?', (chatbot_id,))
                    documents_count = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    pass  # Table doesn't exist
                
                try:
                    cursor.execute('SELECT COUNT(*) FROM leads WHERE chatbot_id = ?', (chatbot_id,))
                    leads_count = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    pass  # Table doesn't exist
                
                try:
                    cursor.execute('SELECT COUNT(*) FROM chatbot_config WHERE chatbot_id = ?', (chatbot_id,))
                    config_count = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    pass  # Table doesn't exist
            
            # Check if any users own this chatbot
            cursor.execute(f'SELECT user_id FROM companies WHERE chatbot_id = {placeholder}', (chatbot_id,))
            user_result = cursor.fetchone()
            
            user_exists = False
            if user_result and user_result[0]:
                cursor.execute(f'SELECT COUNT(*) FROM users WHERE user_id = {placeholder}', (user_result[0],))
                user_exists = cursor.fetchone()[0] > 0
        
        # Print results
        print(f"\nChatbot ID: {chatbot_id}")
        print(f"Found in companies table: {'Yes' if companies_count > 0 else 'No'}")
        print(f"Associated documents: {documents_count}")
        print(f"Associated leads: {leads_count}")
        print(f"Has configuration: {'Yes' if config_count > 0 else 'No'}")
        print(f"Associated with a user: {'Yes' if user_exists else 'No'}")
        
        return companies_count + documents_count + leads_count + config_count > 0
        
    except Exception as e:
        print(f"Error checking tables: {e}")
        return False

def perform_nuclear_reset(chatbot_id):
    """Performs the nuclear reset operation through the API."""
    try:
        # You'll need to have admin session credentials to access this endpoint
        response = requests.post(
            f"{API_URL}/admin-dashboard-08x7z9y2-yoursecretword/nuclear-reset/{chatbot_id}",
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("\nNuclear reset successful!")
                print(f"Message: {data.get('message')}")
                return True
            else:
                print(f"\nAPI error: {data.get('error')}")
                return False
        else:
            print(f"\nHTTP error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"\nError performing nuclear reset: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python nuclear_reset_test.py [chatbot_url]")
        return
        
    url = sys.argv[1]
    print(f"Looking up chatbot for URL: {url}")
    print(f"Database type: {DB_TYPE}")
    print(f"API URL: {API_URL}")
    
    chatbot_id = get_chatbot_id_from_url(url)
    if not chatbot_id:
        return
        
    # Check if chatbot exists in tables
    exists = check_tables_for_chatbot(chatbot_id)
    
    if not exists:
        print("\nChatbot not found in any tables. Nothing to reset.")
        return
        
    # Ask for confirmation
    confirm = input("\nDo you want to perform a nuclear reset on this chatbot? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return
        
    # Perform the reset
    success = perform_nuclear_reset(chatbot_id)
    
    if success:
        # Verify the reset
        print("\nVerifying reset...")
        still_exists = check_tables_for_chatbot(chatbot_id)
        
        if still_exists:
            print("\n⚠️ Warning: The chatbot still exists in one or more tables.")
        else:
            print("\n✅ Success: The chatbot has been completely removed from all tables.")
    
if __name__ == "__main__":
    main()
