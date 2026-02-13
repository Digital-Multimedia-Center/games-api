import requests
from rapidfuzz import fuzz
import pymongo
import re
import json
import time
from tqdm import tqdm
from dotenv import load_dotenv
import os
import math
from collections import deque

from advanced_dmc_parse import metadata_from_msu

# Load credentials from .env file
load_dotenv()

user = os.getenv("MONGO_USER")
password = os.getenv("MONGO_PASSWORD")

CONNECTION_STRING = f"mongodb+srv://{user}:{password}@dmc-games-collection.5usd8rs.mongodb.net/"

client = pymongo.MongoClient(CONNECTION_STRING)
db = client["enriched-game-data"]

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
        platform_by_id = {v["id"]: v for v in platform_data.values()}

    def compare_platform(dmc_platform):
        dmc_platform = dmc_platform.lower()

        for manufacturer in ["nintendo", "microsoft", "sony", "sega"]:
            dmc_platform = dmc_platform.replace(manufacturer, "").strip()
        
        platform_id = -1
        best_score = 0

        for meta_data in platform_data.values():
            similarity = fuzz.token_ratio(dmc_platform.lower(), meta_data["name"].lower())

            if similarity == 100 and meta_data["name"].lower() != dmc_platform.lower():
                similarity = similarity / 1.75

            if similarity >= best_score:
                best_score = similarity
                platform_id = meta_data["id"]

        return platform_id if best_score >= 51 else -1

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

                platforms = set()

                for platform in data["edition"] + data["platform"]:
                    platforms.add(compare_platform(platform))

                if platforms != set([-1]):
                    platforms.discard(-1)
                
                resolved_platforms = [platform_by_id[p] for p in platforms if p in platform_by_id]

                game = {
                    "_id": id,
                    "title": data["title"],
                    "alternative_titles": data["alternative_titles"],
                    "authors": data["authors"],
                    "edition": data["edition"],
                    "platform": data["platform"],
                    "platform_id_guess": resolved_platforms if resolved_platforms else [-1]
                }
                all_games.append(game)

            page_bar.update(1)

    # Prepare a list of operations
    operations = [pymongo.ReplaceOne({"_id": game["_id"]}, game, upsert=True) for game in all_games]
    
    # Execute all operations in one network call
    result = db["dmc-items"].bulk_write(operations)
    
    print(f"Upserted {result.upserted_count} new games.")
    print(f"Updated {result.modified_count} existing games.")

def enrich_with_igdb():
    def build_query(title, platform):
        base_query = """
            fields id, name, summary, first_release_date, category, platforms, status, game_type, rating, cover.image_id, genres.name;
            search "{title}";
            where {conditions};
            limit 100;
        """

        platform_filter = f"platforms = ({','.join(map(str, platform))}) & " if platform != {-1} else ""
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

        # Try splitting on colon or dash - sometimes the second half is the real title
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

    def fetch_igdb_results(title, platform, max_retries=5):
        query = build_query(title, platform)
        retries = 0

        while retries < max_retries:
            rate_limit()
            response = requests.post(IGDB_URL, headers=HEADERS, data=query)

            if response.status_code == 429:
                time.sleep(1)
                retries += 1
                continue

            response.raise_for_status()
            results = response.json()
            return results
        return {}

    # Load MSU catalog games
    pipeline = [
        {
            # Join dmc-items with enriched-items
            "$lookup": {
                "from": "enriched-items",
                "localField": "_id",           # The folio_id in dmc-items
                "foreignField": "dmc_entries", # The array containing folio_ids in enriched-items
                "as": "link_check"
            }
        },
        {
            # Filter for documents where the join result is empty
            "$match": {
                "link_check": {"$size": 0}
            }
        },
        {
            # Remove the temporary join field from the final output
            "$project": {
                "link_check": 0
            }
        }
    ]

    # Execute and convert cursor to list
    games = list(db["dmc-items"].aggregate(pipeline))

    enriched_games = {}

    for game in tqdm(games, desc="Enriching games with IGDB"):
        title = game["title"][0]
        platform = game["platform_id_guess"]
        
        # generate title variants
        possible_titles = generate_title_variants(title)
        possible_titles.extend(game["alternative_titles"])
        results = dict() 

        # search each title variant and keep track of results
        for possible_title in possible_titles:
            igdb_query = fetch_igdb_results(possible_title, platform)
            for hit in igdb_query:
                results[hit["id"]] = hit

        # find best option of all results
        if results:
            igdb_data = max(results.values(), key=lambda r: max(adjusted_similarity(r.get("name", ""), v) for v in possible_titles))
            igdb_id = igdb_data["id"]
            exists = db["enriched-items"].count_documents({"_id": igdb_data["id"]}, limit=1) > 0
            
            if exists:
                db["enriched-items"].update_one(
                    {"_id": igdb_data["id"]},
                    {"$addToSet": {"dmc_entries": game["_id"]}}
                )
            elif igdb_id in enriched_games:
                if game["_id"] not in enriched_games[igdb_id]["dmc_entries"]:
                    enriched_games[igdb_id]["dmc_entries"].append(game["_id"])
            else:
                enriched_games[igdb_id] = {
                    "_id" : igdb_id,
                    "name" : igdb_data.get("name", "Unknown Title"),
                    "cover" : igdb_data.get("cover", {}),
                    "release_date" : igdb_data.get("first_release_date", 0),
                    "genres" : igdb_data.get("genres", []),
                    "summary" : igdb_data.get("summary", ""),
                    "game_type" : igdb_data.get("game_type", 0),
                    "platforms" : igdb_data.get("platforms", []),
                    "dmc_entries" : [game["_id"]]
                }

    enriched_games = list(enriched_games.values())

    with open("temp.json", "w", encoding="utf-8") as f:
        json.dump(enriched_games, f, indent=2, ensure_ascii=False) 

    if enriched_games:
        db["enriched-items"].insert_many(enriched_games, ordered=False)
        print(f"Successfully inserted {len(enriched_games)} new enriched games.")

if __name__ == "__main__":
    search_msu_catalog()
    # enrich_with_igdb()
    pass
