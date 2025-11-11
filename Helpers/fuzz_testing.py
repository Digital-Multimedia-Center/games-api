from rapidfuzz import fuzz
import json
import csv
import sys

# Load platform metadata
with open("Database/platforms.json") as f:
    platform_data = json.load(f)

id_to_name = {v["id"]: v["name"] for v in platform_data.values()}


def compare_platform(s: str) -> int:
    working = s.lower()
    for v in ["nintendo", "microsoft", "sony", "sega"]:
        working = working.replace(v, "")
    working = working.strip()

    best_score = 0
    best_id = -1

    for meta in platform_data.values():
        name = meta["name"].lower()
        score = fuzz.token_ratio(working, name)
        if score == 100 and name != working:
            score = score / 1.75
        if score >= best_score:
            best_score = score
            best_id = meta["id"]

    return best_id if best_score >= 51 else -1


# Read the small games dataset
with open("Database/games_small.json") as f:
    games_data = json.load(f)

# Write CSV to stdout
writer = csv.writer(sys.stdout)
writer.writerow(["title", "all_platform_strings", "platform_id_guess", "platform_names"])

for entry in games_data:
    dmc = entry.get("dmc", {})
    editions = dmc.get("edition", [])
    platforms = dmc.get("platform", [])

    all_platform_strings = editions + platforms
    platform_ids = []

    for plat_str in all_platform_strings:
        pid = compare_platform(plat_str)
        if pid != -1:
            platform_ids.append(pid)

    platform_ids = list(set(platform_ids))  # deduplicate
    platform_names = [id_to_name.get(pid, "UNKNOWN") for pid in platform_ids]

    title = dmc.get("title", [""])[0].replace('"', '""')
    combined_platforms = "|".join(all_platform_strings).replace('"', '""')

    writer.writerow([title, combined_platforms, platform_ids, platform_names])

