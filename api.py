import requests
from rapidfuzz import fuzz
import json
import time
import string
from tqdm import tqdm
from dotenv import load_dotenv
import os

# Load credentials from .env file
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")


# Get a Twitch access token (expires in ~2 months)
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

# IGDB API endpoint + headers
IGDB_URL = "https://api.igdb.com/v4/games"
HEADERS = {
    "Client-ID": CLIENT_ID,
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

def enrich_with_igdb(games_file, output_file):
    def build_query(title):
        return f'search "{title}"; fields id, name, summary, genres.name, cover.image_id, platforms.name, first_release_date; limit 5;'

    def is_pc_platform(name):
        pc_keywords = ["windows", "pc", "macintosh", "dos", "cd-rom", "mac", "ibm"]
        return any(k in name.lower() for k in pc_keywords)

    def compare_platforms(platform_from_dmc, igdb_results, threshold=80):
        """Return IGDB results whose platforms best match the DMC platform using fuzzy matching."""

        # If it's clearly a PC/Mac platform, skip entirely
        if is_pc_platform(platform_from_dmc):
            return []

        filtered = []

        for result in igdb_results:
            if "platforms" in result:
                igdb_platforms = [p['name'] for p in result['platforms']]

                # Compute fuzzy similarity scores for each IGDB platform
                best_match, best_score = None, 0
                for p in igdb_platforms:
                    score = fuzz.ratio(platform_from_dmc.lower(), p.lower())
                    if score > best_score:
                        best_match, best_score = p, score

                # Keep the result if match score is above threshold
                if best_score >= threshold:
                    filtered.append(result)

        return filtered

    def extract_igdb_data(result):
        return {
            "id": result.get("id", ""),
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

    def fetch_igdb_results(title, edition):
        query = build_query(title)
        response = requests.post(IGDB_URL, headers=HEADERS, data=query)
        response.raise_for_status()
        results = response.json()
        filter_by_platform = compare_platforms(edition, results)
        return filter_by_platform if filter_by_platform else results

    # Load MSU catalog games
    with open(games_file, "r", encoding="utf-8") as f:
        games = json.load(f)

    enriched_games = []

    for game in tqdm(games, desc="Enriching games with IGDB"):
        title = game["dmc"]["title"]
        edition = game["dmc"]["edition"]

        try:
            results = fetch_igdb_results(title, edition)

            if not results:
                # Retry using shorter title
                short_title = title.split("/")[0]
                results = fetch_igdb_results(short_title, edition)

            if results:
                result = results[0]
                igdb_data = extract_igdb_data(result)
            else:
                igdb_data = {"title": "", "summary": "", "tags": [], "cover": "", "other": {}}

        except Exception as e:
            with open("debug.txt", "a") as file:
                file.write(f"{title}\n{str(e)}\n")

            igdb_data = {"title": "", "summary": "", "tags": [], "cover": "", "other": {}}

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
            "field[]": ["edition","authors", "title", "id"],
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
                        "id": record.get("id", "N/A"),
                        "title": record.get("title", "N/A"),
                        "authors": list(record["authors"]["corporate"]),
                        "edition": record.get("edition", "N/A").lower().rstrip('.')
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
    pass
