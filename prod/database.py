import sqlite3
import os

# Just use current directory - keep it simple
DB_PATH = '.'
DB_NAME = os.path.join(DB_PATH, "easyafchat.db")

def connect_to_db():
    """Connect to the SQLite database."""
    return sqlite3.connect(DB_NAME)

def upgrade_database(verbose=False):
    """
    Upgrade the database schema.
    Ensures tables exist and adds missing fields without overwriting existing data.
    """
    conn = connect_to_db()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS companies (
        chatbot_id TEXT PRIMARY KEY,
        company_url TEXT NOT NULL,
        pinecone_host_url TEXT,
        pinecone_index TEXT,
        pinecone_namespace TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        home_text TEXT,
        about_text TEXT,
        processed_content TEXT
    )
    ''')
    conn.commit()
    conn.close()
    if verbose:
        print(f"Database schema upgraded successfully in '{DB_NAME}'.")

def initialize_database(verbose=False):
    if verbose:
        print(f"Initializing database in '{DB_NAME}'...")
    upgrade_database(verbose=verbose)

if __name__ == "__main__":
    initialize_database(verbose=True)  # Show messages when run directly