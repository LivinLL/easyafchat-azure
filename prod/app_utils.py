import os
import uuid
import re
from datetime import datetime, UTC
import requests
from openai import OpenAI
from bs4 import BeautifulSoup
import pinecone

def generate_chatbot_id():
    """Generate a unique chatbot ID."""
    return str(uuid.uuid4()).replace('-', '')[:20]

def check_namespace(url):
    """
    Find an appropriate namespace based on the main domain of the URL.
    Handles subdomains and common TLDs appropriately.
    """
    try:
        # Extract the domain from the URL
        domain = url.split('//')[-1].split('/')[0].lower()
        
        # Split the domain into parts
        parts = domain.split('.')
        
        # Common TLDs and second-level domains we want to exclude
        common_tlds = {'com', 'org', 'net', 'edu', 'gov', 'io', 'co', 'us', 'info', 'biz', 'app', 'dev'}
        second_level_domains = {'co.uk', 'com.au', 'co.nz', 'co.jp', 'or.jp', 'ne.jp', 'ac.uk', 'gov.uk', 'org.uk', 'co.za'}
        
        # Check if we have a second-level domain
        if len(parts) >= 3 and '.'.join(parts[-2:]) in second_level_domains:
            # For domains like example.co.uk, use 'example'
            main_domain = parts[-3]
        elif len(parts) >= 2:
            # For typical domains like example.com or subdomain.example.com
            # Check if it's a subdomain structure
            if len(parts) > 2 and parts[0] == 'www':
                # Handle www.example.com -> use 'example'
                main_domain = parts[-2]
            elif parts[-1] in common_tlds:
                # Handle example.com -> use 'example'
                main_domain = parts[-2]
            else:
                # Fallback to second part for unknown patterns
                main_domain = parts[1] if len(parts) > 1 else parts[0]
        else:
            # Fallback for unusual domains
            main_domain = parts[0]
        
        # Clean the main domain to remove any invalid characters
        base = re.sub(r'[^a-zA-Z0-9-]', '', main_domain)
        
        # Default namespace
        return f"{base}-01", None
    except Exception as e:
        print(f"Error checking namespace: {e}")
        # Fallback in case of error
        base = re.sub(r'[^a-zA-Z0-9-]', '', domain.replace('.', '-'))
        return f"{base}-01", None

def chunk_text(text, chunk_size=500):
    """Split text into smaller chunks for processing"""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        current_size += len(word) + 1
        if current_size > chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_size = len(word)
        else:
            current_chunk.append(word)
            
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    return chunks

def get_existing_record(url):
    """Check if URL already exists in database"""
    from database import connect_to_db
    
    with connect_to_db() as conn:
        cursor = conn.cursor()
        
        # Normalize URL by converting to lowercase
        url_lower = url.lower()
        
        if os.getenv('DB_TYPE', '').lower() == 'postgresql':
            cursor.execute('''
                SELECT chatbot_id, pinecone_namespace
                FROM companies 
                WHERE LOWER(company_url) = %s
            ''', (url_lower,))
        else:
            cursor.execute('''
                SELECT chatbot_id, pinecone_namespace
                FROM companies 
                WHERE LOWER(company_url) = ?
            ''', (url_lower,))
            
        row = cursor.fetchone()
        return row

