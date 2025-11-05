import json

with open("games.json", "r", encoding="utf-8") as f:
    data = json.load(f)

editions = set(item["dmc"]["edition"] for item in data)

for i in editions:
    print(i)
