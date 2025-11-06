import requests
from rapidfuzz import fuzz
import re
import json
import time
from tqdm import tqdm
from dotenv import load_dotenv
import os
import math
from collections import deque

from advanced_dmc_parse import metadata_from_msu

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
    with open("Database/platforms.json") as platform_data_file:
        platform_data = json.load(platform_data_file)

    def compare_platform(dmc_platform):
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
                id = record.get("id", "N/A")
                data = metadata_from_msu(id) 
                
                game = {
                    "dmc": {
                        "id": id,
                        "title": data["title"],
                        "alternative_titles": data["alternative_titles"],
                        "authors": data["authors"],
                        "edition": data["edition"],
                        "platform": data["platform"],
                        "platform_id_guess": compare_platform(data["edition"][0]) if data["edition"] else -1
                    },
                }
                all_games.append(game)

            page_bar.update(1)

    with open("Database/games.json", "w", encoding="utf-8") as f:
        json.dump(all_games, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_games)} games to games.json")

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


REQUEST_LIMIT = 4  # per second
REQUEST_WINDOW = 1.0  # seconds
request_times = deque()  # store timestamps of recent requests


def rate_limit():
    now = time.time()
    request_times.append(now)
    # Keep only timestamps within the last second
    while request_times and request_times[0] < now - REQUEST_WINDOW:
        request_times.popleft()

    if len(request_times) >= REQUEST_LIMIT:
        sleep_time = REQUEST_WINDOW - (now - request_times[0])
        if sleep_time > 0:
            time.sleep(sleep_time)

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


    def clean_title(raw_title):
        title = raw_title.lower().strip()

        # Remove common separators and metadata
        title = re.split(r"[\/\(\[\;]", title)[0]

        # Remove phrases like "by XYZ", "developed by", etc.
        title = re.sub(r"\b(by|developed by|written by|produced by|from)\b.*", "", title)

        # Remove trailing punctuation and extra spaces
        title = re.sub(r"[:\-]+$", "", title).strip()
        title = re.sub(r"\s{2,}", " ", title)
        title = title.strip(" :;-,")
        return title


    def normalize_acronyms(title: str) -> str:
        # Insert space between letters and numbers (e.g. PES2017 → PES 2017)
        title = re.sub(r"([A-Za-z])(\d)", r"\1 \2", title)
        title = re.sub(r"(\d)([A-Za-z])", r"\1 \2", title)
        return title


    def generate_title_variants(title: str):
        title = title.strip().lower()

        clean = clean_title(title)
        normalized = normalize_acronyms(clean)
        variants = [title.strip(), clean, normalized]

        # Try splitting on colon or dash — sometimes the second half is the real title
        parts = [p.strip() for p in re.split(r"[:\-]", title) if len(p.strip()) > 3]
        variants.extend(parts)

        # Deduplicate while preserving order
        seen = set()
        ordered = []
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                ordered.append(v)
        return ordered

    def adjusted_similarity(a, b):
        """Compare two titles but penalize long candidates with extra tokens."""
        base = fuzz.token_set_ratio(a, b)
        len_ratio = len(a) / max(len(b), 1)
        length_penalty = min(1.0, len_ratio)  # don’t reward longer strings
        return base * length_penalty

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
        rate_limit()
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
        title = game["dmc"]["title"][0]
        platform = game["dmc"]["platform_id_guess"]
        
        # generate title variants
        possible_titles = generate_title_variants(title)
        possible_titles.extend(game["dmc"]["alternative_titles"])
        results = dict() 

        # search each title variant and keep track of results
        for possible_title in possible_titles:
            igdb_query = fetch_igdb_results(possible_title, platform)
            for hit in igdb_query:
                results[hit["id"]] = hit

        # find best option of all results
        if results:
            igdb_data = max(
                results.values(),
                key=lambda r: max(adjusted_similarity(r.get("name", ""), v) for v in possible_titles)
            )
        else:
            igdb_data = {"title": "", "summary": "", "tags": [], "cover": "", "other": {}}


        enriched_games.append({
            "game": {
                "dmc": game["dmc"],
                "igdb": igdb_data
            }
        })

    # Save enriched data
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enriched_games, f, indent=2) 

    print(f"Enriched data saved to {output_file}")

if __name__ == "__main__":
    # search_msu_catalog()
    enrich_with_igdb("Database/games.json", "temp.json")
    pass
