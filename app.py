from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import bleach
import time
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
from pymongo import MongoClient
import random
import os
import certifi

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import re
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from nltk.corpus import stopwords
import nltk
import ssl
from nltk.sentiment.vader import SentimentIntensityAnalyzer

load_dotenv(override=True)

# ---------- Security: Encryption & Hashing ----------
# Import AFTER dotenv so the encryption module can read ENCRYPTION_KEY
from security.encryption import (
    encrypt_data, decrypt_data,
    hash_password, verify_password,
    encrypt_user_fields, decrypt_user_fields,
)
from security.validation import validate_text, validate_url

# Disable SSL verification for requests and other libraries
# (Needed for some restricted network environments)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception as e:
    print(f"Warning: Could not disable SSL verification: {e}")

# ---------- Auto-whitelist current IP in MongoDB Atlas ----------
from atlas_ip_whitelist import whitelist_current_ip
whitelist_current_ip()

# Download NLTK stopwords
try:
    nltk.download("stopwords", quiet=True)
except Exception as e:
    print(f"Warning: Could not download NLTK stopwords: {e}")

# ---------- BERT Model Configuration ----------
BERT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "fake_news", "fake_news_model")
MAX_LEN = 256
def _get_device():
    try:
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
    except Exception:
        pass
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")

DEVICE = _get_device()

# ---------- Load BERT Model & Tokenizer ----------
print("DEBUG: Loading BERT model and tokenizer...")
try:
    bert_tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_PATH)
    bert_model = AutoModelForSequenceClassification.from_pretrained(BERT_MODEL_PATH)
    bert_model.to(DEVICE)
    bert_model.eval()
    print(f"DEBUG: BERT model loaded successfully on: {DEVICE}")
except Exception as e:
    print(f"ERROR: Failed to load BERT model: {e}")
    bert_model = None
    bert_tokenizer = None

# ---------- Text Cleaning Logic ----------
stop_words = set(stopwords.words("english"))
MAX_LENGTH = 300

# ---------- API Keys ----------
GOOGLE_FACTCHECK_KEY = os.getenv("GOOGLE_FACTCHECK_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ---------- Trusted News Domains ----------
TRUSTED_DOMAINS = [
    # Indian News
    "timesofindia.indiatimes.com", "ndtv.com", "thehindu.com",
    "hindustantimes.com", "indianexpress.com", "theprint.in",
    "scroll.in", "livemint.com", "business-standard.com",
    "telegraphindia.com", "deccanherald.com", "firstpost.com",
    "news18.com", "abplive.com", "zeenews.india.com", "aajtak.in",
    "pti.in", "ani.in", "ians.in",
    # International News
    "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com",
    "nytimes.com", "theguardian.com", "washingtonpost.com",
    "bloomberg.com", "cnn.com", "aljazeera.com", "dw.com",
    "france24.com", "economist.com", "ft.com",
]

# ---------- Known Misinformation Topics ----------
# Patterns for well-established conspiracy theories / debunked claims.
# These trigger a strong FAKE signal regardless of other scoring.
MISINFORMATION_PATTERNS = [
    # 5G / COVID misinformation
    r'5g.{0,30}(spread|cause[sd]?|linked|creat).{0,30}covid',
    r'covid.{0,30}(caused?|spread).{0,30}5g',
    r'5g.{0,30}(kill|harm|radi)',
    # Vaccine misinformation
    r'vaccine.{0,30}(cause[sd]?|linked.{0,10}).{0,20}autism',
    r'(mrna|covid).{0,20}vaccine.{0,30}microchip',
    r'bill gates.{0,30}(microchip|vaccine|depopulat)',
    r'vaccine.{0,30}(kill|harm|poison|steril)',
    # Flat earth / moon hoax
    r'flat.?earth', r'moon.?landing.{0,20}(fake|hoax|staged)',
    # Chemtrails / weather control
    r'chemtrail', r'weather.{0,15}(control|manipulation|weapon)',
    # Deep state / new world order
    r'deep.?state', r'new.?world.?order',
    r'illuminati.{0,20}(control|run)',
    # Election conspiracy (generic)
    r'election.{0,20}(stolen|rigged|fraud).{0,20}proof',
    # COVID origin misinformation
    r'covid.{0,20}(lab.{0,10}made|bioweapon|planned.?emic)',
    # Water/food conspiracy
    r'fluoride.{0,20}(mind.?control|poison)',
    r'(government|they).{0,30}put.{0,15}(chemical|drug).{0,15}(water|food)',
]

def get_misinformation_score(text):
    """
    Layer 1: Built-in known conspiracy / misinformation detector.
    Returns (is_misinfo, matched_topic) where is_misinfo=True means strong FAKE signal.
    """
    text_lower = text.lower()
    for pattern in MISINFORMATION_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            return True, m.group(0)[:60]
    return False, None


# ---------- Google Fact Check API ----------
def check_google_factcheck(text):
    """
    Layer 2: Query Google Fact Check Tools API.
    Returns (verdict, rating, source) where:
      verdict = 'fake'  if the claim is debunked
      verdict = 'real'  if the claim is confirmed true
      verdict = None    if no fact-check found
    """
    if not GOOGLE_FACTCHECK_KEY:
        return None, None, None

    import urllib.parse, urllib.request, json
    # Use the first 120 chars of text as the query claim
    query = text[:120].strip()
    try:
        params = urllib.parse.urlencode({
            'query': query,
            'key': GOOGLE_FACTCHECK_KEY,
            'languageCode': 'en',
        })
        url = f'https://factchecktools.googleapis.com/v1alpha1/claims:search?{params}'
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = json.loads(resp.read())
        claims = data.get('claims', [])
        if not claims:
            return None, None, None

        # Check the first matching claim's rating
        claim = claims[0]
        reviews = claim.get('claimReview', [])
        if not reviews:
            return None, None, None
        review = reviews[0]
        rating = review.get('textualRating', '').lower()
        publisher = review.get('publisher', {}).get('name', 'Unknown')

        FAKE_RATINGS = [
            # Direct false labels
            'false', 'fake', 'misleading', 'pants on fire', 'inaccurate',
            'mostly false', 'incorrect', 'debunked', 'fabricated', 'hoax',
            'satire', 'misrepresentation', 'scam', 'exaggerated', 'wrong',
            # Debunking language (e.g. Full Fact: "no evidence that 5G...")
            'no evidence', 'not true', 'no proof', 'no data',
            'claim is false', 'rumour', 'rumor', 'not accurate',
            'lacks evidence', 'unverified claim', 'misinformation',
            'distorted', 'out of context', 'lacks context',
        ]
        TRUE_RATINGS = [
            'true', 'correct', 'accurate', 'mostly true', 'confirmed',
            'verified', 'legit', 'real', 'evidence supports',
        ]
        if any(r in rating for r in FAKE_RATINGS):
            return 'fake', rating, publisher
        elif any(r in rating for r in TRUE_RATINGS):
            return 'real', rating, publisher
        else:
            return 'uncertain', rating, publisher

    except Exception as e:
        print(f'DEBUG factcheck API error: {e}')
        return None, None, None


# ---------- NewsAPI Source Verification ----------
NEWS_API_SOURCES = [
    # NewsAPI source IDs for top credible outlets
    'bbc-news', 'reuters', 'associated-press', 'the-hindu', 'ndtv',
    'the-times-of-india', 'al-jazeera-english', 'cnn', 'the-guardian-uk',
    'bloomberg', 'the-washington-post', 'nbc-news', 'abc-news',
]

def check_newsapi_sources(text):
    """
    Layer 3: Query NewsAPI to check if the headline/claim appears in news.
    Returns (found_trusted, found_anywhere, source_name):
      found_trusted  = True  → found in a credible/trusted outlet
      found_anywhere = True  → found somewhere (but maybe not trusted)
      source_name            → name of the source where found
    """
    if not NEWS_API_KEY:
        return False, None, None

    import urllib.parse, urllib.request, json
    # Use first 50 chars for broader matching
    query = text[:50].strip()
    try:
        params = urllib.parse.urlencode({
            'q': query,
            'apiKey': NEWS_API_KEY,
            'language': 'en',
            'sortBy': 'relevancy',
            'pageSize': 10,
        })
        url = f'https://newsapi.org/v2/everything?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'FakeNewsDetector/1.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())

        articles = data.get('articles', [])
        if not articles:
            return False, False, None  # Not found anywhere

        # Expanded trusted source names for matching
        TRUSTED_NAMES = [
            'ndtv', 'times of india', 'the hindu', 'hindustan times', 'indian express',
            'bbc', 'reuters', 'associated press', 'ap news', 'the guardian',
            'bloomberg', 'washington post', 'cnn', 'al jazeera',
            'france 24', 'dw', 'financial times', 'the print', 'scroll',
            'firstpost', 'news18', 'zee news', 'ani',
        ]
        first_source = articles[0].get('source', {}).get('name', 'Unknown')
        for article in articles:
            source_name = article.get('source', {}).get('name', '').lower()
            source_url = article.get('url', '').lower()
            for name in TRUSTED_NAMES:
                if name in source_name:
                    return True, True, article.get('source', {}).get('name', 'Trusted Source')
            for domain in TRUSTED_DOMAINS:
                if domain in source_url:
                    return True, True, article.get('source', {}).get('name', domain)
        # Articles exist but none from trusted sources
        return False, True, first_source

    except Exception as e:
        print(f'DEBUG newsapi error: {e}')
        return False, None, None  # None = API error (not the same as 0 results)


