"""
API Helper Utilities for IGDB and MSU Library Catalog integration.

This module provides functions for authentication, rate limiting, and 
data retrieval from the IGDB video game database and the Michigan State 
University library catalog.

Author: Amrit Srivastava
"""

import os
import requests
import time
from collections import deque
from dotenv import load_dotenv
from collections import defaultdict
import xml.etree.ElementTree as ET

# Load environment variables
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# IGDB API Configuration
IGDB_URL = "https://api.igdb.com/v4/games"
IGDB_GAMES_ENDPOINT = "https://api.igdb.com/v4/platforms" 

# Rate Limiting Configuration
REQUEST_LIMIT = 4       # Max requests allowed per window
REQUEST_WINDOW = 1.0    # Window duration in seconds
request_times = deque() # History of request timestamps

def get_access_token():
    """
    Retrieves an OAuth2 access token from Twitch for IGDB API authentication.

    Returns:
        str: Valid access token for IGDB API calls.
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

# Initialize global access token
ACCESS_TOKEN = get_access_token()

def rate_limit():
    """
    Implements a sliding window rate limiter to prevent API 429 errors.
    Should be called immediately before or after every API request.
    """ 
    now = time.time()
    request_times.append(now)
    
    # Remove timestamps older than the current window
    while request_times and request_times[0] < now - REQUEST_WINDOW:
        request_times.popleft()

    # If limit reached, sleep for the remainder of the window
    if len(request_times) >= REQUEST_LIMIT:
        sleep_time = REQUEST_WINDOW - (now - request_times[0])
        if sleep_time > 0:
            time.sleep(sleep_time)

def query_igdb_endpoint(endpoint, query):
    """
    Executes a POST request to a specific IGDB endpoint.

    Args:
        endpoint (str): The IGDB API endpoint URL.
        query (str): The query string in IGDB's wrapper syntax.

    Returns:
        list/dict: Parsed JSON response from the API.
    """
    IGDB_HEADERS = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    response = requests.post(endpoint, headers=IGDB_HEADERS, data=query)
    
    # If query fails we shouldn't silently fail
    try:
        response.raise_for_status()
    except Exception as e:
        print(f"Error querying {endpoint}")
        print(f"Query: {query}")
        print(e)
        exit(1)
        
    return response.json()

def build_igdb_search_game_query(title, platforms):
    """
    Constructs a filtered IGDB search query for game titles.

    Filters out:
    - Non-standalone games (DLCs, mods, etc.)
    - Unreleased or cancelled statuses (Alpha, Beta)

    Args:
        title (str): Game title to search for.
        platforms (list): List of IGDB platform IDs to filter by.

    Returns:
        str: Formatted IGDB query string.
    """
    base_query = """
        fields id, name, summary, first_release_date, category, platforms, status, game_type, rating, cover.image_id, genres.name;
        search "{title}";
        where {conditions};
        limit 100;
    """

    # Filter by specific platforms if provided, otherwise search all
    platform_filter = f"platforms = ({', '.join(map(str, platforms))}) & " if platforms != {-1} else ""
    
    # Logic to exclude specific game types (DLC=1, Mod=5, etc.) and statuses (Alpha=2, etc.)
    # https://api-docs.igdb.com/#game-enums
    conditions = f"{platform_filter} game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null)"
    
    return base_query.format(title=title, conditions=conditions)

def msu_catalog_api(page, limit=100):
    """
    Queries the MSU Library REST API for items tagged as video games.

    Args:
        page (int): Result page number for pagination.
        limit (int): Number of records per page (max 100).

    Returns:
        dict: JSON response containing library records.
    """
    catalog_api_url = "https://catalog.lib.msu.edu/api/v1/search"
    
    params = {
        "lookfor": "genre:video+games",
        "type": "AllFields",
        "field[]": ["edition", "authors", "title", "id"],
        "limit": limit,
        "page": page,
        "sort": "relevance",
        "prettyPrint": "false",
        "lng": "en"
    }

    headers = {"accept": "application/json"}
    response = requests.get(catalog_api_url, params=params, headers=headers)
    
    if response.status_code != 200:
        print(f"MSU Catalog API error: {response.status_code}")
        return {}

    return response.json()

def msu_oai_metadata_api(id):
    """
    Fetches and parses granular MARC21 metadata from the MSU OAI-PMH server.

    Args:
        id (str): The unique identifier for the catalog record.

    Returns:
        dict: Extracted metadata including titles, authors, and call numbers.
    """
    url = f"https://catalog.lib.msu.edu/OAI/Server?verb=GetRecord&identifier={id}&metadataPrefix=marc21"
    response = requests.get(url)
    xml_data = response.text

    # XML Parsing Logic
    root = ET.fromstring(xml_data)
    ns = {
        'oai': 'http://www.openarchives.org/OAI/2.0/',
        'marc': 'http://www.loc.gov/MARC21/slim'
    }

    # Locate MARC record within the OAI wrapper
    record_elem = root.find('.//oai:GetRecord/oai:record/marc:record', ns)
    if record_elem is None:
        record_elem = root.find('.//{http://www.loc.gov/MARC21/slim}record')

    if record_elem is None:
        raise ValueError(f"MARC record not found for ID: {id}")

    # Map MARC tags to subfield values
    datafields_by_tag = defaultdict(list)
    for df in record_elem.findall('{http://www.loc.gov/MARC21/slim}datafield'):
        tag = df.get('tag')
        subfields = {sf.get('code'): sf.text for sf in df.findall('{http://www.loc.gov/MARC21/slim}subfield')}
        datafields_by_tag[tag].append(subfields)

    #  Field Extraction Mapping 
    results = {
        "title": [item['a'] for item in datafields_by_tag.get("245", [])],
        "alternative_titles": [item['a'] for item in datafields_by_tag.get("246", [])],
        "authors": [item['a'] for item in datafields_by_tag.get("710", []) if 'a' in item],
        "edition": [item['a'] for item in datafields_by_tag.get("250", []) if 'a' in item],
        "platform": [item['a'] for item in datafields_by_tag.get("753", []) if 'a' in item],
        "callnumber": datafields_by_tag.get("099", [])[0]['a'] if datafields_by_tag.get("099") else ''
    }

    return results
