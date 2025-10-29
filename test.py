import argparse
import json

parser = argparse.ArgumentParser(description='Tests json file for missing vals')
parser.add_argument('filename')
args = parser.parse_args()

with open(args.filename, 'r') as enriched:
    data = json.load(enriched)
    count = 0
    failed_games = []

    for game in data:
        if not (game["game"]["igdb"].get("cover") and game["game"]["igdb"].get("summary")):
            count += 1
            failed_games.append(game)

# Always overwrite the previous failed_games.json file
with open("failed_games.json", 'w') as f:
    json.dump(failed_games, f, indent=4)

print("Percentage of games that failed", count / len(data))

