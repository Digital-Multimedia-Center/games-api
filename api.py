import requests
from rapidfuzz import fuzz
import pymongo
import re
import json
import time
from tqdm import tqdm
import math

from lib.api_helpers import IGDB_URL, IGDB_HEADERS, rate_limit, msu_catalog_api, msu_oai_metadata_api
from lib.database_helpers import db, platforms_in_db 
from lib.string_matcher import PlatformMatcher

def update_dmc_catalog_data(page_limit=100, debug=False):
    """
    Searches the MSU catalog to look for new items added to the DMC collection, when catalog 
    grows items are added to the database dynamically
    
    page_limit: count of how many pages to search in the catalog
    debug: when debug is on, results are written locally instead of the database
    """
    
    # Make a query to count total pages of content
    data = msu_catalog_api(1)
    result_count = data.get("resultCount", 0)
    total_pages = math.ceil(result_count / 100) if result_count else 0

    if total_pages == 0:
        print("No results found.")
        return

    # load IGDB metadata on consoles and intialize the matching engine
    # matching engine is needed to match our internal platform metadata to the appropriate IGDB console ID
    platforms = platforms_in_db()
    matcher = PlatformMatcher(platforms)

    all_games = []

    with tqdm(total=min(total_pages, page_limit), desc="Fetching pages", unit="page") as page_bar:
        for curr_page in range(1, min(page_limit + 1, total_pages + 1)):
            data = msu_catalog_api(curr_page)
            records = data.get("records", [])

            for record in tqdm(records, desc=f"Page {curr_page}", unit="record", leave=False):
                # Get item metadata from OAI API
                id = record.get("id", "N/A")
                data = msu_oai_metadata_api(id) 

                platforms = set()

                # match edition and platform field to IGDB console ID
                for platform in data["edition"] + data["platform"]:
                    platforms.add(matcher.match(platform))

                # -1 indicates no match, remove extraneous -1 if any match is found
                if platforms != set([-1]):
                    platforms.discard(-1)
                
                game = {
                    "_id": id,
                    "title": data["title"],
                    "alternative_titles": data["alternative_titles"],
                    "authors": data["authors"],
                    "edition": data["edition"],
                    "platform": data["platform"],
                    "platform_id_guess": list(platforms),
                    "callnumber" : data["callnumber"]
                }
                all_games.append(game)

            page_bar.update(1)

    # update entries in database or write it locally if debug flag is set
    if not debug:
        operations = [pymongo.ReplaceOne({"_id": game["_id"]}, game, upsert=True) for game in all_games]
        result = db["dmc-items"].bulk_write(operations)
        print(f"Upserted {result.upserted_count} new games.")
        print(f"Updated {result.modified_count} existing games.")
    else:
        with open("Database/dmc-items.json", "w", encoding="utf-8") as f:
            json.dump(all_games, f, indent=4, ensure_ascii=False)
        print("Platforms written to Database/dmc-items.json")

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
            response = requests.post(IGDB_URL, headers=IGDB_HEADERS, data=query)

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
    update_dmc_catalog_data()
    # enrich_with_igdb()
    pass