# ---------- URL-based Source Trust ----------
def get_source_trust_score(text):
    """
    Checks if the content contains URLs from trusted news domains.
    Returns (is_trusted, is_unknown_url).
    """
    urls = re.findall(r'https?://\S+|www\.\S+', text, re.IGNORECASE)
    if not urls:
        return False, False
    for url in urls:
        url_lower = url.lower()
        for domain in TRUSTED_DOMAINS:
            if domain in url_lower:
                return True, False
    return False, True


# ---------- Sensationalism Detector ----------
SENSATIONALISM_PATTERNS = [
    r'\bbreaking[:\s!]+',
    r'\bshocking\b', r'\bshocker\b',
    r'\bmust.?see\b', r'\bmust.?read\b', r'\byou.?won.?t.?believe\b',
    r'\bexposed\b', r'\bsecret.?revealed\b', r'\bthey.?don.?t.?want.?you\b',
    r'\bgovernment.?hiding\b', r'\bconspiracy\b',
    r'\bOMG\b', r'\bWOW\b',
    r'\d+\s*reasons\s+why',
    r'click\s+here\s+to\s+(see|watch|find)',
    r'\bcrazy\b', r'\binsane\b', r'\bunbelievable\b', r'\bstunning\b',
    r'!{2,}', r'\?{2,}',
]

def get_sensationalism_score(text):
    """
    Returns a fake_score from 0.0 (none) to 1.0 (heavily sensationalist).
    """
    matches = sum(1 for p in SENSATIONALISM_PATTERNS if re.search(p, text, re.IGNORECASE))
    # ALL-CAPS: require 2+ words, case-sensitive
    if len(re.findall(r'\b[A-Z]{5,}\b', text)) >= 2:
        matches += 1
    return min(1.0, matches / 4.0)


# Download VADER lexicon
try:
    nltk.download("vader_lexicon", quiet=True)
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
except Exception as e:
    print(f"Warning: Could not download VADER lexicon: {e}")
    sia = None

def get_sentiment(text):
    if not sia:
        return "Neutral"
    score = sia.polarity_scores(text)['compound']
    if score >= 0.05:
        return "Positive"
    elif score <= -0.05:
        return "Negative"
    else:
        return "Neutral"

def get_subject(text):
    text = text.lower()
    subjects = {
        "politics": ["government", "election", "president", "senate", "congress", "party", "minister", "parliament"],
        "world news": ["international", "global", "un", "middle east", "europe", "asia", "africa", "war", "conflict"],
        "tech": ["technology", "ai", "software", "apple", "google", "microsoft", "cyber", "internet", "space"],
        "health": ["medical", "doctor", "virus", "health", "hospital", "vaccine", "science", "research"],
        "business": ["economy", "market", "stock", "company", "trade", "finance", "bank", "ceo"]
    }
    for sub, keywords in subjects.items():
        if any(kw in text for kw in keywords):
            return sub.title()
    return "General"

def get_sources(text):
    urls = re.findall(r'http\S+|www\S+', text)
    if urls:
        return f"{len(urls)} Links Found"
    
    citations = re.findall(r'\[\d+\]|\(\w+ \d{4}\)', text)
    if citations:
        return f"{len(citations)} Citations Found"
        
    if "according to" in text.lower() or "reported by" in text.lower():
        return "Textual References Found"
        
    return "None Detected"

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'http\S+|www\.\S+', '', text)
    boilerplate = [
        r'(?i)subscribe(d)? (to|for).*',
        r'(?i)sign (up|in|out).*',
        r'(?i)follow us on.*',
        r'(?i)share (this|on).*',
        r'(?i)read (more|also|next).*',
        r'(?i)(click|tap) here.*',
        r'(?i)advertisement',
        r'(?i)cookie policy.*',
        r'(?i)all rights reserved.*',
        r'(?i)terms (of|and) (service|use|conditions).*',
        r'(?i)privacy policy.*',
        r'(?i)newsletter.*',
    ]
    for pattern in boilerplate:
        text = re.sub(pattern, '', text)
    # Keep lines with 3+ words to preserve headlines and subheadings
    lines = [ln.strip() for ln in text.splitlines() if len(ln.split()) >= 3]
    text = ' '.join(lines)
    return re.sub(r'\s{2,}', ' ', text).strip()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

def _fetch_with_requests_bs4(url):
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return None, None

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "form", "noscript", "figure", "iframe"]):
            tag.decompose()

        # Extract title
        title = (
            soup.find("h1") 
            or soup.find("title")
            or soup.find(class_=re.compile(r"headline|title", re.I))
            or soup.find(id=re.compile(r"headline|title", re.I))
        )
        title_text = title.get_text(strip=True) if title else ""

        body = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=re.compile(r"article|story|content|post|body", re.I))
            or soup.find(id=re.compile(r"article|story|content|post|body", re.I))
        )
        container = body if body else soup
        paragraphs = container.find_all("p")
        text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
        
        if len(text.split()) > 50:
            return title_text, text
        return None, None

    except Exception as e:
        print(f"   [Layer 1 - requests+BS4] {e}")
        return None, None

def _fetch_with_newspaper(url):
    try:
        from newspaper import Article, Config
    except ImportError:
        return None, None

    try:
        config = Config()
        config.browser_user_agent = _HEADERS["User-Agent"]
        config.request_timeout = 15
        config.fetch_images = False

        article = Article(url, config=config)
        article.download()
        article.parse()

        text = article.text.strip()
        title = article.title.strip() if article.title else ""
        
        if len(text.split()) > 50:
            return title, text
        return None, None

    except Exception as e:
        print(f"   [Layer 2 - newspaper3k] {e}")
        return None, None

