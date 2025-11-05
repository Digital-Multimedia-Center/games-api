import requests
from collections import defaultdict
import xml.etree.ElementTree as ET


IDENTIFIER = "folio.in00006997485"

url = f"https://catalog.lib.msu.edu/OAI/Server?verb=GetRecord&identifier={IDENTIFIER}&metadataPrefix=marc21"

print(url)

response = requests.get(url)
xml_data = response.text

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
leader = leader_elem.text

# Controlfields
# print("\nControlfields:")
# for cf in record_elem.findall('{http://www.loc.gov/MARC21/slim}controlfield'):
#     print(f"Tag {cf.get('tag')}: {cf.text}")

# Datafields
print("\nDatafields:")

datafields_by_tag = defaultdict(list)

for df in record_elem.findall('{http://www.loc.gov/MARC21/slim}datafield'):
    tag = df.get('tag')
    subfields = {sf.get('code'): sf.text for sf in df.findall('{http://www.loc.gov/MARC21/slim}subfield')}
    datafields_by_tag[tag].append(subfields)

print(datafields_by_tag.get("246"))