def process_simple_content(home_data, about_data):
    """
    Process the scraped content with OpenAI and return both prompt and response
    
    Args:
        home_data (dict): Dictionary containing home page data with 'all_text' and 'meta_info'
        about_data (dict or None): Dictionary containing about page data or None

    Returns:
        tuple: Processed content and full prompt, or None if processing fails
    """
    try:
        # Import OpenAI client locally to avoid circular imports
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Create a comprehensive prompt with all the text data
        prompt = f"""
        Create a comprehensive knowledge base document from this website content. Include clear section headings for all relevant business information such as Company Overview:, Primary Products/Services:, Secondary Products/Services:, Pricing:, Contact Details:, Calls to Action:, etc:

        HOME PAGE TITLE:
        {home_data['meta_info']['title']}

        HOME PAGE DESCRIPTION:
        {home_data['meta_info']['description']}

        HOME PAGE CONTENT:
        {home_data['all_text']}

        """
        
        # Add about page content if available
        if about_data and about_data.get('all_text'):
            prompt += f"""
            ABOUT PAGE TITLE:
            {about_data['meta_info']['title']}

            ABOUT PAGE DESCRIPTION:
            {about_data['meta_info']['description']}

            ABOUT PAGE CONTENT:
            {about_data['all_text']}
            """
        else:
            prompt += "\nABOUT PAGE: Not found or no content available."
            
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Return both the response and the prompt
        return response.choices[0].message.content, prompt
    except Exception as e:
        print(f"Error processing with OpenAI: {e}")
        # In case of error, return None
        return None
    
