import os
import requests
import time
from collections import deque
from dotenv import load_dotenv
from collections import defaultdict
import xml.etree.ElementTree as ET

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

IGDB_HEADERS = {
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

def query_igdb_endpoint(endpoint, query):
    response = requests.post(endpoint, headers=IGDB_HEADERS, data=query)
    response.raise_for_status()
    return response.json()

def msu_catalog_api(page, limit=100):
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
    url = f"https://catalog.lib.msu.edu/OAI/Server?verb=GetRecord&identifier={id}&metadataPrefix=marc21"
    response = requests.get(url)
    xml_data = response.text

    results = dict()

    # Parse XML
    root = ET.fromstring(xml_data)

    # Namespaces
    ns = {
        'oai': 'http://www.openarchives.org/OAI/2.0/',
        'marc': 'http://www.loc.gov/MARC21/slim'
    }

    # Find the MARC record element
    record_elem = root.find('.//oai:GetRecord/oai:record/marc:record', ns)

    # Alternative: sometimes the MARC record is nested with default namespace
    if record_elem is None:
        # Look for any element with the MARC namespace
        record_elem = root.find('.//{http://www.loc.gov/MARC21/slim}record')

    if record_elem is None:
        raise ValueError("MARC record not found.")

    # Leader
    leader_elem = record_elem.find('{http://www.loc.gov/MARC21/slim}leader')
    assert leader_elem is not None, "Leader not found!"

    # Controlfields
    # print("Controlfields:")
    # for cf in record_elem.findall('{http://www.loc.gov/MARC21/slim}controlfield'):
    #     print(f"Tag {cf.get('tag')}: {cf.text}")

    # Datafields
    datafields_by_tag = defaultdict(list)

    for df in record_elem.findall('{http://www.loc.gov/MARC21/slim}datafield'):
        tag = df.get('tag')
        subfields = {sf.get('code'): sf.text for sf in df.findall('{http://www.loc.gov/MARC21/slim}subfield')}
        datafields_by_tag[tag].append(subfields)

    results["title"] = [item['a'] for item in datafields_by_tag.get("245", [])]
    results["alternative_titles"] = [item['a'] for item in datafields_by_tag.get("246", [])]
    results["authors"]  = [item['a'] for item in datafields_by_tag.get("710", []) if 'a' in item]
    results["edition"]  = [item['a'] for item in datafields_by_tag.get("250", []) if 'a' in item]
    results["platform"] = [item['a'] for item in datafields_by_tag.get("753", []) if 'a' in item]
    results["callnumber"] = datafields_by_tag.get("099", [])[0]['a'] if len(datafields_by_tag.get("099", [])) > 0 else ''

    return results
