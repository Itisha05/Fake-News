import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import re, sys

TRUSTED_DOMAINS = [
    "timesofindia.indiatimes.com", "ndtv.com", "thehindu.com",
    "hindustantimes.com", "indianexpress.com", "theprint.in",
    "scroll.in", "livemint.com", "business-standard.com",
    "bbc.com", "reuters.com", "apnews.com", "nytimes.com", "theguardian.com",
]

SENSATIONALISM_PATTERNS = [
    r'\bbreaking[:\s!]+', r'\bshocking\b', r'\bshocker\b',
    r'\bmust.?see\b', r'\bmust.?read\b', r'\byou.?won.?t.?believe\b',
    r'\bexposed\b', r'\bsecret.?revealed\b', r'\bthey.?don.?t.?want.?you\b',
    r'\bgovernment.?hiding\b', r'\bconspiracy\b', r'\bOMG\b', r'\bWOW\b',
    r'\d+\s*reasons\s+why', r'click\s+here\s+to\s+(see|watch|find)',
    r'\bcrazy\b', r'\binsane\b', r'\bunbelievable\b', r'\bstunning\b',
    r'!{2,}', r'\?{2,}',
]

def get_source_trust_score(text):
    urls = re.findall(r'https?://\S+|www\.\S+', text, re.IGNORECASE)
    if not urls:
        return False, False
    for url in urls:
        for domain in TRUSTED_DOMAINS:
            if domain in url.lower():
                return True, False
    return False, True

def get_sensationalism_score(text):
    matches = sum(1 for p in SENSATIONALISM_PATTERNS if re.search(p, text, re.IGNORECASE))
    return min(1.0, matches / 4.0)

def predict(name, text, expected):
    raw_prob = 0.0  # Simulates degenerate model
    is_trusted, is_unknown_url = get_source_trust_score(text)
    fake_signal = get_sensationalism_score(text)

    if is_trusted:
        hybrid_prob = 0.82 - (fake_signal * 0.15)
        method = "trusted_source"
    elif fake_signal >= 0.5:
        hybrid_prob = 0.15 + (raw_prob * 0.10)
        method = "sensationalism_high"
    elif fake_signal >= 0.25:
        hybrid_prob = 0.40 - (fake_signal * 0.20)
        method = "sensationalism_moderate"
    elif is_unknown_url:
        hybrid_prob = max(0.25, 0.50 - (fake_signal * 0.3) + (raw_prob * 0.1))
        method = "unknown_url"
    else:
        word_count = len(text.split())
        length_bonus = min(0.15, word_count / 500)
        hybrid_prob = max(0.30, min(0.70, 0.55 + (raw_prob * 0.3) + length_bonus - (fake_signal * 0.2)))
        method = "model_heuristic"

    status = "REAL" if hybrid_prob > 0.55 else "FAKE" if hybrid_prob < 0.45 else "UNCERTAIN"
    conf = hybrid_prob * 100 if hybrid_prob > 0.55 else (1 - hybrid_prob) * 100
    ok = "PASS" if status == expected else f"FAIL (expected {expected})"
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"  fake_signal={fake_signal:.2f}  trusted={is_trusted}  unknown={is_unknown_url}")
    print(f"  hybrid={hybrid_prob:.3f}  method={method}")
    print(f"  RESULT: {status} ({conf:.1f}%) [{ok}]")

tests = [
    ("TOI fake NIA officer article",
     "fake 'NIA officer' from Pulwama http://timesofindia.indiatimes.com/articleshow/128538777.cms",
     "REAL"),
    ("NDTV real political news",
     "Parliament passes cybersecurity amendment. https://ndtv.com/india-news/parliament-bill",
     "REAL"),
    ("Clearly satirical/clickbait fake",
     "SHOCKING!! Scientists discover eating pizza makes you live FOREVER! Government HIDING this! You won't believe it!!",
     "FAKE"),
    ("Conspiracy fake with unknown URL",
     "THEY don't want you to know!! Secret revealed! http://conspiracy-truth999.blogspot.com",
     "FAKE"),
    ("Normal factual news no URL",
     "The government announced a 50 billion infrastructure spending plan for rural connectivity.",
     "REAL"),
    ("BBC real news",
     "Climate summit leaders meet in Geneva to discuss 2030 targets. https://bbc.com/news/world-climate",
     "REAL"),
    ("Neutral short text no URL",
     "Stock markets rose today as tech earnings beat expectations.",
     "REAL"),
]

for name, text, expected in tests:
    predict(name, text, expected)
