"""
Automated Data Pipeline for the MSU Video Game Collection.

This script manages the ETL (Extract, Transform, Load) process to synchronize 
the Michigan State University library catalog with enriched metadata from IGDB.

Workflow:
1. update_dmc_catalog_data: Scrapes MSU catalog, extracts MARC21 metadata, 
   and stores raw item data in MongoDB.
2. enrich_with_igdb: Identifies new items, performs semantic matching against 
   the IGDB database, and stores the merged enriched results.

Author: Amrit Srivastava
"""

import pymongo
import string
import json
from tqdm import tqdm
import math

from lib.api_helpers import msu_catalog_api, msu_oai_metadata_api, query_igdb_endpoint, IGDB_URL, build_igdb_search_game_query
from lib.database_helpers import db, fetch_unprocessed_games, build_platforms
from lib.string_matcher import PlatformMatcher, GameTitleMatcher

def update_dmc_catalog_data(page_limit=100, debug=False):
    """
    Synchronizes the local 'dmc-items' collection with the MSU Library Catalog.

    Fetches game records via REST and OAI APIs, identifies the target hardware platform,
    and performs a bulk upsert to the database.

    Args:
        page_limit (int): Maximum number of catalog pages to scan.
        debug (bool): If True, writes results to a local JSON file instead of MongoDB.
    """
    
    # Initialize total page count based on the 'video game' genre query
    data = msu_catalog_api(1)
    result_count = data.get("resultCount", 0)
    total_pages = math.ceil(result_count / 100) if result_count else 0

    if total_pages == 0:
        print("No results found.")
        return

    # Initialize PlatformMatcher, matches a game to the platform it's available on
    matcher = PlatformMatcher()

    all_games = []

    # Iterate through paginated results from the MSU Catalog API
    with tqdm(total=min(total_pages, page_limit), desc="Fetching pages", unit="page") as page_bar:
        for curr_page in range(1, min(page_limit + 1, total_pages + 1)):
            data = msu_catalog_api(curr_page)
            records = data.get("records", [])

            for record in tqdm(records, desc=f"Page {curr_page}", unit="record", leave=False):
                # Retrieve granular MARC21 fields for each specific record ID
                id = record.get("id", "N/A")
                data = msu_oai_metadata_api(id) 

                platforms = set()

                # Attempt to extract platform IDs by matching text from edition and platform fields
                for platform_str in data["edition"] + data["platform"]:
                    platforms.add(matcher.match(platform_str))

                # Clean up results: -1 indicates the matcher failed to find a high-confidence ID
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

    # Persist data: Replace existing records or insert new ones (Upsert)
    if not debug:
        operations = [pymongo.ReplaceOne({"_id": game["_id"]}, game, upsert=True) for game in all_games]
        result = db["dmc-items"].bulk_write(operations)
        print(f"Upserted {result.upserted_count} new games.")
        print(f"Updated {result.modified_count} existing games.")
    else:
        with open("Database/dmc-items.json", "w", encoding="utf-8") as f:
            json.dump(all_games, f, indent=4, ensure_ascii=False)
        print("Raw catalog data written to Database/dmc-items.json")

def enrich_with_igdb(debug=False):
    """
    Enriches raw MSU records with data from the Internet Game Database (IGDB).

    Uses semantic matching to link local library items to IGDB entries, 
    enabling access to high-res covers, genres, and release dates.

    Args:
        debug (bool): If True, logs enriched data to a local file.
    """
    
    # Identify items in 'dmc-items' that have no linked record in 'enriched-items'
    unprocessed_games = fetch_unprocessed_games()
    enriched_games = {}
    title_matcher = GameTitleMatcher()

    for unprocessed_game in tqdm(unprocessed_games, desc="Enriching games with IGDB"):
        # Combine and clean all possible title variants for broader search coverage
        titles = unprocessed_game["title"] + unprocessed_game["alternative_titles"]
        titles = list({s.strip(string.punctuation).strip() for s in titles})
        platforms = unprocessed_game["platform_id_guess"]
        
        # Cannot match without both a title and a platform hint
        if not (platforms and titles):
            continue
        
        igdb_candidates = {}
        
        # Query IGDB for every known title variation to maximize match potential
        for title in titles:
            query = build_igdb_search_game_query(title, platforms)
            igdb_results = query_igdb_endpoint(IGDB_URL, query)
            
            for result in igdb_results:
                game_id = result.get("id")
                if game_id and game_id not in igdb_candidates:
                    igdb_candidates[game_id] = result
        
        if not igdb_candidates:
            continue
        
        # Use semantic transformer to find the most likely match among candidates
        igdb_data, confidence = title_matcher.match(titles, list(igdb_candidates.values()))
        igdb_id = igdb_data["id"]
        
        # Check if this IGDB entry already exists (e.g., library has the same game on multiple platforms)
        exists = db["enriched-items"].count_documents({"_id": igdb_id}, limit=1) > 0

        # Case 1: Existing record, Link this new MSU item to the existing IGDB entry
        if exists:
            db["enriched-items"].update_one(
                {"_id": igdb_id},
                {"$addToSet": {"dmc_entries": unprocessed_game["_id"]}}
            )
        # Case 2: New IGDB ID already in the current processing buffer, Update buffer
        elif igdb_id in enriched_games:
            if unprocessed_game["_id"] not in enriched_games[igdb_id]["dmc_entries"]:
                enriched_games[igdb_id]["dmc_entries"].append(unprocessed_game["_id"])
        # Case 3: Completely new entry, Create new enriched record
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
                "dmc_entries" : [unprocessed_game["_id"]]
            }

    # Final Batch Insert
    enriched_games_list = list(enriched_games.values())
    
    if not debug:
        if enriched_games_list:
            db["enriched-items"].insert_many(enriched_games_list, ordered=False)
            print(f"Successfully inserted {len(enriched_games_list)} new enriched games.")
    else:    
        with open("Database/enriched-items.json", "w", encoding="utf-8") as f:
            json.dump(enriched_games_list, f, indent=4, ensure_ascii=False) 
            print(f"Successfully logged {len(enriched_games_list)} new enriched games to local file.")


if __name__ == "__main__":
    # Standard operational flow
    build_platforms()
    update_dmc_catalog_data()
    enrich_with_igdb()
