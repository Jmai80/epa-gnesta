#!/usr/bin/env python3
"""EPA-Gnesta: bygger karta.js från en OpenStreetMap-export.
Koordinater: meter, origo = 59.0482 N, 17.3117 E. x = öster, z = söder.
Data © OpenStreetMap-bidragsgivare, ODbL.
"""
import sys, os, math, json, base64, hashlib, collections
import numpy as np
from matplotlib.path import Path
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
    # Västra Storgatan – Östra Storgatan ända fram till Skillingagatan (bommen borttagen i utkast 13: slinga via Nygatan–Skillingagatan)
    {"namn": "Storgatan", "ways": ['628057219', '38080915', '39780592', '504799985', '481871845', '1562750804', '9702549', '165775238'],
     "fran": (-1100, -226), "till": None, "oppenSlut": True},
    # Tingshusgatan uppför backen, Skolgatan och Frejavägen fram till Frejaskolan
    {"namn": "Tingshusgatan", "ways": ['32552317', '1562747260', '41777527', '256601471', '41777530'],
     "fran": None, "till": (208, 425)},
    # Nygatan förbi vårdcentralen och vidare på Skillingagatan ut på Östra Storgatan
    {"namn": "Nygatan–Skillingagatan", "ways": ['41556699', '41501519'], "fran": None, "till": None, "oppenSlut": True},
    # infarten från Nygatan till Gnesta Vårdcentral, med vändslinga runt refugen
    {"namn": "Infart vårdcentralen", "ways": ['1448573287', '256248201'], "fran": None, "till": None, "oppenSlut": True},
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
    return {"namn": R["namn"], "pts": pts, "noder": nodes_in, "capStart": R["fran"] is not None, "capEnd": not R.get("oppenSlut"),
            "bredd": BREDD[ways[R["ways"][0]][1].get('highway')], "point_at": point_at, "S0": S0, "s_near": s_near}
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
            # leder sidogatan till en bro: sluta en bit före bron så att bron syns bakom avspärrningen
            slut = nds[-1] if dirn == 1 else nds[0]
            if any(t2.get('bridge') == 'yes' and slut in n2 for w2, (n2, t2) in ways.items() if w2 != wid and t2.get('highway')):
                wl = sum(math.hypot(P(nds[q + 1])[0] - P(nds[q])[0], P(nds[q + 1])[1] - P(nds[q])[1]) for q in (range(k, len(nds) - 1) if dirn == 1 else range(0, k)))
                L = min(L, max(6.0, wl - 6.0))
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

# Förskolan Kristallen (H1459, efter foto): enplanshus i mörkgrå stående panel med vita knutar och fönsterfoder,
# rött/orange tegeltak. Fotavtrycket är ett H – en mittkropp med sadeltak på längden och två tvärflyglar med egna sadeltak.
KR_O = (-966.9, 24.0); KR_U = (0.633, 0.774); KR_V = (-0.774, 0.633); KR_ROT = round(math.atan2(KR_U[1], KR_U[0]), 4)
def kr_rekt(u0, u1, v0, v1):
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    return [round(KR_O[0] + cu * KR_U[0] + cv * KR_V[0], 2), round(KR_O[1] + cu * KR_U[1] + cv * KR_V[1], 2), round(u1 - u0, 2), round(v1 - v0, 2), KR_ROT]
def kr_poly(r):
    x, z, b, d, rot = r; c, sn = math.cos(rot), math.sin(rot)
    return [[round(x + lx * c - lz * sn, 1), round(z + lx * sn + lz * c, 1)] for lx, lz in ((-b / 2, -d / 2), (b / 2, -d / 2), (b / 2, d / 2), (-b / 2, d / 2))]
KR_FARG = {"typ": "kindergarten", "van": 1, "fh": 3.1, "vagg": "#555e5a", "tak": "sadel", "takfarg": "#b5643c", "sakerhet": "säker"}
for oid, (u0, u1, v0, v1), fh, txt in (("kristallen_flygel_s", (0, 14.9, 0, 11.4), 3.1, "södra tvärflygeln"),
                                        ("kristallen_flygel_n", (0, 15.2, 24.3, 34.7), 3.1, "norra tvärflygeln"),
                                        ("kristallen_entre", (-2.9, 0.2, 13.4, 22.5), 2.5, "entréutbyggnaden")):
    _r = kr_rekt(u0, u1, v0, v1)
    hus.append({"osm": oid, "namn": "Kristallen", **KR_FARG, "fh": fh, "x": _r[0], "z": _r[1], "area": round(_r[2] * _r[3]), "rekt": _r, "poly": kr_poly(_r),
                "not": "Förskolan Kristallen, " + txt + " (efter foto; delad ur byggnaden i OpenStreetMap för att få sadeltak)."})

# Blomstergården (H022, efter tre foton): komplexet delas i husdelar i fotavtryckets egna axlar
#  - butiken mot parkeringen: mörkbrun träpanel, grått sadeltak, gavel med skylt mot parkeringen, rött skärmtak
#  - stora hallen bakom: ockragul med rött tegeltak och skylt på norra gaveln (syns från Ringvägen)
#  - växthus/förråd i väster och öster: ljusa väggar och ljust plåttak
BL_O = (-448.5, 5.1); BL_U = (0.89654, -0.44296); BL_V = (0.44296, 0.89654); BL_ROT = round(math.atan2(BL_U[1], BL_U[0]), 4)
def bl_rekt(u0, u1, v0, v1):
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    return [round(BL_O[0] + cu * BL_U[0] + cv * BL_V[0], 2), round(BL_O[1] + cu * BL_U[1] + cv * BL_V[1], 2), round(u1 - u0, 2), round(v1 - v0, 2), BL_ROT]
BL_VAXTHUS = {"typ": "hall", "van": 1, "fh": 3.0, "vagg": "#e7ece6", "tak": "sadel", "takfarg": "#dfe3dc", "utanFonster": True, "sakerhet": "foto"}
for oid, (u0, u1, v0, v1), extra, txt in (
        ("blomster_butik", (1.4, 24.4, -44.7, -34.0), {"typ": "affar", "van": 1, "fh": 3.4, "vagg": "#4e3a2e", "tak": "sadel", "takfarg": "#5b5e60", "sakerhet": "foto",
          "skyltar": [{"text": "Blomstergården", "mot": [-425.0, -60.0], "hojd": 3.75, "bg": "#efe6cf", "fg": "#c11f2a", "hgt": 0.95, "bredd": 4.6, "utanTak": True, "kursiv": True}],
          "kapell": [{"mot": [-425.0, -60.0], "djup": 2.2, "takfarg": "#b3362b", "vagg": "#4e3a2e", "trim": 1.0}]},
         "butiken mot parkeringen"),
        ("blomster_vaxthus_o", (28.2, 38.0, -34.0, -14.7), BL_VAXTHUS, "växthuset i öster"),
        ("blomster_vaxthus_v", (-12.6, 0.0, -38.9, -27.8), {"typ": "affar", "van": 1, "fh": 3.4, "vagg": "#d6a23f", "tak": "sadel", "takAxel": "kort", "takfarg": "#a33b2b", "sakerhet": "foto",
          "skyltar": [{"text": "Blomstergården", "mot": [-478.0, -75.0], "hojd": 4.75, "bg": "#d6a23f", "fg": "#c11f2a", "hgt": 1.1, "bredd": 5.0, "utanTak": True, "kursiv": True}]},
         "det gula huset med rött tak och skylt på gaveln mot Ringvägen"),
        ("blomster_vaxthus_v2", (-8.9, 0.0, -18.0, -2.8), BL_VAXTHUS, "förrådet i väster")):
    _r = bl_rekt(u0, u1, v0, v1); x_, z_, b_, d_, rot_ = _r; c_, s_ = math.cos(rot_), math.sin(rot_)
    poly_ = [[round(x_ + lx * c_ - lz * s_, 1), round(z_ + lx * s_ + lz * c_, 1)] for lx, lz in ((-b_ / 2, -d_ / 2), (b_ / 2, -d_ / 2), (b_ / 2, d_ / 2), (-b_ / 2, d_ / 2))]
    hus.append({"osm": oid, "namn": "Blomstergården", **extra, "x": _r[0], "z": _r[1], "area": round(b_ * d_), "rekt": _r, "poly": poly_,
                "not": "Blomstergården, " + txt + " (efter foto; delad ur byggnaden i OpenStreetMap)."})

# Frejahallen (H040, efter två foton): stor idrottshall med blå plåt och fönsterband, entréhuset mot norr med
# "FREJA BAD & GYM" och ENTRÉ, ett mörkt överbyggt teknikrum, och hörntornet mot Frejavägen med blå glasvägg och "FREJA SPORTCENTER"
FR_C = (239.44, 473.35); FR_ROT = -0.1259; FR_U = (math.cos(FR_ROT), math.sin(FR_ROT)); FR_V = (-math.sin(FR_ROT), math.cos(FR_ROT))
def fr_w(u, v): return [round(FR_C[0] + u * FR_U[0] + v * FR_V[0], 2), round(FR_C[1] + u * FR_U[1] + v * FR_V[1], 2)]
def fr_rekt(u0, u1, v0, v1): c = fr_w((u0 + u1) / 2, (v0 + v1) / 2); return [c[0], c[1], round(u1 - u0, 2), round(v1 - v0, 2), FR_ROT]
def fr_poly(u0, u1, v0, v1): return [fr_w(u0, v0), fr_w(u1, v0), fr_w(u1, v1), fr_w(u0, v1)]
FR_TEGEL = "#d8b66f"; FR_GRON = "#2a7a46"
for oid, (u0, u1, v0, v1), extra, txt in (
        ("freja_entre", (-2.0, 13.0, -24.3, -9.0), {"typ": "sports_hall", "van": 1, "fh": 7.5, "vagg": FR_TEGEL, "utanFonster": True, "tak": "platt", "takfarg": "#3a3838",
          "volymer": [{"poly": fr_poly(5.0, 12.4, -23.6, -10.0), "h": 10.3, "vagg": "#3d2e38"}],
          "skyltar": [{"text": "FREJA BAD & GYM", "mot": fr_w(5.5, -70.0), "hojd": 5.7, "bg": FR_TEGEL, "fg": FR_GRON, "hgt": 0.9, "bredd": 5.4, "utanTak": True},
                      {"text": "ENTRÉ", "mot": fr_w(5.5, -70.0), "hojd": 3.35, "bg": FR_TEGEL, "fg": "#2b2b2b", "hgt": 0.42, "bredd": 1.8, "utanTak": True},
                      {"text": "", "stil": "glasvagg", "mot": fr_w(5.5, -70.0), "hojd": 3.4, "bg": "#2b48b8", "hgt": 5.4, "bredd": 1.1, "utanTak": True, "u": 3.4}]},
         "entréhuset mot norr"),
        ("freja_torn", (-16.0, -2.0, -18.3, -9.0), {"typ": "sports_hall", "van": 1, "fh": 9.6, "vagg": FR_TEGEL, "utanFonster": True, "tak": "platt", "takfarg": "#3a3838",
          "skyltar": [{"text": "", "stil": "glasvagg", "mot": fr_w(-70.0, -13.6), "hojd": 4.3, "bg": "#2b48b8", "hgt": 6.9, "bredd": 5.8, "utanTak": True},
                      {"text": "FREJA SPORTCENTER", "mot": fr_w(-70.0, -13.6), "hojd": 8.6, "bg": FR_TEGEL, "fg": FR_GRON, "hgt": 1.0, "bredd": 7.6, "utanTak": True}]},
         "hörntornet mot Frejavägen")):
    _r = fr_rekt(u0, u1, v0, v1)
    hus.append({"osm": oid, "namn": "Frejahallen", **extra, "x": _r[0], "z": _r[1], "area": round(_r[2] * _r[3]), "rekt": _r, "poly": fr_poly(u0, u1, v0, v1), "sakerhet": "foto",
                "not": "Frejahallen, " + txt + " (efter foto; delad ur byggnaden i OpenStreetMap)."})

