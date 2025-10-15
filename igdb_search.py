import requests
import time
from rapidfuzz import fuzz
import os
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Get a Twitch access token (expires in ~2 months)
def get_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

ACCESS_TOKEN = get_access_token()

IGDB_URL = "https://api.igdb.com/v4/games"
HEADERS = {
    "Client-ID": CLIENT_ID,
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

def build_query(title):
    return f'search "{title}"; fields id, name, summary, genres.name, cover.image_id, platforms.name, first_release_date; limit 5;'

def is_pc_platform(name):
    pc_keywords = ["windows", "pc", "macintosh", "dos", "cd-rom", "mac", "ibm"]
    return any(k in name.lower() for k in pc_keywords)

def compare_platforms(platform_from_dmc, igdb_results, threshold=80):
    if is_pc_platform(platform_from_dmc):
        return []
    filtered = []
    for result in igdb_results:
        if "platforms" in result:
            igdb_platforms = [p['name'] for p in result['platforms']]
            best_score = max((fuzz.ratio(platform_from_dmc.lower(), p.lower()) for p in igdb_platforms), default=0)
            if best_score >= threshold:
                filtered.append(result)
    return filtered

def extract_igdb_data(result):
    return {
        "id": result.get("id", ""),
        "title": result.get("name", ""),
        "summary": result.get("summary", ""),
        "tags": [g["name"] for g in result.get("genres", [])] if result.get("genres") else [],
        "cover": (
            f'https://images.igdb.com/igdb/image/upload/t_cover_big/{result["cover"]["image_id"]}.jpg'
            if result.get("cover") else ""
        ),
        "other": {
            "platforms": [p["name"] for p in result.get("platforms", [])] if result.get("platforms") else [],
            "release_year": (
                time.strftime("%Y", time.gmtime(result["first_release_date"]))
                if result.get("first_release_date") else None
            )
        }
    }

def search_igdb(title, edition):
    """Return filtered IGDB results for a single title."""
    def fetch(title):
        query = build_query(title)
        response = requests.post(IGDB_URL, headers=HEADERS, data=query)
        response.raise_for_status()
        results = response.json()
        filtered = compare_platforms(edition, results)
        return filtered if filtered else results

    try:
        results = fetch(title)
        if not results:
            short_title = title.split("/")[0]
            results = fetch(short_title)
        return results or []
    except Exception as e:
        return []

if "__main__" == __name__:
    results = search_igdb("Super Mario Bros", "Nintendo")
    print(results)
    if results:
        print(extract_igdb_data(results[0]))
