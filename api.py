import requests
import json
import time
from tqdm import tqdm
from dotenv import load_dotenv
import os

# Load credentials from .env file
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

print(CLIENT_ID, CLIENT_SECRET)

# Get a Twitch access token (expires in ~2 months)
def get_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=payload)
    print(response)
    response.raise_for_status()
    return response.json()["access_token"]

ACCESS_TOKEN = get_access_token()

# IGDB API endpoint + headers
IGDB_URL = "https://api.igdb.com/v4/games"
HEADERS = {
    "Client-ID": CLIENT_ID,
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

def enrich_with_igdb(games_file, output_file):
    # Load MSU catalog games
    with open(games_file, "r", encoding="utf-8") as f:
        games = json.load(f)

    enriched_games = []

    for game in tqdm(games, desc="Enriching games with IGDB"):
        title = game["dmc"]["title"]

        query = f'search "{title}"; fields name, summary, genres.name, cover.image_id, platforms.name, first_release_date; limit 1;'

        try:
            response = requests.post(IGDB_URL, headers=HEADERS, data=query)
            response.raise_for_status()
            results = response.json()

            if results:
                result = results[0]
                igdb_data = {
                    "title": result.get("name", ""),
                    "summary": result.get("summary", ""),
                    "tags": [g["name"] for g in result.get("genres", [])] if result.get("genres") else [],
                    "cover": (
                        f'https://images.igdb.com/igdb/image/upload/t_cover_big/{result["cover"]["image_id"]}.jpg'
                        if result.get("cover") else ""
                    ),
                    "other": {
                        "platforms": [p["name"] for p in result.get("platforms", [])] if result.get("platforms") else [],
                        "release_year": (
                            time.strftime("%Y", time.gmtime(result["first_release_date"]))
                            if result.get("first_release_date") else None
                        )
                    }
                }
            else:
                igdb_data = {
                    "title": "",
                    "summary": "",
                    "tags": [],
                    "cover": "",
                    "other": {}
                }

        except Exception as e:
            print(f"Error processing {title}: {e}")
            igdb_data = {
                "title": "",
                "summary": "",
                "tags": [],
                "cover": "",
                "other": {}
            }

        enriched_games.append({
            "game": {
                "dmc": game["dmc"],
                "igdb": igdb_data
            }
        })

        # Rate limiting (max 4 req/sec)
        time.sleep(0.25)

    # Save enriched data
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enriched_games, f, indent=2, ensure_ascii=False)

    print(f"Enriched data saved to {output_file}")

def search_msu_catalog():
    curr_page = 1
    results_left = True
    all_games = []

    while results_left:
        url = "https://catalog.lib.msu.edu/api/v1/search"

        params = {
            "lookfor": "genre:video+games",
            "type": "AllFields",
            "field[]": ["edition", "title"],
            "limit": 100,
            "page": curr_page,
            "sort": "relevance",
            "prettyPrint": "false",
            "lng": "en"
        }

        headers = {
            "accept": "application/json"
        }

        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()

            for record in data.get("records", []):
                game = {
                    "dmc": {
                        "title": record.get("title", "N/A"),
                        "edition": record.get("edition", "N/A")
                    }
                }
                all_games.append(game)

            # check if more pages exist
            if curr_page * 100 >= data.get('resultCount', 0):
                results_left = False
            else:
                curr_page += 1
        else:
            print(f"Request failed: {response.status_code}")
            print(response.text)
            results_left = False

    # Save results to JSON file
    with open("games.json", "w", encoding="utf-8") as f:
        json.dump(all_games, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_games)} games to games.json")


if __name__ == "__main__":
    # search_msu_catalog()
    enrich_with_igdb("games.json", "games_enriched.json")