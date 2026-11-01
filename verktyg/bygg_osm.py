#!/usr/bin/env python3
"""EPA-Gnesta: bygger karta.js från en OpenStreetMap-export.

Användning:  python3 verktyg/bygg_osm.py verktyg/data/gnesta.osm karta.js

Koordinater: meter, origo = 59.0482 N, 17.3117 E. x = öster, z = söder.
Data © OpenStreetMap-bidragsgivare, ODbL.
"""
import sys, math, json, base64, hashlib, collections
import numpy as np
from matplotlib.path import Path
import os
HAR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HAR)
from las import load, proj

OSM = sys.argv[1]
OUT = sys.argv[2]
nodes, ways, rels = load(OSM)

def P(n):
    la, lo, _ = nodes[n]
    x, z = proj(la, lo)
    return (round(x, 2), round(z, 2))

def pts_of(nds):
    return [P(n) for n in nds if n in nodes]

def h01(s):  # deterministisk "slump" 0..1 från en sträng
    return int(hashlib.md5(str(s).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF

def area(poly):
    a = 0
    for i in range(len(poly)):
        x1, z1 = poly[i]; x2, z2 = poly[(i + 1) % len(poly)]
        a += x1 * z2 - x2 * z1
    return a / 2

def centroid(poly):
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    return sum(xs) / len(xs), sum(zs) / len(zs)

def clean_ring(pts):
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 0.3:
            out.append(p)
    # ta bort nästan kolinjära punkter
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a = out[i - 1]; b = out[i]; c = out[(i + 1) % len(out)]
            cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            L = math.hypot(c[0] - a[0], c[1] - a[1]) or 1
            if abs(cr) / L < 0.15:
                out.pop(i); changed = True; break
    if area(out) < 0:
        out.reverse()
    return out

def assemble_rings(way_ids):
    """Sätt ihop ytterringar från relationsmedlemmar."""
    segs = [list(ways[w][0]) for w in way_ids if w in ways]
    rings = []
    while segs:
        cur = segs.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == cur[-1]: cur += s[1:]; segs.pop(i); changed = True; break
                if s[-1] == cur[-1]: cur += s[::-1][1:]; segs.pop(i); changed = True; break
                if s[-1] == cur[0]: cur = s + cur[1:]; segs.pop(i); changed = True; break
                if s[0] == cur[0]: cur = s[::-1] + cur[1:]; segs.pop(i); changed = True; break
        if cur[0] == cur[-1]:
            rings.append(cur)
    return rings

def min_rect(poly):
    """Minsta omslutande rektangel (cx, cz, b, d, rot) – b längs rot."""
    pts = np.array(poly)
    best = None
    for i in range(len(pts)):
        e = pts[(i + 1) % len(pts)] - pts[i]
        L = np.hypot(*e)
        if L < 1e-6: continue
        ux = e / L; uz = np.array([-ux[1], ux[0]])
        a = pts @ ux; b = pts @ uz
        A = (a.max() - a.min()) * (b.max() - b.min())
        if best is None or A < best[0]:
            ca = (a.max() + a.min()) / 2; cb = (b.max() + b.min()) / 2
            c = ux * ca + uz * cb
            best = (A, c[0], c[1], a.max() - a.min(), b.max() - b.min(), math.atan2(ux[1], ux[0]))
    return best

# ------------------------------------------------------------------ ramar
la0 = min(n[0] for n in nodes.values()); la1 = max(n[0] for n in nodes.values())
root_bounds = None
with open(OSM, encoding='utf-8') as f:
    head = f.read(2000)
import re
m = re.search(r'minlat="([\d.]+)" minlon="([\d.]+)" maxlat="([\d.]+)" maxlon="([\d.]+)"', head)
minlat, minlon, maxlat, maxlon = map(float, m.groups())
bx0, bz1 = proj(minlat, minlon); bx1, bz0 = proj(maxlat, maxlon)
BOUNDS = [round(bx0), round(bx1), round(bz0), round(bz1)]
print('bounds', BOUNDS)

# ------------------------------------------------------------------ vatten
lake_rel = next(r for r in rels.values() if r[1].get('name') == 'Frösjön')
outer = [ref for typ, ref, role in lake_rel[0] if typ == 'way' and role == 'outer']
inner = [ref for typ, ref, role in lake_rel[0] if typ == 'way' and role == 'inner']
lake_outer = [clean_ring(pts_of(r)) for r in assemble_rings(outer)]
lake_inner = [clean_ring(pts_of(r)) for r in assemble_rings(inner)]
river = []; damm = []
for wid, (nds, t) in ways.items():
    if t.get('natural') == 'water' and nds[0] == nds[-1]:
        ring = clean_ring(pts_of(nds))
        a = abs(area(ring))
        if t.get('water') == 'river' or (t.get('water') == 'lake' and wid == '504536217'):
            river.append(ring)
        else:
            damm.append(ring)
water_main = lake_outer + river
print('vatten: sjö', [len(r) for r in lake_outer], 'öar', len(lake_inner), 'å', len(river), 'dammar', len(damm))

def sdf_grid(x0, z0, res, nx, nz):
    xs = x0 + np.arange(nx) * res; zs = z0 + np.arange(nz) * res
    X, Z = np.meshgrid(xs, zs)
    pts = np.column_stack([X.ravel(), Z.ravel()])
    inside = np.zeros(len(pts), bool)
    for ring in water_main:
        inside |= Path(np.array(ring + [ring[0]])).contains_points(pts)
    for ring in lake_inner:
        inside &= ~Path(np.array(ring + [ring[0]])).contains_points(pts)
    d = np.full(len(pts), 1e9)
    for ring in water_main + lake_inner:
        r = np.array(ring + [ring[0]])
        for i in range(len(r) - 1):
            ax, az = r[i]; bx, bz = r[i + 1]
            dx, dz = bx - ax, bz - az; L2 = dx * dx + dz * dz or 1e-9
            t = np.clip(((pts[:, 0] - ax) * dx + (pts[:, 1] - az) * dz) / L2, 0, 1)
            dd = np.hypot(pts[:, 0] - (ax + dx * t), pts[:, 1] - (az + dz * t))
            np.minimum(d, dd, out=d)
    d = np.where(inside, -d, d)
    q = np.clip(np.round(d * 4), -32000, 32000).astype('<i2')
    return {"x0": x0, "z0": z0, "res": res, "nx": nx, "nz": nz, "data": base64.b64encode(q.tobytes()).decode()}

SDF_FIN = sdf_grid(-1400, -1100, 8, 451, 351)      # -1400..2200, -1100..1700
SDF_GROV = sdf_grid(-6000, -6000, 80, 151, 151)    # hela omgivningen
print('sdf klar')

# ------------------------------------------------------------------ marktäcke
LC = {"residential": 3, "industrial": 6, "commercial": 6, "retail": 6, "railway": 6, "farmland": 4, "meadow": 4,
      "animal_keeping": 4, "farmyard": 4, "grass": 2, "village_green": 2, "park": 2, "garden": 2, "cemetery": 2,
      "forest": 1, "wood": 1, "wetland": 7, "pitch": 9, "track": 9, "bare_rock": 5, "beach": 8, "sand": 8}
ORDER = [3, 6, 4, 2, 1, 7, 9, 5, 8]
lc_polys = collections.defaultdict(list)
def lc_class(t):
    for k in ('landuse', 'natural', 'leisure'):
        v = t.get(k)
        if v in LC and not (k == 'leisure' and v == 'track' and 'highway' in t):
            return LC[v]
    return None
for wid, (nds, t) in ways.items():
    c = lc_class(t)
    if c and nds[0] == nds[-1] and 'building' not in t:
        lc_polys[c].append(pts_of(nds))
for rid, (mem, t) in rels.items():
    if t.get('type') == 'multipolygon':
        c = lc_class(t)
        if c:
            for r in assemble_rings([ref for typ, ref, role in mem if typ == 'way' and role == 'outer']):
                lc_polys[c].append(pts_of(r))
LCX0, LCZ0, LCR = BOUNDS[0] - 30, BOUNDS[2] - 30, 6
LCNX = int((BOUNDS[1] - BOUNDS[0] + 60) / LCR) + 1; LCNZ = int((BOUNDS[3] - BOUNDS[2] + 60) / LCR) + 1
X, Z = np.meshgrid(LCX0 + np.arange(LCNX) * LCR, LCZ0 + np.arange(LCNZ) * LCR)
gp = np.column_stack([X.ravel(), Z.ravel()])
lc = np.zeros(len(gp), np.uint8)
for c in ORDER:
    for poly in lc_polys[c]:
        if len(poly) < 3: continue
        arr = np.array(poly)
        mn = arr.min(0); mx = arr.max(0)
        sel = (gp[:, 0] >= mn[0]) & (gp[:, 0] <= mx[0]) & (gp[:, 1] >= mn[1]) & (gp[:, 1] <= mx[1])
        if not sel.any(): continue
        idx = np.where(sel)[0]
        ins = Path(arr).contains_points(gp[idx])
        lc[idx[ins]] = c
MARK = {"x0": LCX0, "z0": LCZ0, "res": LCR, "nx": LCNX, "nz": LCNZ, "data": base64.b64encode(lc.tobytes()).decode()}
print('marktäcke', collections.Counter(lc.tolist()))

# ------------------------------------------------------------------ gator
BREDD = {"motorway": 10, "trunk": 9, "primary": 8.5, "secondary": 8.0, "tertiary": 7.0, "unclassified": 5.5,
         "residential": 5.5, "living_street": 5, "service": 3.8, "pedestrian": 5, "track": 3, "footway": 2.2,
         "cycleway": 2.6, "path": 1.6, "bridleway": 2}
BIL = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"}
TORG = (40, 50)
gator = []; trappor = []; gid = 0; way2g = {}
for wid, (nds, t) in ways.items():
    hw = t.get('highway')
    if not hw: continue
    if hw == 'steps':
        trappor.append({"pts": pts_of(nds), "steg": int(t.get('step_count', '0') or 0), "namn": t.get('name', '')})
        continue
    if hw not in BREDD: continue
    if t.get('area') == 'yes' and nds[0] == nds[-1]: continue
    pts = pts_of(nds)
    if len(pts) < 2: continue
    b = BREDD[hw]
    if hw == 'service' and t.get('service') in ('driveway', 'parking_aisle'): b = 3.2
    if 'width' in t:
        try: b = max(2, min(12, float(t['width'].replace(',', '.').split()[0])))
        except Exception: pass
    cx, cz = centroid(pts)
    dt = math.hypot(cx - TORG[0], cz - TORG[1])
    trott = 0.0
    if hw in ('primary', 'secondary', 'tertiary') and -800 < cx < 700 and cz < 300: trott = 2.2
    elif hw in ('residential', 'unclassified', 'living_street') and dt < 420: trott = 1.6
    yta = t.get('surface', '')
    if hw in ('footway', 'cycleway', 'pedestrian') and not yta: yta = 'paved'
    gid += 1
    g = {"id": "G%03d" % gid, "osm": wid, "namn": t.get('name', ''), "typ": hw, "pts": [[round(p[0], 1), round(p[1], 1)] for p in pts],
         "bredd": b, "trottoar": trott, "bro": t.get('bridge') == 'yes', "tunnel": t.get('tunnel') in ('yes', 'building_passage'),
         "yta": yta, "bil": hw in BIL}
    gator.append(g); way2g[wid] = g
print('gator', len(gator), 'trappor', len(trappor))

# ------------------------------------------------------------------ järnväg
spar = []; perronger = []
for wid, (nds, t) in ways.items():
    if t.get('railway') == 'rail':
        spar.append({"pts": [[round(p[0], 1), round(p[1], 1)] for p in pts_of(nds)], "bro": t.get('bridge') == 'yes', "sido": bool(t.get('service'))})
    if (t.get('railway') == 'platform' or t.get('highway') == 'platform') and nds[0] == nds[-1]:
        perronger.append({"poly": [[round(p[0], 1), round(p[1], 1)] for p in clean_ring(pts_of(nds))], "namn": t.get('name', ''), "buss": t.get('highway') == 'platform'})

import heapq
def rail_paths():
    adj = collections.defaultdict(list); coord = {}
    for wid, (nds, t) in ways.items():
        if t.get('railway') != 'rail' or t.get('service'): continue
        for i in range(len(nds) - 1):
            a, b = nds[i], nds[i + 1]
            if a not in nodes or b not in nodes: continue
            pa, pb = P(a), P(b); d = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            adj[a].append((b, d, (wid, i))); adj[b].append((a, d, (wid, i))); coord[a] = pa; coord[b] = pb
    # största sammanhängande komponenten
    seen = set(); best = []
    for n0 in coord:
        if n0 in seen: continue
        comp = []; st = [n0]; seen.add(n0)
        while st:
            u = st.pop(); comp.append(u)
            for v, w, e in adj[u]:
                if v not in seen: seen.add(v); st.append(v)
        if len(comp) > len(best): best = comp
    # begränsa ändpunkterna till ett rimligt område runt Gnesta
    near = [n for n in best if -2500 < coord[n][0] < 3000 and -2000 < coord[n][1] < 2000]
    west = min(near, key=lambda n: coord[n][0] - 0.3 * coord[n][1]); east = max(near, key=lambda n: coord[n][0] - 0.3 * coord[n][1])
    print('rälskomponent', len(best), 'av', len(coord), coord[west], coord[east])
    def dijkstra(src, dst, banned):
        dist = {src: 0}; prev = {}; pq = [(0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == dst: break
            if d > dist.get(u, 1e18): continue
            for v, w, e in adj[u]:
                if e in banned: continue
                nd = d + w * (1.0 if e not in banned else 50)
                if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = (u, e); heapq.heappush(pq, (nd, v))
        if dst not in prev: return None, set()
        path = [dst]; used = set()
        while path[-1] != src: u, e = prev[path[-1]]; used.add(e); path.append(u)
        return [coord[n] for n in path[::-1]], used
    A, used = dijkstra(west, east, set())
    # andra spåret: närmaste ändnoder som inte ligger på A
    onA = set()
    for wid, i in used: onA.add(ways[wid][0][i]); onA.add(ways[wid][0][i + 1])
    cand_w = sorted([n for n in coord if n not in onA], key=lambda n: math.hypot(coord[n][0] - coord[west][0], coord[n][1] - coord[west][1]))
    cand_e = sorted([n for n in coord if n not in onA], key=lambda n: math.hypot(coord[n][0] - coord[east][0], coord[n][1] - coord[east][1]))
    B = None
    for w2 in cand_w[:6]:
        for e2 in cand_e[:6]:
            B, _ = dijkstra(w2, e2, used)
            if B: break
        if B: break
    return A, B
SPAR_A, SPAR_B = rail_paths()
print('tågspår A', len(SPAR_A), 'B', len(SPAR_B) if SPAR_B else None)

# järnvägsbroar över vägar -> vägskärningar
def seg_inter(a, b, c, d):
    def cr(o, p, q): return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1 = cr(c, d, a); d2 = cr(c, d, b); d3 = cr(a, b, c); d4 = cr(a, b, d)
    if (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0):
        t = d1 / (d1 - d2); return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return None
skarningar = []
for s in spar:
    if not s["bro"]: continue
    for g in gator:
        if g["bro"] or g["tunnel"] or g["typ"] not in BIL: continue
        for i in range(len(s["pts"]) - 1):
            for j in range(len(g["pts"]) - 1):
                ip = seg_inter(s["pts"][i], s["pts"][i + 1], g["pts"][j], g["pts"][j + 1])
                if ip:
                    dup = next((k for k in skarningar if k["gata"] == g["id"] and math.hypot(k["x"] - ip[0], k["z"] - ip[1]) < 25), None)
                    if dup:
                        dup["x"] = round((dup["x"] + ip[0]) / 2, 1); dup["z"] = round((dup["z"] + ip[1]) / 2, 1); continue
                    skarningar.append({"gata": g["id"], "x": round(ip[0], 1), "z": round(ip[1], 1), "langd": 55, "djup": 5.2, "bredd": g["bredd"] + 2})
                    print('viadukt:', g["namn"], [round(v) for v in ip])

# ------------------------------------------------------------------ ytor (torg, parkering, plan, bryggor)
ytor = []
def add_yta(typ, ring, namn=''):
    ring = clean_ring(ring)
    if len(ring) >= 3:
        y = {"typ": typ, "namn": namn, "poly": [[round(p[0], 1), round(p[1], 1)] for p in ring]}
        if typ in ('parkering', 'fontan'):
            r = min_rect(ring); y["rekt"] = [round(r[1], 2), round(r[2], 2), round(r[3], 2), round(r[4], 2), round(r[5], 4)]
        ytor.append(y)
for wid, (nds, t) in ways.items():
    if nds[0] != nds[-1] or 'building' in t: continue
    if t.get('amenity') == 'parking' and t.get('parking') not in ('underground', 'multi-storey'): add_yta('parkering', pts_of(nds), t.get('name', ''))
    elif t.get('highway') == 'pedestrian' and t.get('area') == 'yes': add_yta('torg', pts_of(nds), t.get('name', ''))
    elif t.get('leisure') in ('pitch', 'track'): add_yta('plan', pts_of(nds), t.get('sport', ''))
    elif t.get('man_made') == 'pier' and t.get('area') == 'yes': add_yta('brygga', pts_of(nds))
    elif t.get('amenity') == 'fountain': add_yta('fontan', pts_of(nds))
    elif t.get('leisure') == 'playground': add_yta('lekplats', pts_of(nds))
for rid, (mem, t) in rels.items():
    if t.get('highway') == 'pedestrian' and t.get('type') == 'multipolygon':
        for r in assemble_rings([ref for typ, ref, role in mem if role == 'outer']):
            add_yta('torg', pts_of(r), t.get('name', ''))
# gräsytor som ligger på torg (ritas ovanpå stenläggningen)
torg_polys = [y["poly"] for y in ytor if y["typ"] == "torg"]
for wid, (nds, t) in ways.items():
    if nds[0] != nds[-1] or 'building' in t: continue
    if t.get('landuse') in ('grass', 'village_green') or t.get('leisure') in ('park', 'garden'):
        ring = clean_ring(pts_of(nds))
        if len(ring) < 3: continue
        cx, cz = centroid(ring)
        if any(Path(np.array(tp)).contains_point((cx, cz)) for tp in torg_polys):
            ytor.append({"typ": "gras", "namn": "", "osm": wid, "poly": [[round(p[0], 1), round(p[1], 1)] for p in ring]})
moblering = []
for nid, (la, lo, t) in nodes.items():
    x, z = proj(la, lo)
    if not (BOUNDS[0] < x < BOUNDS[1] and BOUNDS[2] < z < BOUNDS[3]): continue
    if t.get('amenity') == 'bench': moblering.append({"typ": "bank", "x": round(x, 1), "z": round(z, 1)})
    elif t.get('tourism') == 'artwork': moblering.append({"typ": "skulptur", "x": round(x, 1), "z": round(z, 1)})
# fruktträd på gräsmattan mellan fontänen och stationshuset (ca fem stycken)
frukttrad = []
lawn = next((y for y in ytor if y.get("osm") == '501056280'), None)
if lawn:
    path = Path(np.array(lawn["poly"])); hinder = [(m["x"], m["z"]) for m in moblering if abs(m["x"] - 28) < 40 and abs(m["z"] - 40) < 40]
    poly = lawn["poly"]; xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    def edge_d(x, z):
        best = 1e9
        for i in range(len(poly)):
            ax, az = poly[i]; bx, bz = poly[(i + 1) % len(poly)]; dx, dz = bx - ax, bz - az; L2 = dx * dx + dz * dz or 1e-9
            tt = max(0, min(1, ((x - ax) * dx + (z - az) * dz) / L2)); best = min(best, math.hypot(x - ax - dx * tt, z - az - dz * tt))
        return best
    cand = [(x, z) for x in np.arange(min(xs), max(xs), 0.5) for z in np.arange(min(zs), max(zs), 0.5)
            if path.contains_point((x, z)) and edge_d(x, z) > 2.2 and all(math.hypot(x - hx, z - hz) > 3.2 for hx, hz in hinder)]
    for _ in range(5):
        if not cand: break
        best = max(cand, key=lambda c: min([math.hypot(c[0] - f[0], c[1] - f[1]) for f in frukttrad] + [edge_d(*c) * 1.6]))
        frukttrad.append([round(float(best[0]), 1), round(float(best[1]), 1)])
print('fruktträd', frukttrad)
for y in ytor:
    if y["typ"] == "parkering":
        cx, cz = centroid(y["poly"])
        if 205 < cx < 250 and 395 < cz < 447: y["typ"] = "skolgard"
bryggor = []
for wid, (nds, t) in ways.items():
    if t.get('man_made') == 'pier' and t.get('area') != 'yes':
        bryggor.append([[round(p[0], 1), round(p[1], 1)] for p in pts_of(nds)])
print('ytor', collections.Counter(y['typ'] for y in ytor), 'bryggor', len(bryggor))

# ------------------------------------------------------------------ körbara sträckor
RUTTER = [
    {"namn": "Storgatan", "ways": ['38080915', '39780592', '504799985', '481871845', '1562750804', '9702549'],
     "fran": (-598, -163), "till": (505, 183)},
    # Tingshusgatan uppför backen, Skolgatan och Frejavägen fram till Frejaskolan
    {"namn": "Tingshusgatan", "ways": ['32552317', '1562747260', '41777527', '256601471', '41777530'],
     "fran": None, "till": (208, 425)},
]
ALLA_RUTTWAYS = set(w for r in RUTTER for w in r["ways"])
def build_route(R):
    chain = []
    for w in R["ways"]:
        nds = list(ways[w][0])
        if chain and nds[0] != chain[-1]:
            if nds[-1] == chain[-1]: nds = nds[::-1]
            elif not chain or True:
                if len(chain) and chain[0] in (nds[0], nds[-1]) and len(chain) == len(list(ways[R["ways"][0]][0])):
                    chain = chain[::-1]; nds = nds if nds[0] == chain[-1] else nds[::-1]
                else: raise SystemExit('rutten hänger inte ihop vid ' + w)
        chain += nds if not chain else nds[1:]
    cpts = [P(n) for n in chain]
    cum = [0.0]
    for i in range(1, len(cpts)): cum.append(cum[-1] + math.hypot(cpts[i][0] - cpts[i - 1][0], cpts[i][1] - cpts[i - 1][1]))
    def s_near(x, z):
        best = (1e9, 0)
        for i in range(len(cpts) - 1):
            ax, az = cpts[i]; bx, bz = cpts[i + 1]; dx, dz = bx - ax, bz - az; L2 = dx * dx + dz * dz or 1e-9
            t = max(0, min(1, ((x - ax) * dx + (z - az) * dz) / L2))
            d = math.hypot(x - ax - dx * t, z - az - dz * t)
            if d < best[0]: best = (d, cum[i] + t * math.sqrt(L2))
        return best[1]
    S0 = s_near(*R["fran"]) if R["fran"] else 0.0
    S1 = s_near(*R["till"]) if R["till"] else cum[-1]
    def point_at(s):
        for i in range(len(cpts) - 1):
            if cum[i + 1] >= s:
                t = (s - cum[i]) / ((cum[i + 1] - cum[i]) or 1)
                return (cpts[i][0] + (cpts[i + 1][0] - cpts[i][0]) * t, cpts[i][1] + (cpts[i + 1][1] - cpts[i][1]) * t)
        return cpts[-1]
    pts = [point_at(S0)] + [cpts[i] for i in range(len(cpts)) if S0 < cum[i] < S1] + [point_at(S1)]
    nodes_in = set(chain[i] for i in range(len(chain)) if S0 - 1 < cum[i] < S1 + 1)
    print('körbar sträcka %s: %.0f m' % (R["namn"], S1 - S0))
    return {"namn": R["namn"], "pts": pts, "noder": nodes_in, "capStart": R["fran"] is not None, "capEnd": True,
            "bredd": BREDD[ways[R["ways"][0]][1].get('highway')], "point_at": point_at, "S0": S0}
rutt_data = [build_route(R) for R in RUTTER]
route = rutt_data[0]["pts"]
route_nodes = set().union(*[r["noder"] for r in rutt_data])
point_at = rutt_data[0]["point_at"]; S0 = rutt_data[0]["S0"]

# stumpar in i sidogator
stumpar = []
for wid, (nds, t) in ways.items():
    if wid in ALLA_RUTTWAYS: continue
    hw = t.get('highway')
    if hw not in BIL or t.get('area') == 'yes': continue
    for k, n in enumerate(nds):
        if n not in route_nodes: continue
        for dirn in (1, -1):
            j = k + dirn
            if j < 0 or j >= len(nds): continue
            L = (BREDD['secondary'] / 2 + 2.2 + (9 if hw != 'service' else 4))
            pts = [P(nds[k])]; acc = 0; jj = k
            while 0 <= jj + dirn < len(nds) and acc < L:
                a = P(nds[jj]); b = P(nds[jj + dirn]); seg = math.hypot(b[0] - a[0], b[1] - a[1])
                if acc + seg >= L:
                    t2 = (L - acc) / seg; pts.append((a[0] + (b[0] - a[0]) * t2, a[1] + (b[1] - a[1]) * t2)); acc = L; break
                pts.append(b); acc += seg; jj += dirn
            if acc < 3: continue
            g = way2g.get(wid)
            stumpar.append({"gata": g["id"] if g else '', "namn": t.get('name', ''), "typ": hw, "bredd": g["bredd"] if g else 5,
                            "trottoar": g["trottoar"] if g else 0, "pts": [[round(p[0], 1), round(p[1], 1)] for p in pts]})
print('stumpar', len(stumpar), [s['namn'] or s['typ'] for s in stumpar])

# ------------------------------------------------------------------ byggnader
PUTS = ["#e3cf9a", "#d9b98a", "#efe3c4", "#d6a985", "#c9c2b2", "#e7d6b0", "#cdb79a", "#e5c38a", "#bfc6c4", "#e8dccb"]
TRA = ["#8f2f22", "#8f2f22", "#9a3426", "#e2c46a", "#efe8d8", "#f4f1e8", "#a9b9a0", "#9fb5c4", "#c9b48a", "#d8c070", "#c8c4bc"]
TEGEL = ["#b5764f", "#a96f4f", "#c9a46a", "#b9905a", "#9b5a42"]
INDU = ["#8d949a", "#6f7f8f", "#a8a29a", "#8a3a2c", "#b7b3aa", "#5f6a72"]
TAK_ROTT = ["#7a3328", "#8a3a2c", "#6b2e26"]
TAK_MORKT = ["#3b3836", "#46423f", "#2f2d2c", "#565250"]
COLMAP = {"red": "#8f2f22", "yellow": "#e2c46a", "white": "#f2efe6", "grey": "#9a9a96", "gray": "#9a9a96", "brown": "#7a5a40", "black": "#2a2a2a", "green": "#6e8f68", "blue": "#7f9fbf", "beige": "#e3d3b0"}
def colour(v, fallback):
    if not v: return fallback
    v = v.strip().lower()
    if v.startswith('#') and len(v) in (4, 7): return v
    return COLMAP.get(v, fallback)
def lc_at(x, z):
    i = int(round((x - LCX0) / LCR)); j = int(round((z - LCZ0) / LCR))
    if 0 <= i < LCNX and 0 <= j < LCNZ: return int(lc[j * LCNX + i])
    return 0
NAMNTYP = {"train_station": "station"}
hus = []
def add_building(oid, ring, t):
    ring = clean_ring(ring)
    if len(ring) < 3: return
    A = abs(area(ring))
    if A < 6: return
    cx, cz = centroid(ring)
    b = t.get('building', 'yes'); r = h01(oid)
    lcc = lc_at(cx, cz)
    dt = math.hypot(cx - TORG[0], cz - TORG[1])
    centrum = dt < 330 and cz < 200
    klass = b
    if b in ('yes', 'residential', 'commercial', 'retail'):
        if A < 32: klass = 'bod'
        elif lcc == 6 and A > 280 and not centrum: klass = 'hall'
        elif b == 'residential' and A > 160: klass = 'flerbostad'
        elif b in ('commercial', 'retail'): klass = 'affar'
        elif A < 190 and not centrum: klass = 'villa'
        elif centrum: klass = 'centrum'
        elif A < 190: klass = 'villa'
        else: klass = 'flerbostad'
    elif b in ('house', 'detached', 'semidetached_house', 'bungalow'): klass = 'villa'
    elif b in ('garage', 'garages', 'shed', 'hut', 'roof', 'carport', 'service'): klass = 'bod'
    elif b in ('apartments',): klass = 'flerbostad'
    elif b in ('terrace',): klass = 'radhus'
    elif b in ('industrial', 'warehouse', 'manufacture'): klass = 'hall'
    elif b in ('school', 'kindergarten', 'sports_hall', 'church', 'train_station', 'public', 'civic'): klass = b
    else: klass = 'villa' if A < 190 else 'centrum'
    if b in ('roof', 'carport'): klass = 'tak'
    if t.get('man_made') == 'water_tower': klass = 'vattentorn_gammalt'
    if b == 'train_station': klass = 'station'
    # våningar
    fh = 3.0; van = 2
    if klass == 'villa': van = 2 if (A > 120 or r < 0.45) else 1; fh = 3.0
    elif klass == 'bod': van = 1; fh = 2.7
    elif klass == 'radhus': van = 2
    elif klass == 'flerbostad': van = 3 if (A < 450 or r < 0.5) else 4
    elif klass == 'centrum': van = 2 if A < 260 else 3
    elif klass == 'affar': van = 1 if A > 500 else 2; fh = 4.6
    elif klass == 'hall': van = 1; fh = 6.5 if A > 800 else 5.0
    elif klass == 'school': van = 2; fh = 3.8
    elif klass == 'kindergarten': van = 1; fh = 3.4
    elif klass == 'sports_hall': van = 1; fh = 8.5
    elif klass == 'station': van = 2; fh = 4.6
    elif klass == 'church': van = 1; fh = 8
    if t.get('building:levels'):
        try: van = max(1, int(float(t['building:levels'])))
        except Exception: pass
    hojd = None
    if t.get('height'):
        try: hojd = float(t['height'].split()[0])
        except Exception: pass
    # färger
    if klass in ('villa', 'bod', 'radhus'): vagg = TRA[int(r * len(TRA)) % len(TRA)]
    elif klass in ('hall',): vagg = INDU[int(r * len(INDU)) % len(INDU)]
    elif klass in ('flerbostad',): vagg = (TEGEL + PUTS)[int(r * 15) % 15]
    elif klass == 'station': vagg = '#8e4b36'
    else: vagg = PUTS[int(r * len(PUTS)) % len(PUTS)]
    vagg = colour(t.get('building:colour'), vagg)
    rr = h01(oid + 'tak')
    takf = colour(t.get('roof:colour'), (TAK_ROTT + TAK_MORKT)[int(rr * 7) % 7] if klass in ('villa', 'radhus', 'bod') else TAK_MORKT[int(rr * 4) % 4])
    rect = min_rect(ring)
    fill = A / rect[0] if rect and rect[0] > 0 else 0
    rak = fill > 0.86
    tak = {'gabled': 'sadel', 'hipped': 'valm', 'flat': 'platt', 'skillion': 'pulpet', 'pyramidal': 'valm', 'half-hipped': 'valm'}.get(t.get('roof:shape'))
    if not tak:
        if klass in ('villa', 'radhus'): tak = 'sadel' if rr < 0.8 else 'valm'
        elif klass == 'bod': tak = 'sadel' if rr < 0.5 else 'pulpet'
        elif klass in ('flerbostad', 'centrum'): tak = 'sadel' if rr < 0.55 else ('valm' if rr < 0.75 else 'platt')
        elif klass in ('station',): tak = 'valm'
        elif klass == 'church': tak = 'sadel'
        else: tak = 'platt'
    if not rak and tak != 'platt': tak = 'platt'
    namn = t.get('name', '')
    rec = {"osm": oid, "namn": namn, "typ": klass, "van": van, "fh": fh, "vagg": vagg, "tak": tak, "takfarg": takf,
           "x": round(cx, 1), "z": round(cz, 1), "area": round(A)}
    if hojd: rec["hojd"] = hojd
    if rak:
        rec["rekt"] = [round(rect[1], 2), round(rect[2], 2), round(rect[3], 2), round(rect[4], 2), round(rect[5], 4)]
    rec["poly"] = [[round(p[0], 1), round(p[1], 1)] for p in ring]
    hus.append(rec)

for wid, (nds, t) in ways.items():
    if 'building' in t and nds[0] == nds[-1] and t.get('building') not in ('no', 'construction'):
        add_building('w' + wid, pts_of(nds), t)
for rid, (mem, t) in rels.items():
    if 'building' in t and t.get('type') == 'multipolygon':
        for k, r in enumerate(assemble_rings([ref for typ, ref, role in mem if role == 'outer'])):
            add_building('r%s_%d' % (rid, k), pts_of(r), t)

# namn från intilliggande amenity/shop-noder och ytor utan byggnadstagg
def nearest_house(x, z, maxd=12):
    best = None
    for h in hus:
        if Path(np.array(h["poly"])).contains_point((x, z)):
            return h
        d = math.hypot(h["x"] - x, h["z"] - z)
        if d < maxd and (best is None or d < best[0]): best = (d, h)
    return best[1] if best else None
for nid, (la, lo, t) in nodes.items():
    if 'name' in t and any(k in t for k in ('amenity', 'shop', 'office', 'tourism', 'craft')):
        x, z = proj(la, lo); h = nearest_house(x, z, 6)
        if h and not h["namn"]: h["namn"] = t['name']; h["namnkalla"] = 'nod'
# landmärken som saknar namn i OSM men som är kända
MANUELLA = [
    ((-3, 0), "Stationshuset (1907)", "Tegel, nationalromantik, ritat av Folke Zettervall. Tre kungliga kronor på fasaden mot sjön."),
    ((315, 295), "Gamla vattentornet (1913–14)", "28 m högt. Ersattes 1977 av ett nytt torn."),
]
for (x, z), namn, inf in MANUELLA:
    h = nearest_house(x, z, 15)
    if h: h["namn"] = namn; h["not"] = inf; h["sakerhet"] = "säker"

# Harsprånget = Trappgatan (130 steg)
harspr = next((tr for tr in trappor if tr["steg"] == 130), None)

if harspr:
    a = harspr["pts"][0]; b = harspr["pts"][-1]
    L = math.hypot(b[0] - a[0], b[1] - a[1]); rot = math.atan2(b[1] - a[1], b[0] - a[0])
    cx, cz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    ux, uz = math.cos(rot), math.sin(rot)
    poly = [(cx - ux * L / 2 + uz * 1.6, cz - uz * L / 2 - ux * 1.6), (cx + ux * L / 2 + uz * 1.6, cz + uz * L / 2 - ux * 1.6),
            (cx + ux * L / 2 - uz * 1.6, cz + uz * L / 2 + ux * 1.6), (cx - ux * L / 2 - uz * 1.6, cz - uz * L / 2 + ux * 1.6)]
    hus.append({"osm": "trappa", "namn": "Harsprånget (Trappgatan, 130 steg)", "typ": "trappa", "van": 0, "fh": 3, "vagg": "#9a948a",
                "tak": "platt", "takfarg": "#9a948a", "x": round(cx, 1), "z": round(cz, 1), "area": round(L * 3.2),
                "rekt": [round(cx, 2), round(cz, 2), round(L, 2), 3.2, round(rot, 4)], "poly": [[round(q[0], 1), round(q[1], 1)] for q in poly],
                "not": "Trappan från Östra Storgatan upp till Gnestahöjden, bland de längsta i Sverige.", "sakerhet": "säker"})

# utskjutande tak framför Pelle och Lottas café (Västra Storgatan 14, mittemot Kullagatan)
def kapell_framfor(osm_hus, gata_osm, djup=2.9, marg=0.3):
    h = next(h for h in hus if h["osm"] == osm_hus)
    g = next(g for g in gator if g["osm"] == gata_osm)
    best = None
    for i in range(len(g["pts"]) - 1):
        a = g["pts"][i]; b = g["pts"][i + 1]; dx, dz = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dz * dz or 1e-9
        t = max(0, min(1, ((h["x"] - a[0]) * dx + (h["z"] - a[1]) * dz) / L2))
        d = math.hypot(h["x"] - a[0] - dx * t, h["z"] - a[1] - dz * t)
        if best is None or d < best[0]: best = (d, a, b)
    _, a, b = best; L = math.hypot(b[0] - a[0], b[1] - a[1]); ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    nx, nz = -uz, ux
    if (a[0] - h["x"]) * nx + (a[1] - h["z"]) * nz < 0: nx, nz = -nx, -nz   # n pekar från huset mot gatan
    us = [(q[0] - a[0]) * ux + (q[1] - a[1]) * uz for q in h["poly"]]
    vs = [(q[0] - a[0]) * nx + (q[1] - a[1]) * nz for q in h["poly"]]
    u0, u1 = min(us) + marg, max(us) - marg; v0 = max(vs) - 0.05; v1 = v0 + djup
    P = lambda u, v: (a[0] + ux * u + nx * v, a[1] + uz * u + nz * v)
    cx, cz = P((u0 + u1) / 2, (v0 + v1) / 2)
    poly = [P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)]
    return {"x": round(cx, 1), "z": round(cz, 1), "area": round((u1 - u0) * djup),
            "rekt": [round(cx, 2), round(cz, 2), round(u1 - u0, 2), djup, round(math.atan2(uz, ux), 4)],
            "poly": [[round(q[0], 1), round(q[1], 1)] for q in poly]}
kap = kapell_framfor('w510000345', '39780592')
kap.update({"osm": "kapell_vs14", "namn": "Utskjutande tak", "typ": "tak", "van": 1, "fh": 2.7, "vagg": "#f1f0ea",
            "tak": "platt", "takfarg": "#8a3a2c", "uteservering": [-10.5, 11.5], "sakerhet": "säker",
            "not": "Utskjutande tak med uteserveringen för Pelle och Lotta (tillagt, finns inte i OpenStreetMap)."})
hus.append(kap)

# ICA-kvarteret (efter foto): H052 delas – östra flygeln längst mot vägen blir egen byggnad
# med solarium på bottenplan och Frösjö Vårdcentral på övervåningen
def rekt_av(poly):
    r = min_rect(poly); return [round(r[1], 2), round(r[2], 2), round(r[3], 2), round(r[4], 2), round(r[5], 4)]
ICA_OST = [[-292.4, -50.9], [-276.3, -48.0], [-274.9, -55.9], [-291.1, -58.7]]
ICA_VAST = [[-311.0, -71.2], [-289.5, -67.4], [-292.4, -50.9], [-313.9, -54.7]]
_r = rekt_av(ICA_OST)
hus.append({"osm": "ica_ostflygel", "namn": "Frösjö Vårdcentral", "typ": "centrum", "van": 2, "fh": 3.3, "vagg": "#8f2f22", "tak": "sadel",
            "takfarg": "#b0502f", "x": _r[0], "z": _r[1], "area": round(_r[2] * _r[3]), "rekt": _r, "poly": ICA_OST, "sakerhet": "säker",
            "skyltar": [{"text": "SOLARIUM", "mot": [-250, -50], "hojd": 2.9, "bg": "#1e1e1e", "fg": "#f2c414", "hgt": 0.5, "bredd": 2.4, "utanTak": True},
                        {"text": "Frösjö Vårdcentral", "mot": [-250, -50], "hojd": 5.3, "bg": "#1f5fae", "fg": "#ffffff", "hgt": 0.75, "bredd": 2.6, "utanTak": True}],
            "kapell": [{"mot": [-250, -50], "djup": 2.4}, {"mot": [-283, -20], "djup": 2.4}],
            "not": "Solarium på bottenplan längst mot vägen, Frösjö Vårdcentral på övervåningen (efter foto; saknas som egen byggnad i OpenStreetMap)."})

# ID-ordning: namngivna först (närmast sträckan först), sedan efter avstånd till sträckan
def d_route(h):
    best = 1e9
    for i in range(0, len(route) - 1):
        ax, az = route[i]; bx, bz = route[i + 1]; dx, dz = bx - ax, bz - az; L2 = dx * dx + dz * dz or 1e-9
        t = max(0, min(1, ((h["x"] - ax) * dx + (h["z"] - az) * dz) / L2))
        best = min(best, math.hypot(h["x"] - ax - dx * t, h["z"] - az - dz * t))
    return best
for h in hus: h["_d"] = d_route(h)
hus.sort(key=lambda h: (0 if h["namn"] else 1, h["_d"]))
# behåll ID från tidigare utkast så att rättningar alltid pekar rätt
TIDIGARE = json.load(open(os.path.join(HAR, 'data', 'hus_id.json'), encoding='utf-8'))
nasta = max(int(v[1:]) for v in TIDIGARE.values()) + 1
for h in hus:
    if h["osm"] in TIDIGARE: h["id"] = TIDIGARE[h["osm"]]
    else: h["id"] = "H%03d" % nasta; nasta += 1
    h.setdefault("sakerhet", "osm")
    h.setdefault("not", "")
    del h["_d"]
hus.sort(key=lambda h: int(h["id"][1:]))
# manuella ändringar från rättningar (nyckel = hus-ID)
ANDRINGAR = {
    "H006": {"entre": {"skylt": "Pressbyrån", "bg": "#f6d31c", "fg": "#1e5aa8"}, "vagg": "#b4573a", "takfarg": "#4b5057", "van": 1, "fh": 5.2,
             "not": "Tegel, nationalromantik, ritat av Folke Zettervall. Mittparti med svängd gavel, klocka och tre rundbågar; Pressbyrån bakom de gröna dörrarna i mittbågen (efter foto). Tre kungliga kronor på fasaden mot sjön."},
    "H037": {"vagg": "#d6c28a", "takfarg": "#8f9aa3", "fh": 3.1, "van": 2, "sakerhet": "säker",
             "fasad": {"typ": "frejaskolan", "a": [244.4, 397.2], "b": [249.8, 439.1], "entre": [245.75, 426.05], "torn": [250.1, 440.3], "vag": [212.7, 424.4]},
             "not": "Huvudentrén mot Frejavägen: rött entrétorn med runda fönster, gult tegel, ljusblå plåt och ett högt tegeltorn (efter foto)."},
    # längan på Västra Storgatan: Färghuset (två våningar) och enplans röda trähus mot ICA
    "H004": {"vagg": "#9a3226", "takfarg": "#3b3a39", "van": 2, "fh": 3.1, "tak": "sadel", "takAxel": "kort", "sakerhet": "säker",
             "skyltar": [{"text": "GNESTA FÄRGHUS", "mot": [0, -10], "hojd": 4.1, "stil": "farghus", "hgt": 1.5, "bredd": 6.2, "utanTak": True}],
             "not": "Rött trähus i två våningar. Skylten sitter på kortsidan mot stationen (efter foto)."},
    "H062": {"vagg": "#8f2f22", "takfarg": "#8a3a2c", "van": 1, "fh": 3.2},
    "H053": {"vagg": "#8f2f22", "takfarg": "#8a3a2c", "van": 1, "fh": 3.0},
    "H003": {"namn": "Pelle och Lotta", "namnkalla": "rättning", "vagg": "#76291f", "takfarg": "#8a3a2c", "van": 1, "fh": 3.2, "tak": "sadel", "sakerhet": "säker",
             "skyltar": [{"text": "Pelle och Lotta", "mot": [-199.6, -24.7], "hojd": 2.25, "hgt": 0.5, "bredd": 3.0, "bg": "#f3eee2", "fg": "#76291f", "utanTak": True}],
             "not": "Pelles och Lottas Café, Västra Storgatan 14, mittemot Kullagatan. Uteservering under de utskjutande taken (rättat; hette Cafe Thekannan i OpenStreetMap)."},
    "H055": {"vagg": "#8f2f22", "takfarg": "#8a3a2c", "van": 1, "fh": 3.2, "tak": "sadel"},
    "H050": {"namn": "Utskjutande tak", "vagg": "#f1f0ea", "takfarg": "#8a3a2c", "sakerhet": "säker",
             "not": "Rad av utskjutande tak framför längan mot Färghuset (efter foto)."},
    "H023": {"namn": "Gnestas Indiska Restaurang", "sakerhet": "säker", "vagg": "#e4e3dd", "takfarg": "#5d6062", "tak": "platt", "van": 3, "fh": 3.0,
             "fasad": {"typ": "indiska", "mot": [21, 60], "vag": [14.5, 90]},
             "not": "Tre våningar med vita fönsterband och tegelgavlar. Indisk restaurang med uteservering på bottenplan (efter foto; hette Il forno i OpenStreetMap)."},
    # utkast 7 (efter foton)
    "H052": {"typ": "centrum", "vagg": "#8f2f22", "takfarg": "#b0502f", "van": 2, "fh": 3.3, "tak": "sadel", "poly": ICA_VAST, "rekt": rekt_av(ICA_VAST),
             "x": rekt_av(ICA_VAST)[0], "z": rekt_av(ICA_VAST)[1], "area": round(rekt_av(ICA_VAST)[2] * rekt_av(ICA_VAST)[3]), "sakerhet": "säker",
             "not": "Rött trähus i två våningar, del av ICA-kvarteret (efter foto)."},
    "H009": {"vagg": "#8f2f22", "takfarg": "#b0502f", "van": 2, "fh": 3.3, "tak": "sadel", "sakerhet": "säker",
             "skyltar": [{"text": "Systembolaget", "mot": [-250, -60], "hojd": 2.95, "bg": "#0b6b3a", "fg": "#ffffff", "hgt": 0.55, "bredd": 3.4, "utanTak": True},
                         {"text": "Frösjö Vårdcentral", "mot": [-250, -60], "hojd": 5.6, "bg": "#1f5fae", "fg": "#ffffff", "hgt": 0.75, "bredd": 2.6, "utanTak": True}],
             "kapell": [{"mot": [-250, -60], "djup": 2.4}],
             "not": "Systembolaget på bottenplan, Frösjö Vårdcentral på övervåningen (efter foto)."},
    "H020": {"vagg": "#8f2f22", "takfarg": "#3b3a39", "van": 1, "fh": 5.0, "sakerhet": "säker",
             "skyltar": [{"text": "ICA Supermarket", "mot": [-240, -80], "hojd": 4.0, "bg": "#ffffff", "fg": "#e3000f", "hgt": 0.8, "bredd": 4.4, "utanTak": True}],
             "kapell": [{"mot": [-240, -80], "djup": 3.0, "nara": [-270, -72], "langd": 16}],
             "not": "Röd träfasad med skärmtak mot kundparkeringen (efter foto)."},
    "H007": {"namn": "Stora Hotellet", "vagg": "#eee2bd", "takfarg": "#9a4234", "van": 4, "fh": 3.4, "tak": "platt", "sakerhet": "säker",
             "fasad": {"typ": "hotell", "a": [92.6, 32.2], "b": [122.0, 29.9], "torn": [93.0, 35.6, 3.7], "gavel": 113.0, "vag": [100, 21]},
             "not": "Ljust putsat hus med runt hörntorn, svängd gavel och balkonger med svarta smidesräcken (efter foto)."},
    "H016": {"vagg": "#a14c37", "takfarg": "#3a3a3a", "van": 1, "fh": 4.4, "tak": "platt", "sakerhet": "säker",
             "band": [{"y0": 3.45, "y1": 4.55, "farg": "#2a2426"}],
             "volymer": [{"poly": [[-509.0, -168.9], [-499.2, -181.0], [-488.1, -172.1], [-497.9, -159.9]], "h": 8.4, "vagg": "#4c2c28"},
                         {"poly": [[-482.0, -145.5], [-462.5, -169.5], [-471.4, -180.5], [-490.5, -157.0]], "h": 7.6, "vagg": "#a14c37"}],
             "skyltar": [{"text": "GRANNGÅRDEN", "mot": [-505, -141], "hojd": 4.0, "bg": "#2a2426", "fg": "#ffffff", "hgt": 0.7, "bredd": 5.6, "utanTak": True}],
             "not": "Tegelfasad mot Västra Storgatan, mörkbrun plåtklädd lagerdel och fönsterband på övervåningen (efter foto)."},
    "H011": {"vagg": "#f4f3ef", "takfarg": "#b5532f", "van": 1, "fh": 3.3, "tak": "valm", "sakerhet": "säker",
             "skyltar": [{"text": "Vita Villan", "mot": [-438, -88], "hojd": 3.75, "bg": "#ffffff", "fg": "#1f4fa0", "hgt": 0.6, "bredd": 2.8, "utanTak": True, "kursiv": True}],
             "not": "Litet vitt hus med tegeltak och uteservering med röda parasoller (efter foto)."},
    "H091": {"namn": "Gnesta GYM", "typ": "centrum", "vagg": "#a24e36", "takfarg": "#9a4a33", "van": 2, "fh": 3.6, "tak": "sadel", "sakerhet": "säker",
             "rekt": rekt_av([[-453.7, -144.7], [-452.3, -143.9], [-446.6, -139.4], [-448.5, -136.9], [-436.1, -127.4], [-439.9, -122.5], [-439.2, -122.0], [-443.5, -116.4], [-463.6, -132.0]]),
             "fasad": {"typ": "mejeri", "kaj": [-458.7, -118.6]},
             "kapell": [{"mot": [-458.7, -118.6], "djup": 3.3, "hojd": [4.35, 4.15], "takfarg": "#4a3a30", "vagg": "#2b2b2b", "trim": 2.5}],
             "skyltar": [{"text": "GNESTA GYM", "mot": [-458.7, -118.6], "hojd": 5.6, "bg": "#23272d", "fg": "#ffffff", "hgt": 0.6, "bredd": 3.8, "utanTak": True, "u": 6.5}],
             "not": "Gamla mejeriet: tegel, brant tegeltak med svarta kupor, lastkaj med skärmtak och grön panel, hög tegelskorsten (efter foto)."},
    # Tingshusgatans början (efter foton)
    "H092": {"vagg": "#e3cb8a", "takfarg": "#9a4b33", "tak": "sadel", "van": 2, "fh": 3.3, "sakerhet": "säker",
             "skyltar": [{"text": "Guldsmen´s", "mot": [12, 48], "hojd": 3.05, "bg": "#22282e", "fg": "#efe2bf", "hgt": 0.6, "bredd": 3.6, "utanTak": True, "u": 4.5},
                         {"text": "OPTIK · KONTAKTLINSER", "mot": [12, 48], "hojd": 3.05, "bg": "#22282e", "fg": "#ffffff", "hgt": 0.6, "bredd": 5.4, "utanTak": True, "u": -1.0}],
             "not": "Gult putsat hus i två våningar med butiker i bottenplan längs Tingshusgatan, bl.a. optikern Guldsmen´s. Snedparkering och låga träd framför (efter foto)."},
    "H189": {"vagg": "#e6cf8f", "takfarg": "#9a4b33", "tak": "sadel", "sakerhet": "säker", "not": "Gult hus med butiker i bottenplan, balkonger och takkupor; parkering framför (efter foto)."},
    "H026": {"vagg": "#8f2f22", "takfarg": "#7a3f2e", "van": 1, "fh": 3.3, "tak": "sadel", "takAxel": "kort", "sakerhet": "säker",
             "not": "Litet rött trähus vid foten av Tingshusbacken (efter foto)."},
}
for h in hus:
    if h["id"] in ANDRINGAR: h.update(ANDRINGAR[h["id"]])
print('hus', len(hus), collections.Counter(h["typ"] for h in hus))
print('namngivna', [(h["id"], h["namn"]) for h in hus if h["namn"]][:60])

# räcke mellan Frejavägen och skolgården (efter foto)
RACKEN = []
fv = next(g for g in gator if g["osm"] == '41777530')
dense = []
for i in range(len(fv["pts"]) - 1):
    a = fv["pts"][i]; b = fv["pts"][i + 1]; L = math.hypot(b[0] - a[0], b[1] - a[1]); k = max(1, int(L))
    for j in range(k): t = j / k; dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
dense.append(tuple(fv["pts"][-1]))
line = []
for i in range(1, len(dense) - 1):
    x, z = dense[i]
    if not (401 <= z <= 446): continue
    tx = dense[i + 1][0] - dense[i - 1][0]; tz = dense[i + 1][1] - dense[i - 1][1]; L = math.hypot(tx, tz) or 1
    nx, nz = -tz / L, tx / L
    if nx < 0: nx, nz = -nx, -nz   # mot skolan (öster)
    off = fv["bredd"] / 2 + fv["trottoar"] + 0.35
    line.append([round(x + nx * off, 2), round(z + nz * off, 2)])
line.sort(key=lambda p: p[1])
RACKEN.append({"typ": "cykelracke", "pts": line, "mot": [247, 424]})
print('räcke', len(line), line[0], line[-1])

# startpunkt
sx, sz = point_at(S0 + 22); sx2, sz2 = point_at(S0 + 26)
START = {"x": round(sx, 1), "z": round(sz, 1), "h": round(math.atan2(sx2 - sx, sz2 - sz), 4)}

# ------------------------------------------------------------------ Tingshusgatan vid H092: snedparkering (efter foto)
def _xc(z, pts):
    for i in range(len(pts) - 1):
        (ax, az), (bx, bz) = pts[i], pts[i + 1]
        if min(az, bz) <= z <= max(az, bz) and az != bz: return ax + (bx - ax) * (z - az) / (bz - az)
    return pts[0][0] if z < pts[0][1] else pts[-1][0]
_tg = next(g for g in gator if g["osm"] == '32552317'); _tgp = [tuple(p) for p in _tg["pts"]]
_h92 = next(h for h in hus if h["id"] == 'H092'); _cx, _cz, _b, _d, _rot = _h92["rekt"]
_ax = (math.cos(_rot), math.sin(_rot)); _nx = (_ax[1], -_ax[0]) if _ax[1] > 0 else (-_ax[1], _ax[0])   # normal mot öster
def _xf(z):  # fasadlinjen (östra långsidan) vid z
    px, pz = _cx + _nx[0] * _d / 2, _cz + _nx[1] * _d / 2; t = (z - pz) / _ax[1]; return px + _ax[0] * t
_z0, _z1 = 32.0, 64.0; _zs = [_z0 + (_z1 - _z0) * k / 8 for k in range(9)]
_kant = lambda z: _xc(z, _tgp) - _tg["bredd"] / 2
_park = next(y for y in ytor if y["typ"] == "parkering" and -6 < centroid(y["poly"])[0] < 6 and 30 < centroid(y["poly"])[1] < 66)
_park["poly"] = [[round(_xf(z) + 2.0, 1), round(z, 1)] for z in _zs] + [[round(_kant(z) - 0.1, 1), round(z, 1)] for z in reversed(_zs)]
_park["rekt"] = rekt_av(_park["poly"]); _park["ingaBilar"] = True
ytor.append({"typ": "torg", "namn": "", "poly": [[round(_xf(z) - 0.2, 1), round(z, 1)] for z in _zs] + [[round(_xf(z) + 2.0, 1), round(z, 1)] for z in reversed(_zs)]})
_vink = math.radians(55); _nos = (-math.sin(_vink), math.cos(_vink))   # nosen snett in mot huset, åt söder
parkerade = []
z = _z0 + 1.8
while z < _z1 - 1.5:
    rx = _kant(z) - 0.35; cxp = rx + _nos[0] * 2.2; czp = z + _nos[1] * 2.2
    parkerade.append([round(cxp, 2), round(czp, 2), round(math.atan2(_nos[0], _nos[1]), 3)]); z += 3.05
utan_trottoar = [[[round(_xf(z) + 0.5, 1), round(z, 1)] for z in [31.0] + _zs + [65.0]] + [[round(_xc(z, _tgp) - 1.0, 1), round(z, 1)] for z in reversed([31.0] + _zs + [65.0])]]
sma_trad = [{"x": round(_xf(z) + 1.0, 1), "z": z, "h": 5.2, "r": 2.0} for z in (35.0, 41.0, 47.0, 53.0, 59.0)]
print('snedparkering', len(parkerade), 'platser')

KARTA = {
    "version": "utkast-2 (OSM)",
    "kalla": "Kartdata © OpenStreetMap-bidragsgivare (ODbL)",
    "origo": {"lat": 59.0482, "lon": 17.3117},
    "ram": BOUNDS,
    "terrang": {
        "vatten": 12.2, "bas": 12.6, "lutning": 0.02, "maxAvst": 330,
        # Gnestahöjden: platå med förkastningsbrant mot norr (Harsprånget ~23 m upp), topp vid gamla vattentornet ~60 m
        "plata": [[-5, 205], [55, 135], [120, 98], [168, 86], [250, 72], [330, 82], [370, 122], [392, 182], [405, 250],
                  [415, 330], [395, 420], [335, 500], [240, 520], [120, 470], [40, 390], [0, 290]],
        "plataBredd": [70, 48, 45, 45, 45, 55, 65, 70, 90, 140, 170, 180, 160, 140, 120, 100],
        "plataHojd": 21.0,
        "topp": [315, 290, 150, 19.0],
        "kullar": [[-1150, 450, 420, 14], [300, 1500, 520, 16], [1600, 600, 450, 15], [-800, 1100, 400, 15],
                   [-1600, -900, 500, 12], [-300, 700, 300, 8]],
        "sdf": SDF_FIN, "sdfGrov": SDF_GROV,
        "skarningar": skarningar,
    },
    "marktacke": MARK,
    "vatten": {"dammar": [[[round(p[0], 1), round(p[1], 1)] for p in r] for r in damm]},
    "gator": gator,
    "trappor": [{"pts": [[round(p[0], 1), round(p[1], 1)] for p in tr["pts"]], "steg": tr["steg"], "namn": tr["namn"]} for tr in trappor],
    "harspranget": [[round(p[0], 1), round(p[1], 1)] for p in harspr["pts"]] if harspr else None,
    "jarnvag": {"spar": spar, "perronger": perronger,
                "tagA": [[round(p[0], 1), round(p[1], 1)] for p in SPAR_A], "tagB": [[round(p[0], 1), round(p[1], 1)] for p in (SPAR_B or SPAR_A)]},
    "ytor": ytor,
    "bryggor": bryggor,
    "korbar": {"rutter": [{"namn": r["namn"], "pts": [[round(p[0], 1), round(p[1], 1)] for p in r["pts"]], "bredd": r["bredd"],
                            "trottoar": 2.2 if r["bredd"] >= 7 else 1.6, "capStart": r["capStart"], "capEnd": r["capEnd"]} for r in rutt_data],
               "stumpar": stumpar},
    "moblering": moblering,
    "racken": RACKEN,
    "frukttrad": frukttrad,
    # detaljer efter foton av Tingshusbacken: berghäll bakom restaurangens gavel, stor lind i parkhörnet, övergångsställen
    "detaljer": {
        "berg": [{"x": 28.8, "z": 104.5, "b": 13.0, "d": 8.0, "h": 6.0, "rot": 1.40, "trad": 4}],
        "storaTrad": [{"x": 13.3, "z": 47.5, "h": 17.0, "r": 8.0},
                      {"x": -433.0, "z": -113.5, "h": 14.0, "r": 5.0}, {"x": -408.0, "z": -111.0, "h": 15.0, "r": 7.0}, {"x": -399.0, "z": -96.0, "h": 14.0, "r": 6.5}] + sma_trad,
        "parkeradeBilar": parkerade,
        "utanTrottoar": utan_trottoar,
        "uteplatser": [{"x": -419.3, "z": -99.5, "b": 9.0, "d": 6.5, "rot": 0.6634, "parasoll": "#d0262f"}],
        "skorstenar": [{"x": -453.0, "z": -147.4, "h": 24.0, "r": 1.05}],
        "overgangar": [{"osm": "32552317", "nara": [5.9, 27.5]}, {"osm": "504799985", "nara": [16.0, 19.5]}],
    },
    "hus": hus,
    "start": START,
}
with open(OUT, 'w', encoding='utf-8') as f:
    f.write("// EPA-Gnesta – kartdata (utkast 2). Genererad från OpenStreetMap-export.\n")
    f.write("// Kartdata © OpenStreetMap-bidragsgivare, tillgänglig under ODbL (openstreetmap.org/copyright).\n")
    f.write("export const KARTA = ")
    f.write(json.dumps(KARTA, ensure_ascii=False, separators=(",", ":")))
    f.write(";\n")
import os
print('skrev', OUT, os.path.getsize(OUT) // 1024, 'kB')
