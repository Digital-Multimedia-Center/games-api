from rapidfuzz import fuzz
import json

# --- Minimal test data (subset of your platforms.js) ---
with open("platforms.json") as platform_data_file:
    platform_data = json.load(platform_data_file)

# --- Function under test ---
def compare_platform(dmc_platform):
    # for meta_data in platform_data.values():
    #     abbreivation = meta_data.get("abbreviation").lower()
    #     alternative_names = meta_data.get("alternative_name", "").split(',')
    #     if  abbreivation and abbreivation == dmc_platform.lower() or dmc_platform.lower() in [i.lower() for i in alternative_names]:
    #         return meta_data["id"]

    platform_id = -1
    best_score = 0

    for meta_data in platform_data.values():
        similarity = fuzz.token_ratio(dmc_platform.lower(), meta_data["name"].lower())

        if similarity == 100 and meta_data["name"].lower() != dmc_platform.lower():
            similarity = similarity / 1.75
        
        print(meta_data["name"], similarity)

        if similarity >= best_score:
            best_score = similarity
            platform_id = meta_data["id"]

    return platform_id if best_score >= 50 else -1

# --- Run a few test cases ---
if __name__ == "__main__":
    tests = [
        "sega dreamcast",
    ]

    for t in tests:
        print("=" * 40)
        print(f"Testing: '{t}'")
        result = compare_platform(t)
        print(f"Matched platform id: {result}")

