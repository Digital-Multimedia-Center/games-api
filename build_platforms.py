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

platforms = ["Nintendo 64", "Saturn", "Nintendo GameCube", "Dreamcast", "Nintendo DS", "Playstation Portable", "Playstation Vita", "Playstation", "Playstation 2", "Wii U", "Wii", "Nintendo Switch", "playstation 3", "Xbox", "Xbox 360", "Xbox One", "Xbox Series", "Playstation 4", "Playstation 5"]

def build_query(platform):
    return f"""
    fields *;
    search "{platform}";
    where platform_type = (1, 5);
    limit 1;
    """

all_results = {}

for platform in platforms:
    response = requests.post(
        "https://api.igdb.com/v4/platforms",
        headers=HEADERS,
        data=build_query(platform)
    )
    response.raise_for_status()

    # Save 
    all_results[platform] = response.json()[0]

# Write to one combined JSON file
with open("Database/platforms.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4, ensure_ascii=False)

print("Saved to platforms.json")