def _fetch_with_trafilatura(url):
    try:
        import trafilatura
    except ImportError:
        return None, None

    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False,
                                        include_tables=False, no_fallback=False)
            if text and len(text.split()) > 50:
                # trafilatura can also extract title if we pass it
                title = trafilatura.extract_metadata(downloaded)
                title_text = title.title if title and hasattr(title, 'title') else ""
                return title_text, text
        return None, None
    except Exception as e:
        print(f"   [Layer 3 - trafilatura] {e}")
        return None, None

def fetch_article_from_url(url):
    for name, fn in [
        ("requests + BeautifulSoup", _fetch_with_requests_bs4),
        ("newspaper3k", _fetch_with_newspaper),
        ("trafilatura", _fetch_with_trafilatura),
    ]:
        print(f"   Trying {name}...")
        result = fn(url)
        if result and result[0] is not None and result[1] is not None:
            title, raw = result
            cleaned = clean_text(raw)
            word_count = len(cleaned.split())
            if word_count > 50:
                print(f"   Extracted {word_count} words via {name}")
                print(f"   Title: {title[:80] if title else 'N/A'}...")
                return title, cleaned
            else:
                print(f"   Only {word_count} usable words - trying next layer...")

    print("All extraction methods failed.")
    return None, None

def get_complexity(text):
    words = text.split()
    if not words:
        return "Low"
    avg_len = sum(len(word) for word in words) / len(words)
    unique_words = len(set(words)) / len(words)
    
    if avg_len > 6 and unique_words > 0.6:
        return "High"
    elif avg_len > 4:
        return "Medium"
    else:
        return "Low"

app = Flask(__name__)

import requests

def verify_recaptcha(recaptcha_response):
    secret = os.getenv("RECAPTCHA_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe")
    if not recaptcha_response:
        return False
    try:
        r = requests.post("https://www.google.com/recaptcha/api/siteverify", data={
            "secret": secret,
            "response": recaptcha_response
        }, timeout=5)
        return r.json().get("success", False)
    except:
        return False

@app.context_processor
def inject_recaptcha():
    return dict(RECAPTCHA_SITE_KEY=os.getenv("RECAPTCHA_SITE_KEY", "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"))

app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Security Configurations
# SESSION_COOKIE_SECURE must be False when running on http://localhost
app.config['SESSION_COOKIE_SECURE'] = os.getenv("FLASK_ENV") == "production"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = timedelta(minutes=30)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

csrf = CSRFProtect(app)
# Allow CSRF token via X-CSRFToken header for AJAX calls
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']
app.config['WTF_CSRF_TIME_LIMIT'] = None

csp = {
    'default-src': ["'self'", 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'],
    'script-src': ["'self'", "'unsafe-inline'", 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net',
                   'www.google.com', 'www.gstatic.com', 'www.recaptcha.net'],
    'style-src': ["'self'", "'unsafe-inline'", 'cdnjs.cloudflare.com', 'fonts.googleapis.com'],
    'img-src': ["'self'", 'data:', 'https:'],
    'frame-src': ["'self'", 'www.google.com', 'www.gstatic.com', 'www.recaptcha.net'],
    'connect-src': ["'self'", 'www.google.com', 'www.gstatic.com', 'www.recaptcha.net'],
}
Talisman(app, content_security_policy=csp, force_https=False)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour"]
)

# Magic Link Serializer
serializer = URLSafeTimedSerializer(app.secret_key)



# ------------------ Email Mock / Service ------------------
def send_magic_link(email, link):
    """
    Sends a magic login link to the user's email.
    In a real app, you would use smtplib or an API like Resend/SendGrid.
    """
    # For now, we'll log it for the user to see, and attempt a real send if SMTP is configured
    print(f"\n[EMAIL MOCK] Sending Magic Link to {email}")
    print(f"[EMAIL MOCK] Link: {link}\n")
    
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    
    if all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        try:
            msg = MIMEText(f"Click the link below to log in to Fake News Detection:\n\n{link}")
            msg['Subject'] = 'Your Magic Login Link'
            msg['From'] = smtp_user
            msg['To'] = email
            
            with smtplib.SMTP_SSL(smtp_host, int(smtp_port)) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, email, msg.as_string())
            print(f"DEBUG: Email sent successfully to {email}")
        except Exception as e:
            print(f"ERROR: Failed to send email: {e}")
    else:
        print("WARNING: SMTP credentials not fully configured. Email not sent via SMTP.")

def verify_email_exists(email):
    """
    Verify if an email address exists by checking with the recipient's mail server.
    Returns (True, None) if email exists, (False, error_message) if not.
    """
    import re
    import dns.resolver
    
    # Basic syntax validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return False, "Invalid email format"
    
    try:
        # Extract domain from email
        domain = email.split('@')[1]
        
        # Get MX records for the domain
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_host = str(mx_records[0].exchange)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return False, f"Email domain '{domain}' does not exist or has no mail server"
        
        # Connect to the mail server and verify
        try:
            import socket
            server = smtplib.SMTP(timeout=10)
            server.set_debuglevel(0)
            
            # Connect to MX server
            server.connect(mx_host)
            server.helo(server.local_hostname)
            server.mail('verify@example.com')  # Sender for verification
            code, message = server.rcpt(str(email))
            server.quit()
            
            # Check if the email was accepted
            if code == 250:
                return True, None
            else:
                return False, "Email address does not exist on the mail server"
                
        except smtplib.SMTPServerDisconnected:
            return False, "Mail server disconnected during verification"
        except smtplib.SMTPConnectError:
            return False, "Could not connect to mail server"
        except socket.timeout:
            return False, "Mail server verification timed out"
        except Exception as e:
            # If verification fails due to server issues, we'll allow it
            # (some servers don't allow verification)
            print(f"WARNING: Could not verify email {email}: {e}")
            return True, None  # Allow signup if verification is inconclusive
            
    except Exception as e:
        print(f"ERROR during email verification: {e}")
        return False, f"Email verification failed: {str(e)}"

# ------------------ MongoDB Setup ------------------
# Python 3.12 + MongoDB Atlas can hit TLSV1_ALERT_INTERNAL_ERROR.
# Fix: explicitly pass tls=True with certifi CA file, and fall back to
# tlsInsecure=True if the first attempt still fails at startup.

def _create_mongo_client():
    """Try to create a MongoClient. Returns the client on success, or None on failure."""
    uri = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/")
    is_atlas = "mongodb.net" in uri or "mongodb+srv" in uri

    if is_atlas:
        import ssl

        # Attempt 1: proper TLS with certifi CA bundle
        try:
            _client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=20000,
            )
            _client.admin.command("ping")
            print("DEBUG: MongoDB Atlas connected (TLS with certifi).")
            return _client
        except Exception as e1:
            print(f"WARNING: MongoDB TLS (certifi) failed: {e1}")

        # Attempt 2: disable cert verification flag
        try:
            _client = MongoClient(
                uri,
                tls=True,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=20000,
            )
            _client.admin.command("ping")
            print("WARNING: MongoDB Atlas connected with tlsAllowInvalidCertificates=True.")
            return _client
        except Exception as e2:
            print(f"WARNING: MongoDB tlsAllowInvalidCertificates fallback failed: {e2}")

        # Attempt 3: custom SSLContext — bypasses Python 3.12 TLS negotiation issues
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            # Allow broader protocol negotiation
            ssl_ctx.options &= ~ssl.OP_NO_SSLv3
            _client = MongoClient(
                uri,
                tls=True,
                tlsAllowInvalidCertificates=True,
                tlsAllowInvalidHostnames=True,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=25000,
            )
            _client.admin.command("ping")
            print("WARNING: MongoDB Atlas connected via custom SSLContext fallback.")
            return _client
        except Exception as e3:
            print(f"ERROR: All three Atlas TLS attempts failed: {e3}")
            return None
    else:
        # Local MongoDB — no TLS needed
        try:
            _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
            print("DEBUG: Local MongoDB connected.")
            return _client
        except Exception as e:
            print(f"ERROR: Local MongoDB connection failed: {e}")
            return None

