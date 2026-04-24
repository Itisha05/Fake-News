"""
security/encryption.py
======================
Reusable encryption & hashing utilities for the Fake News Detection app.

Field-Level Encryption  : AES-256 via Fernet (from the `cryptography` library)
Password Hashing        : bcrypt with automatic salt

Key Management:
    - The Fernet key is loaded from the ENCRYPTION_KEY environment variable.
    - If the variable is missing, a key is auto-generated and a loud warning is
      printed so the developer can persist it in .env before going to production.

Versioned Ciphertext:
    - Every encrypted value is stored as  "v1:<fernet-ciphertext>"
    - This allows future key-rotation: a new key version would produce "v2:..."
      and decrypt_data can try each key in order.

Tamper Detection:
    - Fernet includes an HMAC; any bit-flip in the ciphertext raises
      cryptography.fernet.InvalidToken, which we catch gracefully.

Double-Encryption Prevention:
    - encrypt_data() checks for the "v1:gAAAAA" prefix before encrypting so
      already-encrypted values are never encrypted twice.

Usage:
    from security.encryption import encrypt_data, decrypt_data
    from security.encryption import hash_password, verify_password

    cipher  = encrypt_data("sensitive value")   # -> "v1:gAAAAA..."
    plain   = decrypt_data(cipher)              # -> "sensitive value"

    hashed  = hash_password("P@ssw0rd!")        # -> "$2b$12$..."
    ok      = verify_password("P@ssw0rd!", hashed)  # -> True
"""

import os
import base64
import logging

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging – security events go to a dedicated logger so they can be routed
# to a secure log sink without leaking sensitive data to stdout.
# ---------------------------------------------------------------------------
log = logging.getLogger("security.encryption")
log.setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Load environment variables (idempotent if already loaded by app.py)
# ---------------------------------------------------------------------------
load_dotenv(override=True)

# ===========================================================================
#  KEY MANAGEMENT
# ===========================================================================

