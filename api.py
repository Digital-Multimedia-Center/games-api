import requests
import json

def search_msu_catalog():
    curr_page = 1
    results_left = True
    all_games = []

    while results_left:
        url = "https://catalog.lib.msu.edu/api/v1/search"

        params = {
            "lookfor": "genre:video+games",
            "type": "AllFields",
            "field[]": ["edition", "title"],
            "limit": 100,
            "page": curr_page,
            "sort": "relevance",
            "prettyPrint": "false",
            "lng": "en"
        }

        headers = {
            "accept": "application/json"
        }

        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()

            for record in data.get("records", []):
                game = {
                    "dmc": {
                        "title": record.get("title", "N/A"),
                        "edition": record.get("edition", "N/A")
                    }
                }
                all_games.append(game)

            # check if more pages exist
            if curr_page * 100 >= data.get('resultCount', 0):
                results_left = False
            else:
                curr_page += 1
        else:
            print(f"Request failed: {response.status_code}")
            print(response.text)
            results_left = False

    # Save results to JSON file
    with open("games.json", "w", encoding="utf-8") as f:
        json.dump(all_games, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_games)} games to games.json")


if __name__ == "__main__":
    search_msu_catalog()
