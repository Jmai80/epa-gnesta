import xml.etree.ElementTree as ET, math, collections, json, sys
LAT0, LON0 = 59.0482, 17.3117
MX = 111320 * math.cos(math.radians(LAT0)); MZ = 111200
def proj(lat, lon): return ((lon - LON0) * MX, -(lat - LAT0) * MZ)
def load(path):
    root = ET.parse(path).getroot()
    nodes, ways, rels = {}, {}, {}
    for el in root:
        if el.tag == 'node':
            t = {c.get('k'): c.get('v') for c in el if c.tag == 'tag'}
            nodes[el.get('id')] = (float(el.get('lat')), float(el.get('lon')), t)
        elif el.tag == 'way':
            nds = [c.get('ref') for c in el if c.tag == 'nd']
            t = {c.get('k'): c.get('v') for c in el if c.tag == 'tag'}
            ways[el.get('id')] = (nds, t)
        elif el.tag == 'relation':
            mem = [(c.get('type'), c.get('ref'), c.get('role')) for c in el if c.tag == 'member']
            t = {c.get('k'): c.get('v') for c in el if c.tag == 'tag'}
            rels[el.get('id')] = (mem, t)
    return nodes, ways, rels
