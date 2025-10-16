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

query = """
fields id, name, summary, genres.name, cover.image_id, platforms.name, first_release_date, status, game_type;
search "super mario 64";
where status != (2,3,6) & game_type != (5, 12);
limit 20;
"""

# response = requests.post("https://api.igdb.com/v4/games", headers=HEADERS, data=query)

platforms = ["Nintendo 64", "Saturn", "GameCube", "Dreamcast", "Playstation 2", "Wii U", "Nintendo Switch", "playstation 3", "Xbox 360", "Xbox Series X", "Playstation 5"]


query = """
    fields *;
    search "Xbox Series";
    where platform_type = 1;
    limit 100;
    """

response = requests.post("https://api.igdb.com/v4/platforms", headers=HEADERS, data=query)
response.raise_for_status()

platforms = response.json()
print(json.dumps(platforms, indent=4, ensure_ascii=False))