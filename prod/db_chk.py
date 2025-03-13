"""
Database Inspection Script
This script shows all tables, their schemas, and sample records from the database.
It works with both SQLite and PostgreSQL databases.
Output is displayed in the terminal and also saved to a file.
"""

import os
import sqlite3
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager
from datetime import datetime
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

# Output file
OUTPUT_FILE = "db_chk_results.txt"

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

def get_all_tables():
    """Get list of all tables in the database."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if DB_TYPE.lower() == 'postgresql':
            # PostgreSQL query to get tables
            cursor.execute(f"""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = '{DB_SCHEMA}'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cursor.fetchall()]
        else:
            # SQLite query to get tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
            
        return tables

def get_table_schema(table_name):
    """Get schema information for a specific table."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if DB_TYPE.lower() == 'postgresql':
            # PostgreSQL query to get column information
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_schema = '{DB_SCHEMA}' 
                AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    'name': row[0],
                    'type': row[1],
                    'nullable': row[2]
                })
        else:
            # SQLite query to get column information
            cursor.execute(f"PRAGMA table_info({table_name})")
            
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    'name': row[1],
                    'type': row[2],
                    'nullable': "YES" if row[3] == 0 else "NO"
                })
        
        return columns

def get_sample_records(table_name, limit=5):
    """Get sample records from the table."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if DB_TYPE.lower() == 'postgresql':
            cursor.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(
                sql.Identifier(table_name)
            ), (limit,))
        else:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            
        records = cursor.fetchall()
        
        # Get column names
        if DB_TYPE.lower() == 'postgresql':
            columns = [desc[0] for desc in cursor.description]
        else:
            columns = [desc[0] for desc in cursor.description]
            
        return columns, records

def count_records(table_name):
    """Count records in the table."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        if DB_TYPE.lower() == 'postgresql':
            cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(table_name)
            ))
        else:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            
        count = cursor.fetchone()[0]
        return count

def truncate_text(text, max_length=200):
    """Truncate text for display purposes."""
    if text and isinstance(text, str) and len(text) > max_length:
        return text[:max_length] + "..."
    return text

def check_foreign_keys(table_name):
    """Check foreign key relationships for a table."""
    with connect_to_db() as conn:
        cursor = conn.cursor()
        foreign_keys = []
        
        if DB_TYPE.lower() == 'postgresql':
            # PostgreSQL query to get foreign keys
            cursor.execute(f"""
                SELECT
                    kcu.column_name, 
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM 
                    information_schema.table_constraints AS tc 
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu 
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY' 
                AND tc.table_schema = '{DB_SCHEMA}'
                AND tc.table_name = %s
            """, (table_name,))
        else:
            # SQLite query to get foreign keys
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            
            # Format to match PostgreSQL output
            for row in cursor.fetchall():
                foreign_keys.append({
                    'column_name': row[3],
                    'foreign_table_name': row[2],
                    'foreign_column_name': row[4]
                })
            return foreign_keys
                
        if DB_TYPE.lower() == 'postgresql':
            for row in cursor.fetchall():
                foreign_keys.append({
                    'column_name': row[0],
                    'foreign_table_name': row[1],
                    'foreign_column_name': row[2]
                })
        
        return foreign_keys

def inspect_database():
    """Inspect all tables in the database and print information."""
    output_lines = []
    
    def log(message=""):
        """Print to console and add to output lines."""
        print(message)
        output_lines.append(message)
    
    # Get database type and connection info
    log("=" * 80)
    log(f"DATABASE INSPECTION REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 80)
    
    db_type = "PostgreSQL" if DB_TYPE.lower() == 'postgresql' else "SQLite"
    log(f"Database Type: {db_type}")
    
    if DB_TYPE.lower() == 'postgresql':
        log(f"Host: {DB_HOST}")
        log(f"Database: {DB_NAME}")
        log(f"Schema: {DB_SCHEMA}")
    else:
        log(f"Database File: {SQLITE_DB_NAME}")
    log("")
    
    # Get all tables
    tables = get_all_tables()
    log(f"Found {len(tables)} tables: {', '.join(tables)}")
    log("")
    
    # Examine each table
    for table_name in tables:
        log("-" * 80)
        log(f"TABLE: {table_name}")
        log("-" * 80)
        
        # Get schema
        columns = get_table_schema(table_name)
        log("SCHEMA:")
        for col in columns:
            nullable = "NULL" if col['nullable'] == "YES" else "NOT NULL"
            log(f"  {col['name']} ({col['type']}) {nullable}")
        log("")
        
        # Get foreign keys
        foreign_keys = check_foreign_keys(table_name)
        if foreign_keys:
            log("FOREIGN KEYS:")
            for fk in foreign_keys:
                log(f"  {fk['column_name']} -> {fk['foreign_table_name']}.{fk['foreign_column_name']}")
            log("")
        
        # Count records
        record_count = count_records(table_name)
        log(f"RECORD COUNT: {record_count}")
        log("")
        
        # Get sample records
        if record_count > 0:
            log("SAMPLE RECORDS (up to 5):")
            column_names, records = get_sample_records(table_name)
            
            # Print column headers
            header = " | ".join(column_names)
            log(f"  {header}")
            log(f"  {'-' * len(header)}")
            
            # Print records
            for record in records:
                formatted_row = []
                for i, value in enumerate(record):
                    # Handle text fields - truncate if too long
                    if isinstance(value, str) and len(value) > 50:
                        formatted_row.append(f"{value[:47]}...")
                    else:
                        formatted_row.append(str(value))
                log("  " + " | ".join(formatted_row))
            log("")
        
        log("")
    
    log("=" * 80)
    log(f"End of report - Saved to {OUTPUT_FILE}")
    log("=" * 80)
    
    # Write output to file
    with open(OUTPUT_FILE, 'w') as f:
        f.write("\n".join(output_lines))

if __name__ == '__main__':
    inspect_database()
