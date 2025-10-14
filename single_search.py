import requests
import os
from dotenv import load_dotenv
import json

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

def compare_platforms(platform_from_dmc, igdb_results):
    filter = list() 

    for result in igdb_results:
        if "platforms" in result:
            if platform_from_dmc.lower() in [platform['name'].lower() for platform in result['platforms']]:
                filter.append(result)

    return filter

def search_one_game(title, platform_from_dmc):
    ACCESS_TOKEN = get_access_token()
    IGDB_URL = "https://api.igdb.com/v4/games"
    HEADERS = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    query = f'search "{title}";fields id, name, summary, genres.name, cover.image_id, platforms.name, first_release_date, rating; limit 5;'
    response = requests.post(IGDB_URL, headers=HEADERS, data=query)
    response.raise_for_status()

    results = response.json()

    # results = compare_platforms(platform_from_dmc, results)

    if results:
        return results
    else:
        print(results)
        return {"error": f"No results found for {title}"}

if __name__ == "__main__":
    title = "LEGO Indiana Jones: the original adventures / developed by TT Games."
    # title = "LEGO Indiana Jones: the original adventures"
    # title = "Sifu"
    # title = "Destiny" 
    title = "Cat quest / The Gentlebros."
    title = "Metal gear solid. HD collection : Sons of liberty : Snake eater / developed by Kojima Productions."
    title = "sonic riders."
    title = "Portal 2"
    title = "Mighty no. 9."
    title = "super mario 64"

    result = search_one_game(title, "GameCube.")

    for i in result:
        print(i)
        print("\n")