# Tingshuset (H031, efter foto från Parkvägen): ljust ockragult putsat hus i två våningar med vita hörnlisener,
# brutet tak (mansard) i mörk plåt med takkupor, och ett mittparti mot Tingshusgatan med klassisk frontespis
TH_O = (32.3, 222.1); TH_V = (0.18534, 0.98267); TH_U = (0.98267, -0.18534); TH_ROT = round(math.atan2(TH_U[1], TH_U[0]), 4)
def th_w(u, v): return [round(TH_O[0] + u * TH_U[0] + v * TH_V[0], 2), round(TH_O[1] + u * TH_U[1] + v * TH_V[1], 2)]
def th_rekt(u0, u1, v0, v1): c = th_w((u0 + u1) / 2, (v0 + v1) / 2); return [c[0], c[1], round(u1 - u0, 2), round(v1 - v0, 2), TH_ROT]
TH_VAGG = "#e3c793"; TH_TAK = "#4c3d38"
_r = th_rekt(-0.8, 1.0, 8.9, 19.2)
hus.append({"osm": "tingshuset_mittparti", "namn": "Tingshuset", "typ": "flerbostad", "van": 2, "fh": 3.5, "vagg": TH_VAGG, "tak": "sadel", "takAxel": "kort", "taklutning": 0.36,
            "takfarg": TH_TAK, "lisener": "#f3f0e7", "band": [{"y0": 0.0, "y1": 0.7, "farg": "#8c8a86"}, {"y0": 6.75, "y1": 7.0, "farg": "#f3f0e7"}],
            "x": _r[0], "z": _r[1], "area": round(_r[2] * _r[3]), "rekt": _r, "poly": [th_w(-0.8, 8.9), th_w(1.0, 8.9), th_w(1.0, 19.2), th_w(-0.8, 19.2)], "sakerhet": "foto",
            "fasad": {"a": th_w(0.0, 0.0), "b": th_w(0.0, 28.5), "vag": [41.5, 237.0]},
            "not": "Tingshusets mittparti mot Tingshusgatan med entré och klassisk frontespis (efter foto)."})

# allmän hjälp: lokala axlar för ett hus (O = origo, U = enhetsvektor längs u, V = U vriden 90° åt vänster)
def lokal(O, U):
    V = (-U[1], U[0])
    W = lambda u, v: [round(O[0] + u * U[0] + v * V[0], 2), round(O[1] + u * U[1] + v * V[1], 2)]
    def rekt(u0, u1, v0, v1, langs_v=False):
        c = W((u0 + u1) / 2, (v0 + v1) / 2)
        if langs_v: return [c[0], c[1], round(v1 - v0, 2), round(u1 - u0, 2), round(math.atan2(V[1], V[0]), 4)]
        return [c[0], c[1], round(u1 - u0, 2), round(v1 - v0, 2), round(math.atan2(U[1], U[0]), 4)]
    poly = lambda u0, u1, v0, v1: [W(u0, v0), W(u1, v0), W(u1, v1), W(u0, v1)]
    return W, rekt, poly
def husdel(oid, namn, rekt_, poly_, attr, txt):
    hus.append({"osm": oid, "namn": namn, **attr, "x": rekt_[0], "z": rekt_[1], "area": round(rekt_[2] * rekt_[3]), "rekt": rekt_, "poly": poly_, "sakerhet": "foto", "not": txt})

# Torggatan 16 (H217 + H183, efter foton): kvarteret runt en innergård. Närmast Elektron ett blått tornhus i fem våningar med brant
# sadeltak, gavel mot öster och träbalkong högst upp; ockragula flyglar i tre våningar med röda fönsterbågar; mot Thulegatan en röd
# del med ljusgröna balkonger och gula fönsterbågar och en rosa flygel
T16_W, T16_R, T16_P = lokal((-306.6, 51.5), (-0.16529, 0.98623))
T16_OCKRA = {"typ": "flerbostad", "van": 3, "fh": 3.0, "vagg": "#d7a862", "tak": "sadel", "taklutning": 0.55, "takfarg": "#4a4744", "karmFarg": "#b5452f"}
husdel("torggatan16_torn", "", T16_R(-14.5, 1.5, 0.0, 17.0, True), T16_P(-14.5, 1.5, 0.0, 17.0),
       {"typ": "flerbostad", "van": 5, "fh": 3.0, "vagg": "#7f9cc2", "tak": "sadel", "taklutning": 0.85, "takfarg": "#4f5257", "karmFarg": "#e0a838",
        "balkonger": [{"vid": T16_W(-8.5, 0.0), "mot": [-250.0, 40.0], "y": 12.1, "b": 3.4, "d": 1.4, "farg": "#d9a04a", "markis": "#b9823a"}]},
       "Torggatan 16: blått tornhus i fem våningar närmast Elektron, brant sadeltak med gavel mot öster och träbalkong högst upp (efter foto).")
husdel("torggatan16_syd", "", T16_R(13.9, 26.6, 12.4, 35.7, True), T16_P(13.9, 26.6, 12.4, 35.7), T16_OCKRA,
       "Torggatan 16: flygeln mot Torggatan, ockragul puts med röda fönsterbågar (efter foto).")
H183_NW, H183_NR, H183_NP = lokal((-361.9, 21.1), (0.99381, 0.11134))
H183_VW, H183_VR, H183_VP = lokal((-373.1, 56.4), (0.19493, -0.98082))
husdel("torggatan16_rosa", "", H183_VR(-3.5, 27.0, 0.0, 13.2), H183_VP(-3.5, 27.0, 0.0, 13.2),
       {"typ": "flerbostad", "van": 3, "fh": 3.0, "vagg": "#d39a92", "tak": "valm", "takfarg": "#4a4744", "karmFarg": "#e3b23c"},
       "Torggatan 16: rosa flygeln längs Thulegatan med gula fönsterbågar (efter foto).")

# H059 där bilen startar (efter foto): gult trähus med stående panel i två våningar, brun sockel, låglutande sadeltak med
# flera skorstenar i rött tegel, vita fönster och entréer med stenomfattning, grått spjälstaket mot trottoaren
H059_W, H059_R, H059_P = lokal((-549.26, -183.62), (math.cos(-2.8308), math.sin(-2.8308)))

# Ringvägens början (efter tre foton): röd stuga H069 med farstukvist, gult hus H099 med brutet tak, och en lång röd bod mot
# Västra Storgatan; allt omgivet av lummig grönska
H069_W, H069_R, H069_P = lokal((-463.97, -81.31), (math.cos(-0.3408), math.sin(-0.3408)))
husdel("ringvagen_farstukvist", "", H069_R(-4.0, -1.6, 3.785, 5.4), H069_P(-4.0, -1.6, 3.785, 5.4),
       {"typ": "villa", "van": 1, "fh": 2.4, "vagg": "#f2efe6", "tak": "sadel", "takAxel": "kort", "taklutning": 0.9, "takfarg": "#a64a33", "utanFonster": True,
        "skyltar": [{"text": "", "stil": "fonster", "mot": H069_W(-2.8, 30.0), "hojd": 1.25, "hgt": 1.3, "bredd": 1.0, "utanTak": True, "bg": "#f2efe6"}]},
       "Vit farstukvist med snickarglädje på den röda stugan vid Ringvägen (efter foto).")
_bU = (0.822, 0.570); RB_W, RB_R, RB_P = lokal((-452.5, -86.5), _bU)
husdel("ringvagen_bod", "", RB_R(-3.75, 3.75, -1.6, 1.6), RB_P(-3.75, 3.75, -1.6, 1.6),
       {"typ": "bod", "van": 1, "fh": 2.4, "vagg": "#93291f", "tak": "pulpet", "takfarg": "#7d7a75", "utanFonster": True},
       "Lång röd bod med låglutande plåttak mellan stugan och Västra Storgatan (efter foto).")

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
    # utkast 8 (efter foton)
    "H063": {"typ": "bod", "namn": "", "hojd": 1.7, "vagg": "#a3575c", "takfarg": "#8b474c", "tak": "platt", "utanFonster": True, "sakerhet": "säker",
             "not": "Mycket låg byggnad, troligen ett pumphus (efter foto). Bakom den går gång- och cykelvägen ner till tunneln under spåret."},
    "H005": {"vagg": "#cfcac0", "takfarg": "#4a4d50", "van": 1, "fh": 5.6, "tak": "platt", "sakerhet": "säker",
             "fasad": {"typ": "bank", "a": [-76.5, 10.4], "b": [-60.0, 14.0], "vag": [-68.0, 2.0]},
             "not": "Swedbank och Fastighetsbyrån: ljusgrå stenfasad, stora glaspartier och trappa längs fasaden (efter foto)."},
    "H013": {"vagg": "#cfcac0", "takfarg": "#4a4d50", "van": 1, "fh": 5.6, "tak": "platt", "sakerhet": "säker",
             "glastorn": {"x": -56.1, "z": 16.4, "r": 3.4, "h": 8.4, "mot": [-56.0, 2.0]},
             "not": "Biblioteket med runt glastorn vid entrén mot Västra Storgatan (efter foto)."},
    # utkast 9 (efter foton)
    "H039": {"vagg": "#6e3428", "takfarg": "#5a3a30", "van": 2, "fh": 3.2, "tak": "platt", "sakerhet": "säker",
             "band": [{"y0": -0.4, "y1": 0.95, "farg": "#ece9e2"}],
             "fasad": {"typ": "vard", "a": [-599.3, 344.5], "b": [-586.0, 328.3], "vag": [-582.0, 348.0]},
             "not": "Gnesta Vårdcentral (Nygatan 29): mörkt rödbrunt trä och vitt tegel. Entrén har skärmtak med tegeltak, VÅRDCENTRAL i vita bokstäver och vit logga på taket (efter foto)."},
    "H021": {"vagg": "#c6b796", "takfarg": "#3d4148", "van": 1, "fh": 6.5, "tak": "platt", "utanFonster": True, "sakerhet": "säker",
             "band": [{"y0": 5.3, "y1": 6.55, "farg": "#262b33"}],
             "fasad": {"typ": "elektron", "a": [-304.0, -17.5], "b": [-319.2, -20.6], "vag": [-312.0, -50.0]},
             "not": "Kulturhuset Elektron: ljus stenfasad, mörkt band upptill, skärmtak med runda lampor, skylt i krom och atomskulptur (efter foto)."},
    "H017": {"vagg": "#a0463a", "takfarg": "#5b5e60", "van": 2, "fh": 3.4, "tak": "platt", "sakerhet": "säker",
             "band": [{"y0": 6.8, "y1": 7.3, "farg": "#7d9a8b"}],
             "skyltar": [{"text": "GNESTA KOMMUN", "mot": [-322, -60], "hojd": 5.0, "hgt": 0.95, "bredd": 1.35, "stil": "kommun", "utanTak": True, "u": 13.5}],
             "not": "Kommunhuset i rött tegel med vita fönster, flaggstänger och gräsmatta mot Västra Storgatan (efter foto)."},
    # Tingshusgatans början (efter foton)
    "H092": {"vagg": "#e3cb8a", "takfarg": "#9a4b33", "tak": "sadel", "van": 2, "fh": 3.3, "sakerhet": "säker",
             "skyltar": [{"text": "Guldsmen´s", "mot": [12, 48], "hojd": 3.05, "bg": "#22282e", "fg": "#efe2bf", "hgt": 0.6, "bredd": 3.6, "utanTak": True, "u": 4.5},
                         {"text": "OPTIK · KONTAKTLINSER", "mot": [12, 48], "hojd": 3.05, "bg": "#22282e", "fg": "#ffffff", "hgt": 0.6, "bredd": 5.4, "utanTak": True, "u": -1.0}],
             "not": "Gult putsat hus i två våningar med butiker i bottenplan längs Tingshusgatan, bl.a. optikern Guldsmen´s. Snedparkering och låga träd framför (efter foto)."},
    "H189": {"vagg": "#e6cf8f", "takfarg": "#9a4b33", "tak": "sadel", "sakerhet": "säker", "not": "Gult hus med butiker i bottenplan, balkonger och takkupor; parkering framför (efter foto)."},
    "H026": {"vagg": "#8f2f22", "takfarg": "#7a3f2e", "van": 1, "fh": 3.3, "tak": "sadel", "takAxel": "kort", "sakerhet": "säker",
             "not": "Litet rött trähus vid foten av Tingshusbacken (efter foto)."},
}
ANDRINGAR["H078"] = {"vagg": "#e8dcae", "tak": "sadel", "takfarg": "#4b4e51", "van": 2, "fh": 3.2, "rekt": [321.3, 52.1, 17.8, 11.2, 0.034],
                     "volymer": [{"poly": [[329.4, 57.0], [337.3, 57.2], [337.0, 65.8], [329.4, 65.5]], "h": 5.6, "vagg": "#e8dcae"},
                                 {"poly": [[330.6, 47.4], [336.4, 47.6], [336.2, 56.4], [330.4, 56.2]], "h": 2.9, "vagg": "#f2f2ee"}],
                     "sakerhet": "foto", "not": "Ljusgul villa med mörkgrått plåttak och vita knutar, uppe på tomten bakom en stödmur med vitt staket mot Östra Storgatan; glasad veranda åt öster (efter foto)."}
