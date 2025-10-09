import json

with open("games_enriched.json", 'r') as enriched:
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

print(count / len(data))

