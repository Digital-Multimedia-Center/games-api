import requests
import json
from collections import defaultdict
import xml.etree.ElementTree as ET

def metadata_from_msu(id):
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


if __name__ == "__main__":
    # with open("Inspection/failed_games_retry.json") as db:
        # game_data = json.load(db)      
        # for game in game_data:
        #     print(game['dmc']['id'])
        #     metadata_from_msu(game['dmc']['id'])
        #     print("\n")

    IDENTIFIER = "folio.in00006740811"
    print(metadata_from_msu(IDENTIFIER))