ANDRINGAR["H022"] = {**BL_VAXTHUS, "fh": 3.8, "rekt": bl_rekt(0.0, 28.2, -34.0, 0.0), "vagg": "#d6a23f", "takfarg": "#9a3d27", "utanFonster": False,
                     "not": "Blomstergården: stora försäljningshallen/växthuset bakom butiken, ljust tak; butiken mot parkeringen, det gula huset och växthusen är egna delar (efter foton)."}
# Blomstergården: stora hallen och östra växthuset också gula med rostrött tak (rättning)
ANDRINGAR["H040"] = {"van": 1, "fh": 10.0, "vagg": "#3d62b5", "tak": "platt", "takfarg": "#3a3838", "rekt": fr_rekt(-16.0, 16.0, -9.0, 24.3), "utanFonster": True, "sakerhet": "foto",
                     "band": [{"y0": 0.0, "y1": 0.9, "farg": FR_TEGEL}, {"y0": 0.9, "y1": 2.5, "farg": "#22406f"}, {"y0": 2.5, "y1": 3.2, "farg": FR_TEGEL},
                              {"y0": 8.5, "y1": 9.55, "farg": "#e2e7ea"}, {"y0": 9.55, "y1": 10.0, "farg": "#c9cdd0"}],
                     "not": "Frejahallen: idrottshallen med blå korrugerad plåt, fönsterband nertill och ljust fönsterband högst upp, sockel i gult tegel (efter foto)."}
ANDRINGAR["H031"] = {"typ": "flerbostad", "van": 2, "fh": 3.5, "vagg": TH_VAGG, "tak": "mansard", "takfarg": TH_TAK, "kupor": 5, "lisener": "#f3f0e7",
                     "rekt": th_rekt(-11.5, 0.0, 0.0, 28.5), "skorstenar": [th_w(-5.75, 4.0), th_w(-5.75, 24.5)], "skorstenFarg": "#7d7570",
                     "fasad": {"a": th_w(0.0, 0.0), "b": th_w(0.0, 28.5), "vag": [41.5, 237.0]},
                     "band": [{"y0": 0.0, "y1": 0.7, "farg": "#8c8a86"}, {"y0": 6.75, "y1": 7.0, "farg": "#f3f0e7"}],
                     "volymer": [{"poly": [th_w(-11.4, 19.9), th_w(-14.9, 19.8), th_w(-16.7, 18.0), th_w(-17.4, 15.7), th_w(-16.9, 13.2), th_w(-15.9, 11.3), th_w(-14.0, 10.4), th_w(-11.4, 10.3)], "h": 6.4, "vagg": TH_VAGG}],
                     "sakerhet": "säker", "not": "Tingshuset: ljust ockragult putsat hus i två våningar med vita hörnlisener och gesims, brutet tak i mörk plåt med takkupor och skorstenar, mittparti med frontespis mot Tingshusgatan (efter foto)."}
# H471 snett över gatan från Tingshuset: vitt tegelhus i en våning med platt tak, mycket grönska mot gatan (efter foto)
ANDRINGAR["H471"] = {"typ": "villa", "van": 1, "fh": 3.0, "vagg": "#e9e5dc", "tak": "platt", "takfarg": "#3a3a38", "sakerhet": "foto",
                     "band": [{"y0": 0.0, "y1": 0.75, "farg": "#5a4032"}, {"y0": 2.8, "y1": 3.0, "farg": "#3d3a36"}],
                     "not": "Vitt tegelhus i en våning med platt tak och brun sockel; tät grönska och en stödmur mot Skolgatan (efter foto)."}
# H189, Torggatan 1 (efter foto från korsningen vid Tingshusgatan): ljusgult putsat hus, tre våningar, sadeltak med gavel mot öster,
# butiker i bottenplan med stora skyltfönster mot både gaveln och långsidan, balkonger på gaveln och ett halvrunt fönster i gavelspetsen
H189_R = [-57.05, 100.17, 85.28, 13.45, 2.9328]
def h189(u, v):
    c_, s_ = math.cos(H189_R[4]), math.sin(H189_R[4]); return [round(H189_R[0] + u * c_ - v * s_, 2), round(H189_R[1] + u * s_ + v * c_, 2)]
H189_OST = lambda s_: h189(-H189_R[2] / 2, H189_R[3] / 2 - s_)        # gaveln mot öster, s från nordöstra hörnet söderut
H189_NORR = lambda s_: h189(-H189_R[2] / 2 + s_, H189_R[3] / 2)       # långsidan mot Torggatan, s från nordöstra hörnet västerut
MOT_O = [60.0, 76.0]; MOT_N = [-50.0, 20.0]
def butik(vid, mot, bredd, hgt=2.4, hojd=1.55): return {"text": "", "stil": "butik", "vid": vid, "mot": mot, "hojd": hojd, "bg": "#2a2c2e", "hgt": hgt, "bredd": bredd, "utanTak": True}
_sk = [butik(H189_OST(3.0), MOT_O, 4.8), {"text": "", "vid": H189_OST(6.9), "mot": MOT_O, "hojd": 1.3, "bg": "#c4bba6", "hgt": 2.4, "bredd": 1.7, "utanTak": True},
       butik(H189_OST(10.6), MOT_O, 3.0),
       {"text": "Hem ljuva hem", "vid": H189_OST(3.0), "mot": MOT_O, "hojd": 3.75, "bg": "#191919", "fg": "#d8b65c", "hgt": 0.62, "bredd": 3.8, "utanTak": True, "kursiv": True},
       {"text": "Hem ljuva hem", "vid": H189_NORR(3.6), "mot": MOT_N, "hojd": 3.7, "bg": "#191919", "fg": "#d8b65c", "hgt": 0.5, "bredd": 2.8, "utanTak": True, "kursiv": True},
       {"text": "Humbles", "vid": H189_NORR(48.0), "mot": MOT_N, "hojd": 3.7, "bg": "#2f2a26", "fg": "#f3eadb", "hgt": 0.55, "bredd": 3.0, "utanTak": True}]
for s_, w_ in ((2.0, 2.8), (5.2, 2.8), (9.5, 2.4), (12.6, 2.4), (17.5, 2.6), (20.6, 2.6), (26.0, 2.6), (29.2, 2.6), (34.5, 2.6), (37.7, 2.6), (43.0, 2.6),
               (46.4, 2.6), (49.6, 2.6), (53.8, 2.6), (57.0, 2.6), (62.0, 2.4), (67.0, 2.4), (72.0, 2.4), (80.4, 4.0)):
    _sk.append(butik(H189_NORR(s_), MOT_N, w_))
for s_ in (14.8, 23.3, 31.9, 40.4, 51.6, 59.2, 64.0, 69.0, 74.0): _sk.append(butik(H189_NORR(s_), MOT_N, 1.15, 2.3, 1.3))   # butiksdörrar
_sk.append({"text": "", "vid": H189_NORR(76.8), "mot": MOT_N, "hojd": 1.2, "bg": "#4a3426", "hgt": 2.3, "bredd": 1.3, "utanTak": True})   # trapphusentré
# butikerna i västra delen, räknat från västra hörnet: Moas Naglar, Lilla Hudstudion, Redovisningstjänst, Lena Fötter, Station Livs (efter foto)
for txt_, s_, bg_, fg_, br_ in (("Lilla Hudstudion", 72.0, "#f3ece6", "#8a4f6a", 2.6), ("Redovisningstjänst", 67.0, "#2c3e50", "#ffffff", 2.8),
                                 ("Lena Fötter", 62.0, "#ffffff", "#2a6f8f", 2.4), ("Station Livs", 55.4, "#c8202f", "#ffffff", 3.2)):
    _sk.append({"text": txt_, "vid": H189_NORR(s_), "mot": MOT_N, "hojd": 3.0, "bg": bg_, "fg": fg_, "hgt": 0.38 if br_ < 3 else 0.46, "bredd": br_, "utanTak": True})
