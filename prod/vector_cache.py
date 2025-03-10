import time
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global in-memory cache to store vectors by namespace
vector_cache = {}

def add_to_cache(namespace: str, vectors: List[List[float]], chunks: List[str], expiry_seconds: int = 60) -> bool:
    """
    Add vectors and their corresponding text chunks to the cache with expiration
    
    Args:
        namespace: Unique identifier (usually the chatbot_id or namespace)
        vectors: List of embedding vectors
        chunks: Corresponding text chunks
        expiry_seconds: Number of seconds until cache entry expires
        
    Returns:
        bool: True if successfully added to cache
    """
    try:
        if not namespace or not vectors or not chunks:
            return False
            
        if len(vectors) != len(chunks):
            logger.error(f"Vector length {len(vectors)} does not match chunks length {len(chunks)}")
            return False
            
        # Current timestamp in seconds
        current_time = time.time()
        
        # Store in cache
        vector_cache[namespace] = {
            "vectors": vectors,
            "chunks": chunks,
            "created_at": current_time,
            "expires_at": current_time + expiry_seconds
        }
        
        logger.info(f"Added {len(vectors)} vectors to cache for namespace '{namespace}'")
        return True
    except Exception as e:
        logger.error(f"Error adding to cache: {e}")
        return False

def get_from_cache(namespace: str, query_vector: List[float], top_k: int = 3) -> List[Dict]:
    """
    Retrieve the most similar chunks from cache based on vector similarity
    
    Args:
        namespace: Unique identifier (usually the chatbot_id or namespace)
        query_vector: The query embedding vector
        top_k: Number of top results to return
        
    Returns:
        List of dictionaries with 'chunk' and 'score' fields
    """
    try:
        if not is_cache_valid(namespace):
            return []
            
        cached_data = vector_cache[namespace]
        cached_vectors = cached_data["vectors"]
        cached_chunks = cached_data["chunks"]
        
        # Calculate similarity scores
        similarities = calculate_similarity(query_vector, cached_vectors)
        
        # Get indices of top_k highest similarities
        top_indices = np.argsort(similarities)[-top_k:][::-1]  # Descending order
        
        # Create results list
        results = []
        for idx in top_indices:
            results.append({
                "text": cached_chunks[idx],
                "score": float(similarities[idx])
            })
            
        return results
    except Exception as e:
        logger.error(f"Error retrieving from cache: {e}")
        return []

def is_cache_valid(namespace: str) -> bool:
    """
    Check if cache exists for namespace and has not expired
    
    Args:
        namespace: Unique identifier (usually the chatbot_id or namespace)
        
    Returns:
        bool: True if cache exists and has not expired
    """
    if namespace not in vector_cache:
        return False
        
    cache_entry = vector_cache[namespace]
    current_time = time.time()
    
    # Check if cache has expired
    if current_time > cache_entry["expires_at"]:
        # Consider removing expired entries to free memory
        # del vector_cache[namespace]
        logger.info(f"Cache for namespace '{namespace}' has expired")
        return False
        
    return True

def calculate_similarity(query_vector: List[float], cached_vectors: List[List[float]]) -> np.ndarray:
    """
    Calculate cosine similarity between query vector and cached vectors
    
    Args:
        query_vector: The query embedding vector
        cached_vectors: List of cached embedding vectors
        
    Returns:
        numpy array of similarity scores
    """
    # Convert to numpy arrays for faster computation
    query_np = np.array(query_vector)
    vectors_np = np.array(cached_vectors)
    
    # Normalize vectors (in case they aren't already)
    query_norm = query_np / np.linalg.norm(query_np)
    vectors_norm = vectors_np / np.linalg.norm(vectors_np, axis=1, keepdims=True)
    
    # Calculate cosine similarity
    similarities = np.dot(vectors_norm, query_norm)
    
    return similarities

def cleanup_expired_cache() -> int:
    """
    Remove expired entries from the cache
    
    Returns:
        int: Number of entries removed
    """
    namespaces_to_remove = []
    current_time = time.time()
    
    for namespace, cache_entry in vector_cache.items():
        if current_time > cache_entry["expires_at"]:
            namespaces_to_remove.append(namespace)
    
    for namespace in namespaces_to_remove:
        del vector_cache[namespace]
    
    if namespaces_to_remove:
        logger.info(f"Removed {len(namespaces_to_remove)} expired cache entries")
    
    return len(namespaces_to_remove)

