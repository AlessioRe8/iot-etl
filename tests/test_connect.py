import requests


import os
from dotenv import load_dotenv

load_dotenv()
TB_URL = os.getenv("TB_URL")
USERNAME = os.getenv("TB_USER")
PASSWORD = os.getenv("TB_PASSWORD")
if not TB_URL:
    raise ValueError("TB_URL is not set. Please check your .env file.")

print(f"Connecting to ThingsBoard at: {TB_URL}")

def get_token():
    url = f"{TB_URL}/api/auth/login"
    payload = {"username": USERNAME, "password": PASSWORD}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()['token']
    except Exception as e:
        print(f"Error connecting to ThingsBoard: {e}")
        return None

def fetch_assets(token):
    url = f"{TB_URL}/api/tenant/assets?pageSize=100&page=0"
    headers = {"X-Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json()['data']

# Main execution
token = get_token()
if token:
    print("✅ Authentication successful!")
    assets = fetch_assets(token)
    print(f"✅ Found {len(assets)} assets in ThingsBoard.")
    for asset in assets:
        print(f"   - Found Asset: {asset['name']} (Type: {asset['type']})")
else:
    print("❌ Failed to authenticate.")