"""Slår ihop flera OpenStreetMap-exporter till en fil (union av noder, vägar och relationer).
Användning: python3 sla_ihop.py ut.osm in1.osm in2.osm ...
Vid dubbletter behålls elementet med högst version. <bounds> blir unionen av alla exporter."""
import sys, xml.etree.ElementTree as ET
ut, filer = sys.argv[1], sys.argv[2:]
element = {}; b = None
for f in filer:
    rot = ET.parse(f).getroot()
    for el in rot:
        if el.tag == 'bounds':
            v = [float(el.get(k)) for k in ('minlat', 'minlon', 'maxlat', 'maxlon')]
            b = v if b is None else [min(b[0], v[0]), min(b[1], v[1]), max(b[2], v[2]), max(b[3], v[3])]
        elif el.tag in ('node', 'way', 'relation'):
            k = (el.tag, el.get('id')); gammal = element.get(k)
            if gammal is None or int(el.get('version', 0)) > int(gammal.get('version', 0)): element[k] = el
rot = ET.Element('osm', {'version': '0.6', 'generator': 'epa-gnesta sla_ihop.py'})
ET.SubElement(rot, 'bounds', {'minlat': '%.7f' % b[0], 'minlon': '%.7f' % b[1], 'maxlat': '%.7f' % b[2], 'maxlon': '%.7f' % b[3]})
for typ in ('node', 'way', 'relation'):
    for (t, i), el in sorted(element.items(), key=lambda kv: int(kv[0][1])):
        if t == typ: rot.append(el)
ET.ElementTree(rot).write(ut, encoding='UTF-8', xml_declaration=True)
print('skrev', ut, {t: sum(1 for k in element if k[0] == t) for t in ('node', 'way', 'relation')}, 'bounds', b)
