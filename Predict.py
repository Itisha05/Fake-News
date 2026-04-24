import re
import pickle
import tensorflow as tf
from nltk.corpus import stopwords
from tensorflow.keras.preprocessing.sequence import pad_sequences
import nltk

nltk.download("stopwords")

# ---------- Load Model ----------
model = tf.keras.models.load_model("fake_news_model.h5")

# ---------- Load Tokenizer ----------
with open("tokenizer.pkl", "rb") as f:
    tokenizer = pickle.load(f)

# ---------- Text Cleaning ----------
stop_words = set(stopwords.words("english"))

def clean_text(text):
    text = text.lower()
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"[^a-z\s]", "", text)
    words = text.split()
    words = [w for w in words if w not in stop_words]
    return " ".join(words)

MAX_LENGTH = 300

# ---------- Prediction Function ----------
def predict_news(title, text):
    full_text = title + " " + text      
    cleaned = clean_text(full_text)

    seq = tokenizer.texts_to_sequences([cleaned])
    padded = pad_sequences(seq, maxlen=MAX_LENGTH, padding="post")

    prob = model.predict(padded)[0][0]

    if prob > 0.55:
        return f"REAL NEWS ({prob*100:.2f}%)"
    elif prob < 0.45:
        return f"FAKE NEWS  ({(1-prob)*100:.2f}%)"
    else:
        return f"UNCERTAIN  ({prob*100:.2f}%)"

# ---------- Test ----------
title = "Scientists Confirm Moon is Actually Made of Compressed Marshmallow"

text = """
 Researchers at the Institute of Extraterrestrial Confectionery (IEC) announced on Thursday that a newly analyzed lunar rock sample is, in fact, 98% compressed marshmallow. The groundbreaking discovery, published in the Journal of Galactic Desserts, suggests the moon is slowly hardening due to cosmic radiation. NASA has not yet commented on whether the Apollo missions were simply the longest camping trips in history, but they have scheduled a "S'mores Mission" for 2027 to verify the findings.
 """

print(predict_news(title, text))