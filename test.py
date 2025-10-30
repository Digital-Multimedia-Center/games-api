import argparse
import json

parser = argparse.ArgumentParser(description='Tests json file for missing vals')
parser.add_argument('filename')
args = parser.parse_args()

with open(args.filename, 'r') as enriched:
    data = json.load(enriched)
    failed_games = []
    failed_games_retry = []

    for entry in data:
        game = entry["game"]
        igdb = game["igdb"]

        if not (igdb.get("cover") and igdb.get("summary")):
            failed_game = {
                "dmc": game["dmc"],
                "igdb": igdb
            }
            failed_game_entry_retry = {
                "dmc": game["dmc"],
                "igdb": {
                    "platform_id": igdb.get("platform_id")
                }
            }
            failed_games.append(failed_game)
            failed_games_retry.append(failed_game_entry_retry)

# Overwrite the previous failed_games.json file
with open("failed_games.json", 'w') as f:
    json.dump(failed_games, f, indent=4)

with open("failed_games_retry.json", 'w') as f:
    json.dump(failed_games_retry, f, indent=4)

print("Percentage of games that failed", len(failed_games) / len(data))