_sk.append({"text": "Moa's Naglar", "vid": H189_NORR(81.0), "mot": MOT_N, "hojd": 2.05, "bg": "transparent", "fg": "#ffffff", "hgt": 0.5, "bredd": 2.2, "utanTak": True, "kursiv": True})
ANDRINGAR["H189"] = {"typ": "centrum", "van": 3, "fh": 3.1, "vagg": "#ecdcae", "tak": "sadel", "takfarg": "#8a817a", "sakerhet": "foto",
                     "fasad": {"a": H189_OST(0.0), "b": h189(H189_R[2] / 2, H189_R[3] / 2), "vag": [-58.0, 86.0]},
                     "band": [{"y0": -2.0, "y1": 3.15, "farg": "#cac6bd"}, {"y0": 3.15, "y1": 3.3, "farg": "#ddd6c6"}],
                     "skyltar": _sk,
                     "markiser": [{"vid": H189_OST(3.0), "mot": MOT_O, "hojd": 3.3, "bredd": 4.8, "djup": 1.1, "farg": ["#262626", "#efeee8"]}],
                     "balkonger": [{"vid": H189_OST(8.6), "mot": MOT_O, "y": 3.15, "b": 3.6, "d": 1.3, "racke": True},
                                   {"vid": H189_OST(8.6), "mot": MOT_O, "y": 6.25, "b": 3.6, "d": 1.3, "blommor": True, "markis": "#2f6b55"}],
                     "rundfonster": [{"mot": MOT_O, "r": 0.8, "ovanTakfot": 1.3}], "sliten": True,
                     "burspråk": [{"vid": h189(H189_R[2] / 2, H189_R[3] / 2 - 2.2), "mot": [-160.0, 112.0], "y0": 3.3, "y1": 9.25, "b": 2.6, "d": 0.9}],
                     "not": "Torggatan 1: ljusgult putsat hus i tre våningar med sadeltak och halvrunt gavelfönster, butiker i bottenplan med stora skyltfönster mot både gaveln och Torggatan (Hem ljuva hem i hörnet, Humbles längre bort), balkonger på gaveln (efter foto)."}
# H156: utomhusscen med tak som skjuter ut över scenkanten, scenen vänd inåt mot biblioteket, baksidan av glasrutor (efter foto)
ANDRINGAR["H156"] = {"namn": "Utomhusscen", "typ": "scen", "van": 1, "fh": 3.0, "vagg": "#b7b2a8", "tak": "valm", "takfarg": "#8f979c", "sakerhet": "foto",
                     "scen": {"mot": [-70.0, 50.0]},
                     "not": "Utomhusscen på torget: betongscen med tunna stolpar och utskjutande plåttak, vänd mot biblioteket; baksidan mot Torggatan är glasrutor i vita rutnät (efter foto)."}
# H025: Apoteket – äldre, lite nergånget fyravåningshus i sandfärgad puts med fönsterband högst upp under en brun takfotslist,
# butiker med gröna markiser mot gågatan/torget: Apoteket, optikern Synia m.fl. (efter foto)
_AP_S = (-103.9, 89.3); _AP_U = (0.2396, -0.9709); _AP_N = (0.9709, 0.2396)
AP = lambda s_: [round(_AP_S[0] + _AP_U[0] * s_, 2), round(_AP_S[1] + _AP_U[1] * s_, 2)]
MOT_AP = [-80.0, 66.0]
_aps = [{"text": "", "vid": AP(4.5), "mot": MOT_AP, "hojd": 1.25, "bg": "#4a3426", "hgt": 2.3, "bredd": 1.6, "utanTak": True},
        {"text": "APOTEK", "vid": AP(12.0), "mot": MOT_AP, "hojd": 4.15, "bg": "#d2bd93", "fg": "#d8692a", "hgt": 0.75, "bredd": 3.4, "utanTak": True},
        {"text": "APOTEK", "vid": AP(0.9), "mot": MOT_AP, "hojd": 4.4, "bg": "#d8692a", "fg": "#ffffff", "hgt": 0.85, "bredd": 0.95, "utanTak": True},
        {"text": "Synia OPTIKER", "vid": AP(21.0), "mot": MOT_AP, "hojd": 4.05, "bg": "#b8283a", "fg": "#ffffff", "hgt": 0.48, "bredd": 2.6, "utanTak": True}]
_apm = []
for s_ in (8.0, 11.6, 15.2, 19.4, 23.0, 27.6, 31.2, 36.0, 39.6, 44.4, 48.0):
    _aps.append(butik(AP(s_), MOT_AP, 3.0, 2.3, 1.45))
    _apm.append({"vid": AP(s_), "mot": MOT_AP, "hojd": 3.15, "bredd": 3.3, "djup": 1.0, "farg": ["#2e7d4f", "#29704a"]})
# pizzeria Dragon till höger om Synia: bred vit skylt PIZZA · DELI · PASTA, flaggor, uteservering bakom rödbrunt staket med spaljé (efter foto)
_aps.append({"text": "", "stil": "dragon", "vid": AP(32.4), "mot": MOT_AP, "hojd": 4.15, "bg": "#f4f2ec", "hgt": 1.0, "bredd": 6.8, "utanTak": True})
_aps.append({"text": "Dagens Lunch", "vid": AP(26.0), "mot": MOT_AP, "hojd": 1.6, "bg": "#ffffff", "fg": "#b3202c", "hgt": 0.75, "bredd": 1.5, "utanTak": True})
_N = lambda s_, o_: [round(AP(s_)[0] + _AP_N[0] * o_, 2), round(AP(s_)[1] + _AP_N[1] * o_, 2)]
DRAGON_SERVERING = {"delar": [[_N(25.6, 0.2), _N(25.6, 4.2), _N(31.6, 4.2)], [_N(33.0, 4.2), _N(40.4, 4.2), _N(40.4, 0.2)]], "farg": "#8a3a2a",
                    "bord": [_N(s_, o_) for s_ in (27.4, 29.8, 34.6, 37.0, 39.0) for o_ in (1.6, 3.1)], "rot": round(math.atan2(_AP_U[0], _AP_U[1]), 3)}
ANDRINGAR["H025"] = {"typ": "centrum", "van": 4, "fh": 3.0, "vagg": "#d2bd93", "tak": "platt", "takfarg": "#4a4744", "sakerhet": "foto", "sliten": True,
                     "band": [{"y0": -2.0, "y1": 3.3, "farg": "#c4ae86"}, {"y0": 9.45, "y1": 9.6, "farg": "#e6dcc6"}, {"y0": 9.6, "y1": 11.35, "farg": "#34414b"},
                              {"y0": 11.35, "y1": 12.0, "farg": "#7a4a32"}],
                     "skyltar": _aps, "markiser": _apm,
                     "fasadflaggor": [{"vid": AP(s_), "mot": MOT_AP, "hojd": 3.0, "typ": t_} for s_, t_ in ((26.6, "rod"), (29.2, "se"), (34.4, "it"), (37.0, "rod"), (39.8, "vit"))],
                     "not": "Apoteket: äldre och lite nergånget fyravåningshus i sandfärgad puts med fönsterband högst upp under en brun takfotslist; butiker med gröna markiser mot gågatan – Apoteket och optikern Synia (efter foto)."}
# villan H061 vid Kvarngatan (efter foto): gul funkisvilla i två våningar med valmat tegeltak, rundat hörnparti i en våning med
# balkong ovanpå, två skorstenar; häck mot trottoaren
H061_W, H061_R, H061_P = lokal((-520.0, -122.3), (-0.8197, -0.5728))
ANDRINGAR["H061"] = {"typ": "villa", "van": 2, "fh": 3.0, "vagg": "#ecd27e", "tak": "valm", "takfarg": "#b0563a", "sakerhet": "foto",
                     "rekt": H061_R(0.0, 12.9, 0.0, 10.5), "skorstenar": [H061_W(4.0, 4.5), H061_W(9.5, 6.0)], "skorstenFarg": "#6e5a4f",
                     "fasad": {"a": [-513.9, -130.9], "b": [-520.0, -122.3], "vag": [-505.0, -137.0]},
                     "volymer": [{"poly": [[-519.3, -134.5], [-517.8, -135.9], [-515.2, -135.7], [-513.7, -135.0], [-513.3, -133.2], [-513.9, -130.9], [-517.0, -131.5]], "h": 3.0}],
                     "balkonger": [{"vid": [-516.0, -133.5], "mot": [-500.0, -140.0], "y": 3.0, "b": 3.6, "d": 1.3, "farg": "#f2efe6", "racke": True}],
                     "not": "Gul funkisvilla i två våningar med valmat tegeltak, rundat hörnparti med balkong ovanpå och två skorstenar; häck mot gatan (efter foto)."}
# garaget H056: dubbelgarage med gul nederdel, röd panelgavel mot gatan med vitt fönster, två par röda portar, brant sadeltak
ANDRINGAR["H056"] = {"typ": "bod", "van": 1, "fh": 3.0, "vagg": "#9e2f24", "tak": "sadel", "taklutning": 1.05, "takfarg": "#3e3a37", "utanFonster": True, "sakerhet": "foto",
                     "band": [{"y0": -2.0, "y1": 2.85, "farg": "#e6cf96"}],
                     "fasad": {"a": [-540.7, -151.9], "b": [-534.0, -148.2], "vag": [-536.0, -162.0]},
                     "skyltar": [{"text": "", "stil": "garageport", "vid": [-539.6, -151.0], "mot": [-536.0, -170.0], "hojd": 1.15, "hgt": 2.2, "bredd": 2.4, "utanTak": True, "bg": "#9e2f24"},
                                 {"text": "", "stil": "garageport", "vid": [-535.4, -148.8], "mot": [-536.0, -170.0], "hojd": 1.15, "hgt": 2.2, "bredd": 2.4, "utanTak": True, "bg": "#9e2f24"},
                                 {"text": "", "stil": "fonster", "vid": [-537.4, -150.0], "mot": [-536.0, -170.0], "hojd": 4.3, "hgt": 1.1, "bredd": 1.2, "utanTak": True, "bg": "#9e2f24"}],
                     "not": "Dubbelgarage vid Västra Storgatan: gul nederdel, röd panelgavel mot gatan med vitt fönster, två par röda portar, inbyggt i slänten (efter foto)."}
ANDRINGAR["H069"] = {"typ": "villa", "van": 1, "fh": 3.0, "vagg": "#8e2c22", "tak": "sadel", "taklutning": 0.9, "takfarg": "#a64a33", "lisener": "#f2efe6", "sakerhet": "foto",
                     "skorstenar": [H069_W(1.5, 0.0)], "skorstenFarg": "#f0ede4",
                     "skyltar": [{"text": "", "stil": "fonster", "mot": H069_W(40.0, 0.0), "hojd": 4.1, "hgt": 0.95, "bredd": 1.3, "utanTak": True, "bg": "#8e2c22"},
                                 {"text": "", "stil": "fonster", "mot": H069_W(-40.0, 0.0), "hojd": 4.1, "hgt": 0.95, "bredd": 1.3, "utanTak": True, "bg": "#8e2c22"}],
                     "not": "Röd stuga i en våning med vindsvåning, vita knutar och fönster, rött tegeltak och vit farstukvist mot Ringvägen; mycket grönska runt om (efter foto)."}
