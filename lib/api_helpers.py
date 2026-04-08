"""
Helper functions for all APIs used, IGDB and MSU API

author : Amrit Srivastava
"""

import os
import requests
import time
from collections import deque
from dotenv import load_dotenv
from collections import defaultdict
import xml.etree.ElementTree as ET

# Load IGDB API keys
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

def get_access_token():
    """
    Get a Twitch access token, required to make calls to IGDB
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

# Define IGDB API endpoints
IGDB_URL = "https://api.igdb.com/v4/games"
IGDB_GAMES_ENDPOINT = "https://api.igdb.com/v4/platforms" 

# This logic is used to slow our API calls to stay within the API limit

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

def query_igdb_endpoint(endpoint, query):
    """
    Builds the post request needed to query IGDB endpoints
    
    endpoint : string with URL endpoint
    query : query parameters for the request
    """

    IGDB_HEADERS = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    response = requests.post(endpoint, headers=IGDB_HEADERS, data=query)
    # If query isn't built properly or endpoint is deprecated we shouldn't silently fail
    try:
        response.raise_for_status()
    except Exception as e:
        print(f"Couldn't query {endpoint} with query:")
        print(query)
        print(e)
        exit(1)
    return response.json()

def build_igdb_search_game_query(title, platforms):
    """
    Builds query for the games endpoint in IGDB, we fetch the first 100 results and filter by platform to get valid candidates

    title : string for game title
    platforms : list of platform ids supported for this title
    return
    """
    base_query = """
        fields id, name, summary, first_release_date, category, platforms, status, game_type, rating, cover.image_id, genres.name;
        search "{title}";
        where {conditions};
        limit 100;
    """

    # build query to filter only valid platforms. We additionally filter out invalid games:
    # game type cannot be dlc addon, mod, fork, or update
    # game status cannot be alpha, beta, cancelled
    # https://api-docs.igdb.com/#game-enums
    platform_filter = f"platforms = ({', '.join(map(str, platforms))}) & " if platforms != {-1} else ""
    conditions = f"{platform_filter} game_type != (1, 5, 12, 14) & (status != (2,3,6) | status = null)"
    return base_query.format(title=title, conditions=conditions)

def msu_catalog_api(page, limit=100):
    """
    Search the catalog API looking for video games
    
    page : the api uses pagination, with page we can specify which page we're looking to fetch results from
    limit : how many results we want per page, the api only supports up to a 100 results per query
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
        print(f"MSU Catalog API failed: {response.status_code}")
        print(response.text)
        return {}

    return response.json()

def msu_oai_metadata_api(id):
    """
    Fetches and parses MARC21 metadata for a specific record via the MSU OAI-PMH server.

    Args:
        id (str): The unique catalog identifier for the record.

        Returns:
            dict: A dictionary containing titles, alternative titles, authors, 
                edition, platform, and call number.
    """

    # Construct OAI-PMH request URL for MARC21 metadata
    url = f"https://catalog.lib.msu.edu/OAI/Server?verb=GetRecord&identifier={id}&metadataPrefix=marc21"
    response = requests.get(url)
    xml_data = response.text

    results = dict()

    # Parse XML structure
    root = ET.fromstring(xml_data)

    # Define XML namespaces for OAI and MARC21 schemas
    ns = {
        'oai': 'http://www.openarchives.org/OAI/2.0/',
        'marc': 'http://www.loc.gov/MARC21/slim'
    }

    # Locate the MARC record element within the OAI response structure
    record_elem = root.find('.//oai:GetRecord/oai:record/marc:record', ns)

    # Alternative: sometimes the MARC record is nested with default namespace
    if record_elem is None:
        record_elem = root.find('.//{http://www.loc.gov/MARC21/slim}record')

    if record_elem is None:
        raise ValueError("MARC record not found.")

    # Validate the presence of the MARC leader element
    leader_elem = record_elem.find('{http://www.loc.gov/MARC21/slim}leader')
    assert leader_elem is not None, "Leader not found!"

    # Map MARC tags to lists of dictionaries containing subfield codes and values
    datafields_by_tag = defaultdict(list)

    for df in record_elem.findall('{http://www.loc.gov/MARC21/slim}datafield'):
        tag = df.get('tag')
        subfields = {sf.get('code'): sf.text for sf in df.findall('{http://www.loc.gov/MARC21/slim}subfield')}
        datafields_by_tag[tag].append(subfields)

    # Extract specific MARC fields into the results dictionary
    results["title"] = [item['a'] for item in datafields_by_tag.get("245", [])]
    results["alternative_titles"] = [item['a'] for item in datafields_by_tag.get("246", [])]
    results["authors"]  = [item['a'] for item in datafields_by_tag.get("710", []) if 'a' in item]
    results["edition"]  = [item['a'] for item in datafields_by_tag.get("250", []) if 'a' in item]
    results["platform"] = [item['a'] for item in datafields_by_tag.get("753", []) if 'a' in item]
    results["callnumber"] = datafields_by_tag.get("099", [])[0]['a'] if len(datafields_by_tag.get("099", [])) > 0 else ''

    return results
