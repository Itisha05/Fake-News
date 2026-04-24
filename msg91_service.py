import requests
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

AUTH_KEY = os.getenv("MSG91_AUTH_KEY")
TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID")

def send_otp(phone_number, otp):
    """
    Sends an OTP using MSG91 OTP API.
    """
    url = "https://control.msg91.com/api/v5/otp"
    
    # Strictly format phone number: Remove '+', ' ', or '-'
    phone_number = "".join(filter(str.isdigit, phone_number))

    # For India, ensure it starts with 91 but doesn't have duplicate 91
    if len(phone_number) == 10:
        phone_number = "91" + phone_number

    headers = {
        "authkey": AUTH_KEY,
        "Content-Type": "application/json"
    }

    params = {
        "template_id": TEMPLATE_ID,
        "mobile": phone_number,
        "otp": otp
    }

    print(f"DEBUG: Final URL params: template_id={TEMPLATE_ID}, mobile={phone_number}, otp={otp}")

    try:
        # MSG91 v5 OTP API often works best with params in the URL
        response = requests.post(url, params=params, headers=headers)
        result = response.json()
        
        print(f"DEBUG: MSG91 API Full Response: {result}")
        
        if result.get("type") == "success":
            print(f"DEBUG: MSG91 request accepted successfully.")
            return True
        else:
            print(f"ERROR: MSG91 API Rejected: {result.get('message')}")
            return False
            
    except Exception as e:
        print(f"ERROR: Exception while calling MSG91: {e}")
        return False

# Manual test block (optional)
if __name__ == "__main__":
    # Test with a dummy number if you want to verify the connection
    # send_otp("919876543210", "123456")
    pass