_e099 = [-449.5, -79.8]
ANDRINGAR["H099"] = {"typ": "villa", "van": 1, "fh": 3.6, "vagg": "#cf9440", "tak": "mansard", "brytHojd": 3.0, "takfarg": "#a64a33", "kupor": 2, "lisener": "#f2efe6", "sakerhet": "foto",
                     "panel": True, "skorstenar": [[-477.6, -67.8]], "skorstenFarg": "#a24b36",
                     "skyltar": [{"text": "", "stil": "fonster", "mot": _e099, "hojd": 4.75, "hgt": 1.25, "bredd": 1.0, "utanTak": True, "bg": "#cf9440", "u": 2.1},
                                 {"text": "", "stil": "fonster", "mot": _e099, "hojd": 4.75, "hgt": 1.25, "bredd": 1.0, "utanTak": True, "bg": "#cf9440", "u": -2.1},
                                 {"text": "", "stil": "fonster", "mot": _e099, "hojd": 4.65, "hgt": 1.9, "bredd": 0.9, "utanTak": True, "bg": "#cf9440"},
                                 {"text": "", "stil": "fonster", "mot": _e099, "hojd": 7.05, "hgt": 0.6, "bredd": 0.6, "utanTak": True, "bg": "#cf9440"}],
                     "balkonger": [{"mot": _e099, "y": 3.6, "b": 2.4, "d": 1.0, "farg": "#2a2a2a", "racke": True}],
                     "not": "Ockragult trähus med stående panel, vita knutar och fönster, brutet tegeltak med takkupor och balkong på gaveln mot öster (efter foto)."}
ANDRINGAR["H089"] = {"vagg": "#93291f", "tak": "pulpet", "takfarg": "#7d7a75", "utanFonster": True, "sakerhet": "foto", "not": "Liten röd bod med plåttak bakom stugan (efter foto)."}
ANDRINGAR["H217"] = {**T16_OCKRA, "rekt": T16_R(0.0, 26.3, 0.0, 12.6), "sakerhet": "foto",
                     "not": "Torggatan 16: östra flygeln mot brandstationen, ockragul puts i tre våningar med röda fönsterbågar (efter foto)."}
ANDRINGAR["H183"] = {"typ": "flerbostad", "van": 3, "fh": 3.0, "vagg": "#a9493d", "tak": "valm", "takfarg": "#4a4744", "karmFarg": "#e3b23c", "sakerhet": "foto",
                     "rekt": H183_NR(-5.0, 25.0, -1.0, 13.0),
                     "balkonger": [{"vid": H183_NW(u_, -1.0), "mot": [-352.0, -20.0], "y": y_, "b": 2.6, "d": 1.2, "farg": "#a9cdb3"} for u_ in (4.5, 11.5, 18.5) for y_ in (0.35, 3.35, 6.35)],
                     "not": "Torggatan 16: röd del mot Thulegatan och Elektron med valmat tak, gula fönsterbågar och ljusgröna balkonger (efter foto)."}
# H059: gult trähus vid starten (efter foto)
_n059 = (-(-math.sin(-2.8308)), -math.cos(-2.8308))   # utåt mot gatan (söder)
ANDRINGAR["H059"] = {"van": 2, "fh": 3.0, "vagg": "#e4c574", "tak": "sadel", "taklutning": 0.3, "takfarg": "#55524e", "sakerhet": "foto", "panel": True,
                     "band": [{"y0": -2.0, "y1": 0.35, "farg": "#5e4636"}],
                     "skorstenar": [H059_W(u_, 0.0) for u_ in (-18.0, -9.0, 0.0, 9.0, 18.0)], "skorstenFarg": "#a24b36",
                     "not": "Gult trähus med stående panel i två våningar, brun sockel, låglutande sadeltak med skorstenar i rött tegel och grått spjälstaket mot trottoaren (efter foto)."}
ANDRINGAR["H1689"] = {"vagg": "#d6a23f", "takfarg": "#9a3d27", "utanFonster": False}
ANDRINGAR["H058"] = {"vagg": "#cfa75c", "tak": "valm", "takfarg": "#74382a", "van": 2, "fh": 3.1, "sakerhet": "foto",
                     "skorstenar": [[-382.2, -45.75], [-375.3, -44.55]],
                     "not": "Ockragult putsat hus i två våningar med valmat tegeltak, vita fönster med mörkbruna luckor och två ljusa skorstenar; lummig trädgård bakom grått brädstaket mot trottoaren (efter foto)."}
# Coop (H012): ljusgrå fasad med grön linje, entré i det avfasade hörnet mot korsningen, grön coop-skylt (efter foto)
ANDRINGAR["H012"] = {"vagg": "#c9c7c0", "fh": 4.2, "sakerhet": "foto", "band": [{"y0": 3.0, "y1": 3.1, "farg": "#2f8a3e"}], "tegelSidor": [[-1.0, 0.0], [0.0, 1.0]],
                     "skyltar": [{"text": "coop", "mot": [6.0, 22.0], "hojd": 3.55, "bg": "#c9c7c0", "fg": "#1f9a4a", "hgt": 1.25, "bredd": 3.8, "utanTak": True},
                                 {"text": "coop", "mot": [-36.0, 80.0], "hojd": 3.45, "bg": "transparent", "fg": "#1f9a4a", "hgt": 1.6, "bredd": 3.6, "utanTak": True},
                                 {"text": "coop  Öppet alla dagar 7–22", "mot": [-30.0, 0.0], "hojd": 3.55, "bg": "#c9c7c0", "fg": "#1f9a4a", "hgt": 0.95, "bredd": 9.5, "utanTak": True, "u": 8.0}],
                     "not": "Coop Gnesta: ljusgrå butiksbyggnad med grön linje och coop-skyltar, entré med glasdörrar och trappsteg i hörnet mot korsningen (efter foto)."}
ANDRINGAR["H139"] = {"vagg": "#e3b54c", "van": 2, "fh": 3.0, "takfarg": "#9c3b2b", "sakerhet": "foto", "not": "Gult hus i två våningar med rött tak vid Ringvägen, bredvid Blomstergården (efter foto)."}
ANDRINGAR["H094"] = {"vagg": "#e4b94c", "takfarg": "#9c3b2b", "tak": "sadel", "sakerhet": "foto", "not": "Gult trähus med rött tak bredvid Blomstergården (efter foto)."}
ANDRINGAR["H1459"] = {**KR_FARG, "rekt": kr_rekt(0, 11.0, 0, 34.7),
                      "not": "Förskolan Kristallen: enplanshus i mörkgrå stående panel, vita fönsterfoder och knutar, rött tegeltak (efter foto)."}
for h in hus:
    if h["id"] in ANDRINGAR: h.update(ANDRINGAR[h["id"]])
# Granbackavägen (efter foto från korsningen vid Nygatan): husen är som högst två våningar – radhus/flerbostadshus
# i rött tegel med vita balkonger, de lägre husen ljust beige med bruna tegeltak.
_gb = [g["pts"] for g in gator if g.get("namn") == "Granbackavägen"]
def _d_gb(x, z):
    best = 1e9
    for pts in _gb:
        for a, b in zip(pts, pts[1:]):
            dx, dz = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dz * dz or 1e-9; t = max(0, min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / L2))
            best = min(best, math.hypot(x - a[0] - dx * t, z - a[1] - dz * t))
    return best
GB_TEGEL = ["#9a4635", "#a24f3b", "#8f4231"]; GB_LJUS = ["#e4d8bd", "#ddcba4", "#ece3cf"]; GB_TAK = ["#7b4434", "#8a4a35", "#6e3d30"]
_n_gb = 0
for h in hus:
    if h["id"] in ANDRINGAR or h.get("namn") or h["typ"] in ("bod", "trappa", "tak") or h["x"] > -958 or _d_gb(h["x"], h["z"]) > 45: continue
    r = h01(h["osm"] + "gb")
    h["van"] = min(h["van"], 2)
    if h["typ"] == "flerbostad":
        h["vagg"] = GB_TEGEL[int(r * 3) % 3] if r < 0.72 else GB_LJUS[int(r * 7) % 3]; h["takfarg"] = GB_TAK[int(r * 11) % 3]
        if h["tak"] == "platt" and h.get("rekt"): h["tak"] = "sadel"
        h["band"] = [{"y0": 2.75, "y1": 2.95, "farg": "#efece4"}] if h["vagg"] in GB_TEGEL else h.get("band", [])
    else:
        h["vagg"] = GB_LJUS[int(r * 5) % 3] if r < 0.6 else h["vagg"]; h["takfarg"] = GB_TAK[int(r * 13) % 3]
    h["sakerhet"] = "foto"; h["not"] = "Granbackavägen: som högst två våningar, rött tegel eller ljust beige (efter foto)."
    _n_gb += 1
print('Granbackavägen: justerade hus', _n_gb)
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
# startpunkten ligger kvar vid den ursprungliga starten på Västra Storgatan, även när sträckan förlängs västerut
_ss = rutt_data[0]["s_near"](-598, -163)
sx, sz = point_at(_ss + 22); sx2, sz2 = point_at(_ss + 26)
START = {"x": round(sx, 1), "z": round(sz, 1), "h": round(math.atan2(sx2 - sx, sz2 - sz), 4)}

