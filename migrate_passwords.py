"""
migrate_passwords.py
====================
One-time migration script to upgrade existing users:
  1. Hash plaintext passwords with bcrypt
  2. Encrypt plaintext phone numbers with Fernet

Run this ONCE after deploying the encryption changes:
    python migrate_passwords.py

It is safe to run multiple times -- already-hashed passwords and
already-encrypted phones are skipped automatically.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

# Add project root to path so we can import the security module
sys.path.insert(0, os.path.dirname(__file__))

from security.encryption import (
    hash_password, encrypt_data,
)

# ---------- Connect to MongoDB (same logic as app.py) ----------
from pymongo import MongoClient
import certifi

def get_db():
    uri = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/")
    is_atlas = "mongodb.net" in uri or "mongodb+srv" in uri

    if is_atlas:
        try:
            client = MongoClient(uri, tls=True, tlsCAFile=certifi.where(),
                                 serverSelectionTimeoutMS=8000)
            client.admin.command("ping")
            print("[OK] Connected to MongoDB Atlas")
            return client["fake_news_db"]
        except Exception:
            try:
                client = MongoClient(uri, tls=True, tlsAllowInvalidCertificates=True,
                                     serverSelectionTimeoutMS=8000)
                client.admin.command("ping")
                print("[OK] Connected to MongoDB Atlas (insecure TLS fallback)")
                return client["fake_news_db"]
            except Exception as e:
                print(f"[ERROR] Cannot connect to MongoDB: {e}")
                sys.exit(1)
    else:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("[OK] Connected to local MongoDB")
        return client["fake_news_db"]


def migrate():
    db = get_db()
    users = db["users"]

    total = users.count_documents({})
    print(f"\nFound {total} user(s) to check.\n")

    upgraded_pw = 0
    upgraded_phone = 0

    for user in users.find():
        email = user.get("email", "???")
        updates = {}

        # --- Password: hash if still plaintext ---
        pw = user.get("password", "")
        if pw and not pw.startswith("$2b$"):
            updates["password"] = hash_password(pw)
            upgraded_pw += 1
            print(f"  [KEY] {email}: password -> bcrypt hash")

        # --- Phone: encrypt if still plaintext ---
        phone = user.get("phone", "")
        if phone and not phone.startswith("v1:"):
            updates["phone"] = encrypt_data(phone)
            upgraded_phone += 1
            print(f"  [LOCK] {email}: phone -> encrypted")

        if updates:
            users.update_one({"_id": user["_id"]}, {"$set": updates})

    print(f"\n[DONE] Migration complete!")
    print(f"   Passwords upgraded: {upgraded_pw}")
    print(f"   Phones encrypted:   {upgraded_phone}")
    print(f"   Already migrated:   {total - max(upgraded_pw, upgraded_phone)}")


if __name__ == "__main__":
    migrate()