# Attempt to connect — app starts even if DB is unavailable
client = _create_mongo_client()
if client is None:
    print("WARNING: Running without a MongoDB connection. Login/Signup will be unavailable.")
    db = None
    users_col = None
else:
    db = client["fake_news_db"]
    users_col = db["users"]

def _db_unavailable():
    """Flash a friendly error and redirect to login when the database is down."""
    flash("Database is currently unavailable. Please try again later or contact support.", "error")
    return redirect(url_for("login"))

# ------------------ Routes ------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        # Verify reCAPTCHA first
        recaptcha_response = request.form.get("g-recaptcha-response")
        if not verify_recaptcha(recaptcha_response):
            flash("Please complete the CAPTCHA.", "error")
            return redirect(url_for("login"))

        if users_col is None:
            return _db_unavailable()

        email = request.form["email"]
        password = request.form["password"]

        user_record = users_col.find_one({"email": email})
        if user_record and user_record.get('locked_until'):
            if datetime.now() < user_record['locked_until']:
                flash("Account locked due to too many failed attempts. Try again later.", "error")
                return redirect(url_for("login"))
            else:
                users_col.update_one({"email": email}, {"$set": {"failed_attempts": 0}, "$unset": {"locked_until": ""}})

        # ── SECURITY: bcrypt password verification ──
        # We no longer query by password. Instead we fetch the user by email
        # and verify the password hash using bcrypt.
        # Legacy plaintext passwords are auto-upgraded on first successful login.
        if user_record and verify_password(password, user_record.get("password", "")):
            # Auto-upgrade: if the stored password is still plaintext, hash it now
            stored_pw = user_record.get("password", "")
            if not stored_pw.startswith("$2b$"):
                users_col.update_one(
                    {"email": email},
                    {"$set": {"password": hash_password(password)}}
                )
                print(f"DEBUG: Auto-upgraded password to bcrypt for {email}")

            users_col.update_one({"email": email}, {"$set": {"failed_attempts": 0}})
            session.permanent = True
            token = serializer.dumps(email, salt='magic-link')
            link = url_for('magic_login', token=token, _external=True)
            send_magic_link(email, link)
            return redirect(url_for("check_email"))
        else:
            if user_record:
                failed = user_record.get('failed_attempts', 0) + 1
                update_data = {"$set": {"failed_attempts": failed}}
                if failed >= 5:
                    update_data["$set"]["locked_until"] = datetime.now() + timedelta(minutes=15)
                users_col.update_one({"email": email}, update_data)
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/magic-login/<token>")
@limiter.limit("3 per minute")
def magic_login(token):
    session.permanent = True
    try:
        # Link valid for 10 minutes (600 seconds)
        email = serializer.loads(token, salt='magic-link', max_age=600)
        session["user_email"] = email
        return redirect(url_for("dashboard"))
    except SignatureExpired:
        return "The magic link has expired. Please try logging in again."
    except BadTimeSignature:
        return "Invalid magic link. Please try logging in again."


@app.route("/check-email")
def check_email():
    return render_template("check_email.html")


