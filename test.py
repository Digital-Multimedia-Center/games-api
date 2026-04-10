from lib.database_helpers import fetch_unprocessed_games
from lib.string_matcher import GameTitleMatcher
import json

# TODO : this will get moved to an admin front end because a developer isn't responsible
# for erroneous results

unprocessed_games = fetch_unprocessed_games()
with open("Tests/unprocessed_games.json", "w", encoding="utf-8") as f:
    json.dump(unprocessed_games, f, indent=4, ensure_ascii=False)

with open("Database/enriched-items.json", "r", encoding="utf-8") as f:
    enriched_items = json.load(f)
    enriched_items = {item["_id"] : item for item in enriched_items}

with open("Database/dmc-items.json", "r", encoding="utf-8") as f:
    dmc_items = json.load(f)
    dmc_items = {item["_id"] : item for item in dmc_items}

with open("Tests/low_confidence.json", "w", encoding="utf-8") as f:
    for id, game in enriched_items.items():
        for folio_id in game["dmc_entries"]:
            pass
        pass
    pass

