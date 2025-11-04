import requests
import xml.etree.ElementTree as ET

url = "https://catalog.lib.msu.edu/OAI/Server?verb=GetRecord&identifier=folio.in00006748922&metadataPrefix=marc21"

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

# Build a dictionary of datafields by tag
datafields_by_tag = {}
for df in record_elem.findall('{http://www.loc.gov/MARC21/slim}datafield'):
    tag = df.get('tag')
    datafields_by_tag[tag] = {sf.get('code'): sf.text for sf in df.findall('{http://www.loc.gov/MARC21/slim}subfield')}

# Now you can index directly
print(datafields_by_tag.get("753"))

