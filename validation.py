"""
security/validation.py
======================
Strict input validation, sanitization, and protection mechanisms.
Ensures no malicious, suspicious, or invalid input is allowed to proceed
to analysis or storage.
"""

import re
import ipaddress
from urllib.parse import urlparse
import bleach
import requests
import os
import logging

log = logging.getLogger("security.validation")

# ===========================================================================
#  MALICIOUS PATTERN DETECTION
# ===========================================================================

# Common XSS / malicious injection payloads
MALICIOUS_PATTERNS = [
    r'javascript:',      # Inline JS execution
    r'vbscript:',        # VBScript execution
    r'data:text/html',   # Data URI HTML injection
    r'onload\s*=',       # Event handlers
    r'onerror\s*=',      # Event handlers
    r'eval\(',           # Eval execution
    r'<script',          # Explicit scripts
    r'document\.cookie', # Cookie theft attempts
    r'window\.location', # Redirect attempts
]

def detect_malicious_patterns(text: str) -> bool:
    """
    Scans the text for explicitly malicious keywords and patterns (regex).
    Returns True if a malicious pattern is detected, False otherwise.
    """
    if not text:
        return False
        
    text_lower = text.lower()
    for pattern in MALICIOUS_PATTERNS:
        if re.search(pattern, text_lower):
            log.warning(f"Malicious pattern detected: {pattern}")
            return True
            
    return False

# ===========================================================================
#  INPUT SANITIZATION
# ===========================================================================

def sanitize_input(text: str) -> str:
    """
    Aggressively sanitize input text by stripping all HTML tags, JavaScript, 
    and CSS overrides using the Bleach library.
    """
    if not text:
        return ""
        
    # strip=True removes the tags instead of escaping them, leaving plain text
    sanitized = bleach.clean(
        text,
        tags=[],          # Allow NO tags
        attributes={},    # Allow NO attributes
        strip=True        # Delete tags entirely
    )
    return sanitized.strip()

# ===========================================================================
#  TEXT VALIDATION
# ===========================================================================

def validate_text(text: str, max_length: int = 50000) -> tuple[bool, str, str, str]:
    """
    Validates and sanitizes text input strictly.
    Returns:
        (is_valid, final_sanitized_text, error_message, status_type)
        
    status_type is either 'error' (for invalid input) or 'blocked' (for malicious).
    """
    if not text or not text.strip():
        return False, "", "Invalid input. Please enter a valid text.", "error"
        
    if len(text) > max_length:
        return False, "", f"Invalid input. Content too long (max {max_length} characters).", "error"
        
    # Check for explicitly malicious patterns before sanitization
    if detect_malicious_patterns(text):
        return False, "", "⚠️ Suspicious or malicious input detected. Request blocked.", "blocked"
        
    # Sanitize the input
    clean_text = sanitize_input(text)
    
    # Catch cases where text was purely malicious HTML and became empty after bleach
    if not clean_text:
        return False, "", "Invalid input. Content contains unsafe tags.", "error"
        
    # Extra check on sanitized text just to be safe
    if detect_malicious_patterns(clean_text):
        return False, "", "⚠️ Suspicious or malicious input detected. Request blocked.", "blocked"
        
    return True, clean_text, "", "success"

# ===========================================================================
#  URL VALIDATION & SAFE BROWSING
# ===========================================================================

def _check_safe_browsing(url: str) -> bool:
    """
    Calls Google Safe Browsing API.
    Returns True if the URL is SAFE, False if it is FLAGED AS MALICIOUS.
    """
    api_key = os.getenv("SAFE_BROWSING_API_KEY", "").strip()
    
    # If API key is not configured, we allow the traffic to proceed or log a warning.
    # In production, missing this key would disable Google Safe Browsing checks.
    if not api_key:
        log.warning("SAFE_BROWSING_API_KEY is missing. Skipping Safe Browsing checks.")
        return True
        
    api_url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={api_key}"
    
    payload = {
        "client": {
            "clientId": "truthguard-api",
            "clientVersion": "1.0.0"
        },
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [
                {"url": url}
            ]
        }
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # If 'matches' is in the JSON response, the URL was flagged!
        if "matches" in data and len(data["matches"]) > 0:
            log.warning(f"Google Safe Browsing flagged URL: {url} | Details: {data['matches']}")
            return False
            
    except Exception as e:
        log.error(f"Error querying Google Safe Browsing API: {e}")
        # Fail-open: if Google's server is down, we don't totally break our app.
        return True
        
    return True

def validate_url(url: str) -> tuple[bool, str, str]:
    """
    Validates a URL securely.
    Ensures safe schemes, prevents IP addressing, drops malicious domains.
    Returns:
        (is_valid, error_message, status_type)
        
    status_type is either 'error' (for invalid formatting) or 'blocked' (for malicious).
    """
    if not url or not url.strip():
        return False, "Invalid input. Please enter a valid URL.", "error"
        
    url = url.strip()
    
    # Fix scheme if missing, exactly as app.py did, but gently
    if not url.startswith(('http://', 'https://')):
        # However, block if they tried another scheme completely
        if '://' in url:
            scheme = url.split('://')[0].lower()
            if scheme not in ["http", "https"]:
                return False, "⚠️ Suspicious or malicious input detected. Request blocked.", "blocked"
        url = 'https://' + url

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid input. Malformed URL.", "error"

    hostname = parsed.hostname or ""
    
    if not hostname:
        return False, "Invalid input. Please enter a valid URL.", "error"
        
    # Check explicitly for bad schemes (just in case urlparse bypassed above check)
    if parsed.scheme.lower() not in ["http", "https"]:
        return False, "⚠️ Suspicious or malicious input detected. Request blocked.", "blocked"
        
    # Block IP-based URLs to prevent internal port scanning / SSRF
    try:
        ipaddress.ip_address(hostname)
        return False, "Invalid input. IP-based URLs are not allowed.", "error"
    except ValueError:
        pass  # It's a normal domain, which is good

    # Basic malicious pattern check inside URL string (e.g. javascript payloads in query)
    if detect_malicious_patterns(url):
        return False, "⚠️ Suspicious or malicious input detected. Request blocked.", "blocked"
        
    # Google Safe Browsing API Integration
    if not _check_safe_browsing(url):
        return False, "⚠️ Suspicious or malicious input detected. Request blocked.", "blocked"
        
    return True, "", "success"
