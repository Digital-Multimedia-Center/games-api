import json
from lib.api_helpers import query_igdb_endpoint, IGDB_URL
from lib.string_matcher import GameTitleMatcher

query = """
fields id, name, summary, genres.name, cover.image_id, platforms.name, first_release_date, status, game_type;
search "super mario 64";
where status != (2,3,6) & game_type != (5, 12);
limit 20;
"""

query = """
fields name, category, platforms, status, game_type, rating;
search "battle revolution";
where platforms = (20) & game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null);
limit 100;
"""

query = """
fields name, category, platforms, status, game_type, rating, first_release_date;
search "live a live.";
where platforms = (130);
limit 100;
"""

query = """
fields name, category, platforms, status, game_type, rating, first_release_date;
search "dead or alive 5";
where platforms = (9);
limit 100;
"""

# ^ status here gets rid of all options, some games dont have status apparently?













# matcher = GameTitleMatcher()

# entry = {
#         "_id": "folio.in00006014722",
#         "title": [
#             "FIFA 14"
#         ],
#         "alternative_titles": [
#             "FIFA 14",
#             "FIFA soccer 14",
#             "FIFA fourteen"
#         ],
#         "authors": [
#             "EA Sports (Firm),",
#             "Sony Computer Entertainment."
#         ],
#         "edition": [
#             "PlayStation 4."
#         ],
#         "platform": [
#             "Sony PlayStation 4"
#         ],
#         "platform_id_guess": [
#             48
#         ],
#         "callnumber": "G0020121 video game disc"
#     }
    

# platform_id = entry["platform_id_guess"][0]
# search_title = entry["title"][0].replace(":", "").strip()

# query = f"""
# fields name, category, platforms, game_type, rating, first_release_date;
# search "{search_title}";
# where platforms = ({platform_id}) & game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null);
# """

# igdb_json = query_igdb_endpoint(IGDB_URL, query)
# print(json.dumps(igdb_json, indent=4, ensure_ascii=False))

# result = matcher.match(entry, igdb_json)
    
# if result and result['score'] > 0.85:
#     print(f"Match Found: {result['name']} (ID: {result['igdb_id']}) Score: {result['score']}")
# else:
#     print("No confident match found.")

games = ['Lego party! /']
platform = [49, 169]

def build_query(title, platform):
    base_query = """
        fields id, name, summary, first_release_date, category, platforms, status, game_type, rating, cover.image_id, genres.name;
        search "{title}*";
        where {conditions};
        limit 100;
        """

    platform_filter = f"platforms = ({', '.join(map(str, platform))}) & " if platform != {-1} else ""
    conditions = f"{platform_filter}game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null)"

    return base_query.format(title=title, conditions=conditions)

unique_games = {}
for title in games:
    query = build_query(title, platform)
    igdb_results = query_igdb_endpoint(IGDB_URL, query)
    
    for game in igdb_results:
        game_id = game.get("id")
        if game_id and game_id not in unique_games:
            unique_games[game_id] = game

title_matcher = GameTitleMatcher()
print(title_matcher.match(games, list(unique_games.values())))