import sqlite3
import os
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager

# Get database configuration from environment variables
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

def upgrade_database(verbose=False):
    """
    Upgrade the database schema.
    Ensures tables exist and adds missing fields without overwriting existing data.
    """
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if DB_TYPE.lower() == 'postgresql':
            # Create schema if it doesn't exist
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(DB_SCHEMA)
            ))
            
            # Create tables in PostgreSQL
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {DB_SCHEMA}.companies (
                chatbot_id TEXT PRIMARY KEY,
                company_url TEXT NOT NULL,
                pinecone_host_url TEXT,
                pinecone_index TEXT,
                pinecone_namespace TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scraped_text TEXT,
                processed_content TEXT
            )
            """)
            
            # Check if the old fields exist and migrate data if needed
            try:
                cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = '{DB_SCHEMA}' 
                AND table_name = 'companies' 
                AND column_name = 'home_text'
                """)
                
                if cursor.fetchone():
                    # Migrate data from old fields to new field
                    cursor.execute(f"""
                    UPDATE {DB_SCHEMA}.companies 
                    SET scraped_text = CONCAT(
                        'OpenAI Prompt\n', home_text, 
                        '\n\nAbout Scrape\n', COALESCE(about_text, 'About page not found')
                    )
                    WHERE scraped_text IS NULL AND home_text IS NOT NULL
                    """)
                    
                    # Drop old columns
                    cursor.execute(f"""
                    ALTER TABLE {DB_SCHEMA}.companies 
                    DROP COLUMN IF EXISTS home_text,
                    DROP COLUMN IF EXISTS about_text
                    """)
                    
                    if verbose:
                        print("Migrated data from home_text and about_text to scraped_text")
            except Exception as e:
                print(f"Error checking or migrating columns: {e}")
        else:
            # Create tables in SQLite
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                chatbot_id TEXT PRIMARY KEY,
                company_url TEXT NOT NULL,
                pinecone_host_url TEXT,
                pinecone_index TEXT,
                pinecone_namespace TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                scraped_text TEXT,
                processed_content TEXT
            )
            ''')
            
            # Check if the old fields exist and migrate data if needed
            try:
                cursor.execute("PRAGMA table_info(companies)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'home_text' in columns:
                    # Create temporary table with new schema
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS companies_new (
                        chatbot_id TEXT PRIMARY KEY,
                        company_url TEXT NOT NULL,
                        pinecone_host_url TEXT,
                        pinecone_index TEXT,
                        pinecone_namespace TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        scraped_text TEXT,
                        processed_content TEXT
                    )
                    ''')
                    
                    # Migrate data
                    cursor.execute('''
                    INSERT INTO companies_new (
                        chatbot_id, company_url, pinecone_host_url, pinecone_index,
                        pinecone_namespace, created_at, updated_at, scraped_text, processed_content
                    )
                    SELECT 
                        chatbot_id, company_url, pinecone_host_url, pinecone_index,
                        pinecone_namespace, created_at, updated_at, 
                        'OpenAI Prompt
' || home_text || '

About Scrape
' || COALESCE(about_text, 'About page not found'), 
                        processed_content
                    FROM companies
                    ''')
                    
                    # Replace old table with new one
                    cursor.execute('DROP TABLE companies')
                    cursor.execute('ALTER TABLE companies_new RENAME TO companies')
                    
                    if verbose:
                        print("Migrated data from home_text and about_text to scraped_text")
            except Exception as e:
                print(f"Error checking or migrating columns: {e}")
        
        conn.commit()
        
        if verbose:
            db_type_str = "PostgreSQL" if DB_TYPE.lower() == 'postgresql' else "SQLite"
            print(f"Database schema upgraded successfully using {db_type_str}.")

def initialize_database(verbose=False):
    if verbose:
        db_type_str = "PostgreSQL" if DB_TYPE.lower() == 'postgresql' else "SQLite"
        print(f"Initializing {db_type_str} database...")
    upgrade_database(verbose=verbose)

if __name__ == "__main__":
    initialize_database(verbose=True)  # Show messages when run directly