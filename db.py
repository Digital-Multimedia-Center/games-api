import pymongo
from dotenv import load_dotenv
import os

load_dotenv()

user = os.getenv("MONGO_USER")
password = os.getenv("MONGO_PASSWORD")

# Use your specific cluster URI from earlier
CONNECTION_STRING = f"mongodb+srv://{user}:{password}@dmc-games-collection.5usd8rs.mongodb.net/"

# 1. Connect to the Cluster
client = pymongo.MongoClient(CONNECTION_STRING)

# 2. Access the Database
db = client["enriched-game-data"]

# 3. Access the Collection
collection = db["dmc-items"]

# pipeline = [
#     {
#         # Join dmc-items with enriched-items
#         "$lookup": {
#             "from": "enriched-items",
#             "localField": "_id",           # The folio_id in dmc-items
#             "foreignField": "dmc_entries", # The array containing folio_ids in enriched-items
#             "as": "link_check"
#         }
#     },
#     {
#         # Filter for documents where the join result is empty
#         "$match": {
#             "link_check": {"$size": 0}
#         }
#     },
#     {
#         # Remove the temporary join field from the final output
#         "$project": {
#             "link_check": 0
#         }
#     }
# ]
#
# # Execute and convert cursor to list
# unassigned_docs = list(db["dmc-items"].aggregate(pipeline))
#
# print(f"Total unassigned documents: {unassigned_docs[0]["_id"]}")

collection = db["enriched-items"]

# 1. Your static input data
test_input = {
    "game": {
      "dmc": {
        "id": "folio.in00006792065",
        "title": ["Hitman III /"],
        "alternative_titles": ["Hitman 3", "Hitman three"],
        "authors": ["Io Interactive (Firm),", "Sony Interactive Entertainment America LLC."],
        "edition": ["PlayStation 4.", "Deluxe edition."],
        "platform": ["Sony PlayStation 4"],
        "platform_id_guess": [48]
      },
      "igdb": {
        "id": 134595,
        "cover": {"id": 105761, "image_id": "co29lt"},
        "genres": [
          {"id": 5, "name": "Shooter"},
          {"id": 24, "name": "Tactical"},
          {"id": 31, "name": "Adventure"}
        ],
        "name": "Hitman 3",
        "platforms": [170, 169, 48, 165, 6, 167, 49],
        "summary": "Hitman 3 is the dramatic conclusion...",
        "game_type": 0
      }
    }
}

# 2. Extract specific variables for clarity
igdb_data = test_input["game"]["igdb"]
dmc_id = test_input["game"]["dmc"]["id"]

# 3. Check if the IGDB ID exists in enriched-items
exists = collection.count_documents({"_id": igdb_data["id"]}, limit=1) > 0

if exists:
    # Update: Add the folio_id to dmc_entries if it's not already there
    result = collection.update_one(
        {"_id": igdb_data["id"]},
        {"$addToSet": {"dmc_entries": "pickle_rick"}}
    )
    print(f"Updated existing game {igdb_data['id']}. Added {dmc_id} to dmc_entries.")
else:
    # Insert: Create the new record with the initial dmc_entries array
    new_enriched_doc = {
        "_id": igdb_data["id"],
        "name": igdb_data["name"],
        "cover": igdb_data["cover"],
        "genres": igdb_data["genres"],
        "summary": igdb_data["summary"],
        "game_type": igdb_data["game_type"],
        "dmc_entries": [dmc_id] 
    }
    collection.insert_one(new_enriched_doc)
    print(f"Inserted new enriched game: {igdb_data['name']} ({igdb_data['id']})")
