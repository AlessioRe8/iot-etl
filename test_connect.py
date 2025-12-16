import requests

# Configuration
TB_URL = "http://localhost:9090" # Make sure this matches your docker port
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"

def get_token():
    url = f"{TB_URL}/api/auth/login"
    payload = {"username": USERNAME, "password": PASSWORD}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() # Check for errors
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