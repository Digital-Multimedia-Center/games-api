"""
Database interface for managing game and platform data in MongoDB.

Provides utilities for synchronizing platform metadata from IGDB and 
identifying library items that require data enrichment.

Author: Amrit Srivastava
"""

from dotenv import load_dotenv
import json
import os
import pymongo
from lib.api_helpers import IGDB_GAMES_ENDPOINT, query_igdb_endpoint

# Load environment variables and initialize MongoDB connection
load_dotenv()
user = os.getenv("MONGO_USER")
password = os.getenv("MONGO_PASSWORD")

CONNECTION_STRING = f"mongodb+srv://{user}:{password}@dmc-games-collection.5usd8rs.mongodb.net/"

client = pymongo.MongoClient(CONNECTION_STRING)
db = client["enriched-game-data"]
platform_db = db["platform-data"]

def platforms_in_db():
    """
    Retrieves all platform records currently stored in the database.

    Returns:
        list: A list of all documents in the platform collection.
    """
    return list(platform_db.find({})) 

def build_platforms(debug=False):
    """
    Fetches platform metadata from IGDB and upserts it into the database.

    Args:
        platforms (list): List of platform names (strings) to process.
        debug (bool): If True, writes results to a local JSON file instead of the database.
    """
    def build_query():
        """
        Helper to construct an IGDB query for all platform metadata.
        Filters for console and handheld platform types (1, 5).
        """
        return """
        fields *;
        where platform_type = (1, 5);
        limit 500;
        """
    
    operations = []
    all_results = []

    response = query_igdb_endpoint(IGDB_GAMES_ENDPOINT, build_query())

    for console in response:
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
        # Execute all upserts in a single database call
        result = platform_db.bulk_write(operations)
        print(f"Inserted {result.upserted_count} new platforms")
    elif debug:
        # Export to local file for verification
        with open("Database/platforms.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=4, ensure_ascii=False)
        print("Platforms written to Database/platforms.json")
    else:
        print("No platforms to process") 

def fetch_unprocessed_games():
    """
    Identifies games in the 'dmc-items' collection that have not yet been enriched.
    
    Uses an aggregation pipeline to perform a left outer join and filter for 
    records with no corresponding entry in 'enriched-items'.

    Returns:
        list: Documents from 'dmc-items' that require processing.
    """
    pipeline = [
        {
            # Join 'dmc-items' with 'enriched-items' based on the item ID
            "$lookup": {
                "from": "enriched-items",
                "localField": "_id",           # Primary ID in source
                "foreignField": "dmc_entries", # Referenced ID in target array
                "as": "link_check"
            }
        },
        {
            # Filter for documents where no match was found in the target collection
            "$match": {
                "link_check": {"$size": 0}
            }
        },
        {
            # Clean up temporary field used for filtering
            "$project": {
                "link_check": 0
            }
        }
    ]

    return list(db["dmc-items"].aggregate(pipeline))

if __name__ == "__main__":
    build_platforms(debug=True)
    
    # Preview the first 10 games needing metadata enrichment
    # print(fetch_unprocessed_games()[:10])
