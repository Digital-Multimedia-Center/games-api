import requests
from rapidfuzz import fuzz
import json
import time
from tqdm import tqdm
from dotenv import load_dotenv
import os
import math

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
    def build_query(title, platform):
        base_query = """
            fields id, name, summary, category, platforms, status, game_type, rating, cover.image_id, genres.name;
            search "{title}";
            where {conditions};
            limit 100;
        """

        platform_filter = f"platforms = ({platform}) & " if platform != -1 else ""
        conditions = f"{platform_filter}game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null)"

        return base_query.format(title=title, conditions=conditions)

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

    def fetch_igdb_results(title, platform):
        query = build_query(title, platform)
        response = requests.post(IGDB_URL, headers=HEADERS, data=query)
        response.raise_for_status()
        results = response.json()
        return results

    # Load MSU catalog games
    with open(games_file, "r", encoding="utf-8") as f:
        games = json.load(f)

    enriched_games = []

    for game in tqdm(games, desc="Enriching games with IGDB"):
        title = game["dmc"]["title"]
        platform = game["dmc"]["platform_id_guess"]

        try:
            results = fetch_igdb_results(title, platform)
            if not results:
                # TODO : make this logic better...probably tokenize, currently shortens title statically from / but it should be dynamic
                short_title = title.split("/")[0]
                results = fetch_igdb_results(short_title, platform)

            if results:
                igdb_data = max(results, key=lambda r: fuzz.ratio(r.get("name", ""), title))
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
        time.sleep(0.20)

    # Save enriched data
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enriched_games, f, indent=2) 

    print(f"Enriched data saved to {output_file}")

def search_msu_catalog():
    url = "https://catalog.lib.msu.edu/api/v1/search"

    params = {
        "lookfor": "genre:video+games",
        "type": "AllFields",
        "field[]": ["edition", "authors", "title", "id"],
        "limit": 100,
        "page": 1,
        "sort": "relevance",
        "prettyPrint": "false",
        "lng": "en"
    }

    headers = {"accept": "application/json"}

    # initial request to find total number of results
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        print(f"Initial request failed: {response.status_code}")
        print(response.text)
        return []

    data = response.json()
    result_count = data.get("resultCount", 0)
    total_pages = math.ceil(result_count / 100) if result_count else 0

    if total_pages == 0:
        print("No results found.")
        return []

    # load platform data once
    with open("platforms.json") as platform_data_file:
        platform_data = json.load(platform_data_file)

    def compare_platform(dmc_platform):
        # for meta_data in platform_data.values():
        #     abbreivation = meta_data.get("abbreviation").lower()
        #     alternative_names = meta_data.get("alternative_name", "").split(',')
        #     if  abbreivation and abbreivation == dmc_platform.lower() or dmc_platform.lower() in [i.lower() for i in alternative_names]:
        #         return meta_data["id"]

        platform_id = -1
        best_score = 0

        for meta_data in platform_data.values():
            similarity = fuzz.token_ratio(dmc_platform.lower(), meta_data["name"].lower())

            if similarity == 100 and meta_data["name"].lower() != dmc_platform.lower():
                similarity = similarity / 1.75

            if similarity >= best_score:
                best_score = similarity
                platform_id = meta_data["id"]

        return platform_id if best_score >= 50 else -1

    all_games = []

    with tqdm(total=total_pages, desc="Fetching pages", unit="page") as page_bar:
        for curr_page in range(1, total_pages + 1):
            params["page"] = curr_page
            response = requests.get(url, params=params, headers=headers)

            if response.status_code != 200:
                print(f"Request failed on page {curr_page}: {response.status_code}")
                print(response.text)
                break

            data = response.json()
            records = data.get("records", [])

            for record in tqdm(records, desc=f"Page {curr_page}", unit="record", leave=False):
                edition = record.get("edition", "N/A").rstrip('.').lower()
                
                platform_id = compare_platform(edition)

                game = {
                    "dmc": {
                        "id": record.get("id", "N/A"),
                        "title": record.get("title", "N/A").rstrip('.'),
                        "authors": list(record.get("authors", {}).get("corporate", [])),
                        "edition": edition,
                        "platform_id_guess": platform_id
                    },
                }
                all_games.append(game)

            page_bar.update(1)

    with open("games.json", "w", encoding="utf-8") as f:
        json.dump(all_games, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_games)} games to games.json")

if __name__ == "__main__":
    search_msu_catalog()
    # enrich_with_igdb("games.json", "temp.json")
    pass