def generate_key() -> str:
    """Generate a new Fernet-compatible key (URL-safe base64, 32 bytes)."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def _load_fernet():
    """
    Load (or auto-generate) the Fernet cipher object.

    Returns the Fernet instance.  If ENCRYPTION_KEY is missing from the
    environment we generate one on the fly and warn loudly – this is only
    acceptable during local development.
    """
    from cryptography.fernet import Fernet

    key = os.getenv("ENCRYPTION_KEY")

    if not key:
        # ----- FALLBACK: generate a temporary key (NOT PRODUCTION SAFE) -----
        key = Fernet.generate_key().decode()
        log.warning(
            "ENCRYPTION_KEY not set in .env! A temporary key was generated. "
            "Data encrypted with this key will be UNRECOVERABLE after restart. "
            "Add  ENCRYPTION_KEY=%s  to your .env file.",
            key,
        )
        print(
            "\n⚠️  WARNING: ENCRYPTION_KEY not set in .env!\n"
            f"   Temporary key: {key}\n"
            "   Add this to .env to persist encrypted data across restarts.\n"
        )

    # Fernet requires a 32-byte URL-safe base64-encoded key
    return Fernet(key.encode() if isinstance(key, str) else key)


# Singleton cipher – created once at import time
_fernet = _load_fernet()

# Current encryption version tag (for future key rotation)
_ENCRYPTION_VERSION = "v1"
_VERSION_PREFIX = f"{_ENCRYPTION_VERSION}:"


# ===========================================================================
#  FIELD-LEVEL ENCRYPTION  (AES-256-CBC via Fernet)
# ===========================================================================

def encrypt_data(plaintext: str) -> str | None:
    """
    Encrypt a plaintext string using AES-256 (Fernet).

    - Returns None for None/empty input (safe pass-through).
    - Prevents double-encryption by checking for the version prefix.
    - Output format: "v1:<base64-fernet-token>"

    Parameters
    ----------
    plaintext : str
        The sensitive value to encrypt.

    Returns
    -------
    str or None
        The versioned ciphertext, or None if input was empty.
    """
    # ── Guard: None / empty ──
    if not plaintext:
        return plaintext  # preserve None vs ""

    plaintext = str(plaintext)

    # ── Guard: already encrypted ──
    if plaintext.startswith(_VERSION_PREFIX):
        log.debug("Skipping double-encryption for value starting with '%s'", _VERSION_PREFIX)
        return plaintext

    try:
        token = _fernet.encrypt(plaintext.encode("utf-8"))
        return f"{_VERSION_PREFIX}{token.decode('utf-8')}"
    except Exception as e:
        log.error("Encryption failed: %s", e)
        # Return the plaintext rather than crashing – the app stays up
        return plaintext


def decrypt_data(ciphertext: str) -> str | None:
    """
    Decrypt a versioned ciphertext string.

    - Returns None for None/empty input.
    - If the value is NOT prefixed with a version tag it is assumed to be
      legacy plaintext and is returned as-is (backward compatibility).
    - Detects tampered ciphertext via Fernet's built-in HMAC.

    Parameters
    ----------
    ciphertext : str
        The encrypted value (e.g. "v1:gAAAAA...").

    Returns
    -------
    str or None
        The decrypted plaintext, or the original value if decryption fails.
    """
    # ── Guard: None / empty ──
    if not ciphertext:
        return ciphertext

    ciphertext = str(ciphertext)

    # ── Guard: not encrypted (legacy plaintext) ──
    if not ciphertext.startswith(_VERSION_PREFIX):
        return ciphertext  # backward-compatible pass-through

    try:
        # Strip version prefix → raw Fernet token
        token = ciphertext[len(_VERSION_PREFIX):]
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as e:
        # InvalidToken (tampered / wrong key), or any other error
        log.error("Decryption failed (data may be corrupted or tampered): %s", e)
        # Return a safe placeholder so the app does not crash
        return "[DECRYPTION ERROR]"


# ===========================================================================
#  PASSWORD HASHING  (bcrypt)
# ===========================================================================

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt with an automatic random salt.

    Parameters
    ----------
    password : str
        The plaintext password.

    Returns
    -------
    str
        The bcrypt hash string (starts with '$2b$').
    """
    import bcrypt
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Also supports **legacy plaintext comparison**: if `hashed` does not start
    with '$2b$' (i.e. it was stored before bcrypt was introduced), a direct
    string comparison is performed.  This allows existing users to log in once
    and have their password upgraded to bcrypt automatically.

    Parameters
    ----------
    password : str
        The plaintext password the user just typed.
    hashed : str
        The stored hash (or legacy plaintext) from the database.

    Returns
    -------
    bool
    """
    import bcrypt

    if not password or not hashed:
        return False

    # ── Legacy plaintext password (pre-bcrypt migration) ──
    if not hashed.startswith("$2b$"):
        return password == hashed

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except Exception as e:
        log.error("Password verification error: %s", e)
        return False


# ===========================================================================
#  HELPER: encrypt / decrypt a dict's sensitive fields in bulk
# ===========================================================================

# Fields that should be encrypted when storing a user document
SENSITIVE_USER_FIELDS = ("phone",)


def encrypt_user_fields(doc: dict) -> dict:
    """
    Return a **copy** of *doc* with sensitive fields encrypted.
    Non-sensitive fields are left untouched.
    """
    out = dict(doc)
    for field in SENSITIVE_USER_FIELDS:
        if field in out and out[field]:
            out[field] = encrypt_data(out[field])
    return out


def decrypt_user_fields(doc: dict) -> dict:
    """
    Return a **copy** of *doc* with sensitive fields decrypted.
    Safe for display on the frontend.
    """
    if doc is None:
        return doc
    out = dict(doc)
    for field in SENSITIVE_USER_FIELDS:
        if field in out and out[field]:
            out[field] = decrypt_data(out[field])
    return out