def get_cache_status(namespace: str = None) -> Dict:
    """
    Get status information about the cache
    
    Args:
        namespace: Optional specific namespace to check
        
    Returns:
        Dictionary with cache statistics
    """
    if namespace:
        if namespace in vector_cache:
            entry = vector_cache[namespace]
            return {
                "exists": True,
                "vector_count": len(entry["vectors"]),
                "created_at": entry["created_at"],
                "expires_at": entry["expires_at"],
                "time_remaining": max(0, entry["expires_at"] - time.time())
            }
        else:
            return {"exists": False}
    
    # Return overall cache stats
    total_entries = len(vector_cache)
    total_vectors = sum(len(entry["vectors"]) for entry in vector_cache.values())
    
    return {
        "total_entries": total_entries,
        "total_vectors": total_vectors,
        "namespaces": list(vector_cache.keys())
    }

# Added to allow dashboard document uploads with near immediate use of the new vectors
def add_document_to_cache(namespace: str, doc_id: str, vectors: List[List[float]], chunks: List[str], expiry_seconds: int = 60) -> bool:
    """
    Add document vectors and their corresponding text chunks to the cache with expiration
    
    Args:
        namespace: The company namespace
        doc_id: The document ID
        vectors: List of embedding vectors
        chunks: Corresponding text chunks
        expiry_seconds: Number of seconds until cache entry expires
        
    Returns:
        bool: True if successfully added to cache
    """
    try:
        if not namespace or not doc_id or not vectors or not chunks:
            return False
            
        if len(vectors) != len(chunks):
            logger.error(f"Vector length {len(vectors)} does not match chunks length {len(chunks)}")
            return False
            
        # Current timestamp in seconds
        current_time = time.time()
        
        # Create a unique cache key for the document
        cache_key = f"{namespace}-doc-{doc_id}"
        
        # Store in cache
        vector_cache[cache_key] = {
            "vectors": vectors,
            "chunks": chunks,
            "created_at": current_time,
            "expires_at": current_time + expiry_seconds,
            "doc_id": doc_id,
            "namespace": namespace
        }
        
        logger.info(f"Added {len(vectors)} vectors for document {doc_id} to cache with key '{cache_key}'")
        return True
    except Exception as e:
        logger.error(f"Error adding document to cache: {e}")
        return False

def get_document_from_cache(namespace: str, doc_id: str, query_vector: List[float], top_k: int = 3) -> List[Dict]:
    """
    Retrieve the most similar chunks from a specific document in cache
    
    Args:
        namespace: The company namespace
        doc_id: The document ID
        query_vector: The query embedding vector
        top_k: Number of top results to return
        
    Returns:
        List of dictionaries with 'text' and 'score' fields
    """
    try:
        cache_key = f"{namespace}-doc-{doc_id}"
        
        if not is_cache_valid(cache_key):
            return []
            
        cached_data = vector_cache[cache_key]
        cached_vectors = cached_data["vectors"]
        cached_chunks = cached_data["chunks"]
        
        # Calculate similarity scores
        similarities = calculate_similarity(query_vector, cached_vectors)
        
        # Get indices of top_k highest similarities
        top_indices = np.argsort(similarities)[-top_k:][::-1]  # Descending order
        
        # Create results list
        results = []
        for idx in top_indices:
            results.append({
                "text": cached_chunks[idx],
                "score": float(similarities[idx])
            })
            
        return results
    except Exception as e:
        logger.error(f"Error retrieving document from cache: {e}")
        return []

def get_all_document_cache_keys(namespace: str) -> List[str]:
    """
    Get all document cache keys for a namespace
    
    Args:
        namespace: The company namespace
        
    Returns:
        List of document cache keys
    """
    return [key for key in vector_cache.keys() if key.startswith(f"{namespace}-doc-")]

def get_cached_document_results(namespace: str, query_vector: List[float], top_k: int = 5) -> List[Dict]:
    """
    Search all document caches for a namespace and return top results
    
    Args:
        namespace: The company namespace
        query_vector: The query embedding vector
        top_k: Number of top results to return
        
    Returns:
        List of dictionaries with 'text' and 'score' fields
    """
    try:
        all_results = []
        
        # Get all document cache keys for this namespace
        doc_cache_keys = get_all_document_cache_keys(namespace)
        
        # If no document caches found, return empty list
        if not doc_cache_keys:
            return []
            
        # Collect results from all document caches
        for cache_key in doc_cache_keys:
            if not is_cache_valid(cache_key):
                continue
                
            cached_data = vector_cache[cache_key]
            cached_vectors = cached_data["vectors"]
            cached_chunks = cached_data["chunks"]
            
            # Calculate similarity scores
            similarities = calculate_similarity(query_vector, cached_vectors)
            
            # Get indices of top similarities 
            # Get more than top_k since we'll merge and sort later
            top_indices = np.argsort(similarities)[-top_k*2:][::-1]  # Descending order
            
            # Add results
            for idx in top_indices:
                all_results.append({
                    "text": cached_chunks[idx],
                    "score": float(similarities[idx])
                })
        
        # Sort by score and take top_k
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]
        
    except Exception as e:
        logger.error(f"Error retrieving cached document results: {e}")
        return []