# ------------------------------------------------------------------ höjder: topografisk karta (utkast 11) + justeringar längs vissa gator
TOPO_FIL = os.path.join(HAR, 'data', 'topo_hojd.json')
TOPO = json.load(open(TOPO_FIL, encoding='utf-8')) if os.path.exists(TOPO_FIL) else None
# Järnvägen: kartans höjder är ytmodell (träd och hus ingår) och utsmetade, så banvallen skulle annars få puckel
# öster om stationen. Banans höjdprofil görs jämn (högst 0,8 % lutning, aldrig över omgivningens lägsta nivå)
# och marken närmast spåret följer den – skärning där kartan är högre, bank där den är lägre.
if TOPO:
    _g = TOPO; _G = np.frombuffer(base64.b64decode(_g["data"]), dtype='<i2').astype(float).reshape(_g["nz"], _g["nx"]) / 10
    _xs = _g["x0"] + np.arange(_g["nx"]) * _g["steg"]; _zs = _g["z0"] + np.arange(_g["nz"]) * _g["steg"]
    def _topo_at(x, z):
        fx = (x - _g["x0"]) / _g["steg"]; fz = (z - _g["z0"]) / _g["steg"]
        if fx < 0 or fz < 0 or fx > _g["nx"] - 1.001 or fz > _g["nz"] - 1.001: return None
        i, j = int(fx), int(fz); tx, tz = fx - i, fz - j
        return (_G[j, i] * (1 - tx) * (1 - tz) + _G[j, i + 1] * tx * (1 - tz) + _G[j + 1, i] * (1 - tx) * tz + _G[j + 1, i + 1] * tx * tz)
    _segs = []; _prov = []
    for sp_ in spar:
        if sp_["bro"]: continue
        for a, b in zip(sp_["pts"], sp_["pts"][1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 0.1: continue
            _segs.append((a, b)); n_ = max(1, int(L / 5))
            for k in range(n_ + 1):
                x_, z_ = a[0] + (b[0] - a[0]) * k / n_, a[1] + (b[1] - a[1]) * k / n_; h_ = _topo_at(x_, z_)
                if h_ is not None: _prov.append((x_, h_))
    if _prov:
        BIN = 20.0; bx0 = min(p_[0] for p_ in _prov); nb = int((max(p_[0] for p_ in _prov) - bx0) / BIN) + 1
        lo = np.full(nb, np.inf)
        for x_, h_ in _prov: k = int((x_ - bx0) / BIN); lo[k] = min(lo[k], h_)
        ok = np.isfinite(lo); bxs = bx0 + (np.arange(nb) + 0.5) * BIN; lo = np.interp(bxs, bxs[ok], lo[ok])
        sm = np.array([lo[max(0, k - 6):k + 7].mean() for k in range(nb)])                      # utjämnad över ±120 m
        T = np.array([min(sm[j] + 0.008 * abs(bxs[k] - bxs[j]) for j in range(nb)) for k in range(nb)])  # högst 0,8 % lutning
        T = np.maximum(T, 13.0)
        # där en väg går under banan (skärning) måste banan ligga så högt att vägen under bron hamnar över sjönivån
        for sk in skarningar:
            T = np.maximum(T, 12.2 + 1.5 + sk["djup"] - 0.012 * np.abs(bxs - sk["x"]))
        Dmin = np.full(_G.shape, 1e9); X, Z = np.meshgrid(_xs, _zs)
        for a, b in _segs:
            if max(a[0], b[0]) < _xs[0] - 50 or min(a[0], b[0]) > _xs[-1] + 50 or max(a[1], b[1]) < _zs[0] - 50 or min(a[1], b[1]) > _zs[-1] + 50: continue
            dx, dz = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dz * dz
            t_ = np.clip(((X - a[0]) * dx + (Z - a[1]) * dz) / L2, 0, 1); Dmin = np.minimum(Dmin, np.hypot(X - a[0] - dx * t_, Z - a[1] - dz * t_))
        w_ = np.clip((Dmin - 8) / 16, 0, 1); w_ = 1 - w_ * w_ * (3 - 2 * w_)   # banvall ±8 m, slänt ut till 24 m
        Tg = np.interp(X, bxs, T)
        _G2 = _G + (Tg - _G) * w_
        print('järnväg: banprofil %.1f–%.1f m, största ändring av marken %.1f m' % (T.min(), T.max(), np.abs(_G2 - _G).max()))
        TOPO = dict(TOPO, data=base64.b64encode(np.round(_G2 * 10).astype('<i2').tobytes()).decode())
def _poly_s(chain):
    pts = [P(n) for n in chain]; c = [0.0]
    for a, b in zip(pts, pts[1:]): c.append(c[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    def at(s):
        for i in range(len(pts) - 1):
            if c[i + 1] >= s: t = (s - c[i]) / ((c[i + 1] - c[i]) or 1); return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
        return pts[-1]
    return at, c[-1]
_sm = lambda t: max(0.0, min(1.0, t)) ** 2 * (3 - 2 * max(0.0, min(1.0, t)))
hojdankare = []
# Nygatans början ligger norr om topokartans överkant. I verkligheten är backen upp från Västra Storgatan brant
# (användarens iakttagelse), så de första ~100 m får en egen profil som sedan tonar över i kartans höjder.
_at, _L = _poly_s(ways['41556699'][0])
# (utkast 13: brantare – ca 15 % de första 50 m, sedan krön vid ~100 m och planare mot Granbackavägen)
for s_, T_ in ((0, 19.0), (10, 20.5), (20, 22.1), (30, 23.7), (40, 25.3), (50, 26.8), (60, 27.9), (70, 28.7), (80, 29.2), (95, 29.5), (110, 29.6),
               (125, 29.6), (140, 29.5), (160, None), (180, None)):
    x_, z_ = _at(s_); hojdankare.append([round(x_, 1), round(z_, 1), T_, 13, 1.0])
# Västra Storgatan kring korsningen: jämn dalbotten
_at, _L = _poly_s(ways['628057219'][0])
for s_, T_ in ((0, 20.2), (25, 19.9), (50, 19.6), (75, 19.3), (100, 19.1), (115, 19.0), (130, 19.1), (150, 19.4), (175, 19.7), (200, 20.0), (250, None)):
    x_, z_ = _at(s_); hojdankare.append([round(x_, 1), round(z_, 1), T_, 26, 1.0])
# stenlagd trottoar längs H189:s långsida mot Torggatan och framför gaveln (efter foto)
_O = lambda u, v: [-57.05 + u * -0.97828 - v * 0.20728, 100.17 + u * 0.20728 + v * -0.97828]
add_yta('torg', [_O(-42.64, 6.7), _O(42.64, 6.7), _O(42.64, 9.4), _O(-45.6, 9.4), _O(-45.6, -6.7), _O(-42.64, -6.7)])
# uppfart framför garaget H056 och gårdsplan mellan Torggatan 16:s röda del och det blå tornhuset (efter foton)
ytor.append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": [[-541.2, -152.4], [-533.5, -148.1], [-530.4, -153.5], [-538.6, -158.6]]})
ytor.append({"typ": "torg", "namn": "", "poly": [[-336.8, 24.2], [-326.5, 22.6], [-322.4, 34.0], [-323.2, 42.0], [-336.4, 40.0]]})
gator.append({"id": "G_T16", "osm": "egen_torggatan16", "namn": "", "typ": "cycleway", "pts": [[-368.4, 13.8], [-362.0, 13.4], [-350.0, 14.2], [-342.0, 15.6], [-336.0, 18.4], [-331.5, 23.5], [-329.5, 28.5]],
              "bredd": 2.6, "trottoar": 0.0, "bro": False, "tunnel": False, "yta": "asphalt", "bil": False})
# Coops parkeringar: färre bilar (rättning: 60 % bort)
for y in ytor:
    if y["typ"] == "parkering" and y.get("rekt") and abs(y["rekt"][0] + 41.3) < 0.5 and abs(y["rekt"][1] - 53.85) < 0.5: y["fyllnad"] = 0.24
# parkering med bilar vinkelrätt mot H189:s gavel (efter foto)
_pc = [-9.95, 90.19]; _U = (-0.97828, 0.20728); _V = (-0.20728, -0.97828)
add_yta('parkering', [[_pc[0] + a_ * 2.5 * _U[0] + b_ * 6.2 * _V[0], _pc[1] + a_ * 2.5 * _U[1] + b_ * 6.2 * _V[1]] for a_, b_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
# Torggatan från H189 till Thulegatan: i stort sett plan (efter foto)
TG_PROFIL = [(-100, 16.0), (-140, 15.5), (-185, 15.0), (-240, 14.9), (-330, 15.1), (-390, 15.5)]
for g in gator:
    if g["osm"] != '32552347': continue
    for a, b in zip(g["pts"], g["pts"][1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n_ = max(1, int(L / 8))
        for k in range(n_):
            x_, z_ = a[0] + (b[0] - a[0]) * k / n_, a[1] + (b[1] - a[1]) * k / n_
            if not (-392 <= x_ <= -104): continue
            hojdankare.append([round(x_, 1), round(z_, 1), round(float(np.interp(-x_, [-q[0] for q in TG_PROFIL], [q[1] for q in TG_PROFIL])), 2), 15, 1.0])
# Östra Storgatan öster om stationen ligger på sluttningen ovanför järnvägen (Bryggargränd går på bro över spåren
# direkt från gatan), men kartans ytmodell lägger den för högt (hus och träd i sluttningen). Måttlig profil: ~22 m som högst.
# (utkast 13: plan förbi stationen och Stora Hotellet enligt foto, sedan en svag backe upp mot Bryggargränd)
OS_PROFIL = [(7, 15.6), (50, 15.6), (95, 15.7), (130, 16.6), (170, 18.3), (220, 20.3), (260, 21.2), (300, 21.3), (360, 20.0), (410, 18.6), (450, 17.5), (480, 16.4)]
for g in gator:
    if g["namn"] != "Östra Storgatan": continue
    for a, b in zip(g["pts"], g["pts"][1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n_ = max(1, int(L / 8))
        for k in range(n_):
            x_, z_ = a[0] + (b[0] - a[0]) * k / n_, a[1] + (b[1] - a[1]) * k / n_
            if not (7 <= x_ <= 520 and z_ < 160): continue
            T_ = None if x_ > 480 else round(float(np.interp(x_, [q[0] for q in OS_PROFIL], [q[1] for q in OS_PROFIL])), 2)
            hojdankare.append([round(x_, 1), round(z_, 1), T_, 15, 1.0])
# Plana ytor i centrum (efter foton). Kartans ytmodell lägger kullar här av husen och träden.
# - Stora Torget med parken och fontänen, gågatan Stora Torget och Tingshusgatans nedre del
# - stationsplanen med bussterminalen norr om Östra Storgatan, i nivå med gatan och svagt fall mot perrongerna
# Runt ytorna en 30 m bred övergångszon där höjden tonas mot kartans (så att det inte blir en vägg).
TORG_PLAN = [(0, 22), (84, 20), (92, 30), (60, 62), (40, 76), (22, 85), (0, 85)]
STN_PLAN = [(-55, -22), (140, -14), (150, 14), (84, 17), (7, 15), (-55, 8)]
# - Torggatan med H189 och parkeringen framför: gatan i samma nivå som korsningen vid Tingshusgatan (efter foto, utkast 18)
TORGGATAN_PLAN = [(2, 64), (-16, 66), (-100, 82), (-104, 120), (-12, 104), (2, 101)]
PLANA = [(TORG_PLAN, lambda x, z: 15.7 + 1.3 * max(0.0, min(1.0, (z - 22) / 62))), (STN_PLAN, lambda x, z: 15.5 - 0.02 * (16 - max(-22, min(16, z)))),
         (TORGGATAN_PLAN, lambda x, z: 16.75 + 0.0075 * max(-104.0, min(0.0, x)))]
_Gt = np.frombuffer(base64.b64decode(TOPO["data"]), dtype='<i2').astype(float).reshape(TOPO["nz"], TOPO["nx"]) / 10 if TOPO else None
def _topo_h(x, z):
    fx = (x - TOPO["x0"]) / TOPO["steg"]; fz = (z - TOPO["z0"]) / TOPO["steg"]; i, j = int(fx), int(fz); tx, tz = fx - i, fz - j
    return _Gt[j, i] * (1 - tx) * (1 - tz) + _Gt[j, i + 1] * tx * (1 - tz) + _Gt[j + 1, i] * (1 - tx) * tz + _Gt[j + 1, i + 1] * tx * tz
def _narmast_kant(poly, x, z):
    best = (1e9, None)
    for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
        dx, dz = bx - ax, bz - az; L2 = dx * dx + dz * dz; t = max(0, min(1, ((x - ax) * dx + (z - az) * dz) / L2))
        px, pz = ax + dx * t, az + dz * t; d = math.hypot(x - px, z - pz)
        if d < best[0]: best = (d, (px, pz))
    return best
_paths = [Path(pl) for pl, _ in PLANA]; RING = 30.0
for zz in range(-60, 151, 6):
    for xx in range(-138, 190, 6):
        inne = [k for k, pa in enumerate(_paths) if pa.contains_point((xx, zz))]
        if inne:
            k = inne[0]; hojdankare.append([xx, zz, round(PLANA[k][1](xx, zz), 2), 8, 1.0]); continue
        if _Gt is None: continue
        d, kp, kk = min((_narmast_kant(pl, xx, zz) + (k,) for k, (pl, _) in enumerate(PLANA)), key=lambda r: r[0])
        if d >= RING: continue
        Te = PLANA[kk][1](*kp); t = d / RING; t = t * t * (3 - 2 * t)
        hojdankare.append([xx, zz, round(Te + (_topo_h(xx, zz) - Te) * t, 2), 8, 1.0])
# Västra Storgatan vid Kvarngatan (efter foto): söder om gatan stiger en brant grässlänt bakom garaget (H056), som sedan fortsätter
# uppåt mot Värmlandsbergsgatan. Villan H061 ligger bara lite högre än gatan. Släntens höjd räknas från gatans höjd.
_vs = [(-664.4, -190.8), (-644.9, -187.6), (-572.8, -175.6), (-542.0, -164.4), (-526.9, -156.7), (-517.4, -150.7), (-495.1, -134.2)]
def _vs_avst(x, z):
    best = (1e9, None)
    for (ax, az), (bx, bz) in zip(_vs, _vs[1:]):
        dx, dz = bx - ax, bz - az; L2 = dx * dx + dz * dz; t = max(0, min(1, ((x - ax) * dx + (z - az) * dz) / L2))
        px, pz = ax + dx * t, az + dz * t; d = math.hypot(x - px, z - pz); sida = (dx * (z - az) - dz * (x - ax))
        if d < best[0]: best = (d if sida > 0 else -d, (px, pz))
    return best
for zz in range(-176, -70, 5):
    for xx in range(-632, -500, 5):
        d_, (px_, pz_) = _vs_avst(xx, zz)
        if d_ < 12 or d_ > 80 or _Gt is None: continue
        f_ = max(0.0, min(1.0, (-506.0 - xx) / 32.0)); f_ = f_ * f_ * (3 - 2 * f_)
        t_ = max(0.0, min(1.0, (d_ - 13.0) / 13.0)); rise_ = 5.0 * t_ * t_ * (3 - 2 * t_) + 0.11 * max(0.0, d_ - 26.0)
        if f_ * rise_ < 0.3: continue
        base_ = _topo_h(px_, pz_); hojdankare.append([xx, zz, round(max(_topo_h(xx, zz), base_ + 0.4 + f_ * rise_), 2), 6, 1.0])
print('topografisk karta:', 'ja' if TOPO else 'saknas', 'höjdankare', len(hojdankare))
# refug med träd i vändslingan framför vårdcentralen, entréplan och möbler
_lp = [P(n) for n in ways['256248201'][0][:-1]]; REF_X = sum(p[0] for p in _lp) / len(_lp); REF_Z = sum(p[1] for p in _lp) / len(_lp)
_ref = []
for (x_, z_) in _lp:
    d_ = math.hypot(x_ - REF_X, z_ - REF_Z) or 1; k_ = max(0.15, (d_ - 2.6) / d_); _ref.append([round(REF_X + (x_ - REF_X) * k_, 1), round(REF_Z + (z_ - REF_Z) * k_, 1)])
ytor.append({"typ": "gras", "namn": "", "poly": _ref})
ytor.append({"typ": "torg", "namn": "", "poly": [[-586.0, 328.3], [-599.3, 344.5], [-595.2, 347.9], [-588.8, 344.6], [-581.6, 333.7]]})   # stenlagd entréplan

# ------------------------------------------------------------------ utkast 8: Auktionisten (gamla godsmagasinet) är riven
BORTTAGNA = {"H015": "Godsmagasinet/Auktionisten är rivet – asfaltsparkering i dag"}
_auk = next(h for h in hus if h["id"] == "H015")
hus = [h for h in hus if h["id"] not in BORTTAGNA]
_va, _vb = (-121.7, -8.8), (-77.5, 1.1)                      # Västra Storgatan vid parkeringen
_L = math.hypot(_vb[0] - _va[0], _vb[1] - _va[1]); _u = ((_vb[0] - _va[0]) / _L, (_vb[1] - _va[1]) / _L); _n = (_u[1], -_u[0])   # _n mot norr (spåren)
_UV = lambda p: ((p[0] - _va[0]) * _u[0] + (p[1] - _va[1]) * _u[1], (p[0] - _va[0]) * _n[0] + (p[1] - _va[1]) * _n[1])
_XZ = lambda u, v: (_va[0] + _u[0] * u + _n[0] * v, _va[1] + _u[1] * u + _n[1] * v)
_us = [_UV(q)[0] for q in _auk["poly"]]; _vs = [_UV(q)[1] for q in _auk["poly"]]
_u0, _u1 = min(_us), max(_us); _v0, _v1 = 6.6, max(_vs) - 0.6
_park_auk = [[round(c, 1) for c in _XZ(u, v)] for u, v in ((_u0, _v0), (_u1, _v0), (_u1, _v1), (_u0, _v1))]
ytor.append({"typ": "parkering", "namn": "", "poly": _park_auk, "rekt": rekt_av(_park_auk), "ingaBilar": True})
parkeringslinjer = []; parkerade_auk = []
for (a, b, nos) in ((0.5, 5.5, -1), (13.0, 18.0, 1), (18.0, 23.0, -1), (28.5, 33.5, 1)):
    if _v0 + b > _v1: continue
    nb = int((_u1 - _u0 - 2.0) // 2.6); us = [_u0 + 1.0 + k * 2.6 for k in range(nb + 1)]
    for uu in us: parkeringslinjer.append([round(c, 2) for c in _XZ(uu, _v0 + a) + _XZ(uu, _v0 + b)])
    vb = a if nos == 1 else b
    parkeringslinjer.append([round(c, 2) for c in _XZ(us[0], _v0 + vb) + _XZ(us[-1], _v0 + vb)])
    for k in range(nb):
        cx, cz = _XZ((us[k] + us[k + 1]) / 2, _v0 + (a + b) / 2); fx, fz = _n[0] * nos, _n[1] * nos
        parkerade_auk.append([round(cx, 2), round(cz, 2), round(math.atan2(fx, fz), 3)])
RACKEN.append({"typ": "racke", "pts": [[round(c, 2) for c in _XZ(u, _v0 + 0.25)] for u in (_u0 + 0.3, (_u0 + _u1) / 2, _u1 - 0.3)], "mot": list(_XZ((_u0 + _u1) / 2, _v0 + 10))})
print('parkering vid gamla godsmagasinet:', len(parkerade_auk), 'platser')
# gång- och cykeltunnel under spåret (OSM 38081529) med ramper på båda sidor
_g13 = next(g for g in gator if g["osm"] == '38081233'); _g14 = next(g for g in gator if g["osm"] == '38081529'); _g249 = next(g for g in gator if g["osm"] == '243726262')
_tp = _g13["pts"] + _g14["pts"][1:] + list(reversed(_g249["pts"]))[1:]
_cs = [0.0]
for i in range(1, len(_tp)): _cs.append(_cs[-1] + math.hypot(_tp[i][0] - _tp[i - 1][0], _tp[i][1] - _tp[i - 1][1]))
_t0 = _cs[len(_g13["pts"]) - 1]; _t1 = _cs[len(_g13["pts"]) + len(_g14["pts"]) - 2]
gangtunnlar = [{"pts": _tp, "t0": round(_t0, 2), "t1": round(_t1, 2), "djup": 3.9, "bredd": 9.0, "kant": 3.0, "vagg": 2.1}]
print('gångtunnel', round(_t1 - _t0, 1), 'm')

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
ytor.append({"typ": "torg", "namn": "", "poly": [[-316.6, -41.6], [-319.4, -42.2], [-325.6, -25.4], [-322.6, -24.8]]})   # gång till kommunhusets entré
ytor.append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": [[-305.0, -41.0], [-313.6, -42.6], [-312.4, -22.4], [-305.6, -21.0]]})   # asfalterad plan framför Elektron
_vink = math.radians(55); _nos = (-math.sin(_vink), math.cos(_vink))   # nosen snett in mot huset, åt söder
parkerade = []
z = _z0 + 1.8
while z < _z1 - 1.5:
    rx = _kant(z) - 0.35; cxp = rx + _nos[0] * 2.2; czp = z + _nos[1] * 2.2
    parkerade.append([round(cxp, 2), round(czp, 2), round(math.atan2(_nos[0], _nos[1]), 3)]); z += 3.05
utan_trottoar = [[[round(_xf(z) + 0.5, 1), round(z, 1)] for z in [31.0] + _zs + [65.0]] + [[round(_xc(z, _tgp) - 1.0, 1), round(z, 1)] for z in reversed([31.0] + _zs + [65.0])]]
sma_trad = [{"x": round(_xf(z) + 1.0, 1), "z": z, "h": 5.2, "r": 2.0} for z in (35.0, 41.0, 47.0, 53.0, 59.0)]
print('snedparkering', len(parkerade), 'platser')

# ------------------------------------------------------------------ Torggatan framför scenen: snedparkering direkt mot gatan (efter foto, utkast 19)
# bara en smal kullerstensrad skiljer fickorna från körbanan; bilarna står med nosen snett in mot scenen
ytor[:] = [y for y in ytor if not (y["typ"] == "parkering" and y["poly"] and abs(y["poly"][0][0] + 96.3) < 0.6 and abs(y["poly"][0][1] - 87.1) < 0.6)]
_tgg = next(g for g in gator if g["osm"] == '32552347'); _hb = _tgg["bredd"] / 2
_vink2 = math.radians(65); _ct = 1 / math.tan(_vink2); _dj = 5.6; _sl = 2.5 / math.sin(_vink2)
torg_skyltar = []
for (a_, b_, s0_, s1_) in (((-6.0, 79.0), (-52.5, 88.5), 8.0, 42.0), ((-52.5, 88.5), (-92.3, 96.1), 4.0, 39.0)):
    L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1]); u_ = ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_); n_ = (-u_[1], u_[0])   # n_ mot norr (bort från gatan)
    XZ_ = lambda s, v: (a_[0] + u_[0] * s + n_[0] * (_hb + v), a_[1] + u_[1] * s + n_[1] * (_hb + v))
    ytor.append({"typ": "torg", "namn": "", "poly": [[round(c, 1) for c in XZ_(s, v)] for s, v in ((s0_ - 0.5, -0.05), (s1_ + 2.6, -0.05), (s1_ + 2.6, 0.45), (s0_ - 0.5, 0.45))]})
    _pp = [[round(c, 1) for c in XZ_(s, v)] for s, v in ((s0_, 0.45), (s1_, 0.45), (s1_ + _dj * _ct, 0.45 + _dj), (s0_ + _dj * _ct, 0.45 + _dj))]
    ytor.append({"typ": "parkering", "namn": "", "poly": _pp, "rekt": rekt_av(_pp), "ingaBilar": True})
    s_ = s0_
    while s_ <= s1_ + 0.01:
        parkeringslinjer.append([round(c, 2) for c in XZ_(s_, 0.45) + XZ_(s_ + _dj * _ct, 0.45 + _dj)])
        if s_ + _sl <= s1_ + 0.01:
            cx_, cz_ = XZ_(s_ + _sl / 2 + (_dj / 2) * _ct, 0.45 + _dj / 2); fx_, fz_ = u_[0] * math.cos(_vink2) + n_[0] * math.sin(_vink2), u_[1] * math.cos(_vink2) + n_[1] * math.sin(_vink2)
            parkerade_auk.append([round(cx_, 2), round(cz_, 2), round(math.atan2(fx_, fz_), 3)])
        s_ += _sl
    if a_[0] < -50:   # två P-skyltar med tidsbegränsning bakom fickorna framför scenen
        for s_ in (16.0, 30.0):
            x_, z_ = XZ_(s_ + (_dj + 0.9) * _ct, _dj + 1.2); torg_skyltar.append({"x": round(x_, 2), "z": round(z_, 2), "rot": round(math.atan2(-n_[0], -n_[1]), 3), "typ": "P", "under": ["2 tim", "8–18"], "pil": True})
_fore = len(parkerade_auk)
parkerade_auk[:] = [p_ for k_, p_ in enumerate(parkerade_auk) if not (60 < p_[1] < 100 and -100 < p_[0] < -5) or k_ % 5 in (0, 2)]
print('snedparkering vid scenen:', len(parkerade_auk), 'av', _fore, 'platser kvar med bil (inkl. godsmagasinet)')

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
        "hojdankare": hojdankare,
        "topo": TOPO,
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
        "storaTrad": [{"x": 13.3, "z": 47.5, "h": 17.0, "r": 8.0}, {"x": round(REF_X, 1), "z": round(REF_Z, 1), "h": 8.5, "r": 3.4}, {"x": -349.0, "z": -41.0, "h": 15.0, "r": 7.0},
                      {"x": -433.0, "z": -113.5, "h": 14.0, "r": 5.0}, {"x": -408.0, "z": -111.0, "h": 15.0, "r": 7.0}, {"x": -399.0, "z": -96.0, "h": 14.0, "r": 6.5},
                      # två stora lindar vid Blomstergårdens infart från Västra Storgatan (efter foto)
                      {"x": -427.5, "z": -67.5, "h": 15.0, "r": 5.5}, {"x": -414.5, "z": -63.0, "h": 15.5, "r": 6.0},
                      # lövträd kring stugan och det gula huset vid Ringvägen (efter foton)
                      {"x": -446.5, "z": -83.5, "h": 10.5, "r": 4.2}, {"x": -455.5, "z": -71.0, "h": 8.5, "r": 3.2}, {"x": -486.0, "z": -86.0, "h": 14.0, "r": 5.5},
                      {"x": -476.0, "z": -91.5, "h": 12.5, "r": 4.8}, {"x": -462.5, "z": -91.0, "h": 9.0, "r": 3.4},
                      # stora lövträd i H058:s trädgård (efter foto)
                      {"x": -393.0, "z": -54.5, "h": 14.0, "r": 6.0}, {"x": -357.5, "z": -47.0, "h": 13.0, "r": 4.5},
                      # fyra höga, smala träd på torget mellan Apoteket och biblioteket (efter foto)
                      {"x": -91.0, "z": 68.0, "h": 16.0, "r": 3.2, "smal": True}, {"x": -86.5, "z": 58.0, "h": 15.0, "r": 3.0, "smal": True},
                      {"x": -71.0, "z": 59.0, "h": 15.5, "r": 3.1, "smal": True}, {"x": -66.5, "z": 66.5, "h": 16.5, "r": 3.2, "smal": True},
                      # stora träd vid H471 (efter foto)
                      {"x": 77.5, "z": 262.5, "h": 15.0, "r": 5.5}, {"x": 47.0, "z": 276.0, "h": 12.0, "r": 4.5}] + sma_trad,
        # lummig grönska (buskar och en tuja) mellan H058 och brädstaketet mot trottoaren (efter foto)
        "buskage": [{"pts": [[-388.5, -54.4], [-372.0, -51.3], [-361.8, -49.3], [-362.8, -43.0]], "bredd": 2.8, "hojd": 1.7, "tujor": [[-368.6, -50.2]]},
                    # lummig grönska runt hörntomten vid Ringvägens början, med lupiner och vildrosor (efter foton)
                    {"pts": [[-463.0, -99.6], [-449.0, -89.4], [-438.5, -81.6], [-436.3, -76.4], [-439.8, -71.6]], "bredd": 3.6, "hojd": 2.0, "tujor": [], "blommor": ["#e8d23a", "#d9579a", "#f4f2ec", "#e8d23a"]},
                    {"pts": [[-444.4, -71.0], [-453.2, -66.9], [-462.4, -64.9]], "bredd": 3.0, "hojd": 2.1, "tujor": [], "blommor": ["#e8d23a", "#c94a8a", "#f4f2ec"]},
                    {"pts": [[-468.6, -63.2], [-472.6, -62.3]], "bredd": 1.6, "hojd": 1.8, "tujor": [], "blommor": ["#d9579a"]},
                    {"pts": [[-456.0, -93.0], [-466.5, -95.0], [-474.0, -92.5]], "bredd": 3.0, "hojd": 2.3, "tujor": [], "blommor": ["#f4f2ec"]},
                    # häck framför villan H061 mot Västra Storgatan (efter foto)
                    {"pts": [[-529.5, -148.6], [-522.0, -144.3], [-514.5, -139.4], [-507.5, -133.4]], "bredd": 1.6, "hojd": 1.7, "tujor": []},
                    # tät grönska mellan H471 och Skolgatan/Tingshusgatan (efter foto)
                    {"pts": [[49.5, 262.5], [53.0, 259.5], [60.0, 258.6], [68.0, 258.2], [76.0, 258.0]], "bredd": 4.5, "hojd": 2.4, "tujor": [[51.5, 262.0], [57.0, 260.5], [73.5, 259.5]]},
                    {"pts": [[48.5, 266.0], [50.5, 272.0], [51.5, 279.0]], "bredd": 3.0, "hojd": 2.0, "tujor": []}],
        # stenblock längs parkeringens kant mot Västra Storgatan, gatupratare med öppettider, brädstaket med skyltar längs Ringvägen (efter foton)
        "stenblock": [{"x": -423.6, "z": -66.6, "r": 0.75}, {"x": -419.8, "z": -65.4, "r": 0.8}, {"x": -411.0, "z": -62.6, "r": 0.85}, {"x": -407.5, "z": -61.8, "r": 0.7}, {"x": -432.0, "z": -70.0, "r": 0.7}],
        "vagskyltar": torg_skyltar,
        "serveringar": [DRAGON_SERVERING],
        # glasskylt (stående figurskylt) på trottoaren utanför Station Livs (efter foto)
        "reklamskyltar": [{"x": h189(-H189_R[2] / 2 + 55.4, H189_R[3] / 2 + 1.1)[0], "z": h189(-H189_R[2] / 2 + 55.4, H189_R[3] / 2 + 1.1)[1], "rot": round(math.atan2(-0.20728, -0.97828), 3), "typ": "glass"}],
        # rund anslagstavla (pelare med litet tak) på gågatan framför Apoteket (efter foto)
        "anslagspelare": [{"x": -95.5, "z": 73.8}],
        "gatupratare": [{"x": -426.0, "z": -68.4, "rot": 0.45, "farg": "#c4202a"}, {"x": -416.2, "z": -65.2, "rot": 0.45, "farg": "#e8e4dc"}, {"x": -7.6, "z": 24.6, "rot": 2.27, "farg": "#f2f2ee"}],
        "staket": [{"pts": [[-463.5, -41.5], [-465.5, -47.5], [-472.0, -50.5], [-484.0, -50.8]], "hojd": 1.8, "farg": "#4a3a30", "skyltar": 5},
                   {"pts": [[-390.3, -56.3], [-359.3, -50.1], [-360.9, -42.0]], "hojd": 1.15, "farg": "#8f8b83", "skyltar": 0},
                   {"pts": [H059_W(u_, -8.3) for u_ in (-23.5, -8.0, 8.0, 23.5)], "hojd": 1.1, "farg": "#9a9a94", "skyltar": 0},
                   # grå gärdsgård med grind mot Ringvägen och en bit längs Västra Storgatan (efter foton)
                   {"pts": [[-462.6, -64.8], [-468.4, -63.4]], "hojd": 1.2, "farg": "#8f8b82", "stil": "gardsgard", "grind": True},
                   {"pts": [[-441.0, -86.2], [-452.0, -94.2]], "hojd": 1.0, "farg": "#8f8b82", "stil": "gardsgard"}],
        "brevlador": [{"x": -457.0, "z": -63.95, "rot": -2.92, "farg": "#2f7a4a"}],
        "parkeradeBilar": parkerade + parkerade_auk,
        "parkeringslinjer": parkeringslinjer,
        "gangtunnlar": gangtunnlar,
        # stödmur av betong med vitt brädstaket längs Östra Storgatans södra trottoar vid H078 (efter foto)
        "stodmurar": [{"gata": next(g["id"] for g in gator if g["osm"] == '9702549'), "fran": [294.0, 27.3], "till": [352.0, 34.1], "sida": [326.0, 60.0], "hojd": 1.8, "staket": "#eeeeea"},
                      # låg betongmur med nätstaket i hörnet Skolgatan/Tingshusgatan vid H471 (efter foto)
                      {"gata": next(g["id"] for g in gator if g["osm"] == '256601471'), "fran": [50.0, 252.6], "till": [74.0, 251.0], "sida": [62.0, 270.0], "hojd": 1.1, "staket": "#a7acae"}],
        "utanTrottoar": utan_trottoar,
        "flaggstanger": [{"x": -448.0, "z": -57.5, "h": 10.0, "flagga": None}, {"x": -441.5, "z": -55.0, "h": 10.0, "flagga": None}, {"x": -317.6, "z": -31.0, "h": 11.0, "flagga": None}, {"x": -321.8, "z": -31.9, "h": 11.0, "flagga": "#1f4fa0"}, {"x": -326.0, "z": -32.7, "h": 11.0, "flagga": None}],
        "skyltstall": [{"x": -315.0, "z": -39.5, "rot": -0.2, "text": "GNESTA KOMMUN"}],
        "bankar": [{"x": -459.0, "z": -63.65, "rot": -2.92, "farg": "#9a9284"}, {"x": -336.5, "z": -44.6, "rot": -0.2}, {"x": -340.4, "z": -45.4, "rot": -0.2}, {"x": -595.6, "z": 341.0, "rot": 4.027, "farg": "#1e1e1e"}],
        "dorrar": [{"x": H059_W(u_, -5.64)[0], "z": H059_W(u_, -5.64)[1], "rot": round(math.atan2(_n059[0], _n059[1]), 4), "w": 1.2, "h": 2.1} for u_ in (-12.0, 0.0, 12.0)] + [{"x": -325.66, "z": -23.77, "rot": 2.944, "w": 1.9, "h": 2.4}, {"x": -9.9, "z": 28.45, "rot": 2.27, "w": 3.4, "h": 2.4}, {"x": 241.85, "z": 448.55, "rot": -3.0156, "w": 2.6, "h": 2.5}],
        "papperskorgar": [{"x": -333.6, "z": -44.0}],
        "rabatter": [{"x": -345.0, "z": -36.5, "r": 2.6, "farg": "#d4384a"}],
        "uteplatser": [{"x": -419.3, "z": -99.5, "b": 9.0, "d": 6.5, "rot": 0.6634, "parasoll": "#d0262f"}],
        "skorstenar": [{"x": -453.0, "z": -147.4, "h": 24.0, "r": 1.05}],
        "overgangar": [{"osm": "32552317", "nara": [5.9, 27.5]},
                       # övergångsstället från stationen till parken (efter foto): trafikljus åt båda hållen, refug med håll-höger-skylt, P-skylt vid parken
                       {"osm": "504799985", "nara": [16.0, 19.5], "trafikljus": True, "refug": True, "skyltar": [{"typ": "P", "sida": 1, "ds": 3.5}]},
                       # övergångsstället över Skolgatan vid H471 (efter foto)
                       {"osm": "256601471", "nara": [53.0, 252.5]}],
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