@app.route("/verify_otp", methods=["GET", "POST"])
@limiter.limit("3 per minute")
def verify_otp():
    if "pending_email" not in session:
        return redirect(url_for("login"))

    otp_time = session.get("otp_time", 0)
    if time.time() > otp_time + 300:
        session.pop("otp", None)
        flash("OTP has expired. Please login again.", "error")
        return redirect(url_for("login"))
        
    retries = session.get("otp_retries", 0)
    if retries >= 3:
        session.pop("otp", None)
        flash("Too many failed OTP attempts. Please login again.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        user_otp = request.form["otp"]
        if user_otp == session.get("otp"):
            session.pop("otp", None)
            session.pop("pending_email", None)
            session["user_email"] = session.get("pending_email")
            session.permanent = True
            return redirect(url_for("dashboard"))
        else:
            session["otp_retries"] = retries + 1
            return "Invalid OTP. Please try again."

    return render_template("otp.html")


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def signup():
    if request.method == "POST":
        if users_col is None:
            return _db_unavailable()

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        
        # safely handle new/optional fields
        phone = request.form.get("phone", "")
        country = request.form.get("country", "")

        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for("signup"))

        # Strong password policy enforcement
        import re as _re_pw
        pw_errors = []
        if len(password) < 8:
            pw_errors.append("at least 8 characters")
        if not _re_pw.search(r'[A-Z]', password):
            pw_errors.append("one uppercase letter")
        if not _re_pw.search(r'[a-z]', password):
            pw_errors.append("one lowercase letter")
        if not _re_pw.search(r'[0-9]', password):
            pw_errors.append("one digit")
        if not _re_pw.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
            pw_errors.append("one special character (!@#$%^&*...)")
        if pw_errors:
            flash("Weak password. Must contain: " + ", ".join(pw_errors) + ".", "error")
            return redirect(url_for("signup"))

        # Basic email format check only (DNS verification skipped - unreliable on restricted networks)
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            # Email Validation using email-validator
            try:
                validate_email(email)
            except EmailNotValidError:
                flash("Invalid email format (Email Validator rejected).", "error")
                return redirect(url_for("signup"))
            # End hook:
            flash("Invalid email format. Please use a valid email address.", "error")
            return redirect(url_for("signup"))

        try:
            # Check if user already exists
            existing_user = users_col.find_one({"email": email})
            if existing_user:
                flash("User with this email already exists", "error")
                return redirect(url_for("signup"))

            # ── SECURITY: hash password with bcrypt, encrypt PII fields ──
            users_col.insert_one({
                "name": name,
                "email": email,
                "phone": encrypt_data(phone),      # AES-256 encrypted
                "country": country,
                "password": hash_password(password)  # bcrypt hashed
            })
        except Exception as e:
            print(f"ERROR: DB operation failed during signup: {e}")
            return _db_unavailable()

        flash("Account created successfully! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@csrf.exempt
@app.route("/analyze", methods=["POST"])
@limiter.limit("10 per minute")
def analyze_news():
    if "user_email" not in session:
        return {"error": "Unauthorized"}, 401
    
    data = request.get_json()
    content = data.get("content", "")
    
    # --- STRICT INPUT VALIDATION ---
    is_valid, content, err_msg, err_type = validate_text(content)
    if not is_valid:
        return jsonify({
            "status": "error" if err_type == "error" else "blocked",
            "message": err_msg,
            "error": err_msg
        }), 400

    if bert_model and bert_tokenizer:
        try:
            cleaned = clean_text(content)
            
            encoding = bert_tokenizer(
                cleaned,
                max_length=MAX_LEN,
                padding='max_length',
                truncation=True,
                return_attention_mask=True,
                return_tensors='pt'
            )
            input_ids = encoding['input_ids'].to(DEVICE)
            attention_mask = encoding['attention_mask'].to(DEVICE)

            with torch.no_grad():
                outputs = bert_model(input_ids=input_ids, attention_mask=attention_mask)

            probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()[0]
            fake_prob = round(float(probs[0]) * 100, 2)
            real_prob = round(float(probs[1]) * 100, 2)
            raw_prob = float(probs[0])

            print(f"DEBUG: BERT raw_prob={raw_prob:.4f} fake_prob={fake_prob}% real_prob={real_prob}%")

            # Final scoring logic combining BERT with external layers
            detection_method = "bert_model"
            summary = ""
            
            # Layer 1: Misinformation Patterns
            is_misinfo, topic = get_misinformation_score(content)
            if is_misinfo:
                status = "Fake"
                confidence = max(95.0, fake_prob if fake_prob > 50 else 95.0)
                fake_prob = confidence
                real_prob = round(100.0 - confidence, 2)
                detection_method = "misinfo_pattern"
                summary = f"Flagged by pattern detector for known misinformation topic: {topic}"
            else:
                # Layer 2: Google Fact Check
                verdict, rf_rating, publisher = check_google_factcheck(content)
                if verdict == 'fake':
                    status = "Fake"
                    confidence = 94.0
                    fake_prob = confidence
                    real_prob = round(100.0 - confidence, 2)
                    detection_method = "factcheck_api"
                    summary = f"Debunked by Fact-Check tools ({publisher}: {rf_rating})"
                elif verdict == 'real':
                    status = "Real"
                    confidence = 94.0
                    real_prob = confidence
                    fake_prob = round(100.0 - confidence, 2)
                    detection_method = "factcheck_api"
                    summary = f"Verified by Fact-Check tools ({publisher}: {rf_rating})"
                else:
                    # Fallback to BERT
                    if real_prob > fake_prob:
                        status = "Real"
                        confidence = real_prob
                    else:
                        status = "Fake"
                        confidence = fake_prob
                        
                    summary = (f"Analysis complete. The BERT model has classified this as {status.lower()} "
                               f"news with {confidence}% confidence.")

            # Additional features
            sentiment = get_sentiment(content)
            subject = get_subject(content)
            sources = get_sources(content)

            # Optional detailed data
            detailed_data = {}
            if data.get("detailed"):
                detailed_data = {
                    "complexity": get_complexity(content),
                    "word_count": len(content.split()),
                    "reading_time": f"{max(1, len(content.split()) // 200)} min"
                }

            return jsonify({
                "status": status,
                "confidence": confidence,
                "summary": summary,
                "sentiment": sentiment,
                "subject": subject,
                "sources": sources,
                "detailed": detailed_data,
                "raw_prob": raw_prob,
                "fake_prob": fake_prob,
                "real_prob": real_prob,
                "detection_method": detection_method,
                "is_model": True
            })
            
        except Exception as e:
            print(f"ERROR during prediction: {e}")
            return jsonify({"error": f"AI prediction failed: {str(e)}"}), 500
    else:
        return jsonify({
            "error": "BERT model not loaded. Please ensure model files exist.",
            "status": "Error",
            "is_model": False
        }), 503

@csrf.exempt
@app.route("/analyze_url", methods=["POST"])
@limiter.limit("5 per minute")
def analyze_url():
    if "user_email" not in session:
        return {"error": "Unauthorized"}, 401
    
    data = request.get_json()
    url = data.get("url", "")
    
    # --- STRICT URL VALIDATION & SAFE BROWSING ---
    is_valid, err_msg, err_type = validate_url(url)
    if not is_valid:
        return jsonify({
            "status": "error" if err_type == "error" else "blocked",
            "message": err_msg,
            "error": err_msg
        }), 400
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # --- URL Safety & Legitimacy Check ---
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    
    # 1. Block IP-address URLs (e.g. http://192.168.1.1/article)
    import ipaddress
    try:
        ipaddress.ip_address(hostname)
        return jsonify({
            "error": "Suspicious URL: IP-based URLs are not allowed. Please use a domain name.",
            "status": "Blocked",
            "url_safety": "suspicious",
            "is_model": False
        }), 400
    except ValueError:
        pass  # Not an IP — good
    
    # 2. Block suspicious TLDs commonly used by spam/phishing
    SUSPICIOUS_TLDS = ['.xyz', '.tk', '.ml', '.ga', '.cf', '.gq', '.top', '.buzz',
                       '.club', '.work', '.loan', '.click', '.icu', '.su', '.bid']
    if any(hostname.endswith(tld) for tld in SUSPICIOUS_TLDS):
        return jsonify({
            "error": f"Suspicious URL: The domain '{hostname}' uses a TLD commonly associated with spam/phishing.",
            "status": "Blocked",
            "url_safety": "suspicious",
            "is_model": False
        }), 400
    
    # 3. Block URL obfuscation patterns (excessive subdomains, @ in URL)
    if '@' in url:
        return jsonify({
            "error": "Suspicious URL: Contains '@' character which can be used for URL obfuscation.",
            "status": "Blocked",
            "url_safety": "suspicious",
            "is_model": False
        }), 400
    
    subdomain_count = hostname.count('.')
    if subdomain_count > 4:
        return jsonify({
            "error": "Suspicious URL: Excessive subdomains detected, often a sign of phishing.",
            "status": "Blocked",
            "url_safety": "suspicious",
            "is_model": False
        }), 400
    
    # 4. Check if domain is from a known trusted source
    is_trusted_source = any(hostname.endswith(td) for td in TRUSTED_DOMAINS)
    
    print(f"DEBUG: Fetching article from URL: {url} (trusted={is_trusted_source})")
    
    try:
        title, scraped_text = fetch_article_from_url(url)
        
        if not scraped_text:
            if is_trusted_source:
                return jsonify({
                    "error": "Could not extract article content from URL. The site may block scraping or require JavaScript.",
                    "status": "Error",
                    "is_model": False,
                    "source": "scraping_failed"
                }), 422
            else:
                return jsonify({
                    "status": "Fake",
                    "confidence": 96.5,
                    "summary": "Failed to extract content. Site drops connections or blocks analysis, which is highly common for scam/phishing pages.",
                    "sentiment": "Negative",
                    "subject": "Suspicious Activity",
                    "sources": "Unreachable",
                    "detailed": {},
                    "raw_prob": 0.965,
                    "fake_prob": 96.5,
                    "real_prob": 3.5,
                    "detection_method": "scraping_failed_scam",
                    "is_model": True
                })
        
        print(f"DEBUG: Successfully scraped {len(scraped_text.split())} words")
        print(f"DEBUG: Title: {title}")
        
        if bert_model and bert_tokenizer:
            # Combine title + text for better prediction (title carries important signals)
            full_text = f"{title}. {scraped_text}" if title else scraped_text
            cleaned = clean_text(full_text)
            
            print(f"DEBUG: Cleaned text has {len(cleaned.split())} words")
            
            encoding = bert_tokenizer(
                cleaned,
                max_length=MAX_LEN,
                padding='max_length',
                truncation=True,
                return_attention_mask=True,
                return_tensors='pt'
            )
            input_ids = encoding['input_ids'].to(DEVICE)
            attention_mask = encoding['attention_mask'].to(DEVICE)

            with torch.no_grad():
                outputs = bert_model(input_ids=input_ids, attention_mask=attention_mask)

            probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()[0]
            fake_prob = round(float(probs[0]) * 100, 2)
            real_prob = round(float(probs[1]) * 100, 2)
            raw_prob = float(probs[0])

            print(f"DEBUG: BERT prediction - fake: {fake_prob}%, real: {real_prob}%")

            # Final scoring logic combining BERT with external layers
            detection_method = "bert_model"
            summary = ""
            
            # For URLs, use the full combined text for fact checking
            check_text = title + " " + scraped_text if title else scraped_text
            
            # Layer 1: Misinformation Patterns
            is_misinfo, topic = get_misinformation_score(check_text)
            if is_misinfo:
                status = "Fake"
                confidence = max(95.0, fake_prob if fake_prob > 50 else 95.0)
                fake_prob = confidence
                real_prob = round(100.0 - confidence, 2)
                detection_method = "misinfo_pattern"
                summary = f"Flagged by pattern detector for known misinformation topic: {topic}"
            else:
                # Layer 2: Google Fact Check
                verdict, rf_rating, publisher = check_google_factcheck(check_text)
                if verdict == 'fake':
                    status = "Fake"
                    confidence = 94.0
                    fake_prob = confidence
                    real_prob = round(100.0 - confidence, 2)
                    detection_method = "factcheck_api"
                    summary = f"Debunked by Fact-Check tools ({publisher}: {rf_rating})"
                elif verdict == 'real':
                    status = "Real"
                    confidence = 94.0
                    real_prob = confidence
                    fake_prob = round(100.0 - confidence, 2)
                    detection_method = "factcheck_api"
                    summary = f"Verified by Fact-Check tools ({publisher}: {rf_rating})"
                else:
                    # Layer 3: Trusted Source Check
                    is_trusted, is_unknown = get_source_trust_score(url)
                    if is_trusted:
                        status = "Real"
                        confidence = max(90.0, real_prob if real_prob > 50 else 90.0)
                        real_prob = confidence
                        fake_prob = round(100.0 - confidence, 2)
                        detection_method = "trusted_source"
                        summary = f"Verified as coming from a known trusted domain."
                    else:
                        # Fallback to BERT
                        if real_prob > fake_prob:
                            status = "Real"
                            confidence = real_prob
                        else:
                            status = "Fake"
                            confidence = fake_prob
                            
                        summary = (f"Analysis complete. The BERT model has classified this as {status.lower()} "
                                   f"news with {confidence}% confidence.")

            sentiment = get_sentiment(scraped_text)
            subject = get_subject(scraped_text)
            sources = get_sources(scraped_text)

            return jsonify({
                "status": status,
                "confidence": confidence,
                "summary": summary,
                "sentiment": sentiment,
                "subject": subject,
                "sources": sources,
                "raw_prob": raw_prob,
                "fake_prob": fake_prob,
                "real_prob": real_prob,
                "detection_method": detection_method,
                "is_model": True,
                "source": "url",
                "article_title": title if title else "",
                "scraped_content": scraped_text[:500] + "..." if len(scraped_text) > 500 else scraped_text,
                "word_count": len(scraped_text.split())
            })
        else:
            return jsonify({
                "error": "BERT model not loaded. Please ensure model files exist.",
                "status": "Error",
                "is_model": False
            }), 503
            
    except Exception as e:
        print(f"ERROR during URL analysis: {e}")
        return jsonify({"error": f"URL analysis failed: {str(e)}"}), 500

@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    name = request.form.get("name")
    country = request.form.get("country")
    
    users_col.update_one(
        {"email": session["user_email"]},
        {"$set": {"name": name, "country": country}}
    )
    
    flash("Profile updated successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    from datetime import datetime, timedelta
    from collections import defaultdict
    
    user = users_col.find_one({"email": session["user_email"]})
    # ── SECURITY: decrypt PII fields before rendering template ──
    user = decrypt_user_fields(user)
    history = list(db["history"].find({"user_email": session["user_email"]}).sort("_id", -1))
    
    # Calculate basic statistics
    total_checks = len(history)
    real_count = sum(1 for item in history if item.get("status") == "Real")
    fake_count = sum(1 for item in history if item.get("status") == "Fake")
    
    real_percentage = round((real_count / total_checks * 100), 1) if total_checks > 0 else 0
    fake_percentage = round((fake_count / total_checks * 100), 1) if total_checks > 0 else 0
    
    # Calculate average confidence
    avg_confidence = round(sum(item.get("confidence", 0) for item in history) / total_checks, 1) if total_checks > 0 else 94
    
    # Calculate trust score (based on accuracy and activity)
    trust_score = min(95, 70 + (real_count * 2)) if total_checks > 0 else 70
    
    # TEMPORAL ANALYTICS - Parse timestamps and calculate real patterns
    dates_with_activity = set()
    day_counts = defaultdict(int)  # Day of week counts
    hour_counts = defaultdict(int)  # Hour of day counts
    weekly_activity = [0, 0, 0, 0, 0, 0, 0]  # Last 7 days
    weekly_real = [0, 0, 0, 0, 0, 0, 0]
    weekly_fake = [0, 0, 0, 0, 0, 0, 0]
    
    now = datetime.now()
    today = now.date()
    
    for item in history:
        try:
            # Parse timestamp
            timestamp_str = item.get("timestamp", "")
            if timestamp_str:
                # Parse format: "YYYY-MM-DD HH:MM:SS"
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                date = dt.date()
                dates_with_activity.add(date)
                
                # Count by day of week (0=Monday, 6=Sunday)
                day_of_week = dt.weekday()
                day_counts[day_of_week] += 1
                
                # Count by hour of day
                hour_counts[dt.hour] += 1
                
                # Last 7 days activity
                days_ago = (today - date).days
                if 0 <= days_ago < 7:
                    weekly_activity[6 - days_ago] += 1
                    if item.get("status") == "Real":
                        weekly_real[6 - days_ago] += 1
                    else:
                        weekly_fake[6 - days_ago] += 1
        except (ValueError, TypeError):
            continue
    
    # Calculate real streak (consecutive days with activity)
    streak_days = 0
    if dates_with_activity:
        sorted_dates = sorted(dates_with_activity, reverse=True)
        current_date = today
        
        for date in sorted_dates:
            if date == current_date or (current_date - date).days == 1:
                streak_days += 1
                current_date = date
            else:
                break
    
    # Find most active day of week
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if day_counts:
        most_active_day_index = max(day_counts, key=day_counts.get)
        most_active_day = days[most_active_day_index]
    else:
        most_active_day = "Monday"
    
    # Find most active hour
    most_active_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 12
    
    # Activity data for weekly chart (last 7 days)
    activity_data = weekly_activity
    
    # Trends data (last 4 weeks)
    real_trend = []
    fake_trend = []
    
    for week_offset in range(4):
        week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
        week_end = week_start + timedelta(days=6)
        
        week_real = 0
        week_fake = 0
        
        for item in history:
            try:
                timestamp_str = item.get("timestamp", "")
                if timestamp_str:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    if week_start <= dt.date() <= week_end:
                        if item.get("status") == "Real":
                            week_real += 1
                        else:
                            week_fake += 1
            except (ValueError, TypeError):
                continue
        
        real_trend.insert(0, week_real)
        fake_trend.insert(0, week_fake)
    
    # Ensure we have 4 data points
    while len(real_trend) < 4:
        real_trend.insert(0, 0)
    while len(fake_trend) < 4:
        fake_trend.insert(0, 0)
    
    # Confidence distribution
    high_confidence = sum(1 for item in history if item.get("confidence", 0) > 90)
    med_confidence = sum(1 for item in history if 70 <= item.get("confidence", 0) <= 90)
    low_confidence = sum(1 for item in history if item.get("confidence", 0) < 70)
    
    # Platform comparison (compare with all users)
    all_users_history = list(db["history"].find())
    platform_avg_checks = len(all_users_history) / max(users_col.count_documents({}), 1)
    user_rank_percentile = 50  # Default
    
    if total_checks > 0:
        # Calculate user's rank
        user_checks_counts = []
        for u in users_col.find():
            u_count = db["history"].count_documents({"user_email": u.get("email")})
            user_checks_counts.append(u_count)
        
        user_checks_counts.sort(reverse=True)
        if total_checks in user_checks_counts:
            rank = user_checks_counts.index(total_checks) + 1
            user_rank_percentile = round((1 - rank / len(user_checks_counts)) * 100)
    
    # Personalized insights
    insights = []
    
    if most_active_hour < 12:
        insights.append("You're an early bird! Most active in the morning.")
    elif most_active_hour > 18:
        insights.append("Night owl detected! Most active in the evening.")
    
    if streak_days >= 7:
        insights.append(f"Amazing! {streak_days}-day streak going strong!")
    elif streak_days >= 3:
        insights.append(f"Keep it up! {streak_days}-day streak.")
    
    if user_rank_percentile >= 75:
        insights.append(f"Top {100-user_rank_percentile}% most active user!")
    
    if fake_percentage > 60:
        insights.append("You encounter a lot of misinformation. Stay vigilant!")
    elif real_percentage > 80:
        insights.append("Great! Most content you check is reliable.")
    
    # Get current hour for greeting
    current_hour = now.hour
    
    return render_template("dashboard.html", 
                          user=user, 
                          history=history,
                          total_checks=total_checks,
                          real_count=real_count,
                          fake_count=fake_count,
                          real_percentage=real_percentage,
                          fake_percentage=fake_percentage,
                          avg_confidence=avg_confidence,
                          trust_score=trust_score,
                          most_active_day=most_active_day,
                          most_active_hour=most_active_hour,
                          streak_days=streak_days,
                          activity_data=activity_data,
                          real_trend=real_trend,
                          fake_trend=fake_trend,
                          high_confidence=high_confidence,
                          med_confidence=med_confidence,
                          low_confidence=low_confidence,
                          current_hour=current_hour,
                          platform_avg_checks=round(platform_avg_checks, 1),
                          user_rank_percentile=user_rank_percentile,
                          insights=insights)


@csrf.exempt
@app.route("/get_history")
def get_history():
    """API endpoint to get user's analysis history"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_email = session["user_email"]
    history = list(db["history"].find({"user_email": user_email}).sort("_id", -1))
    
    # Convert ObjectId to string for JSON serialization
    for item in history:
        item["_id"] = str(item["_id"])
    
    return jsonify({"success": True, "history": history})


@csrf.exempt
@app.route("/get_stats")
def get_stats():
    """API endpoint to get user statistics"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_email = session["user_email"]
    history = list(db["history"].find({"user_email": user_email}))
    
    total_checks = len(history)
    real_count = sum(1 for item in history if item.get("status") == "Real")
    fake_count = sum(1 for item in history if item.get("status") == "Fake")
    
    real_percentage = round((real_count / total_checks * 100), 1) if total_checks > 0 else 0
    fake_percentage = round((fake_count / total_checks * 100), 1) if total_checks > 0 else 0
    
    avg_confidence = round(sum(item.get("confidence", 0) for item in history) / total_checks, 1) if total_checks > 0 else 94
    trust_score = min(95, 70 + (real_count * 2)) if total_checks > 0 else 70
    
    return jsonify({
        "success": True,
        "total_checks": total_checks,
        "real_count": real_count,
        "fake_count": fake_count,
        "real_percentage": real_percentage,
        "fake_percentage": fake_percentage,
        "avg_confidence": avg_confidence,
        "trust_score": trust_score
    })


@csrf.exempt
@app.route("/get_analytics")
def get_analytics():
    """API endpoint to get detailed analytics with date range filtering"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    from datetime import datetime, timedelta
    from collections import defaultdict
    
    date_range = request.args.get('range', '7days')
    user_email = session["user_email"]
    
    now = datetime.now()
    today = now.date()
    
    if date_range == '7days':
        start_date = today - timedelta(days=6)
    elif date_range == '30days':
        start_date = today - timedelta(days=29)
    else:
        start_date = None
    
    # Fetch all history for user, then filter in Python
    # (MongoDB string comparison won't work correctly with datetime strings)
    all_history = list(db["history"].find({"user_email": user_email}))
    
    # Filter by date range in Python
    history = []
    if start_date:
        for item in all_history:
            try:
                timestamp_str = item.get("timestamp", "")
                if timestamp_str:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    if dt.date() >= start_date:
                        history.append(item)
            except (ValueError, TypeError):
                continue
    else:
        history = all_history
    
    total_checks = len(history)
    real_count = sum(1 for item in history if item.get("status") == "Real")
    fake_count = sum(1 for item in history if item.get("status") == "Fake")
    
    real_percentage = round((real_count / total_checks * 100), 1) if total_checks > 0 else 0
    fake_percentage = round((fake_count / total_checks * 100), 1) if total_checks > 0 else 0
    
    avg_confidence = round(sum(item.get("confidence", 0) for item in history) / total_checks, 1) if total_checks > 0 else 94
    trust_score = min(95, 70 + (real_count * 2)) if total_checks > 0 else 70
    
    dates_with_activity = set()
    day_counts = defaultdict(int)
    hour_counts = defaultdict(int)
    
    # Initialize activity arrays based on date range
    if date_range == '7days':
        activity_days = 7
    elif date_range == '30days':
        activity_days = 30
    else:
        activity_days = 30
    
    weekly_activity = [0] * activity_days
    weekly_real = [0] * activity_days
    weekly_fake = [0] * activity_days
    
    for item in history:
        try:
            timestamp_str = item.get("timestamp", "")
            if timestamp_str:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                date = dt.date()
                dates_with_activity.add(date)
                
                day_of_week = dt.weekday()
                day_counts[day_of_week] += 1
                
                hour_counts[dt.hour] += 1
                
                if date_range == '7days':
                    days_ago = (today - date).days
                    if 0 <= days_ago < 7:
                        weekly_activity[6 - days_ago] += 1
                        if item.get("status") == "Real":
                            weekly_real[6 - days_ago] += 1
                        else:
                            weekly_fake[6 - days_ago] += 1
                elif date_range == '30days':
                    days_ago = (today - date).days
                    if 0 <= days_ago < 30:
                        idx = 29 - days_ago
                        weekly_activity[idx] += 1
                        if item.get("status") == "Real":
                            weekly_real[idx] += 1
                        else:
                            weekly_fake[idx] += 1
        except (ValueError, TypeError):
            continue
    
    streak_days = 0
    if dates_with_activity:
        sorted_dates = sorted(dates_with_activity, reverse=True)
        current_date = today
        
        for date in sorted_dates:
            if date == current_date or (current_date - date).days == 1:
                streak_days += 1
                current_date = date
            else:
                break
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    most_active_day_index = max(day_counts, key=day_counts.get) if day_counts else 0
    most_active_day = days[most_active_day_index]
    most_active_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 12
    
    real_trend = []
    fake_trend = []
    
    for week_offset in range(4):
        week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
        week_end = week_start + timedelta(days=6)
        
        week_real = 0
        week_fake = 0
        
        for item in history:
            try:
                timestamp_str = item.get("timestamp", "")
                if timestamp_str:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    if week_start <= dt.date() <= week_end:
                        if item.get("status") == "Real":
                            week_real += 1
                        else:
                            week_fake += 1
            except (ValueError, TypeError):
                continue
        
        real_trend.insert(0, week_real)
        fake_trend.insert(0, week_fake)
    
    while len(real_trend) < 4:
        real_trend.insert(0, 0)
    while len(fake_trend) < 4:
        fake_trend.insert(0, 0)
    
    high_confidence = sum(1 for item in history if item.get("confidence", 0) > 90)
    med_confidence = sum(1 for item in history if 70 <= item.get("confidence", 0) <= 90)
    low_confidence = sum(1 for item in history if item.get("confidence", 0) < 70)
    
    all_users_history = list(db["history"].find())
    platform_avg_checks = len(all_users_history) / max(users_col.count_documents({}), 1)
    user_rank_percentile = 50
    
    if total_checks > 0:
        user_checks_counts = []
        for u in users_col.find():
            u_count = db["history"].count_documents({"user_email": u.get("email")})
            user_checks_counts.append(u_count)
        
        user_checks_counts.sort(reverse=True)
        if total_checks in user_checks_counts:
            rank = user_checks_counts.index(total_checks) + 1
            user_rank_percentile = round((1 - rank / len(user_checks_counts)) * 100)
    
    if date_range == '7days':
        activity_data = weekly_activity[-7:]
    elif date_range == '30days':
        activity_data = weekly_activity
    else:
        activity_data = weekly_activity
    
    return jsonify({
        "success": True,
        "total_checks": total_checks,
        "real_count": real_count,
        "fake_count": fake_count,
        "real_percentage": real_percentage,
        "fake_percentage": fake_percentage,
        "avg_confidence": avg_confidence,
        "trust_score": trust_score,
        "most_active_day": most_active_day,
        "most_active_hour": most_active_hour,
        "streak_days": streak_days,
        "activity_data": activity_data,
        "real_trend": real_trend,
        "fake_trend": fake_trend,
        "high_confidence": high_confidence,
        "med_confidence": med_confidence,
        "low_confidence": low_confidence,
        "platform_avg_checks": round(platform_avg_checks, 1),
        "user_rank_percentile": user_rank_percentile,
        "date_range": date_range
    })


@csrf.exempt
@app.route("/save_history", methods=["POST"])
def save_history():
    """API endpoint to save analysis to history"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    user_email = session["user_email"]
    
    history_item = {
        "user_email": user_email,
        "content": data.get("content", ""),
        "status": data.get("status", ""),
        "confidence": data.get("confidence", 0),
        "summary": data.get("summary", ""),
        "sentiment": data.get("sentiment", "Neutral"),
        "subject": data.get("subject", "General"),
        "sources": data.get("sources", "None Detected"),
        "fake_prob": data.get("fake_prob"),
        "real_prob": data.get("real_prob"),
        "detection_method": data.get("detection_method", "bert_model"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    db["history"].insert_one(history_item)
    
    return jsonify({"success": True, "message": "Saved to history"})


@csrf.exempt
@app.route("/delete_history/<int:index>", methods=["DELETE"])
def delete_history_item(index):
    """API endpoint to delete a history item"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_email = session["user_email"]
    history = list(db["history"].find({"user_email": user_email}).sort("_id", -1))
    
    if 0 <= index < len(history):
        item_id = history[index]["_id"]
        db["history"].delete_one({"_id": item_id})
        return jsonify({"success": True, "message": "Item deleted"})
    
    return jsonify({"error": "Invalid index"}), 400


@csrf.exempt
@app.route("/clear_history", methods=["POST"])
def clear_all_history():
    """API endpoint to clear all history"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_email = session["user_email"]
    db["history"].delete_many({"user_email": user_email})
    
    return jsonify({"success": True, "message": "History cleared"})


@app.route("/get_settings")
def get_settings():
    """API endpoint to get user settings and preferences"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user = users_col.find_one({"email": session["user_email"]})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # ── SECURITY: decrypt PII before sending to frontend ──
    user = decrypt_user_fields(user)
    
    preferences = user.get("preferences", {
        "email_notifications": True,
        "dark_mode": False,
        "auto_save_history": True,
        "show_confidence": True,
        "sound_effects": False
    })
    
    return jsonify({
        "success": True,
        "user": {
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "phone": user.get("phone", ""),
            "country": user.get("country", "")
        },
        "preferences": preferences
    })


@csrf.exempt
@app.route("/save_preferences", methods=["POST"])
def save_preferences():
    """API endpoint to save user preferences"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    preferences = data.get("preferences", {})
    
    users_col.update_one(
        {"email": session["user_email"]},
        {"$set": {"preferences": preferences}}
    )
    
    return jsonify({"success": True, "message": "Preferences saved"})


@csrf.exempt
@app.route("/save_profile", methods=["POST"])
def save_profile():
    """API endpoint to save user profile"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    
    update_data = {}
    if "name" in data:
        update_data["name"] = data["name"]
    if "phone" in data:
        # ── SECURITY: encrypt phone before storing ──
        update_data["phone"] = encrypt_data(data["phone"])
    if "country" in data:
        update_data["country"] = data["country"]
    
    users_col.update_one(
        {"email": session["user_email"]},
        {"$set": update_data}
    )
    
    return jsonify({"success": True, "message": "Profile saved"})


@csrf.exempt
@app.route("/change_password", methods=["POST"])
def change_password():
    """API endpoint to change password"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    
    user = users_col.find_one({"email": session["user_email"]})
    
    # ── SECURITY: verify current password using bcrypt ──
    if not user or not verify_password(current_password, user.get("password", "")):
        return jsonify({"success": False, "message": "Current password is incorrect"}), 400
    
    # ── SECURITY: hash new password with bcrypt before storing ──
    users_col.update_one(
        {"email": session["user_email"]},
        {"$set": {"password": hash_password(new_password)}}
    )
    
    return jsonify({"success": True, "message": "Password changed successfully"})


@csrf.exempt
@app.route("/export_user_data")
def export_user_data():
    """API endpoint to export all user data"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_email = session["user_email"]
    user = users_col.find_one({"email": user_email})
    # ── SECURITY: decrypt PII before exporting ──
    user = decrypt_user_fields(user)
    history = list(db["history"].find({"user_email": user_email}))
    
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "user": {
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "phone": user.get("phone", ""),
            "country": user.get("country", "")
        },
        "preferences": user.get("preferences", {}),
        "history_count": len(history),
        "history": history
    }
    
    for item in export_data["history"]:
        item["_id"] = str(item["_id"])
    
    return jsonify({"success": True, "data": export_data})


@csrf.exempt
@app.route("/delete_account", methods=["POST"])
def delete_account():
    """API endpoint to delete user account"""
    if "user_email" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_email = session["user_email"]
    
    users_col.delete_one({"email": user_email})
    db["history"].delete_many({"user_email": user_email})
    
    session.clear()
    
    return jsonify({"success": True, "message": "Account deleted"})


# ---------- Error Handlers ----------
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.is_json:
        return jsonify({"error": "CSRF token missing or incorrect", "status": "Error"}), 400
    return "CSRF Error", 400

@app.errorhandler(400)
def bad_request(e):
    if request.is_json: return jsonify({"error": "Bad Request"}), 400
    return "Bad Request", 400

@app.errorhandler(401)
def unauthorized(e):
    if request.is_json: return jsonify({"error": "Unauthorized"}), 401
    return "Unauthorized", 401

@app.errorhandler(403)
def forbidden(e):
    if request.is_json: return jsonify({"error": "Forbidden"}), 403
    return "Forbidden", 403

@app.errorhandler(429)
def ratelimit_handler(e):
    if request.is_json: return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
    return "Rate Limit Exceeded", 429

@app.errorhandler(500)
def internal_error(e):
    if request.is_json: return jsonify({"error": "Internal Server Error"}), 500
    return "Internal Server Error", 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    # Disable reloader on Windows to prevent socket errors
    app.run(debug=False, use_reloader=False)
