import pymongo
import string
import json
from tqdm import tqdm
import math

from lib.api_helpers import msu_catalog_api, msu_oai_metadata_api, query_igdb_endpoint, IGDB_URL
from lib.database_helpers import db, platforms_in_db, fetch_unprocessed_games
from lib.string_matcher import PlatformMatcher, GameTitleMatcher

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

def enrich_with_igdb(debug=False):
    def build_query(title, platforms):
        base_query = """
            fields id, name, summary, first_release_date, category, platforms, status, game_type, rating, cover.image_id, genres.name;
            search "{title}";
            where {conditions};
            limit 100;
        """

        platform_filter = f"platforms = ({', '.join(map(str, platforms))}) & " if platforms != {-1} else ""
        conditions = f"{platform_filter} game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null)"

        return base_query.format(title=title, conditions=conditions)

    games = fetch_unprocessed_games()
    enriched_games = {}
    title_matcher = GameTitleMatcher()

    for game in tqdm(games, desc="Enriching games with IGDB"):
        titles = game["title"] + game["alternative_titles"]
        titles = list({s.strip(string.punctuation).strip() for s in titles})
        platforms = game["platform_id_guess"]
        
        if not (platforms and titles):
            continue
        
        igdb_candidates = {}
        
        for title in titles:
            query = build_query(title, platforms)
            igdb_results = query_igdb_endpoint(IGDB_URL, query)
            
            for result in igdb_results:
                game_id = result.get("id")
                if game_id and game_id not in igdb_candidates:
                    igdb_candidates[game_id] = result
        
        # there are no IGDB candidates to compare
        if not igdb_candidates:
            continue
        
        # find best option of all results
        igdb_data, confidence = title_matcher.match(titles, list(igdb_candidates.values()))
        igdb_id = igdb_data["id"]
        
        exists = db["enriched-items"].count_documents({"_id": igdb_id}, limit=1) > 0
        
        if exists:
            db["enriched-items"].update_one(
                {"_id": igdb_id},
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

    
    if not debug:
        if enriched_games:
            db["enriched-items"].insert_many(enriched_games, ordered=False)
            print(f"Successfully inserted {len(enriched_games)} new enriched games.")
    else:    
        with open("Database/enriched-items.json", "w", encoding="utf-8") as f:
            json.dump(enriched_games, f, indent=4, ensure_ascii=False) 
            print(f"Successfully logged {len(enriched_games)} new enriched games to Database/enriched-items.json")


if __name__ == "__main__":
    # update_dmc_catalog_data()
    enrich_with_igdb()
