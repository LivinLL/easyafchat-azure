import os
import uuid
import docx
import io
from datetime import datetime

class DocumentsHandler:
    """
    Handler for processing uploaded documents.
    Extracts text, chunks it, generates embeddings, and stores in Pinecone.
    """
    def __init__(self, openai_client=None, pinecone_client=None, pinecone_index=None):
        """Initialize the document handler with required clients"""
        self.openai_client = openai_client
        self.pinecone_client = pinecone_client
        self.pinecone_index = pinecone_index
        
    def process_document(self, file_data, filename, chatbot_id, namespace, doc_type="uploaded_doc"):
        """
        Process a document from binary data
        
        Args:
            file_data (bytes): Binary content of the document
            filename (str): Original filename
            chatbot_id (str): ID of the chatbot this document belongs to
            namespace (str): Pinecone namespace for the company
            doc_type (str): Type of document (default: "uploaded_doc")
            
        Returns:
            dict: Processing results including doc_id, vectors_count
        """
        doc_id = str(uuid.uuid4())
        
        # Extract text based on file type
        if filename.lower().endswith('.docx'):
            extracted_text = self.extract_text_from_docx(file_data)
        elif filename.lower().endswith('.doc'):
            # For old .doc files, you might need a different library
            # This is a simplified version that might not work for all .doc files
            extracted_text = self.extract_text_from_docx(file_data)
        elif filename.lower().endswith('.txt'):
            extracted_text = file_data.decode('utf-8')
        else:
            raise ValueError(f"Unsupported file type: {filename}")
        
        # Chunk the text
        chunks = self.chunk_text(extracted_text)
        
        # Generate embeddings
        embeddings = self.get_embeddings(chunks)
        
        # Upload to Pinecone
        vectors_count = self.upload_to_pinecone(
            namespace, 
            chunks, 
            embeddings, 
            doc_id=doc_id
        )
        
        return {
            "doc_id": doc_id,
            "doc_name": filename,
            "chatbot_id": chatbot_id,
            "doc_type": doc_type,
            "content": extracted_text,
            "vectors_count": vectors_count,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
    
    def extract_text_from_docx(self, file_data):
        """Extract text from a DOCX file"""
        try:
            doc = docx.Document(io.BytesIO(file_data))
            full_text = []
            
            # Extract text from paragraphs
            for para in doc.paragraphs:
                if para.text.strip():  # Skip empty paragraphs
                    full_text.append(para.text)
            
            # Extract text from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        if cell.text.strip():
                            row_text.append(cell.text.strip())
                    if row_text:
                        full_text.append(" | ".join(row_text))
            
            return "\n\n".join(full_text)
        except Exception as e:
            print(f"Error extracting text from DOCX: {e}")
            return ""
    
    def chunk_text(self, text, chunk_size=500):
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
    
    def get_embeddings(self, text_chunks):
        """Get embeddings for text chunks using OpenAI"""
        embeddings = []
        for chunk in text_chunks:
            response = self.openai_client.embeddings.create(
                input=chunk,
                model="text-embedding-ada-002"
            )
            embeddings.append(response.data[0].embedding)
        return embeddings
    
    def upload_to_pinecone(self, namespace, text_chunks, embeddings, doc_id=None):
        """Upload vectors to Pinecone with document metadata"""
        try:
            index = self.pinecone_client.Index(self.pinecone_index)
            
            vectors = [
                (f"{namespace}-{doc_id}-{i}", 
                 embedding, 
                 {
                     "text": chunk,
                     "doc_id": doc_id,
                     "doc_type": "uploaded",
                     "chunk_index": i
                 })
                for i, (chunk, embedding) in enumerate(zip(text_chunks, embeddings))
            ]
            
            # Upsert vectors in batches of 100
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i+batch_size]
                index.upsert(vectors=batch, namespace=namespace)
            
            return len(vectors)
        except Exception as e:
            print(f"Error in Pinecone upload: {e}")
            return 0
    
    def delete_document_vectors(self, namespace, doc_id):
        """Delete all vectors for a specific document from Pinecone"""
        try:
            index = self.pinecone_client.Index(self.pinecone_index)
            
            # Find all vectors with this doc_id
            # Note: This is a simple implementation - in a production system,
            # you might want to store vector IDs for faster deletion
            filter_obj = {"doc_id": {"$eq": doc_id}}
            
            # Delete vectors
            delete_response = index.delete(
                namespace=namespace,
                filter=filter_obj
            )
            
            return True
        except Exception as e:
            print(f"Error deleting document vectors: {e}")
            return False
            
    def create_initial_document_from_website(self, chatbot_id, namespace, processed_content):
        """
        Create the initial document entry from website content
        
        Args:
            chatbot_id (str): ID of the chatbot
            namespace (str): Pinecone namespace
            processed_content (str): The processed website content
            
        Returns:
            dict: Document information
        """
        doc_id = str(uuid.uuid4())
        
        # For initial documents, vectors are already uploaded during website processing
        # So we just need to create the document record
        return {
            "doc_id": doc_id,
            "doc_name": "Scraped Content",
            "chatbot_id": chatbot_id,
            "doc_type": "scraped_content",
            "content": processed_content,
            # We don't know the vector count, would need to query Pinecone
            "vectors_count": 0,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
