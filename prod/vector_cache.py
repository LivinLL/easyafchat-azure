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
