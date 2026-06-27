from playwright.sync_api import sync_playwright
from fake_useragent import UserAgent, FakeUserAgentError
from nltk.sentiment import SentimentIntensityAnalyzer
from bs4 import BeautifulSoup
from pymongo import MongoClient
import spacy
import pandas as pd
import datetime
import time
import random

# --- Load models once ---
nlp = spacy.load("en_core_web_sm")
sia = SentimentIntensityAnalyzer()

# --- User Agent ---
def get_user_agent():
    try:
        return UserAgent().random
    except FakeUserAgentError:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# --- Fetch ---
def fetch_page(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=get_user_agent(),
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_selector("h2", timeout=10000)
            html = page.content()
            browser.close()
            time.sleep(random.uniform(1.5, 3.5))
            return html
    except Exception as e:
        print(f"Fetch error: {e}")
        return None

# --- Parse ---
def parse_headlines(html):
    soup = BeautifulSoup(html, "html.parser")
    headline_tags = soup.find_all("h2", class_="YOUR_CLASS_HERE")
    headlines = []
    for tag in headline_tags:
        link_tag = tag.find("a")
        if link_tag:
            headlines.append({
                "text":       link_tag.text.strip(),
                "url":        link_tag.get("href"),
                "source":     "Dawn",
                "scraped_at": str(datetime.date.today())
            })
    return headlines

# --- NLP + Sentiment ---
def extract_nlp(text):
    doc = nlp(text)
    entities = {
        "persons":       [e.text for e in doc.ents if e.label_ == "PERSON"],
        "locations":     [e.text for e in doc.ents if e.label_ == "GPE"],
        "organizations": [e.text for e in doc.ents if e.label_ == "ORG"],
        "dates":         [e.text for e in doc.ents if e.label_ == "DATE"],
    }
    keywords = [
        token.text.lower()
        for token in doc
        if not token.is_stop and not token.is_punct and len(token.text) > 2
    ]
    compound = sia.polarity_scores(text)["compound"]
    sentiment = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"

    return {
        "entities":        entities,
        "keywords":        keywords,
        "sentiment":       sentiment,
        "sentiment_score": round(compound, 3)
    }

# --- Clean ---
def clean(headlines):
    df = pd.DataFrame(headlines)
    df = df.dropna()
    df = df.drop_duplicates(subset="text")
    return df.to_dict("records")

# --- Store ---
def store(collection, headlines):
    new_count = 0
    for h in headlines:
        if not collection.find_one({"text": h["text"]}):
            nlp_data = extract_nlp(h["text"])
            collection.insert_one({**h, **nlp_data})
            new_count += 1
    print(f"Stored {new_count} new | Skipped duplicates")

# --- Run ---
CONNECTION_STRING = "MONGO_URI"
collection = MongoClient(CONNECTION_STRING)["news_db"]["headlines"]

html = fetch_page("https://www.dawn.com")
if html:
    raw     = parse_headlines(html)
    cleaned = clean(raw)
    store(collection, cleaned)
    
    # Quick sentiment summary
    pos = collection.count_documents({"sentiment": "positive"})
    neg = collection.count_documents({"sentiment": "negative"})
    neu = collection.count_documents({"sentiment": "neutral"})
    print(f"\nSentiment breakdown:")
    print(f"  Positive: {pos}")
    print(f"  Negative: {neg}")
    print(f"  Neutral:  {neu}")