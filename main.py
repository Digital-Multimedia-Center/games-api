"""
This file does 2 operations, fetches all "video game" entries from the MSU Catalog, and then
matches each video game to an IGDB entry. This should be scheduled to run regularly so that
new catalog items are automatically parsed and added to the database

author : Amrit Srivastava
"""

import pymongo
import string
import json
from tqdm import tqdm
import math

from lib.api_helpers import msu_catalog_api, msu_oai_metadata_api, query_igdb_endpoint, IGDB_URL, build_igdb_search_game_query
from lib.database_helpers import db, platforms_in_db, fetch_unprocessed_games
from lib.string_matcher import PlatformMatcher, GameTitleMatcher

def update_dmc_catalog_data(page_limit=100, debug=False):
    """
    Searches the MSU catalog to look for new items added to the video game collection, when catalog 
    grows items are added to the database dynamically
    
    page_limit: count of how many pages to search in the catalog
    debug: when debug is on, results are written locally instead of the database to allow for inspection
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

    # Loop through all pages
    with tqdm(total=min(total_pages, page_limit), desc="Fetching pages", unit="page") as page_bar:
        for curr_page in range(1, min(page_limit + 1, total_pages + 1)):
            data = msu_catalog_api(curr_page)
            records = data.get("records", [])

            for record in tqdm(records, desc=f"Page {curr_page}", unit="record", leave=False):
                # Get item metadata from OAI API
                id = record.get("id", "N/A")
                data = msu_oai_metadata_api(id) 

                platforms = set()

                # The console supported by a game can be in edition or platform field
                # we will match each candidate to a platform id using the engine
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

def enrich_with_igdb(debug=False):
    """
    Fetch entries in our catalog that haven't been processed. For each entry that hasn't been matched to an IGDB entry:
    1) take their title + alternative title
    2) query igdb api for matches
    3) find closest match from all candidates to our msu catalog entry

    debug : boolean debug flag, if true write locally instead of to database
    """
    
    unprocessed_games = fetch_unprocessed_games()
    enriched_games = {}
    title_matcher = GameTitleMatcher()

    for unprocessed_game in tqdm(unprocessed_games, desc="Enriching games with IGDB"):
        # make a set of all potential titles for this game and clean surrounding punctuations like '/' or '.'
        titles = unprocessed_game["title"] + unprocessed_game["alternative_titles"]
        titles = list({s.strip(string.punctuation).strip() for s in titles})
        platforms = unprocessed_game["platform_id_guess"]
        
        # we need both platform and title to make a query to IGDB API
        if not (platforms and titles):
            continue
        
        # key : igdb_id
        # value : igdb game data
        igdb_candidates = {}
        
        # for every title, we will fetch 100 matches from IGDB and store them
        for title in titles:
            query = build_igdb_search_game_query(title, platforms)
            igdb_results = query_igdb_endpoint(IGDB_URL, query)
            
            for result in igdb_results:
                game_id = result.get("id")
                if game_id and game_id not in igdb_candidates:
                    igdb_candidates[game_id] = result
        
        # couldn't find any IGDB entry with title in our database
        # this can happen if we buy the game on the first day of release or the title in our internal database
        # is severely different from what IGDB calls it
        if not igdb_candidates:
            continue
        
        # find best option of all results
        igdb_data, confidence = title_matcher.match(titles, list(igdb_candidates.values()))
        igdb_id = igdb_data["id"]
        
        # check if this game already exists in our database, we might have added the game already for another platform
        exists = db["enriched-items"].count_documents({"_id": igdb_id}, limit=1) > 0
        

        # if the game already exists, simply update the existing entry
        if exists:
            db["enriched-items"].update_one(
                {"_id": igdb_id},
                {"$addToSet": {"dmc_entries": unprocessed_game["_id"]}}
            )
        # enriched_games is a list that holds all the updates to the database for a bulk write operation
        # if we have the entry in our buffer for a bulk write, update it in the buffer instead
        elif igdb_id in enriched_games:
            if unprocessed_game["_id"] not in enriched_games[igdb_id]["dmc_entries"]:
                enriched_games[igdb_id]["dmc_entries"].append(unprocessed_game["_id"])
        # if entry is neither in the database, nor in our local buffer, we can add an operation to make a new entry
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

    # convert our buffer of operations into a list from a dictionary
    enriched_games = list(enriched_games.values())
    
    if not debug:
        if enriched_games:
            db["enriched-items"].insert_many(enriched_games, ordered=False)
            print(f"Successfully inserted {len(enriched_games)} new enriched games.")
    else:    
        with open("Database/enriched-items.json", "w", encoding="utf-8") as f:
            json.dump(enriched_games, f, indent=4, ensure_ascii=False) 
            print(f"Successfully logged {len(enriched_games)} new enriched games to Database/enriched-items.json")


if __name__ == "__main__":
    update_dmc_catalog_data()
    enrich_with_igdb()