def update_pinecone_index(namespace, text_chunks, embeddings):
    """
    Update Pinecone index with text chunks and their embeddings
    
    Args:
        namespace (str): Namespace for the vectors
        text_chunks (list): List of text chunks
        embeddings (list): List of embedding vectors
    
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Import Pinecone client locally to avoid circular imports
        from pinecone import Pinecone
        import os
        
        # Get Pinecone configuration from environment variables
        pinecone_api_key = os.getenv('PINECONE_API_KEY')
        pinecone_index_name = os.getenv('PINECONE_INDEX', 'all-companies')
        
        # Validate inputs
        if not namespace or not text_chunks or not embeddings:
            print("Error: Invalid inputs for Pinecone update")
            return False
        
        # Validate input lengths
        if len(text_chunks) != len(embeddings):
            print(f"Error: Mismatch in chunks ({len(text_chunks)}) and embeddings ({len(embeddings)})")
            return False
        
        # Initialize Pinecone client
        pc = Pinecone(api_key=pinecone_api_key)
        
        # Get the index
        index = pc.Index(pinecone_index_name)
        
        # Prepare vectors for upsert
        vectors = [
            (f"{namespace}-{i}", embedding, {"text": chunk})
            for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings))
        ]
        
        # Upsert vectors
        try:
            upsert_response = index.upsert(vectors=vectors, namespace=namespace)
            print(f"Pinecone upsert successful. Namespace: {namespace}, Vectors: {len(vectors)}")
            return True
        except Exception as upsert_error:
            print(f"Error during Pinecone upsert: {upsert_error}")
            return False
    
    except Exception as e:
        print(f"Comprehensive Pinecone update error: {e}")
        
        # Additional context logging
        print("Debug Information:")
        print(f"Namespace: {namespace}")
        print(f"Text Chunks Count: {len(text_chunks) if text_chunks else 'N/A'}")
        print(f"Embeddings Count: {len(embeddings) if embeddings else 'N/A'}")
        print(f"Pinecone Index: {os.getenv('PINECONE_INDEX', 'Not Set')}")
        
        return False
    
def add_manual_company(website_url, scraped_text, skip_openai_processing=False, processed_content="", openai_client=None, pinecone_client=None, pinecone_index=None, pinecone_host=None):
    """
    Add a new company/chatbot manually to the system.
    
    Args:
        website_url (str): The website URL of the company
        scraped_text (str): The raw text scraped from the website
        skip_openai_processing (bool): Whether to skip OpenAI processing
        processed_content (str): Pre-processed content (used only if skip_openai_processing is True)
        openai_client (OpenAI): OpenAI client instance
        pinecone_client (Pinecone): Pinecone client instance
        pinecone_index (str): Name of the Pinecone index
        pinecone_host (str): Pinecone host URL
        
    Returns:
        dict: A dictionary with success status and relevant information or error
    """
    from database import connect_to_db
    from datetime import datetime, UTC
    
    try:
        # Validate required fields
        if not website_url or not scraped_text:
            return {
                'success': False, 
                'error': 'Website URL and scraped text are required'
            }

        # Check if the URL already exists in the database
        existing_record = get_existing_record(website_url)
        
        if existing_record:
            return {
                'success': False, 
                'error': 'A chatbot for this URL already exists'
            }

        # Generate chatbot ID and namespace
        chatbot_id = generate_chatbot_id()
        namespace, _ = check_namespace(website_url)

        # Process content with OpenAI or use provided processed content
        if not skip_openai_processing:
            if not openai_client:
                return {
                    'success': False, 
                    'error': 'OpenAI client is required for processing content'
                }
                
            try:
                # Use OpenAI to process the scraped text
                home_data = {
                    'all_text': scraped_text,
                    'meta_info': {
                        'title': '',
                        'description': ''
                    }
                }
                
                # Create a comprehensive prompt with all the text data
                prompt = f"""
                Create a comprehensive knowledge base document from this website content. Include clear section headings for all relevant business information such as Company Overview:, Primary Products/Services:, Secondary Products/Services:, Pricing:, Contact Details:, Calls to Action:,  etc:

                HOME PAGE CONTENT:
                {home_data['all_text']}
                """
                            
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}]
                )
                
                processed_content = response.choices[0].message.content
                
                if not processed_content:
                    return {
                        'success': False, 
                        'error': 'Failed to process content with OpenAI'
                    }
                
            except Exception as e:
                return {
                    'success': False, 
                    'error': f'OpenAI processing error: {str(e)}'
                }
        elif not processed_content:
            return {
                'success': False, 
                'error': 'Processed content is required when skipping OpenAI processing'
            }

        # Chunk the content for embedding
        chunks = chunk_text(processed_content)
        
        # Generate embeddings for the chunks
        if not openai_client:
            return {
                'success': False, 
                'error': 'OpenAI client is required for generating embeddings'
            }
            
        embeddings = []
        for chunk in chunks:
            response = openai_client.embeddings.create(
                input=chunk,
                model="text-embedding-ada-002"
            )
            embeddings.append(response.data[0].embedding)

        # Update Pinecone index
        if not pinecone_client or not pinecone_index or not pinecone_host:
            return {
                'success': False, 
                'error': 'Pinecone configuration is required'
            }
            
        pinecone_update_success = update_pinecone_index(namespace, chunks, embeddings)
        if not pinecone_update_success:
            return {
                'success': False, 
                'error': 'Failed to update Pinecone index'
            }

        # Prepare data for database insertion
        now = datetime.now(UTC)
        
        # Insert company data into database
        with connect_to_db() as conn:
            cursor = conn.cursor()
            
            if os.getenv('DB_TYPE', '').lower() == 'postgresql':
                # PostgreSQL uses %s placeholders
                cursor.execute('''
                    INSERT INTO companies 
                    (chatbot_id, company_url, pinecone_host_url, pinecone_index, pinecone_namespace, 
                    created_at, updated_at, scraped_text, processed_content, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (chatbot_id, website_url, pinecone_host, pinecone_index, namespace, now, now, scraped_text, processed_content, None))
            else:
                # SQLite uses ? placeholders
                cursor.execute('''
                    INSERT INTO companies 
                    (chatbot_id, company_url, pinecone_host_url, pinecone_index, pinecone_namespace, 
                    created_at, updated_at, scraped_text, processed_content, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (chatbot_id, website_url, pinecone_host, pinecone_index, namespace, now, now, scraped_text, processed_content, None))

        # Return success response
        return {
            'success': True,
            'message': 'Company added successfully',
            'chatbot_id': chatbot_id,
            'namespace': namespace,
            'website_url': website_url
        }

    except Exception as e:
        # Catch any unexpected errors
        print(f"Unexpected error in manual company addition: {e}")
        return {
            'success': False, 
            'error': f'Unexpected error: {str(e)}'
        }