import requests
import os
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

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

def search_one_game(title):
    ACCESS_TOKEN = get_access_token()
    IGDB_URL = "https://api.igdb.com/v4/games"
    HEADERS = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    query = f'search "{title}"; fields name, summary, genres.name, cover.image_id, platforms.name, first_release_date; limit 1;'
    response = requests.post(IGDB_URL, headers=HEADERS, data=query)
    response.raise_for_status()

    results = response.json()
    if results:
        return results[0]
    else:
        return {"error": f"No results found for {title}"}

if __name__ == "__main__":
    title = "Destiny / Bungie, Activision." 
    result = search_one_game(title)
    print(result)
