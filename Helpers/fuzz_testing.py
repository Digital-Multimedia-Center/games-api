from rapidfuzz import fuzz
import json

# --- Minimal test data (subset of your platforms.js) ---
with open("Database/platforms.json") as platform_data_file:
    platform_data = json.load(platform_data_file)

# --- Function under test ---
def compare_platform(dmc_platform):
    for i in ["nintendo", "microsoft", "sony", "sega"]:
        dmc_platform = dmc_platform.lower().replace(i, "").strip()

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
        "Nintendo Wii"
    ]

    for t in tests:
        print("=" * 40)
        print(f"Testing: '{t}'")
        result = compare_platform(t)
        print(f"Matched platform id: {result}")

