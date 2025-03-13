"""
Database Cleanup Utility Script

This script cleans up the users table and related tables in your database.
It will drop any users_old tables and recreate the users table with the correct schema.
Run this once to fix your database, then use the normal initialize_database() function.
"""

import sqlite3
import os
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager

# Database configuration - copied from database.py for standalone operation
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

def clean_database():
    """Clean up the database tables and recreate them with the correct schema."""
    print("Starting database cleanup...")
    
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if DB_TYPE.lower() == 'postgresql':
            # PostgreSQL cleanup
            try:
                # Drop users table if it exists
                cursor.execute(f"""
                DROP TABLE IF EXISTS {DB_SCHEMA}.users CASCADE
                """)
                print("Dropped users table")
                
                # Create users table with all required columns
                cursor.execute(f"""
                CREATE TABLE {DB_SCHEMA}.users (
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
                print("Created users table with correct schema")
                
                # Update foreign key constraint in companies table
                cursor.execute(f"""
                ALTER TABLE {DB_SCHEMA}.companies 
                DROP CONSTRAINT IF EXISTS companies_user_id_fkey,
                ADD CONSTRAINT companies_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES {DB_SCHEMA}.users(user_id)
                """)
                print("Updated foreign key constraints")
            
            except Exception as e:
                print(f"PostgreSQL Error: {e}")
                conn.rollback()
        
        else:
            # SQLite cleanup
            try:
                # Check if users_old table exists and drop it
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_old'")
                if cursor.fetchone():
                    cursor.execute("DROP TABLE users_old")
                    print("Dropped users_old table")
                
                # Check if users table exists and drop it
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if cursor.fetchone():
                    cursor.execute("DROP TABLE users")
                    print("Dropped users table")
                
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
                print("Created users table with correct schema")
                
                # Check if temporary tables exist and drop them
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_temp'")
                if cursor.fetchone():
                    cursor.execute("DROP TABLE users_temp")
                    print("Dropped users_temp table")
                
            except Exception as e:
                print(f"SQLite Error: {e}")
                conn.rollback()
    
    print("Database cleanup completed successfully")

if __name__ == "__main__":
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded environment variables from .env file")
    except ImportError:
        print("dotenv package not found, using environment variables as is")
    
    # Run the cleanup
    clean_database()
