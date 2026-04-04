import os
import requests
import time
from collections import deque
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

def get_access_token():
    """
    Get a Twitch access token (expires in ~2 months)
    """
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

# Define IGDB API endpoint + headers
IGDB_URL = "https://api.igdb.com/v4/games"
IGDB_GAMES_ENDPOINT = "https://api.igdb.com/v4/platforms" 

HEADERS = {
    "Client-ID": CLIENT_ID,
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

REQUEST_LIMIT = 4       # per second
REQUEST_WINDOW = 1.0    # seconds
request_times = deque() # store timestamps of recent requests

def rate_limit():
    """
    Call this function between API calls to stay within rate limit
    """ 
    now = time.time()
    request_times.append(now)
    while request_times and request_times[0] < now - REQUEST_WINDOW:
        request_times.popleft()

    if len(request_times) >= REQUEST_LIMIT:
        sleep_time = REQUEST_WINDOW - (now - request_times[0])
        if sleep_time > 0:
            time.sleep(sleep_time)

def query_endpoint(endpoint, query):
    response = requests.post(endpoint, headers=HEADERS, data=query)
    response.raise_for_status()
    return response.json()
