"""
Azure PostgreSQL Database Cleanup Script
Run this ONCE on your Azure environment to clean up database tables.
IMPORTANT: This will drop and recreate the users table!
"""

import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection details
DB_HOST = os.getenv('DB_HOST', '')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'easychat')
DB_SSL = os.getenv('DB_SSL', '')

def clean_azure_database():
    """Clean up the PostgreSQL database tables in Azure."""
    print("Starting Azure PostgreSQL database cleanup...")
    
    conn = None
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            sslmode=DB_SSL if DB_SSL else None
        )
        
        # Create cursor
        cursor = conn.cursor()
        
        # Set the schema search path
        cursor.execute(sql.SQL("SET search_path TO {}").format(
            sql.Identifier(DB_SCHEMA)
        ))
        
        # Drop users table if it exists (CASCADE to handle foreign key constraints)
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
        
        # Commit changes
        conn.commit()
        print("Azure database cleanup completed successfully")
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error during Azure database cleanup: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    clean_azure_database()