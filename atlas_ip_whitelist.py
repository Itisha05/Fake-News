"""
atlas_ip_whitelist.py
---------------------
Automatically adds the machine's current public IP to the MongoDB Atlas
IP Access List on every app startup.

Requirements in .env:
    ATLAS_PUBLIC_KEY   - Atlas API public key
    ATLAS_PRIVATE_KEY  - Atlas API private key
    ATLAS_PROJECT_ID   - Atlas Project / Group ID

How to get these:
  1. Open MongoDB Atlas → top-left hamburger → "Organization Settings"
  2. Go to: Access Manager → API Keys → "Create API Key"
     Role: Project Data Access Admin  (or Project Owner for full access)
  3. Copy the Public Key and Private Key shown.
  4. Your Project ID is in the Atlas URL:
     https://cloud.mongodb.com/v2/<THIS_IS_YOUR_PROJECT_ID>#/...
"""

import os
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime, timezone


def get_public_ip() -> str | None:
    """Fetch the machine's current public IP from a reliable external service."""
    services = [
        "https://api.ipify.org",
        "https://api4.my-ip.io/ip",
        "https://checkip.amazonaws.com",
    ]
    for url in services:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                ip = resp.text.strip()
                if ip:
                    return ip
        except Exception:
            continue
    return None


def whitelist_current_ip() -> bool:
    """
    Detect the current public IP and add it to the MongoDB Atlas IP Access List.
    Returns True on success, False on any failure (non-fatal — app still starts).
    """
    public_key = os.getenv("ATLAS_PUBLIC_KEY")
    private_key = os.getenv("ATLAS_PRIVATE_KEY")
    project_id = os.getenv("ATLAS_PROJECT_ID")

    # Skip silently if Atlas API credentials are not configured
    if not all([public_key, private_key, project_id]):
        print(
            "INFO [Atlas Whitelist]: ATLAS_PUBLIC_KEY / ATLAS_PRIVATE_KEY / ATLAS_PROJECT_ID "
            "not set in .env — skipping auto-whitelist."
        )
        return False

    # Get current public IP
    current_ip = get_public_ip()
    if not current_ip:
        print("WARNING [Atlas Whitelist]: Could not determine public IP — skipping auto-whitelist.")
        return False

    print(f"INFO [Atlas Whitelist]: Current public IP = {current_ip}")

    # Atlas Data API endpoint
    url = f"https://cloud.mongodb.com/api/atlas/v1.0/groups/{project_id}/accessList"
    auth = HTTPDigestAuth(public_key, private_key)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # Check if this IP is already whitelisted
    try:
        check_resp = requests.get(
            f"{url}/{current_ip}",
            auth=auth,
            headers=headers,
            timeout=10,
        )
        if check_resp.status_code == 200:
            print(f"INFO [Atlas Whitelist]: IP {current_ip} is already in the Access List — no action needed.")
            return True
    except Exception as e:
        print(f"WARNING [Atlas Whitelist]: Could not check existing whitelist: {e}")

    # Add the IP
    payload = [
        {
            "ipAddress": current_ip,
            "comment": f"Auto-added by app startup @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        }
    ]

    try:
        resp = requests.post(url, auth=auth, headers=headers, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            print(f"SUCCESS [Atlas Whitelist]: IP {current_ip} successfully added to Atlas Access List.")
            return True
        elif resp.status_code == 409:
            # 409 = already exists — not an error
            print(f"INFO [Atlas Whitelist]: IP {current_ip} was already whitelisted (409 Conflict — ignored).")
            return True
        else:
            print(
                f"WARNING [Atlas Whitelist]: Unexpected response {resp.status_code}: {resp.text[:300]}"
            )
            return False
    except Exception as e:
        print(f"ERROR [Atlas Whitelist]: Failed to add IP to Atlas Access List: {e}")
        return False


if __name__ == "__main__":
    # Allow running standalone for a quick test: python atlas_ip_whitelist.py
    from dotenv import load_dotenv
    load_dotenv(override=True)
    whitelist_current_ip()
