import pandas as pd
import numpy as np
import re
import nltk
import pickle
import tensorflow as tf

from nltk.corpus import stopwords
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense, Bidirectional, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import seaborn as sns

nltk.download("stopwords")

import os

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- Load Dataset ----------
true_df = pd.read_csv(os.path.join(MODEL_DIR, "True.csv"))
fake_df = pd.read_csv(os.path.join(MODEL_DIR, "Fake.csv"))

true_df["label"] = 1
fake_df["label"] = 0

df = pd.concat([true_df, fake_df]).sample(frac=1).reset_index(drop=True)

# ---------- Text Cleaning ----------
stop_words = set(stopwords.words("english"))

def clean_text(text):
    text = text.lower()
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"[^a-z\s]", "", text)
    words = text.split()
    words = [w for w in words if w not in stop_words]
    return " ".join(words)

df["full_text"] = (df["title"] + " " + df["text"]).astype(str)
df["full_text"] = df["full_text"].apply(clean_text)

X = df["full_text"]
y = df["label"].values

# ---------- Tokenization ----------
VOCAB_SIZE = 15000
MAX_LENGTH = 300

tokenizer = Tokenizer(num_words=VOCAB_SIZE, oov_token="<OOV>")
tokenizer.fit_on_texts(X)

sequences = tokenizer.texts_to_sequences(X)
padded = pad_sequences(sequences, maxlen=MAX_LENGTH, padding="post")

# ---------- Train Test Split ----------
X_train, X_test, y_train, y_test = train_test_split(
    padded, y, test_size=0.2, random_state=42
)

# ---------- Model ----------
model = Sequential([
    Embedding(VOCAB_SIZE, 128, input_length=MAX_LENGTH),
    Bidirectional(LSTM(64, return_sequences=True)),
    Dropout(0.3),
    Bidirectional(LSTM(32)),
    Dropout(0.3),
    Dense(64, activation="relu"),
    Dropout(0.5),
    Dense(1, activation="sigmoid")
])

model.compile(
    loss="binary_crossentropy",
    optimizer="adam",
    metrics=["accuracy"]
)

# ---------- Train ----------
early_stop = EarlyStopping(
    monitor="val_loss",
    patience=2,
    restore_best_weights=True
)

history = model.fit(
    X_train,
    y_train,
    epochs=20,
    batch_size=64,
    validation_data=(X_test, y_test),
    callbacks=[early_stop]
)

# ---------- SAVE MODEL ----------
model.save(os.path.join(MODEL_DIR, "fake_news_model.h5"))

# ---------- SAVE TOKENIZER ----------
with open(os.path.join(MODEL_DIR, "tokenizer.pkl"), "wb") as f:
    pickle.dump(tokenizer, f)

print("Model and tokenizer saved successfully")

# ---------- 1. Evaluation Metrics ----------
y_pred = (model.predict(X_test) > 0.5).astype("int32")

print("\n--- Model Evaluation ---")
print(f"Accuracy Score: {accuracy_score(y_test, y_pred):.4f}")
print("\nClassification Report:\n", classification_report(y_test, y_pred, target_names=['Fake', 'True']))

plt.savefig("confusion_matrix.png")
print("Confusion matrix saved to confusion_matrix.png")
# plt.show()

# ---------- 2. Plotting Training Graphs ----------
def plot_graphs(history, metric):
    plt.plot(history.history[metric])
    plt.plot(history.history['val_'+metric])
    plt.xlabel("Epochs")
    plt.ylabel(metric)
    plt.legend([metric, 'val_'+metric])
    plt.savefig(f"{metric}_graph.png")
    print(f"{metric.capitalize()} graph saved to {metric}_graph.png")
    # plt.show()

print("\n--- Training Progress ---")
plot_graphs(history, "accuracy")
plot_graphs(history, "loss")