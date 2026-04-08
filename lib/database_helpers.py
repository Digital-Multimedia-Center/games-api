from dotenv import load_dotenv
import json
import os
import pymongo
from lib.api_helpers import IGDB_GAMES_ENDPOINT, query_igdb_endpoint

load_dotenv()

user = os.getenv("MONGO_USER")
password = os.getenv("MONGO_PASSWORD")

CONNECTION_STRING = f"mongodb+srv://{user}:{password}@dmc-games-collection.5usd8rs.mongodb.net/"

client = pymongo.MongoClient(CONNECTION_STRING)
db = client["enriched-game-data"]
platform_db = db["platform-data"]

def platforms_in_db():
    """
    This returns a list of all platforms stored in database
    """
    return list(platform_db.find({})) 

def build_platforms(platforms, debug = False):
    """
    Add consoles that we support to database, allows us to narrow game searches
    
    platforms : list of strings of platforms to add to the database
    """
    def build_query(platform):
        """
        Helper function that makes a query for IGDB API to retrieve platform metadata from console name
        """
        return f"""
        fields *;
        search "{platform}";
        where platform_type = (1, 5);
        limit 1;
        """
    
    operations = []
    all_results = []
    
    for platform in platforms:
            response = query_igdb_endpoint(IGDB_GAMES_ENDPOINT, build_query(platform))
            if not response:
                continue
                
            console = response[0]
            console["_id"] = console.pop("id")
    
            op = pymongo.UpdateOne(
                {"_id": console["_id"]},
                {"$setOnInsert": console},
                upsert=True
            )
            if debug:
                all_results.append(console)
            else:
                operations.append(op)
            
    
    if operations:
        result = platform_db.bulk_write(operations)
        print(f"Inserted {result.upserted_count} new platforms")
    elif debug:
        with open("Database/platforms.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=4, ensure_ascii=False)
        print("Platforms written to Database/platforms.json")
    else:
        print("No platforms to process") 
    return

def fetch_unprocessed_games():
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
    return list(db["dmc-items"].aggregate(pipeline))

if __name__ == "__main__":
    # platforms = ["Nintendo 64", "Saturn", "Nintendo GameCube", "Dreamcast", "Nintendo DS", "Playstation Portable", "Playstation Vita", "Playstation", "Playstation 2", "Wii U", "Wii", "Nintendo Switch", "playstation 3", "Xbox", "Xbox 360", "Xbox One", "Xbox Series", "Playstation 4", "Playstation 5", "Switch 2"]
    
    # build_platforms(platforms, True)
    
    print(fetch_unprocessed_games()[:10])
