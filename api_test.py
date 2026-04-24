import os, sys, urllib.parse, urllib.request, json
from dotenv import load_dotenv
load_dotenv()

GOOGLE_KEY = os.getenv("GOOGLE_FACTCHECK_API_KEY", "")
NEWS_KEY = os.getenv("NEWS_API_KEY", "")
print("Google key:", GOOGLE_KEY[:12] + "..." if GOOGLE_KEY else "MISSING")
print("NewsAPI key:", NEWS_KEY[:12] + "..." if NEWS_KEY else "MISSING")

print("\n--- Google Fact Check: 5G COVID ---")
try:
    params = urllib.parse.urlencode({
        "query": "5G towers spread COVID-19",
        "key": GOOGLE_KEY,
        "languageCode": "en"
    })
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search?" + params
    with urllib.request.urlopen(url, timeout=8) as r:
        data = json.loads(r.read())
    claims = data.get("claims", [])
    print("Claims found:", len(claims))
    if claims:
        rev = claims[0].get("claimReview", [{}])[0]
        print("Rating:", rev.get("textualRating"), "| Publisher:", rev.get("publisher", {}).get("name"))
except Exception as e:
    print("ERROR:", e)

print("\n--- Google Fact Check: PM Modi MANAV AI Summit ---")
try:
    params = urllib.parse.urlencode({
        "query": "PM Modi Highlights India MANAV Vision Mega AI Impact Summit",
        "key": GOOGLE_KEY,
        "languageCode": "en"
    })
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search?" + params
    with urllib.request.urlopen(url, timeout=8) as r:
        data = json.loads(r.read())
    claims = data.get("claims", [])
    print("Claims found:", len(claims))
    if claims:
        rev = claims[0].get("claimReview", [{}])[0]
        print("Rating:", rev.get("textualRating"), "| Publisher:", rev.get("publisher", {}).get("name"))
except Exception as e:
    print("ERROR:", e)

print("\n--- NewsAPI: PM Modi AI Summit ---")
try:
    params = urllib.parse.urlencode({
        "q": "PM Modi MANAV Vision AI Impact Summit",
        "apiKey": NEWS_KEY,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": 5
    })
    url = "https://newsapi.org/v2/everything?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "FakeNewsDetector/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    articles = data.get("articles", [])
    print("Articles found:", len(articles))
    for a in articles[:3]:
        print(" -", a["source"]["name"], "|", a["url"][:80])
except Exception as e:
    print("ERROR:", e)

print("\n--- NewsAPI: taylor swift is dead ---")
try:
    params = urllib.parse.urlencode({
        "q": "taylor swift is dead",
        "apiKey": NEWS_KEY,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": 3
    })
    url = "https://newsapi.org/v2/everything?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "FakeNewsDetector/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    print("Articles found:", len(data.get("articles", [])))
    print("Status:", data.get("status"))
except Exception as e:
    print("ERROR:", e)
