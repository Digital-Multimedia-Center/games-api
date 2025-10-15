import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Get Twitch/IGDB access token
def get_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

ACCESS_TOKEN = get_access_token()

HEADERS = {
    "Client-ID": CLIENT_ID,
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

# Fetch top 50 platforms
query = 'fields *; where name ~ "xbox 36"*; limit 10;'
response = requests.post("https://api.igdb.com/v4/platforms", headers=HEADERS, data=query)
response.raise_for_status()

# Pretty-print JSON
platforms = response.json()
print(json.dumps(platforms, indent=4, ensure_ascii=False))
