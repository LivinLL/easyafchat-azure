"""
List of blocked domains that should not be processed by the chatbot creator.
This includes major platforms, competitors, and other services we don't want to process.
"""

# List of common major domains to block
BLOCKED_DOMAINS = [
    # Major search engines
    "google.com",
    "bing.com",
    "yahoo.com",
    "baidu.com",
    "yandex.com",
    
    # Major e-commerce sites
    "amazon.com",
    "walmart.com",
    "alibaba.com",
    "ebay.com",
    "target.com",
    "bestbuy.com",
    
    # Major social media
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "linkedin.com",
    "tiktok.com",
    "reddit.com",
    "pinterest.com",
    "youtube.com",
    
    # Other major sites
    "microsoft.com",
    "apple.com",
    "netflix.com",
    "spotify.com",
    "wikipedia.org",
    "github.com",
    "cloudflare.com"
]

def is_domain_blocked(url):
    """
    Check if a domain should be blocked based on our blocklist.
    
    Args:
        url (str): The URL or domain to check
        
    Returns:
        bool: True if the domain should be blocked, False otherwise
    """
    # Handle empty input
    if not url:
        return False
        
    # Strip protocol (http://, https://)
    if '://' in url:
        url = url.split('://', 1)[1]
    
    # Get domain (strip path, query params, etc)
    domain = url.split('/', 1)[0].lower()
    
    # Remove port number if present
    if ':' in domain:
        domain = domain.split(':', 1)[0]
    
    # Check for exact match
    if domain in BLOCKED_DOMAINS:
        return True
    
    # Check for subdomain match
    for blocked_domain in BLOCKED_DOMAINS:
        # Check if it's a subdomain of a blocked domain
        if domain.endswith('.' + blocked_domain):
            return True
        
        # Check if the domain without 'www.' is blocked
        if domain.startswith('www.'):
            if domain[4:] in BLOCKED_DOMAINS:
                return True
    
    # No match found
    return False
