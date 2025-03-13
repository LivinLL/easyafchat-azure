"""
Quick script to clear user_id references in the companies table.
This will set all user_id fields to NULL, effectively "unclaiming" all chatbots.
"""

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

def clear_user_id_from_companies():
    """Clear all user_id values in the companies table."""
    print("Starting to clear user_id values from companies table...")
    
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        # First check how many records will be affected
        if DB_TYPE.lower() == 'postgresql':
            cursor.execute("SELECT COUNT(*) FROM companies WHERE user_id IS NOT NULL")
        else:
            cursor.execute("SELECT COUNT(*) FROM companies WHERE user_id IS NOT NULL")
            
        count = cursor.fetchone()[0]
        print(f"Found {count} companies with user_id set")
        
        # Now update all records
        if DB_TYPE.lower() == 'postgresql':
            cursor.execute("UPDATE companies SET user_id = NULL")
        else:
            cursor.execute("UPDATE companies SET user_id = NULL")
            
        print(f"Cleared user_id from all companies")
        
        # Also display all chatbots for verification
        if DB_TYPE.lower() == 'postgresql':
            cursor.execute("SELECT chatbot_id, company_url FROM companies")
        else:
            cursor.execute("SELECT chatbot_id, company_url FROM companies")
            
        chatbots = cursor.fetchall()
        print("\nCurrent chatbots in database:")
        for chatbot in chatbots:
            print(f"  - {chatbot[0]}: {chatbot[1]}")
    
    print("\nCompleted successfully!")

if __name__ == "__main__":
    clear_user_id_from_companies()
