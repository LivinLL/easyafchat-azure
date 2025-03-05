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
            
            # First check if the companies table exists at all
            cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = '{DB_SCHEMA}'
                AND table_name = 'companies'
            )
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                # Create the table if it doesn't exist yet
                if verbose:
                    print(f"Creating new companies table in {DB_SCHEMA} schema")
                cursor.execute(f"""
                CREATE TABLE {DB_SCHEMA}.companies (
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
            else:
                # Table exists, check if scraped_text column exists
                cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = '{DB_SCHEMA}' 
                AND table_name = 'companies' 
                AND column_name = 'scraped_text'
                """)
                
                if not cursor.fetchone():
                    # scraped_text column doesn't exist, so add it
                    if verbose:
                        print(f"Adding scraped_text column to existing companies table")
                    cursor.execute(f"""
                    ALTER TABLE {DB_SCHEMA}.companies 
                    ADD COLUMN scraped_text TEXT
                    """)
            
            # Now check if the old fields exist and migrate data if needed
            cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = '{DB_SCHEMA}' 
            AND table_name = 'companies' 
            AND column_name = 'home_text'
            """)
            
            if cursor.fetchone():
                # home_text exists, so it's time to migrate and drop old columns
                if verbose:
                    print("Found home_text column, migrating data to scraped_text")
                try:
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
                    print(f"Error migrating columns: {e}")
            
            # Check if leads table exists
            cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = '{DB_SCHEMA}'
                AND table_name = 'leads'
            )
            """)
            leads_table_exists = cursor.fetchone()[0]
            
            if not leads_table_exists:
                # Create the leads table if it doesn't exist yet
                if verbose:
                    print(f"Creating new leads table in {DB_SCHEMA} schema")
                cursor.execute(f"""
                CREATE TABLE {DB_SCHEMA}.leads (
                    lead_id SERIAL PRIMARY KEY,
                    chatbot_id TEXT REFERENCES companies(chatbot_id),
                    thread_id TEXT NOT NULL,
                    name TEXT,
                    email TEXT,
                    phone TEXT,
                    initial_question TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'new',
                    notes TEXT
                )
                """)
                
            # Check if chatbot_config table exists
            cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = '{DB_SCHEMA}'
                AND table_name = 'chatbot_config'
            )
            """)
            config_table_exists = cursor.fetchone()[0]
            
            if not config_table_exists:
                # Create the chatbot_config table if it doesn't exist yet
                if verbose:
                    print(f"Creating new chatbot_config table in {DB_SCHEMA} schema")
                cursor.execute(f"""
                CREATE TABLE {DB_SCHEMA}.chatbot_config (
                    config_id SERIAL PRIMARY KEY,
                    chatbot_id TEXT UNIQUE REFERENCES companies(chatbot_id),
                    chat_model TEXT DEFAULT 'gpt-4o',
                    temperature NUMERIC(3,2) DEFAULT 0.7,
                    max_tokens INTEGER DEFAULT 500,
                    system_prompt TEXT,
                    chat_title TEXT,
                    chat_subtitle TEXT,
                    lead_form_title TEXT DEFAULT 'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
                    primary_color TEXT DEFAULT '#0084ff',
                    accent_color TEXT DEFAULT '#ffffff',
                    icon_image_url TEXT DEFAULT NULL,
                    show_lead_form TEXT DEFAULT 'Yes',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
        else:
            # SQLite handling
            # Create companies table if not exists
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
            
            # Create leads table if not exists
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chatbot_id TEXT REFERENCES companies(chatbot_id),
                thread_id TEXT NOT NULL,
                name TEXT,
                email TEXT,
                phone TEXT,
                initial_question TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'new',
                notes TEXT
            )
            ''')
            
            # Create chatbot_config table if not exists
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chatbot_config (
                config_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chatbot_id TEXT UNIQUE REFERENCES companies(chatbot_id),
                chat_model TEXT DEFAULT 'gpt-4o',
                temperature NUMERIC(3,2) DEFAULT 0.7,
                max_tokens INTEGER DEFAULT 500,
                system_prompt TEXT,
                chat_title TEXT,
                chat_subtitle TEXT,
                lead_form_title TEXT DEFAULT 'Want us to reach out? Need to keep this chat going? Just fill out the info below.',
                primary_color TEXT DEFAULT '#0084ff',
                accent_color TEXT DEFAULT '#ffffff',
                icon_image_url TEXT DEFAULT NULL,
                show_lead_form TEXT DEFAULT 'Yes',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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