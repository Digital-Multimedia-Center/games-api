from rapidfuzz import fuzz
import json
import argparse

with open("Database/platforms.json") as f:
    platform_data = json.load(f)

id_to_name = {v["id"]: v["name"] for v in platform_data.values()}


def compare_platform_verbose():
    tests = [
        "Microsoft Windows XP",
        "Microsoft Windows 7",
        "Apple Mac X 10.5",
        "Microsoft Windows Vista"
    ]

    for t in tests:
        print("=" * 40)
        print(f"Testing: '{t}'")
        pid, score = compare_platform_scored(t)
        print(f"Matched platform id: {pid}")
        print(f"Match score: {score}")

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

def compare_platform_scored(s: str):
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

    return (best_id if best_score >= 51 else -1), best_score

def run_bulk():
    with open("Database/games.json") as f:
        games_data = json.load(f)

    print("title,platform_string,old_id,old_name,new_id,new_name")

    for entry in games_data:
        dmc = entry.get("dmc", {})
        platforms = dmc.get("platform", [])
        old_id = dmc.get("platform_id_guess")
        if not platforms:
            continue

        new_id = max(compare_platform(p) for p in platforms)

        if new_id != old_id:
            old_name = id_to_name.get(old_id, "UNKNOWN")
            new_name = id_to_name.get(new_id, "UNKNOWN")
            t = dmc.get("title", [""])[0].replace('"', '""')
            p = "|".join(platforms).replace('"', '""')
            print(f'"{t}","{p}",{old_id},{old_name},{new_id},{new_name}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-one", action="store_true", help="check a single platform string with scoring")
    args = parser.parse_args()

    if args.one:
        compare_platform_verbose()
    else:
        run_bulk()


if __name__ == "__main__":
    main()

