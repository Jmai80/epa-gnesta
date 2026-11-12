#!/usr/bin/env python3
"""EPA-Gnesta utkast 2: bygger karta.js från en OpenStreetMap-export.
Koordinater: meter, origo = 59.0482 N, 17.3117 E. x = öster, z = söder.
Data © OpenStreetMap-bidragsgivare, ODbL.
"""
import sys, os, math, json, base64, hashlib, collections
import numpy as np
from matplotlib.path import Path
HERE = os.path.dirname(os.path.abspath(__file__))   # verktyg/ i repot (eller /home/claude/osmtools)
sys.path.insert(0, HERE)
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

# ------------------------------------------------------------------ rondellen vid Circle K (utkast 50)
# I OSM är ringen vid Östra Storgatan/Dansutvägen/Nibblegatan bara ~9 m i diameter och de delade körfälten ligger inne i den. I verkligheten
# är rondellen ungefär dubbelt så stor: ringen blir en cirkel med 12,5 m radie till mittlinjen (8 m bred, ytterkant ~16,5 m). Korta
# tillfarter som hamnar helt inne i ringen tas bort, övriga kapas där de möter ringen eller förlängs ut till den. I mitten en grusad
# rondellö med kantsten.
RONDELL_C, RONDELL_R = (948.3, 973.95), 12.5
_ring_osm = ['487783205', '487783206', '487783201', '487783202']          # ringens delar i OSM (G337, G338, G335, G336)
_r_ = lambda p: math.hypot(p[0] - RONDELL_C[0], p[1] - RONDELL_C[1])
def _pa_ring(a, b):
    """skärningen mellan sträckan a->b (a inne i ringen, b utanför) och ringens mittlinje"""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2; q = (a[0] + (b[0] - a[0]) * m, a[1] + (b[1] - a[1]) * m)
        if _r_(q) < RONDELL_R: lo = m
        else: hi = m
    return [round(a[0] + (b[0] - a[0]) * hi, 2), round(a[1] + (b[1] - a[1]) * hi, 2)]
_ring_g = next(g for g in gator if g["osm"] == _ring_osm[0]); _anslut = []; _bort = set(_ring_osm[1:])
for g in gator:
    if g["osm"] in _ring_osm or not g["bil"]: continue
    pts = g["pts"]
    if min(_r_(p) for p in pts) > RONDELL_R + 4: continue
    inne = [_r_(p) < RONDELL_R for p in pts]; ny_ = []
    if all(inne): _bort.add(g["osm"]); continue
    if inne[0]:
        k = inne.index(False); pts = [_pa_ring(pts[k - 1], pts[k])] + pts[k:]; ny_.append(pts[0])
    elif _r_(pts[0]) < RONDELL_R + 4:
        q = [round(RONDELL_C[0] + (pts[0][0] - RONDELL_C[0]) * RONDELL_R / _r_(pts[0]), 2), round(RONDELL_C[1] + (pts[0][1] - RONDELL_C[1]) * RONDELL_R / _r_(pts[0]), 2)]
        pts = [q] + pts; ny_.append(q)
    if inne[-1]:
        k2 = max(i for i in range(len(pts)) if _r_(pts[i]) >= RONDELL_R); pts = pts[:k2 + 1] + [_pa_ring(pts[k2 + 1], pts[k2])]; ny_.append(pts[-1])
    elif _r_(pts[-1]) < RONDELL_R + 4:
        q = [round(RONDELL_C[0] + (pts[-1][0] - RONDELL_C[0]) * RONDELL_R / _r_(pts[-1]), 2), round(RONDELL_C[1] + (pts[-1][1] - RONDELL_C[1]) * RONDELL_R / _r_(pts[-1]), 2)]
        pts = pts + [q]; ny_.append(q)
    if max(_r_(p) for p in pts) < RONDELL_R + 4: _bort.add(g["osm"]); continue   # bara en stump kvar utanför ringen (delade körfält)
    g["pts"] = pts; _anslut += ny_
_vinklar = sorted(set([round(k_ * math.pi / 16, 4) for k_ in range(32)] + [round(math.atan2(q[1] - RONDELL_C[1], q[0] - RONDELL_C[0]) % (2 * math.pi), 4) for q in _anslut]))
_ring_pts = []
for a_ in _vinklar:
    q = next((q for q in _anslut if abs((math.atan2(q[1] - RONDELL_C[1], q[0] - RONDELL_C[0]) % (2 * math.pi)) - a_) < 1e-3), None)
    if q is None and any(abs(((math.atan2(q_[1] - RONDELL_C[1], q_[0] - RONDELL_C[0]) - a_ + math.pi) % (2 * math.pi)) - math.pi) < 0.08 for q_ in _anslut): continue
    _ring_pts.append(q or [round(RONDELL_C[0] + RONDELL_R * math.cos(a_), 2), round(RONDELL_C[1] + RONDELL_R * math.sin(a_), 2)])
_ring_g["pts"] = _ring_pts + [_ring_pts[0]]
gator[:] = [g for g in gator if g["osm"] not in _bort]
ytor.append({"typ": "ljus", "namn": "", "hojd": 0.165, "poly": [[round(RONDELL_C[0] + 8.55 * math.cos(k_ * math.pi / 24), 2), round(RONDELL_C[1] + 8.55 * math.sin(k_ * math.pi / 24), 2)] for k_ in range(48)]})
ytor.append({"typ": "grus", "namn": "", "hojd": 0.19, "poly": [[round(RONDELL_C[0] + 8.0 * math.cos(k_ * math.pi / 24), 2), round(RONDELL_C[1] + 8.0 * math.sin(k_ * math.pi / 24), 2)] for k_ in range(48)]})
print('rondellen: anslutningar', len(_anslut), 'borttagna vägar', len(_bort), 'ringpunkter', len(_ring_pts))

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
# Thulegatan från Västra Storgatan (bommen borttagen i utkast 29) till Torggatan och vidare österut på Torggatan till Tingshusgatan
def _nod_kedja(wid, fran, till):
    nds = list(ways[wid][0]); i, j = nds.index(fran), nds.index(till)
    return nds[i:j + 1] if i <= j else nds[j:i + 1][::-1]
_thule = list(ways['41556702'][0]); _torg = list(ways['32552347'][0])
_korsning = [n for n in _thule if n in set(_torg)][0]
RUTTER.append({"namn": "Thulegatan–Torggatan", "ways": [], "typ": "residential", "fran": None, "till": None, "oppenSlut": True,
               "kedja": _nod_kedja('41556702', _thule[-1], _korsning) + _nod_kedja('32552347', _korsning, _torg[0])[1:]})
ALLA_RUTTWAYS = set(w for r in RUTTER for w in r["ways"])
# påskägg (utkast 40): Granbackavägen från Nygatan och servicevägen fram till parkeringen vid Granbackavägen 108
_gbv = list(ways['42350258'][0]); _sv = list(ways['42350260'][0])
_gb_knut = [n for n in _gbv if n in set(_sv)][0]
RUTTER.append({"namn": "Granbackavägen", "ways": [], "typ": "residential", "fran": None, "till": None, "oppenSlut": True,
               "kedja": _gbv[:_gbv.index(_gb_knut) + 1] + (_sv[1:] if _sv[0] == _gb_knut else _sv[::-1][1:])})
# utkast 55: hela Torggatan (även västerut från Thulegatan fram till Nygatan och Platåvägen) och hela Platåvägen med slingan uppe på platån är
# öppna i EPA-läget, så bommarna på de gatorna är borta (sidogator som korsar dem får egna bommar som vanligt)
RUTTER.append({"namn": "Torggatan väster", "ways": [], "typ": "residential", "fran": None, "till": None, "oppenSlut": True,
               "kedja": _nod_kedja('32552347', _korsning, _torg[-1])})
for _pw in ('41644461', '1062800387', '1062800389'):
    RUTTER.append({"namn": "Platåvägen", "ways": [], "typ": "residential", "fran": None, "till": None, "oppenSlut": True, "kedja": list(ways[_pw][0])})
def build_route(R):
    chain = list(R.get("kedja", []))
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
            "bredd": BREDD[R.get("typ") or ways[R["ways"][0]][1].get('highway')], "point_at": point_at, "S0": S0, "s_near": s_near,
            "kanter": set(frozenset(chain[i:i + 2]) for i in range(len(chain) - 1) if S0 - 1 < cum[i + 1] and cum[i] < S1 + 1)}
rutt_data = [build_route(R) for R in RUTTER]
route = rutt_data[0]["pts"]
route_nodes = set().union(*[r["noder"] for r in rutt_data])
route_kanter = set().union(*[r["kanter"] for r in rutt_data])
point_at = rutt_data[0]["point_at"]; S0 = rutt_data[0]["S0"]

# infarten mittemot Blomstergården (upp mot återvinningen vid spåret) är en bred, sliten asfaltsväg (efter foto, utkast 31)
for g in gator:
    if g["osm"] == "510000278": g["bredd"] = 5.0
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
            if frozenset((nds[k], nds[j])) in route_kanter: continue   # sträckan är redan körbar
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
    if t.get('addr:street') and t.get('addr:housenumber'): rec["adress"] = "%s %s" % (t['addr:street'], t['addr:housenumber'])   # sökbar i spelet
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
_bU = (0.768, 0.641); RB_W, RB_R, RB_P = lokal((-460.68, -91.07), _bU)   # längs Västra Storgatan, ca 2,5 m innanför trottoaren
husdel("ringvagen_bod", "", RB_R(-3.5, 3.5, -1.6, 1.6), RB_P(-3.5, 3.5, -1.6, 1.6),
       {"typ": "bod", "van": 1, "fh": 2.4, "vagg": "#93291f", "tak": "pulpet", "takfarg": "#7d7a75", "utanFonster": True},
       "Lång röd bod med låglutande plåttak mellan stugan och Västra Storgatan (efter foto).")

# Gnesta brandstation (H024, efter foto från Kullagatan): lång tvåvåningsdel i rött tegel med vit bottenvåning, fyra grå och tre röda
# garageportar mot Kullagatan och ljus takfotslist; i norra änden en högre tegeldel med röda portar och slangtorn
BR_W, BR_R, BR_P = lokal((-236.4, 21.9), (-0.193, 0.981))   # u norrut→söderut längs fasaden mot Kullagatan, v västerut
BR_MOT = BR_W(25.0, -80.0)
BR_TEGEL = {"tegel": True, "vagg": "#ffffff", "tak": "platt", "takfarg": "#4a4744"}
husdel("brandstation_norr", "Gnesta brandstation", BR_R(0.0, 9.4, 0.0, 21.3), BR_P(0.0, 9.4, 0.0, 21.3),
       {**BR_TEGEL, "typ": "centrum", "van": 3, "fh": 3.5,
        "band": [{"y0": -2.0, "y1": 3.2, "farg": "#ecebe6"}, {"y0": 9.9, "y1": 10.55, "farg": "#cdbb94"}],
        "volymer": [{"poly": BR_P(2.5, 6.5, 8.0, 12.0), "h": 16.5}],
        "skyltar": [{"text": "", "stil": "garageport", "vid": BR_W(u_, 0.0), "mot": BR_MOT, "hojd": 1.6, "hgt": 3.2, "bredd": 2.8, "utanTak": True, "bg": "#b3262a"} for u_ in (2.6, 6.4)]},
       "Gnesta brandstation, den högre norra delen i tegel med röda portar och slangtorn (efter foto).")

# H226 (efter foto från Kullagatan): bostadshus i rött tegel i fem våningar med ljus bottenvåning och ljus takfotslist, Bokcafé i
# hörnet mot Kullagatan med randig markis och trappa med räcken, balkonger i innerhörnet och garage i bottenplan; liten gräsmatta
# med rött staket och picknickbord mot gatan

# H010, Västra Storgatan 12–14 mittemot Pelle och Lotta (efter två foton): rödputsat hus i tre våningar med sadeltak, bottenvåning
# klädd i mörk sten med vit list ovanför; butiker från öster till väster: Svensk Fastighetsförmedling, Salong Carina, Direkten och
# Röda Korset. Burspråk på gaveln mot Färghuset, svängda balkonger i västra hörnet, flygel söderut i väster
H010_W, H010_R, H010_P = lokal((-206.3, -17.2), (0.9836, 0.1808))   # u från västra hörnet österut längs gatan, v söderut in i huset
H010_VAGG = "#ad5a50"; H010_TAK = "#7a3b2e"
husdel("h010_flygel", "", H010_R(0.0, 12.2, 12.7, 27.6, True), H010_P(0.0, 12.2, 12.7, 27.6),
       {"typ": "flerbostad", "van": 3, "fh": 3.0, "vagg": H010_VAGG, "tak": "sadel", "takfarg": H010_TAK,
        "band": [{"y0": -2.0, "y1": 3.0, "farg": "#3a3d42"}, {"y0": 3.0, "y1": 3.22, "farg": "#efeee8"}]},
       "Västra Storgatan 14: flygeln söderut på gården, samma röda puts (efter foto).")

# H008 (efter två foton) är två hus som sitter ihop längs Västra Storgatan:
#  - Elon i väster: grå stående panel i tre våningar, låglutande tak, butiksplan med stora fönster och blått skyltband
#  - mot Swedbank i öster: gult trähus med stående panel, mörkbruna fönsterbågar, sadeltak med två frontespiser med balkonger,
#    grå sockelvåning med Gerdtmans Skor längst österut, trapphusentré och Gnesta Blommor
H008_W, H008_R, H008_P = lokal((-145.8, -7.2), (0.9778, 0.2100))   # u från västra hörnet österut, v söderut in i huset
H008_SKIFTE = 36.0; MOT_H008 = H008_W(36.0, -60.0)
GUL = {"typ": "centrum", "van": 3, "fh": 3.0, "vagg": "#d8b98c", "tak": "sadel", "takfarg": "#55524e", "karmFarg": "#4a2e22", "panel": True, "sakerhet": "foto",
       "band": [{"y0": -2.0, "y1": 3.15, "farg": "#a3a29d"}]}
def _gs(u, **kw):  # skyltar inom frontespisernas bredd lyfts ut framför deras vägg
    ut = 0.17 if any(abs(u - c) < 3.4 for c in (58.6, 44.2)) else 0.0
    return {"vid": H008_W(u, 0.0), "mot": MOT_H008, "utanTak": True, **({"ut": ut} if ut else {}), **kw}
_gul_sk = [_gs(63.0, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.4), _gs(60.2, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.4),
           _gs(56.8, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.2), _gs(54.2, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.2),
           _gs(61.6, text="SKOR", hojd=3.75, bg="transparent", fg="#2a2f3a", hgt=0.65, bredd=2.6),
           _gs(57.2, text="Gerdtmans Skor", hojd=2.8, bg="#2f5a44", fg="#f1ece0", hgt=0.32, bredd=4.6, kursiv=True),
           _gs(51.2, text="", hojd=1.25, bg="#2c2c2c", hgt=2.4, bredd=1.9),
           _gs(47.6, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.6), _gs(44.6, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.4),
           _gs(41.0, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=3.0), _gs(37.6, text="", stil="butik", hojd=1.5, bg="#2a2c2e", hgt=2.1, bredd=2.4),
           _gs(44.0, text="Gnesta Blommor", hojd=2.8, bg="#2f4a3a", fg="#f1ece0", hgt=0.32, bredd=4.4, kursiv=True)]
husdel("h008_gul", "", H008_R(H008_SKIFTE, 65.3, 0.0, 12.0), H008_P(H008_SKIFTE, 65.3, 0.0, 12.0),
       {**GUL, "skyltar": _gul_sk, "fasadflaggor": [{"vid": H008_W(u_, 0.0), "mot": MOT_H008, "hojd": 2.7, "typ": "rea"} for u_ in (55.4, 62.3)]},
       "Gult trähus mot Swedbank: stående panel, mörkbruna fönsterbågar, sadeltak med två frontespiser, Gerdtmans Skor och Gnesta Blommor i bottenvåningen (efter foto).")
husdel("h008_gul_flygel", "", H008_R(55.4, 65.2, 12.0, 19.6, True), H008_P(55.4, 65.2, 12.0, 19.6), dict(GUL),
       "Gula trähusets flygel på gården mot Swedbank (efter foto).")
for oid_, u_, bal_ in (("h008_frontespis_ost", 58.6, (3.25, 6.3)), ("h008_frontespis_vast", 44.2, (6.3, 9.2))):
    husdel(oid_, "", H008_R(u_ - 3.3, u_ + 3.3, -0.15, 3.6), H008_P(u_ - 3.3, u_ + 3.3, -0.15, 3.6),
           {**GUL, "takAxel": "kort", "taklutning": 1.0,
            "balkonger": [{"vid": H008_W(u_, -0.15), "mot": MOT_H008, "y": y_, "b": 3.2, "d": 1.3, "farg": "#cdb48a"} for y_ in bal_]},
           "Frontespis med balkonger på det gula trähuset mot Västra Storgatan (efter foto).")

# H068 (Västra Storgatan 11): bottenvåning i gult tegel med butiker (Järna Gnesta Sportbutik), två våningar med långa balkonger bakom
# stående ljusa ribbor och mörkröda ribbskärmar, flackt sadeltak med stort utsprång. Fasaden mot gatan har två utskjutande butiksdelar
# vars tak är balkonggolv; i de indragna delarna hänger balkongerna i tunna vita stänger från takfoten (efter foton).
H068_U = (0.98066, 0.19575)
H068_W, H068_R, H068_P = lokal((-294.49, -33.01), H068_U)   # u österut längs Västra Storgatan, v söderut; v=0 är butiksdelarnas fasad
MOT_H068 = H068_W(40.0, -40.0); H068_ROT = round(-math.atan2(H068_U[1], H068_U[0]), 4)
H068_TEGEL = {"typ": "centrum", "van": 1, "fh": 3.1, "tegel": "gul", "tak": "platt", "takfarg": "#9a958c", "vagg": "#c39a5c", "sakerhet": "foto"}
def _h068_sk(u, v, **kw): return {"vid": H068_W(u, v), "mot": MOT_H068, "utanTak": True, **kw}
_FONSTER = dict(text="", stil="butik", hojd=1.45, bg="#2b2522", hgt=2.2)
_DORR = dict(text="", hojd=1.2, bg="#2a2420", hgt=2.4)
_REA = dict(text="SOMMAR-REA 20–70%", hojd=1.35, bg="#f3d33a", fg="#c62a2a", hgt=0.85, bredd=0.62, ut=0.05)
husdel("h068_botten", "", H068_R(8.86, 72.14, 1.56, 19.94), H068_P(8.86, 72.14, 1.56, 19.94),
       {**H068_TEGEL, "skyltar": [_h068_sk(u_, 1.56, bredd=2.4, **_FONSTER) for u_ in (11.2, 14.4, 17.6, 38.6, 44.2, 66.2, 69.4)] + [_h068_sk(41.6, 1.56, bredd=1.5, **_DORR)]},
       "H068: bottenvåning i gult tegel under de indragna balkongdelarna (efter foto).")
husdel("h068_butik_vast", "", H068_R(19.7, 36.4, 0.0, 1.6), H068_P(19.7, 36.4, 0.0, 1.6),
       {**H068_TEGEL, "skyltar": [_h068_sk(u_, 0.0, bredd=2.4, **_FONSTER) for u_ in (25.0, 28.2, 31.4, 34.4)] + [_h068_sk(22.0, 0.0, bredd=2.0, **_DORR), _h068_sk(31.4, 0.0, **_REA)]},
       "H068: utskjutande butiksdel i gult tegel; taket är balkonggolv (efter foto).")
husdel("h068_butik_ost", "", H068_R(46.4, 63.6, 0.0, 1.6), H068_P(46.4, 63.6, 0.0, 1.6),
       {**H068_TEGEL, "skyltar": [_h068_sk(u_, 0.0, bredd=2.5, **_FONSTER) for u_ in (48.2, 51.4, 58.6, 62.0)] + [_h068_sk(55.6, 0.0, bredd=1.5, **_DORR),
        _h068_sk(58.6, 0.0, **_REA), _h068_sk(53.5, 0.0, **{**_REA, "hojd": 1.6}), _h068_sk(51.4, 0.0, **{**_REA, "text": "NYHET!", "bredd": 0.8, "hgt": 0.55, "hojd": 1.9}),
        _h068_sk(57.4, 0.0, text="JÄRNA GNESTA", text2="SPORTBUTIK", stil="tvafarg", bg="#d8263c", bg2="#2a3f9e", fg="#ffffff", hojd=3.75, hgt=1.0, bredd=3.5, ut=0.24)]},
       "H068: utskjutande butiksdel med Järna Gnesta Sportbutik; taket är balkonggolv (efter foto).")

# H385 (Margretedalsvägen 15): det höga korallröda hörnhuset i åtta våningar med sadeltak och grå glasbalkonger,
# ett modernt landmärke som syns från centrum (efter foto); längorna intill är vita i fem våningar
H385_U = (0.5211, -0.8535)
H385_W, H385_R, H385_P = lokal((-300.1, -235.2), H385_U)   # u längs Järnvägsgatan norrut, v = 0 är fasaden mot Järnvägsgatan, huset ligger mot negativa v
_m385o, _m385s = H385_W(6.6, 20.0), H385_W(-20.0, -5.7)    # riktpunkter österut (Järnvägsgatan) och söderut (Margretedalsvägen)
husdel("h385_torn", "", H385_R(-0.3, 13.6, -11.7, 0.3), H385_P(-0.3, 13.6, -11.7, 0.3),
       {"typ": "flerbostad", "van": 8, "fh": 3.0, "vagg": "#d7603d", "tak": "sadel", "taklutning": 0.55, "takfarg": "#3c3e41", "karmFarg": "#2e2e30", "sakerhet": "foto",
        "band": [{"y0": -2.0, "y1": 1.2, "farg": "#a9acad"}],
        "balkonger": [{"vid": H385_W(1.9, 0.3), "mot": _m385o, "y": 3.0 * k_ + 0.05, "b": 3.0, "d": 1.4, "farg": "#a7aeb2"} for k_ in range(1, 8)] +
                     [{"vid": H385_W(-0.3, -2.4), "mot": _m385s, "y": 3.0 * k_ + 0.05, "b": 3.2, "d": 1.4, "farg": "#a7aeb2"} for k_ in range(1, 8)]},
       "Margretedalsvägen 15: hög korallröd hörndel i åtta våningar med sadeltak och grå glasbalkonger (efter foto).")

# Nya vattentornet vid Platåvägen (1977): finns i OSM bara som man_made=water_tower utan building-tagg (way 71306420, rund kontur ~23 m),
# så det läggs in här. Vitt betongtorn med mittskaft, breda ben och djup cistern (efter foto) på platån söder om Granbackavägen (utkast 44)
VISA_NYA_TORNET = True   # efter foto från användaren (utkast 44)
_vt = [P(n_) for n_ in ways["71306420"][0][:-1]] if (VISA_NYA_TORNET and "71306420" in ways) else []
if _vt:
    _vx = sum(p_[0] for p_ in _vt) / len(_vt); _vz = sum(p_[1] for p_ in _vt) / len(_vt); _vr = sum(math.hypot(p_[0] - _vx, p_[1] - _vz) for p_ in _vt) / len(_vt)
    _mot = min((q for g in gator if g["typ"] in ("cycleway", "footway", "residential", "unclassified", "service") for q in g["pts"]), key=lambda q: math.hypot(q[0] - _vx, q[1] - _vz))
    husdel("vattentorn_nytt", "Vattentornet (nya, 1977)", [round(_vx, 2), round(_vz, 2), 10.0, 10.0, 0.0], [[round(p_[0], 2), round(p_[1], 2)] for p_ in _vt],
           {"typ": "vattentorn_nytt", "van": 1, "fh": 3.0, "vagg": "#f1f1ec", "tak": "platt", "takfarg": "#8e918f", "radie": round(_vr, 2), "mot": [round(_mot[0], 1), round(_mot[1], 1)]},
           "Nya vattentornet vid Platåvägen, i drift sedan 1977: vitt betongtorn med mittskaft, åtta breda ben och djup cistern med antenner på taket (efter foto). Läge och diameter från OpenStreetMap, höjder uppskattade.")
# ================================================================== PÅSKÄGG: Kadriljvägen 1 (H1234), hörntomten vid Menuettvägen (efter två foton, utkast 45)
# 1½-plansvilla: bottenvåning i gult tegel, vit stående lockpanel på gavlarna, brant mörkt tegeltak, burspråk med plåttak på gaveln mot
# Kadriljvägen och en indragen entré under ett skärmtak mellan huset och garaget. Garaget i vit stående panel med platt tak, vit sektionsport
# mot Kadriljvägen och två små fönster mot Menuettvägen. Fotavtrycket i OSM är hus + garage i ett; här delas det i husdelar i husets egna axlar.
KD_U = (0.99909, 0.04252); _n_ = math.hypot(*KD_U); KD_U = (KD_U[0] / _n_, KD_U[1] / _n_)   # u österut längs gaveln mot Kadriljvägen
KD_O = (486.9, 968.7)                                                                         # huvudbyggnadens nordöstra hörn (OSM)
KD_W, KD_R, KD_P = lokal(KD_O, KD_U)                                                          # v söderut in i huset
KD_V = (-KD_U[1], KD_U[0]); KD_YAW = -math.atan2(KD_U[1], KD_U[0])
KD_HUS = (-9.4, 0.0, 0.0, 11.6)       # huvudbyggnaden (u0, u1, v0, v1)
KD_GAR = (1.93, 5.33, 2.6, 12.8)      # garaget
KD_TILL = (-13.1, -9.4, 0.0, 6.65)    # tillbyggnaden i väster (bakom trädet på fotot)
KD_VIT, KD_TAK, KD_GLAS = "#efeee7", "#463c37", "#2b3540"
def _kd_ring(uv):
    r = [KD_W(u_, v_) for u_, v_ in uv]
    return r if area(r) > 0 else r[::-1]
husdel("kadrilj1_garage", "Mormor", KD_R(*KD_GAR), KD_P(*KD_GAR),
       {"typ": "bod", "van": 1, "fh": 2.2, "vagg": "#eceae2", "panel": True, "utanFonster": True, "tak": "platt", "takfarg": "#3b3d3f",
        "kantFarg": "#f1f0ea", "kantHojd": 0.32, "band": [{"y0": -1.0, "y1": 0.02, "farg": "#3a3d40"}, {"y0": 1.72, "y1": 2.2, "farg": "#efeee8"}]},
       "Kadriljvägen 1: garaget i vit stående panel med platt tak, vit sektionsport mot Kadriljvägen och två små fönster mot Menuettvägen (efter foto).")
husdel("kadrilj1_tillbyggnad", "Mormor", KD_R(*KD_TILL), KD_P(*KD_TILL),
       {"typ": "villa", "van": 1, "fh": 2.3, "vagg": KD_VIT, "panel": True, "utanFonster": True, "tak": "platt", "takfarg": KD_TAK,
        "kantFarg": "#f1f0ea", "kantHojd": 0.3, "band": [{"y0": -1.0, "y1": 0.02, "farg": "#3a3d40"}]},
       "Kadriljvägen 1: låg tillbyggnad i vit panel på västra sidan, delvis dold bakom trädet (efter foto; utformningen uppskattad).")
# entréns vindfång i gult tegel (dörren mot öster, i nischen mellan huset och garaget) med förbindelsen till garaget; platt tak under skärmtaket
_ring = _kd_ring([(0.0, 1.6), (1.0, 1.6), (1.0, 6.8), (1.93, 6.8), (1.93, 8.1), (0.0, 8.1)]); _cx, _cz = centroid(_ring)
hus.append({"osm": "kadrilj1_entre", "namn": "Mormor", "adress": "Kadriljvägen 1", "typ": "villa", "van": 1, "fh": 2.2, "tegel": "gul", "vagg": KD_VIT, "tak": "platt", "takfarg": KD_TAK,
            "kantFarg": "#f1f0ea", "kantHojd": 0.3, "x": round(_cx, 1), "z": round(_cz, 1), "area": round(abs(area(_ring))), "poly": [[round(p_[0], 2), round(p_[1], 2)] for p_ in _ring],
            "sakerhet": "foto", "not": "Kadriljvägen 1: entrén i gult tegel med vit dörr mot öster, i nischen mellan huset och garaget under ett skärmtak (efter foto)."})

# ================================================================== STOPP Köpcentrum (H044) vid Östra Storgatan (efter foto från Östra Storgatan, utkast 46)
# Hela köpcentret är envåningshus i grå profilplåt utom delen vid entrén, som har två våningar och ett trapphustorn ut mot parkeringen.
# OSM har allt som en byggnad (som spelet ritade som en enda låda); här delas det i husdelar i fasadens egna axlar:
# u norrut längs fasaden mot Östra Storgatan, v ut mot parkeringen. v = 0 är fasadlinjen i mitten, södra delen ligger 5,7 m indragen.
ST_U = (-13.3, -33.3); _n_ = math.hypot(*ST_U); ST_U = (ST_U[0] / _n_, ST_U[1] / _n_)
ST_O = (886.6, 921.9)                                   # hörnet där mittdelens fasad börjar (OSM)
ST_W, ST_R, ST_P = lokal(ST_O, ST_U)
ST_MOT = ST_W(25.0, 80.0)                               # riktpunkt ut mot Östra Storgatan
ST_PLAT = {"typ": "affar", "van": 1, "tak": "platt", "takfarg": "#5d6064", "utanFonster": True, "panel": "ligg", "kantHojd": 0.5}
ST_SOCKEL = [{"y0": -1.0, "y1": 0.05, "farg": "#55595d"}]
def _st_sk(u, v=0.0, **kw): return {"vid": ST_W(u, v), "mot": ST_MOT, "utanTak": True, **kw}
_BUTIK = dict(text="", stil="butik", hojd=1.35, hgt=2.3)
husdel("stopp_sodra", "Stopp Köpcentrum", ST_R(-17.9, 0.0, -53.7, -5.67), ST_P(-17.9, 0.0, -53.7, -5.67),
       {**ST_PLAT, "fh": 4.2, "vagg": "#8e949a", "kantFarg": "#7d838a", "band": ST_SOCKEL,
        "skyltar": [_st_sk(-5.4, -5.67, bredd=4.8, **_BUTIK), _st_sk(-1.9, -5.67, bredd=2.4, **_BUTIK)]},
       "Stopp Köpcentrum, södra delen: indragen envåningsdel i grå profilplåt med en vit glasad entré och en röd skylt i hörnet (efter foto).")
husdel("stopp_bakom", "Stopp Köpcentrum", ST_R(26.0, 42.0, -53.7, -16.0), ST_P(26.0, 42.0, -53.7, -16.0),
       {**ST_PLAT, "fh": 4.4, "vagg": "#8b9197", "kantFarg": "#7f858b", "band": ST_SOCKEL},
       "Stopp Köpcentrum: envåningsdelen bakom tvåvåningshuset vid entrén.")
husdel("stopp_tvavaning", "Stopp Köpcentrum", ST_R(26.0, 42.0, -16.0, 0.0), ST_P(26.0, 42.0, -16.0, 0.0),
       {**ST_PLAT, "van": 2, "fh": 3.6, "vagg": "#979da3", "kantFarg": "#888e94", "band": ST_SOCKEL,
        "skyltar": [_st_sk(32.3, text="STOPP", text2="KÖPCENTRUM", stil="tvarad", bg="#f3f3ef", fg="#d21e2a", fg2="#262626", hojd=4.3, hgt=1.55, bredd=4.0, ut=0.62),
                    _st_sk(28.2, bredd=2.6, **_BUTIK)]},
       "Stopp Köpcentrum: delen vid entrén har två våningar, med den stora skylten STOPP KÖPCENTRUM över ingången och kontor och butiker på övervåningen (efter foto).")
husdel("stopp_torn", "Stopp Köpcentrum", ST_R(35.9, 42.0, 0.0, 4.0), ST_P(35.9, 42.0, 0.0, 4.0),
       {**ST_PLAT, "van": 2, "fh": 3.6, "vagg": "#8d9399", "kantFarg": "#80868c", "band": ST_SOCKEL},
       "Stopp Köpcentrum: trapphustornet i två våningar ut mot parkeringen, bredvid kundvagnsgaraget (efter foto).")
husdel("stopp_norra", "Stopp Köpcentrum", ST_R(42.0, 60.5, -53.7, 0.0), ST_P(42.0, 60.5, -53.7, 0.0),
       {**ST_PLAT, "fh": 5.2, "vagg": "#b2b5b6", "panel": True, "kantFarg": "#a2a5a7", "band": ST_SOCKEL},
       "Stopp Köpcentrum, norra delen: ljusare och lite högre envåningshall med stående plåt, ett litet skärmtak över en dörr och en mörk skylt (efter foto).")

# Platåvägens början (utkast 48): flygeln på baksidan av den grå villan H736 (resten av husen vid Nygatan 28 längre ner, efter Lador)
P36_O, P36_U = (-848.0, 159.6), (12.7 / 15.92, 9.6 / 15.92)
P36_W, P36_R, P36_P = lokal(P36_O, P36_U); P36_L, P36_D = 15.92, 8.58
husdel("nygatan_h736_flygel", "", P36_R(0.0, 7.22, P36_D, 12.7), P36_P(0.0, 7.22, P36_D, 12.7),
       {"typ": "villa", "van": 1, "fh": 2.55, "vagg": "#5c6571", "panel": True, "utanFonster": True, "tak": "sadel", "taklutning": 0.42, "takfarg": "#363636",
        "takUtsprang": 0.35, "takfotFarg": "#f2f2ee", "band": [{"y0": -3.0, "y1": 0.05, "farg": "#7b7d7c"}]},
       "Flygeln på baksidan av den grå villan vid Platåvägens början (form från OpenStreetMap, färg efter foto).")
# H823 vid Platåvägen (utkast 49, efter foto från Platåvägen): gul trävilla med "Villa Villekulla"-känsla. Huvudkroppen med den branta gaveln mot
# gatan är H823; tvärhuset på baksidan och den låga utbyggnaden mot söder är egna delar. u går söderut längs gaveln, v västerut in i huset.
P23_O, P23_U = (-868.6, 231.4), (-0.63324, 0.77396)
P23_W, P23_R, P23_P = lokal(P23_O, P23_U); P23_B, P23_FRAM = 9.95, 12.4
P23_ATTR = {"typ": "villa", "vagg": "#f0e2a6", "panel": True, "karmFarg": "#ffffff", "takfarg": "#d8b866", "takfotFarg": "#ffffff", "takUndersida": "#f6f1e2",
            "band": [{"y0": -3.0, "y1": -0.05, "farg": "#c9c5b8"}]}
husdel("h823_tvarhus", "", P23_R(-0.5, P23_B + 0.5, P23_FRAM, 19.68), P23_P(-0.5, P23_B + 0.5, P23_FRAM, 19.68),
       {**P23_ATTR, "van": 2, "fh": 3.0, "tak": "sadel", "taklutning": 1.5, "takUtsprang": 0.4},
       "Tvärhuset på baksidan av den gula villan vid Platåvägen: brant tak med vita vindskivor och spira (efter foto).")
husdel("h823_utbyggnad", "", P23_R(P23_B, 12.13, 3.62, P23_FRAM), P23_P(P23_B, 12.13, 3.62, P23_FRAM),
       {**P23_ATTR, "van": 1, "fh": 3.0, "tak": "platt", "kantFarg": "#1d1d1d", "kantHojd": 0.08},
       "Låg utbyggnad mot söder på den gula villan, terrass med svart räcke på taket (efter foto).")
# Circle K vid rondellen (utkast 50, efter foto från rondellen): OSM-huset H046 ("Circle K Gnesta", korsformat) blir butiken i norra delen och
# taket över pumparna en egen del framför den västra halvan. u går mot SSO (mot rondellen), v mot VSV (mot Östra Storgatan).
P46_O, P46_U = (982.4, 911.9), (0.38256, 0.92393)
P46_W, P46_R, P46_P = lokal(P46_O, P46_U)
husdel("circlek_tak", "Circle K Gnesta", P46_R(2.0, 16.0, 17.0, 29.0), P46_P(2.0, 16.0, 17.0, 29.0),
       {"typ": "bensintak", "van": 1, "fh": 5.0, "vagg": "#f2f2f0", "tak": "platt", "takfarg": "#d9d9d6", "adress": "Östra Storgatan 71"},
       "Taket över pumparna på Circle K: röd fris med vit text, vita pelare och tre pumpöar (efter foto från rondellen).")

# Längan mellan Kullagatan och torget, norr om Torggatan (H200, utkast 59, foton från Torggatan 12 och 5): tre förskjutna huskroppar i fyra
# våningar med sadeltak i rött tegel. Den västra och den östra är i gult tegel, den mittersta i rosarött. Varje del är en egen rektangel
# (SE-hörn, SV-hörn, djup); u går från sydöstra hörnet västerut längs fasaden mot Torggatan och v norrut in i huset.
KULLA = {"v": ((-197.2, 90.5), (-227.1, 84.4), 11.2), "m": ((-167.4, 92.2), (-196.3, 86.4), 11.75), "o": ((-140.0, 92.8), (-166.4, 87.2), 11.05)}
def _kulla_ram(k_):
    se, sv, d_ = KULLA[k_]; L_ = math.hypot(sv[0] - se[0], sv[1] - se[1]); return se, ((sv[0] - se[0]) / L_, (sv[1] - se[1]) / L_), L_, d_
KULLA_GUL, KULLA_ROSA, KULLA_TAK = "#dcb884", "#cb917c", "#a85a42"
def _kulla_attr(farg): return {"typ": "flerbostad", "van": 4, "fh": 2.8, "tegel": "ljus", "vagg": farg, "tak": "sadel", "taklutning": 0.5, "takfarg": KULLA_TAK,
                               "takUtsprang": 0.5, "takfotFarg": "#f1efe8", "gavelUtsprang": 0.3, "band": [{"y0": -3.0, "y1": -0.12, "farg": "#9b9a94"}]}
for k_, oid_, farg_, txt_ in (("m", "h200_mitt", KULLA_ROSA, "Mittdelen av längan vid Kullagatan: rosarött tegel i fyra våningar, sadeltak i rött tegel och tre balkongstaplar med vita bågar överst (efter foto från Torggatan 12)."),
                              ("o", "h200_ost", KULLA_GUL, "Östra delen av längan vid Kullagatan: gult tegel i fyra våningar, sadeltak i rött tegel och balkongstaplar med pergola överst (efter foto från Torggatan 5).")):
    _se, _u, _l, _d = _kulla_ram(k_); _w, _r, _p = lokal(_se, _u)
    husdel(oid_, "", _r(0.0, _l, 0.0, _d), _p(0.0, _l, 0.0, _d), _kulla_attr(farg_), txt_)
# trapphusen på norra sidan där delarna möts (finns i OpenStreetMap, syns inte på fotona)
for k_, oid_, farg_, u0_, u1_, v1_ in (("m", "h200_trapp1", KULLA_GUL, 25.7, 34.2, 14.2), ("o", "h200_trapp2", KULLA_ROSA, 25.0, 32.7, 13.7)):
    _se, _u, _l, _d = _kulla_ram(k_); _w, _r, _p = lokal(_se, _u)
    husdel(oid_, "", _r(u0_, u1_, 9.0, v1_), _p(u0_, u1_, 9.0, v1_), {**_kulla_attr(farg_), "tak": "platt", "takfarg": "#5a5654", "utanFonster": True},
           "Trapphus på längans norra sida (läge från OpenStreetMap; utseendet är antaget).")

# Västra Storgatan 25 (H070, utkast 64, foto från infarten): lokalt system med origo i husets nordvästra hörn, u längs fasaden mot
# gatan (åt nordost) och v bort från gatan in i huset. Huset ligger på u 0–19,5 och v 0–9,07; gatan går längs v ≈ −17.
V25_O, V25_U = (-499.8, -115.8), (0.8045, 0.5940)
V25_W, V25_R, V25_P = lokal(V25_O, V25_U)
husdel("h070_garage", "", V25_R(-12.6, -6.9, -2.0, 4.2), V25_P(-12.6, -6.9, -2.0, 4.2),
       {"typ": "bod", "van": 1, "fh": 2.7, "vagg": "#e4dfd0", "panel": True, "utanFonster": True, "tak": "platt", "takfarg": "#4a4a4a", "kantFarg": "#f1efe8", "kantHojd": 0.2},
       "Garage i ljus panel med platt tak och mörkgrå port (efter foto från infarten på Västra Storgatan). Läget är uppskattat från fotot; garaget finns inte i OpenStreetMap.")

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
TIDIGARE = json.load(open(os.path.join(HERE, 'id_v2.json'), encoding='utf-8'))
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
ANDRINGAR["H024"] = {**BR_TEGEL, "typ": "centrum", "van": 2, "fh": 3.5, "rekt": BR_R(9.4, 44.15, 1.2, 21.3), "sakerhet": "foto",
                     "band": [{"y0": -2.0, "y1": 3.2, "farg": "#ecebe6"}, {"y0": 6.4, "y1": 7.05, "farg": "#cdbb94"}],
                     "skyltar": [{"text": "", "stil": "garageport", "vid": BR_W(u_, 1.2), "mot": BR_MOT, "hojd": 1.6, "hgt": 3.1, "bredd": 3.1, "utanTak": True, "bg": "#7c8086"} for u_ in (40.6, 36.8, 33.0, 29.2)]
                              + [{"text": "", "stil": "garageport", "vid": BR_W(u_, 1.2), "mot": BR_MOT, "hojd": 1.65, "hgt": 3.3, "bredd": 2.7, "utanTak": True, "bg": "#b3262a"} for u_ in (20.6, 17.4, 14.2)]
                              + [{"text": "", "stil": "glasvagg", "vid": BR_W(17.4, 1.2), "mot": BR_MOT, "hojd": 5.0, "hgt": 2.6, "bredd": 10.2, "utanTak": True, "bg": "#3b4c58"},
                                 {"text": "", "vid": BR_W(24.6, 1.2), "mot": BR_MOT, "hojd": 1.1, "hgt": 2.2, "bredd": 1.0, "utanTak": True, "bg": "#4a3426"}],
                     "not": "Gnesta brandstation: lång tvåvåningsdel i rött tegel med vit bottenvåning, fyra grå och tre röda garageportar mot Kullagatan, glasat övre plan över de röda portarna och ljus takfotslist (efter foto)."}
H226_SYD = [-254.0, 140.0]; H226_OST = [-200.0, 84.0]
ANDRINGAR["H226"] = {"typ": "flerbostad", "van": 5, "fh": 2.9, "tegel": True, "vagg": "#ffffff", "tak": "platt", "takfarg": "#4a4744", "sakerhet": "foto",
                     "band": [{"y0": -2.0, "y1": 2.95, "farg": "#d9d7d0"}, {"y0": 13.95, "y1": 14.6, "farg": "#c8b88f"}],
                     "skyltar": [butik([-255.0, 87.8], H226_SYD, 3.6, 2.0, 1.45), butik([-259.5, 87.0], H226_SYD, 3.0, 2.0, 1.45),
                                 butik([-245.2, 82.0], H226_OST, 2.4, 2.0, 1.45), butik([-245.7, 85.2], H226_OST, 2.4, 2.0, 1.45),
                                 {"text": "Bokcafé", "vid": [-249.6, 88.8], "mot": H226_SYD, "hojd": 3.3, "bg": "#2a2826", "fg": "#f2ece0", "hgt": 0.62, "bredd": 2.0, "utanTak": True, "kursiv": True},
                                 {"text": "", "stil": "garageport", "vid": [-251.8, 69.6], "mot": H226_OST, "hojd": 1.15, "hgt": 2.3, "bredd": 2.5, "utanTak": True, "bg": "#7c8086"},
                                 {"text": "", "stil": "garageport", "vid": [-252.3, 72.4], "mot": H226_OST, "hojd": 1.15, "hgt": 2.3, "bredd": 2.5, "utanTak": True, "bg": "#7c8086"}],
                     "markiser": [{"vid": [-255.0, 87.8], "mot": H226_SYD, "hojd": 2.75, "bredd": 4.0, "djup": 1.0, "farg": ["#2e7d5f", "#efeee8"]}],
                     "balkonger": [{"vid": [-252.9, 75.6], "mot": H226_OST, "y": y_, "b": 2.4, "d": 1.2, "farg": "#b9b5ab", "racke": True} for y_ in (2.9, 5.8, 8.7, 11.6)],
                     "not": "Bostadshus i rött tegel i fem våningar med ljus bottenvåning och ljus takfotslist; Bokcafé i hörnet mot Kullagatan, balkonger i innerhörnet, garage i bottenplan, gräsmatta med rött staket (efter foto)."}
MOT_H010 = H010_W(21.0, -60.0)
def _h010_skylt(u, **kw): return {"vid": H010_W(u, 0.0), "mot": MOT_H010, "utanTak": True, **kw}
_h010 = [
    # Svensk Fastighetsförmedling (östra änden)
    _h010_skylt(37.6, text="SvenskFastighetsförmedling", hojd=3.75, bg="transparent", fg="#ffffff", hgt=0.55, bredd=6.2),
    _h010_skylt(40.3, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=3.0), _h010_skylt(37.9, text="", stil="butik", hojd=1.3, bg="#2a2c2e", hgt=2.3, bredd=1.1),
    _h010_skylt(35.3, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=3.2),
    _h010_skylt(32.6, text="", hojd=1.25, bg="#6b4a2e", hgt=2.3, bredd=1.2),
    # Salong Carina
    _h010_skylt(29.4, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=2.4), _h010_skylt(27.8, text="", stil="butik", hojd=1.3, bg="#2a2c2e", hgt=2.3, bredd=1.0),
    _h010_skylt(28.9, text="Salong Carina", hojd=2.75, bg="#1d1d1d", fg="#ffffff", hgt=0.45, bredd=2.6, kursiv=True),
    # Direkten
    _h010_skylt(25.0, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=2.6), _h010_skylt(23.2, text="", stil="butik", hojd=1.3, bg="#2a2c2e", hgt=2.3, bredd=1.0),
    _h010_skylt(21.6, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=2.0),
    _h010_skylt(24.0, text="Direkten", hojd=2.75, bg="#ffffff", fg="#c8202f", hgt=0.45, bredd=2.2, kursiv=True),
    _h010_skylt(22.4, text="Direkten", hojd=4.45, bg="transparent", fg="#e0263a", hgt=0.6, bredd=2.0, kursiv=True),
    _h010_skylt(26.4, text="SPEL", hojd=2.6, bg="#f2c418", fg="#1a1a1a", hgt=0.5, bredd=0.8),
    _h010_skylt(18.6, text="", hojd=1.25, bg="#6b4a2e", hgt=2.3, bredd=1.2),
    # Röda Korset (västra änden)
    _h010_skylt(15.6, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=2.2), _h010_skylt(13.9, text="", stil="butik", hojd=1.3, bg="#2a2c2e", hgt=2.3, bredd=1.1),
    _h010_skylt(12.0, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=2.4), _h010_skylt(6.6, text="", stil="butik", hojd=1.45, bg="#2a2c2e", hgt=2.0, bredd=6.2),
    _h010_skylt(12.0, text="Second Hand", hojd=2.72, bg="#f4f2ec", fg="#1d1d1d", hgt=0.4, bredd=2.3),
    _h010_skylt(6.6, text="", stil="rodakorset", hojd=2.72, bg="#f4f2ec", hgt=0.4, bredd=6.0),
    _h010_skylt(15.6, text="", stil="rodakorset", hojd=2.72, bg="#f4f2ec", hgt=0.4, bredd=2.1),
    _h010_skylt(1.4, text="V.Storgatan 1–9", hojd=2.3, bg="#f2f0ea", fg="#2a2a2a", hgt=0.42, bredd=1.5)]
ANDRINGAR["H010"] = {"typ": "flerbostad", "van": 3, "fh": 3.0, "vagg": H010_VAGG, "tak": "sadel", "takfarg": H010_TAK, "rekt": H010_R(0.0, 42.6, 0.0, 12.7), "sakerhet": "foto",
                     "band": [{"y0": -2.0, "y1": 3.0, "farg": "#3a3d42"}, {"y0": 3.0, "y1": 3.22, "farg": "#efeee8"}],
                     "skyltar": _h010,
                     "markiser": [{"vid": H010_W(37.8, 0.0), "mot": MOT_H010, "hojd": 2.95, "bredd": 7.4, "djup": 0.9, "farg": ["#1f4f9e", "#f2c418"]}],
                     "balkonger": [{"vid": H010_W(1.9, 0.0), "mot": MOT_H010, "y": y_, "b": 3.4, "d": 1.5, "farg": "#cfccc4"} for y_ in (3.25, 6.25)],
                     "burspråk": [{"vid": H010_W(42.6, 2.2), "mot": H010_W(90.0, 6.0), "y0": 3.25, "y1": 9.0, "b": 2.6, "d": 0.9}],
                     "not": "Rödputsat hus i tre våningar med sadeltak, bottenvåning i mörk sten med vit list; butiker från öster: Svensk Fastighetsförmedling, Salong Carina, Direkten och Röda Korset; burspråk på gaveln mot Färghuset och svängda balkonger i västra hörnet (efter foton)."}
# H200 längre söderut (syns i bakgrunden på fotot): orangeröd fasad med vita balkongfronter våning för våning
ANDRINGAR["H200"] = {"vagg": "#bf6b4b", "takfarg": "#5a4a44", "sakerhet": "foto",
                     "band": [{"y0": 2.75, "y1": 3.75, "farg": "#ebe8e0"}, {"y0": 5.75, "y1": 6.75, "farg": "#ebe8e0"}],
                     "not": "Orangeröd fasad med rader av vita balkongfronter (efter foto)."}
def _es(u, **kw): return {"vid": H008_W(u, 0.0), "mot": MOT_H008, "utanTak": True, **kw}
_elon_sk = [_es(18.0, text="", stil="elonband", hojd=3.25, bg="#1f2d6e", hgt=0.55, bredd=35.6),
            _es(30.6, text="elon", hojd=4.55, bg="#25368a", fg="#ffffff", hgt=0.95, bredd=1.05),
            _es(3.2, text="", stil="butik", hojd=1.55, bg="#2a2c2e", hgt=2.4, bredd=4.2),
            _es(11.6, text="", stil="elonposter", hojd=1.6, bg="#ffffff", hgt=2.5, bredd=2.0, text2="Välkommen hem"),
            _es(13.8, text="", stil="elonposter", hojd=1.6, bg="#ffffff", hgt=2.5, bredd=2.0, text2="Noga utvalt för varje rum"),
            _es(17.4, text="", stil="butik", hojd=1.6, bg="#2a2c2e", hgt=2.3, bredd=3.0), _es(20.9, text="", stil="butik", hojd=1.6, bg="#2a2c2e", hgt=2.3, bredd=3.0),
            _es(23.4, text="", stil="butik", hojd=1.4, bg="#2a2c2e", hgt=2.5, bredd=1.3), _es(26.2, text="", stil="butik", hojd=1.6, bg="#2a2c2e", hgt=2.3, bredd=3.2),
            _es(29.8, text="", stil="butik", hojd=1.6, bg="#2a2c2e", hgt=2.3, bredd=3.2), _es(33.4, text="", stil="butik", hojd=1.6, bg="#2a2c2e", hgt=2.3, bredd=3.0)]
ANDRINGAR["H008"] = {"typ": "affar", "van": 3, "fh": 3.0, "vagg": "#a9aea8", "tak": "sadel", "taklutning": 0.22, "takfarg": "#6d7073", "panel": True, "sakerhet": "foto",
                     "rekt": H008_R(0.0, H008_SKIFTE, 0.0, 12.0), "skyltar": _elon_sk,
                     "not": "Elon: grå stående panel i tre våningar med låglutande tak, butiksplan med stora skyltfönster och blått skyltband med elon-logga (efter foto)."}
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
# H068: ljus träfasad bakom balkongerna, flackt sadeltak med stort utsprång och mörkröd takfotsbräda (efter foton)
_rb = []; _box = []; _st = []
def _h068_ribba(u0, u1, y0, y1, farg, v=-0.12, delning=0.13):
    c_ = H068_W((u0 + u1) / 2, v); _rb.append({"x": c_[0], "z": c_[1], "b": round(u1 - u0, 2), "y0": y0, "y1": y1, "rot": H068_ROT, "farg": farg, "delning": delning})
LJUS, MORKROD = "#e6dcc1", "#74302f"
for y_ in (2.98, 5.93):   # balkongplattor längs hela fasaden
    c_ = H068_W(40.5, 0.72); _box.append({"x": c_[0], "z": c_[1], "y": y_, "b": 63.2, "h": 0.22, "d": 1.74, "rot": H068_ROT, "farg": "#d9d3c6"})
for (u0, u1, f2, f3) in ((8.9, 19.7, MORKROD, LJUS), (19.7, 36.4, LJUS, LJUS), (36.4, 46.4, LJUS, LJUS), (46.4, 63.6, LJUS, LJUS), (63.6, 72.1, MORKROD, LJUS)):
    _h068_ribba(u0, u1, 3.2, 4.85, f2); _h068_ribba(u0, u1, 6.15, 7.75, f3)
for uc in (9.5, 19.7, 36.4, 46.4, 63.6, 71.5):   # mörkröda ribbskärmar över båda balkongvåningarna
    w_ = 1.2; _h068_ribba(uc - w_ / 2, uc + w_ / 2, 3.2, 8.45, MORKROD, v=-0.2, delning=0.09)
for ue in (8.95, 72.05):   # gavelskärmar vid balkongernas ändar
    c_ = H068_W(ue, 0.72); _rb.append({"x": c_[0], "z": c_[1], "b": 1.74, "y0": 3.2, "y1": 8.45, "rot": round(H068_ROT + math.pi / 2, 4), "farg": MORKROD, "delning": 0.09})
for u_ in (12.5, 16.5, 23.0, 28.0, 33.0, 40.0, 43.5, 50.0, 55.0, 60.0, 66.5, 69.5):   # tunna vita stänger från takfoten
    c_ = H068_W(u_, -0.08); _st.append({"x": c_[0], "z": c_[1], "y0": 3.2, "y1": 8.6})
ANDRINGAR["H068"] = {"typ": "centrum", "van": 3, "fh": 2.95, "hojd": 8.9, "vagg": "#ece5d2", "karmFarg": "#3b302b", "tak": "sadel", "taklutning": 0.2,
                     "takfarg": "#3c3c3e", "takUtsprang": 2.0, "takfotFarg": "#6b2b2b", "rekt": H068_R(8.9, 72.1, 1.6, 19.9), "poly": H068_P(8.9, 72.1, 1.6, 19.9),
                     "fasadBoxar": _box, "ribbor": _rb, "stanger": _st, "sakerhet": "foto",
                     "not": "Västra Storgatan 11: gult tegel med butiker i bottenvåningen (Järna Gnesta Sportbutik), två våningar balkonger bakom ljusa stående ribbor med mörkröda ribbskärmar, flackt sadeltak med stort utsprång (efter foton)."}
ANDRINGAR["H385"] = {"typ": "flerbostad", "van": 5, "fh": 3.0, "vagg": "#e9ebea", "tak": "platt", "takfarg": "#4a4c4f", "karmFarg": "#2e2e30", "sakerhet": "foto",
                     "not": "Margretedalsvägen 15: vita längor i fem våningar kring det höga korallröda hörnhuset (efter foto)."}
# H194 (Thulegatan 3, Gnesta Hem): vitt funkishus i två höga våningar med platt tak, två halvrunda trapphus mot Thulegatan,
# röda dörrar, Gnesta Hems blå G-logga, antennmast på taket och en tre våningar hög del i södra änden (efter foto)
H194_U = (0.1911, -0.9816)
H194_W, H194_R, H194_P = lokal((-400.7, 63.5), H194_U)   # u norrut längs fasaden mot Thulegatan från södra änden, v = 0 fasaden, huset mot negativa v
MOT_H194 = H194_W(30.0, 40.0)
_mast = H194_W(21.5, -4.0)
ANDRINGAR["H194"] = {"namn": "Gnesta Hem", "typ": "centrum", "van": 2, "fh": 3.8, "vagg": "#f1f0ec", "tak": "platt", "takfarg": "#b7b6b0", "karmFarg": "#2b2b2b", "sakerhet": "foto",
                     "rekt": H194_R(0.0, 61.2, -15.4, 0.0), "poly": H194_P(0.0, 61.2, -15.4, 0.0),
                     "volymer": [{"poly": H194_P(0.0, 12.5, -15.4, 0.0), "h": 10.8}],
                     "rundaTorn": [{"vid": H194_W(u_, 0.0), "mot": MOT_H194, "r": 2.3, "h": 10.0} for u_ in (21.0, 41.5)],
                     "skyltar": [{"vid": H194_W(25.2, 0.0), "mot": MOT_H194, "text": "", "stil": "gnestahem", "hojd": 4.9, "hgt": 1.9, "bredd": 1.9, "bg": "transparent", "utanTak": True},
                                 {"vid": H194_W(12.9, 0.0), "mot": MOT_H194, "text": "G", "stil": "gnestahem", "hojd": 3.1, "hgt": 0.7, "bredd": 0.7, "bg": "transparent", "utanTak": True}],
                     "stanger": [{"x": _mast[0], "z": _mast[1], "y0": 7.6, "y1": 15.5, "farg": "#9a9da0"}],
                     "fasadBoxar": [{"x": _mast[0], "z": _mast[1], "y": 13.0 + 1.3 * k_, "b": 1.6 - 0.3 * k_, "h": 0.05, "d": 0.05, "rot": 0.4, "farg": "#9a9da0"} for k_ in range(3)],
                     "not": "Thulegatan 3: Gnesta Hems vita funkishus med halvrunda trapphus, röda dörrar och blå G-logga (efter foto)."}
# ================================================================== PÅSKÄGG: Granbackavägen 108 (H1605), gaveln längst österut i längan (efter foton)
# ljusgult stående träpanel, vita knutar och vit gördel mellan våningarna, rödbrunt tegeltak, farstukvistar med rött plåttak, vita stolpar och räcken,
# vita dörrar (108 med smalt svart glas), brevlådor, runda svarta lampor, stuprör, antenn och ett grått räcke uppe vid nocken
GB_U = (-0.92166, 0.38783)
GB_W, GB_R, GB_P = lokal((-1119.35, 79.99), GB_U)   # u västerut längs entrésidan från östra gaveln, v norrut (ut mot parkeringen); huset ligger vid v -11.08..0
GB_V = (-GB_U[1], GB_U[0]); GB_YAW = round(-math.atan2(GB_U[1], GB_U[0]), 4)   # lådornas x-axel längs u, z-axel ut från fasaden
GB_L, GB_D, GB_N = 30.89, 11.08, 6; GB_WU = GB_L / GB_N
VIT, GLAS, PERS = "#f4f3ee", "#2b3540", "#cfd3d6"
def radlanga(O, U, L, D, N, slitsdorr=(), pers=(), vp=(4,), antenn=None):
    """Radhuslänga i Granbacka-stil (efter foton av Granbackavägen 108): O = hörnet vid östra gaveln på entrésidan, U västerut längs entrésidan.
    Ger fasadlådor (fönster, farstukvistar, dörrar, brevlådor, lampor, stuprör, hängrännor, knutar, värmepumpar, nockräcke) och ev. antenn."""
    W, _r, _p = lokal(O, U); YAW = round(-math.atan2(U[1], U[0]), 4); WU = L / N; ut = []
    def box(u, v, y, b, h, d, farg, rot=None, rx=0.0, form=None):
        x_, z_ = W(u, v); e = {"x": x_, "z": z_, "y": round(y, 3), "b": round(b, 3), "h": round(h, 3), "d": round(d, 3), "rot": YAW if rot is None else rot, "farg": farg}
        if rx: e["rx"] = round(rx, 4)
        if form: e["form"] = form
        ut.append(e)
    def fonster(u, yc, w, hh, sida="n", poster=2, pers_=False):
        """fönster med vit karm, mörkt glas, spröjs och fönsterbleck; sida n = entrésidan (v=0), s = trädgårdssidan (v=-D), o/w = gavlarna (u=0 / u=L)"""
        if sida in ("n", "s"):
            v0, ut_ = (0.0, 1) if sida == "n" else (-D, -1)
            box(u, v0 + ut_ * 0.03, yc - hh / 2 - 0.07, w + 0.14, hh + 0.14, 0.06, VIT)
            box(u, v0 + ut_ * 0.055, yc - hh / 2, w, hh, 0.06, GLAS)
            if pers_: box(u, v0 + ut_ * 0.06, yc + hh * 0.05, w - 0.04, hh * 0.45, 0.06, PERS)
            if poster == 2: box(u, v0 + ut_ * 0.07, yc - hh / 2, 0.06, hh, 0.05, VIT)
            box(u, v0 + ut_ * 0.08, yc - hh / 2 - 0.1, w + 0.2, 0.05, 0.12, VIT)
        else:
            u0, ut_ = (0.0, -1) if sida == "o" else (L, 1); rot = round(YAW + math.pi / 2, 4)
            box(u0 + ut_ * 0.03, u, yc - hh / 2 - 0.07, w + 0.14, hh + 0.14, 0.06, VIT, rot)
            box(u0 + ut_ * 0.055, u, yc - hh / 2, w, hh, 0.06, GLAS, rot)
            box(u0 + ut_ * 0.08, u, yc - hh / 2 - 0.1, w + 0.2, 0.05, 0.12, VIT, rot)
    for k in range(N):
        b0 = k * WU; jamn = k % 2 == 0; grans = b0 if not jamn else b0 + WU
        pos = lambda d_: (b0 + d_) if jamn else (2 * grans - ((grans - WU) + d_))   # udda enheter spegelvända mot paret
        dorr, brev, f_stor, f_liten = pos(3.45), pos(4.45), pos(1.6), pos(4.4)
        p0, p1 = sorted((pos(2.75), pos(5.0)))
        pe = k in pers
        fonster(f_stor, 1.5, 1.3, 1.15, "n", 2, pe); fonster(f_stor, 4.2, 1.3, 1.15, "n", 2, pe); fonster(f_liten, 4.5, 0.55, 0.55, "n", 1)
        # farstukvist: betongplatta, rött plåttak som lutar ut, vita stolpar och vita liggande räckesribbor på sidorna
        pm = (p0 + p1) / 2; pb = p1 - p0
        box(pm, 0.7, -0.05, pb, 0.2, 1.4, "#b9b7b0")
        box(pm, 0.72, 2.32, pb + 0.15, 0.05, 1.5, "#9c3a2b", rx=0.17)
        box(pm, 1.45, 2.22, pb + 0.15, 0.12, 0.05, "#9c3a2b")
        for uu in (p0 + 0.06, p1 - 0.06):
            box(uu, 1.38, 0.1, 0.1, 2.2, 0.1, VIT)
            for yy in (0.25, 0.48, 0.71, 0.94): box(uu, 0.72, yy, 0.04, 0.08, 1.3, VIT)
        # dörr, brevlåda, lampa och skylt
        box(dorr, 0.04, 0.15, 1.0, 2.1, 0.06, VIT); box(dorr, 0.05, 0.12, 1.14, 0.06, 0.08, VIT)
        if k in slitsdorr: box(dorr - 0.22, 0.07, 0.75, 0.11, 1.35, 0.04, "#1b1f24")
        else: box(dorr, 0.07, 1.45, 0.42, 0.5, 0.04, GLAS)
        box(dorr, 0.075, 1.05, 0.06, 0.06, 0.06, "#9a9da0")
        box(brev, 0.11, 1.05, 0.42, 0.48, 0.22, "#f2f1ec")
        box(brev, 0.23, 1.47, 0.42, 0.03, 0.04, "#9a9da0")
        box(dorr - 0.64 if jamn else dorr + 0.64, 0.12, 1.98, 0.22, 0.22, 0.22, "#151617", form="klot")
        box(dorr - 0.64 if jamn else dorr + 0.64, 0.05, 2.05, 0.08, 0.08, 0.1, "#151617")
        # trädgårdssidan: altandörr och fönster nere, två fönster uppe
        mid = b0 + WU / 2
        box(mid - 0.9, -D - 0.03, 0.1, 1.0, 2.15, 0.06, VIT); box(mid - 0.9, -D - 0.06, 0.18, 0.84, 1.95, 0.05, GLAS)
        fonster(mid + 1.1, 1.5, 1.3, 1.15, "s"); fonster(mid - 1.0, 4.2, 1.1, 1.1, "s"); fonster(mid + 1.2, 4.2, 1.1, 1.1, "s")
    # stuprör vid paren, hängränna längs takfoten, vita knutbrädor, värmepumpar, gavelfönster
    for uu in [2 * j * WU - 0.05 for j in range(1, (N + 1) // 2) if 2 * j < N] + [0.25, L - 0.25]:
        box(uu, 0.14, 0.15, 0.09, 5.3, 0.09, VIT, form="cyl")
    box(L / 2, 0.52, 5.33, L + 0.9, 0.12, 0.13, VIT); box(L / 2, -D - 0.52, 5.33, L + 0.9, 0.12, 0.13, VIT)
    for uu, vv in ((0.0, 0.0), (L, 0.0), (0.0, -D), (L, -D)):
        box(uu + (0.09 if uu == 0 else -0.09), vv + (0.03 if vv == 0 else -0.03), 0.15, 0.17, 5.4, 0.05, VIT)
        box(uu + (-0.03 if uu == 0 else 0.03), vv + (-0.09 if vv == 0 else 0.09), 0.15, 0.05, 5.4, 0.17, VIT)
    for e_ in vp: box(e_ * WU + 1.0, 0.18, 0.95, 0.8, 0.55, 0.3, "#eceeee")
    for sida in ("o", "w"):
        fonster(-D * 0.2708, 4.3, 0.7, 0.7, sida); fonster(-D * 0.7310, 4.3, 0.7, 0.7, sida); fonster(-D * 0.4964, 1.5, 1.0, 1.0, sida)
    # grått räcke uppe vid nocken på norra takfallet
    vr = -(D / 2 - 0.79); box(5.8, vr, 5.5 - vr * 0.36 + 0.03, 6.5, 0.07, 0.55, "#5d6166", rx=round(math.atan(0.36), 4))
    stanger = []
    if antenn is not None:   # tv-antenn med tre tvärslåar
        au = antenn; vm = -D / 2 + 0.14; a_ = W(au, vm)
        stanger = [{"x": a_[0], "z": a_[1], "y0": 7.3, "y1": 9.7, "farg": "#8e9194"}, {"x": W(au + 0.45, vm)[0], "z": W(au + 0.45, vm)[1], "y0": 7.3, "y1": 9.0, "farg": "#8e9194"}]
        for yy, bb in ((9.2, 1.1), (8.75, 0.8), (8.35, 0.6)): box(au, vm, yy, bb, 0.03, 0.03, "#8e9194", rot=round(YAW + 0.5, 4))
    return ut, stanger
_gb, GB_STANGER = radlanga((-1119.35, 79.99), GB_U, GB_L, GB_D, GB_N, slitsdorr=(0,), pers=(0, 3), vp=(4,), antenn=1.3)
_nr = GB_W(4.05, 0.12)
ANDRINGAR["H1605"] = {"namn": "Samuels hus", "adress": "Granbackavägen 108", "alias": ["Samuel"], "typ": "radhus", "van": 2, "fh": 2.75, "vagg": "#ead48f", "panel": True, "utanFonster": True, "sakerhet": "foto",
                      "tak": "sadel", "taklutning": 0.36, "takfarg": "#a6492d", "takUtsprang": 0.5, "takfotFarg": "#f3f1ea", "takUndersida": "#f3f1ea",
                      "rekt": GB_R(0.0, GB_L, -GB_D, 0.0), "poly": GB_P(0.0, GB_L, -GB_D, 0.0),
                      "band": [{"y0": -1.0, "y1": 0.18, "farg": "#a9a8a2"}, {"y0": 2.72, "y1": 2.86, "farg": "#f4f3ee"}],
                      "fasadBoxar": _gb, "stanger": GB_STANGER,
                      "skyltar": [{"vid": _nr, "mot": GB_W(4.0, 30.0), "text": "108", "bg": "#f6f6f2", "fg": "#1d1d1f", "hojd": 1.62, "hgt": 0.17, "bredd": 0.27, "utanTak": True, "ut": 0.06}],
                      "not": "Radhuslänga i ljusgul träpanel med rött tegeltak. Samuels hus, Granbackavägen 108, är gavellägenheten längst österut (påskägg, efter foton)."}
# grannhusen: längan österut i samma stil, de två garagelängorna vid servicevägen och de små gula förråden
# längan österut (H1580) är byggd exakt som Granbackavägen 108: samma enheter, farstukvistar, fönster, dörrar, lampor och detaljer (utkast 43)
_hh = next(h for h in hus if h["id"] == "H1580"); _x, _z, _b, _d, _r = _hh["rekt"]
H80_U = (math.cos(_r), math.sin(_r)) if _b >= _d else (-math.sin(_r), math.cos(_r)); H80_L, H80_D = max(_b, _d), min(_b, _d)
if H80_U[0] > 0: H80_U = (-H80_U[0], -H80_U[1])   # u västerut, v norrut mot entrésidan
_vn = (-H80_U[1], H80_U[0])
H80_O = (_x - H80_U[0] * H80_L / 2 + _vn[0] * H80_D / 2, _z - H80_U[1] * H80_L / 2 + _vn[1] * H80_D / 2)
H80_W, H80_R, H80_P = lokal(H80_O, H80_U); H80_N = max(2, round(H80_L / 5.15))
_b80, _st80 = radlanga(H80_O, H80_U, H80_L, H80_D, H80_N, pers=(1, 5), vp=(2, 6))
ANDRINGAR["H1580"] = {"typ": "radhus", "van": 2, "fh": 2.75, "vagg": "#ead48f", "panel": True, "utanFonster": True, "sakerhet": "foto",
                      "tak": "sadel", "taklutning": 0.36, "takfarg": "#a6492d", "takUtsprang": 0.5, "takfotFarg": "#f3f1ea", "takUndersida": "#f3f1ea",
                      "rekt": H80_R(0.0, H80_L, -H80_D, 0.0), "poly": H80_P(0.0, H80_L, -H80_D, 0.0),
                      "band": [{"y0": -1.0, "y1": 0.18, "farg": "#a9a8a2"}, {"y0": 2.72, "y1": 2.86, "farg": "#f4f3ee"}],
                      "fasadBoxar": _b80, "stanger": _st80,
                      "not": "Radhuslänga i ljusgul träpanel med rött tegeltak, byggd exakt som grannlängan med Granbackavägen 108 (efter foto)."}
def _garage(rkt, dorrar_mot):
    x, z, b, d, rot = rkt; c, s_ = math.cos(rot), math.sin(rot); Wg = lambda lx, lz: (x + lx * c - lz * s_, z + lx * s_ + lz * c)
    ax = (c, s_) if b >= d else (-s_, c); L = max(b, d); D = min(b, d); nrm = (-ax[1], ax[0])
    if (Wg(0, 0)[0] + nrm[0] - dorrar_mot[0]) ** 2 + (Wg(0, 0)[1] + nrm[1] - dorrar_mot[1]) ** 2 > (Wg(0, 0)[0] - nrm[0] - dorrar_mot[0]) ** 2 + (Wg(0, 0)[1] - nrm[1] - dorrar_mot[1]) ** 2: nrm = (-nrm[0], -nrm[1])
    yaw = round(math.atan2(nrm[0], nrm[1]), 4); ut = []; n = 7; steg = L / n
    for i in range(n):
        t = -L / 2 + steg * (i + 0.5); px, pz = x + ax[0] * t + nrm[0] * (D / 2 + 0.03), z + ax[1] * t + nrm[1] * (D / 2 + 0.03)
        ut.append({"x": round(px, 2), "z": round(pz, 2), "y": 0.0, "b": steg - 0.42, "h": 2.15, "d": 0.06, "rot": yaw, "farg": "#b9773b"})
        ut.append({"x": round(px + nrm[0] * 0.02, 2), "z": round(pz + nrm[1] * 0.02, 2), "y": 0.95, "b": 0.12, "h": 0.06, "d": 0.05, "rot": yaw, "farg": "#d0d2d4"})
        for f in (-0.5, 0.5):
            qx, qz = px + ax[0] * f * steg, pz + ax[1] * f * steg; ut.append({"x": round(qx, 2), "z": round(qz, 2), "y": 0.0, "b": 0.36, "h": 2.45, "d": 0.12, "rot": yaw, "farg": "#f1ede0"})
    return ut
_vag_mitt = GB_W(2.5, 27.0)
for hid_ in ("H1591", "H1601"):
    _hh = next(h for h in hus if h["id"] == hid_)
    ANDRINGAR[hid_] = {"namn": "", "typ": "bod", "van": 1, "fh": 2.55, "vagg": "#efe4c4", "panel": True, "utanFonster": True, "tak": "platt", "takfarg": "#2c2d2f", "sakerhet": "foto",
                       "band": [{"y0": 2.36, "y1": 2.62, "farg": "#242527"}, {"y0": -1.0, "y1": 0.12, "farg": "#5d5f61"}],
                       "fasadBoxar": _garage(_hh["rekt"], _vag_mitt), "not": "Låg garagelänga för de boende med bruna portar mot servicevägen (efter foto)."}
for hid_, mot_ in (("H1607", GB_W(3.0, 12.0)),):
    _hh = next(h for h in hus if h["id"] == hid_); x, z, b, d, rot = _hh["rekt"]; c, s_ = math.cos(rot), math.sin(rot)
    ax = (c, s_) if b >= d else (-s_, c); L = max(b, d); sg = 1 if (ax[0] * (mot_[0] - x) + ax[1] * (mot_[1] - z)) > 0 else -1
    gx, gz = x + ax[0] * sg * (L / 2 + 0.04), z + ax[1] * sg * (L / 2 + 0.04); yaw = round(math.atan2(ax[0] * sg, ax[1] * sg), 4); tx, tz = math.cos(yaw), -math.sin(yaw)
    ANDRINGAR[hid_] = {"namn": "", "typ": "bod", "van": 1, "fh": 2.7, "vagg": "#ecdca0", "panel": True, "utanFonster": True, "tak": "sadel", "taklutning": 0.42, "takfarg": "#7c7f83",
                       "takfotFarg": "#f3f1ea", "sakerhet": "foto",
                       "fasadBoxar": [{"x": round(gx, 2), "z": round(gz, 2), "y": 0.05, "b": 1.0, "h": 2.05, "d": 0.06, "rot": yaw, "farg": "#f4f3ee"},
                                      {"x": round(gx - tx * 0.9, 2), "z": round(gz - tz * 0.9, 2), "y": 1.5, "b": 0.2, "h": 0.25, "d": 0.04, "rot": yaw, "farg": "#c4262d"},
                                      {"x": round(gx + tx * 0.75, 2), "z": round(gz + tz * 0.75, 2), "y": 2.05, "b": 0.18, "h": 0.18, "d": 0.18, "rot": yaw, "farg": "#151617", "form": "klot"}],
                       "not": "Litet gult förråd med vit dörr på gaveln (efter foto)."}
# H1593: litet envåningshus i samma färger som Granbackavägen 108 (ljusgul panel, vita knutar och karmar, rödbrunt tegeltak), dörren på norra gaveln
# mot grusvägen mellan häckarna (utkast 43)
_hh = next(h for h in hus if h["id"] == "H1593"); _x, _z, _b, _d, _r = _hh["rekt"]
_ax = (math.cos(_r), math.sin(_r)) if _b >= _d else (-math.sin(_r), math.cos(_r)); _L, _D = max(_b, _d), min(_b, _d)
_mot = GB_W(-6.0, 0.0)
if _ax[0] * (_mot[0] - _x) + _ax[1] * (_mot[1] - _z) < 0: _ax = (-_ax[0], -_ax[1])   # +s mot dörrgaveln i norr
_nr = (-_ax[1], _ax[0]); H93_L, H93_D = _L, _D
H93_W = lambda s_, t_, x0=_x, z0=_z, a=_ax, n=_nr: (x0 + a[0] * s_ + n[0] * t_, z0 + a[1] * s_ + n[1] * t_)
_h93 = []
def _hbox(s_, t_, y, b, h, d, farg, n_, form=None):
    x_, z_ = H93_W(s_, t_); e = {"x": round(x_, 2), "z": round(z_, 2), "y": round(y, 3), "b": round(b, 3), "h": round(h, 3), "d": round(d, 3), "rot": round(math.atan2(n_[0], n_[1]), 4), "farg": farg}
    if form: e["form"] = form
    _h93.append(e)
def _hfonster(s_, t_, n_, w, hh, yc=1.5):
    """fönster i 108-stil på fasaden med utåtnormal n_ (s_, t_ = fasadpunkt)"""
    o = lambda k: (s_ + (n_[2] * k), t_ + (n_[3] * k))
    for k, y, b, h, d, f in ((0.03, yc - hh / 2 - 0.07, w + 0.14, hh + 0.14, 0.06, VIT), (0.055, yc - hh / 2, w, hh, 0.06, GLAS), (0.07, yc - hh / 2, 0.06, hh, 0.05, VIT), (0.08, yc - hh / 2 - 0.1, w + 0.2, 0.05, 0.12, VIT)):
        a_, b_ = o(k); _hbox(a_, b_, y, b, h, d, f, n_[:2])
for sg in (-1, 1):   # långsidorna: två fönster var
    n_ = (_nr[0] * sg, _nr[1] * sg, 0.0, sg)
    for s_ in (-3.4, 1.6): _hfonster(s_, sg * _D / 2, n_, 1.3, 1.15)
_hfonster(-_L / 2, 0.0, (-_ax[0], -_ax[1], -1.0, 0.0), 1.0, 1.0)   # södra gaveln
_ng = (_ax[0], _ax[1])   # norra gaveln: vit dörr med glasruta, lampa, liten röd skylt och en trappsten
_hbox(_L / 2 + 0.04, 0.0, 0.1, 1.0, 2.1, 0.06, VIT, _ng); _hbox(_L / 2 + 0.07, 0.0, 1.4, 0.42, 0.5, 0.04, GLAS, _ng)
_hbox(_L / 2 + 0.08, -0.36, 1.05, 0.06, 0.06, 0.06, "#9a9da0", _ng)
_hbox(_L / 2 + 0.06, 0.9, 1.5, 0.2, 0.25, 0.04, "#c4262d", _ng)
_hbox(_L / 2 + 0.12, -0.78, 2.0, 0.2, 0.2, 0.2, "#151617", _ng, form="klot"); _hbox(_L / 2 + 0.05, -0.78, 2.07, 0.08, 0.08, 0.1, "#151617", _ng)
_hbox(_L / 2 + 0.45, 0.0, -0.05, 1.5, 0.2, 0.8, "#b9b7b0", _ng)
for s_ in (_L / 2, -_L / 2):   # vita knutbrädor
    for t_ in (_D / 2, -_D / 2):
        sa, ta = (1 if s_ > 0 else -1), (1 if t_ > 0 else -1)
        _hbox(s_ + sa * 0.03, t_ - ta * 0.09, 0.15, 0.17, 2.65, 0.05, VIT, (_ax[0] * sa, _ax[1] * sa))
        _hbox(s_ - sa * 0.09, t_ + ta * 0.03, 0.15, 0.17, 2.65, 0.05, VIT, (_nr[0] * ta, _nr[1] * ta))
ANDRINGAR["H1593"] = {"namn": "", "typ": "villa", "van": 1, "fh": 2.75, "vagg": "#ead48f", "panel": True, "utanFonster": True, "sakerhet": "foto",
                      "tak": "sadel", "taklutning": 0.36, "takfarg": "#a6492d", "takUtsprang": 0.4, "takfotFarg": "#f3f1ea", "takUndersida": "#f3f1ea",
                      "band": [{"y0": -1.0, "y1": 0.18, "farg": "#a9a8a2"}], "fasadBoxar": _h93,
                      "not": "Litet envåningshus i samma färger som Granbackavägen 108, dörren mot grusvägen mellan häckarna (efter beskrivning)."}
for hid_ in ("H1553", "H1562", "H1572", "H1578", "H1599", "H1610", "H1613", "H1614"):
    _hh = next((h for h in hus if h["id"] == hid_), None)
    if not _hh: continue
    ANDRINGAR[hid_] = {"tegel": True, "van": 2, "fh": 2.9, "vagg": "#a24f3b", "takfarg": "#d98a5c", "sakerhet": "foto",
                       **({"tak": "sadel", "taklutning": 0.3} if _hh.get("rekt") else {}), "not": "Tegelhus i två våningar med ljust orange tegeltak vid Granbackavägen (efter foto)."}
# ================================================================== PÅSKÄGG Kadriljvägen 1 (H1234): fasaddetaljer, tak, garage, entré, gården och gatuhörnet
# (efter två foton: från infarten vid Menuettvägen och från Menuettvägen norr om huset, utkast 45). Allt läggs som lådor i huvudbyggnadens
# höjdsystem: y över golvet g0; marken ligger plan på y = -0.25 och uppfartens stenläggning på y = -0.13.
_kd = []; KD_STANGER = []
KD_MARK_Y, KD_STEN_Y = -0.25, -0.13
KD_FH, KD_LUT = 2.95, 0.94                                  # väggens höjd till takfoten och takets lutning (brant 1½-planstak)
KD_NOCK_U = (KD_HUS[0] + KD_HUS[1]) / 2
KD_NOCK_Y = KD_FH + (KD_HUS[1] - KD_HUS[0]) / 2 * KD_LUT
KD_KARM = "#f4f3ee"
def _kd_tak(u): return KD_NOCK_Y - abs(u - KD_NOCK_U) * KD_LUT     # huvudtakets yta
def kbox(u, v, y, b, h, d, farg, a=0.0, rx=0.0, form=None):
    """låda med mittpunkt (u, v) och undersida y; b längs riktningen a (0 = +u österut, pi/2 = +v söderut), d tvärs; rx lutar d-axeln nedåt"""
    x_, z_ = KD_W(u, v); e = {"x": x_, "z": z_, "y": round(y, 3), "b": round(b, 3), "h": round(h, 3), "d": round(d, 3), "rot": round(KD_YAW - a, 4), "farg": farg}
    if rx: e["rx"] = round(rx, 4)
    if form: e["form"] = form
    _kd.append(e)
def kskiva(u, v, yc, bredd, langd, tjock, farg, fall, lut):
    """lutande skiva (t.ex. tak) med mitt i (u, v, yc) som faller åt riktningen fall med vinkeln lut"""
    kbox(u, v, yc - tjock / 2, bredd, tjock, langd, farg, fall - math.pi / 2, lut)
def krör(u, v, yc, diam, langd, farg, a):
    """liggande cylinder (t.ex. hjul) med axeln längs riktningen a"""
    kbox(u, v, yc - langd / 2, diam, langd, diam, farg, a - math.pi / 2, math.pi / 2, "cyl")
def kpinne(u, v, y0, y1, diam, farg): kbox(u, v, y0, diam, y1 - y0, diam, farg, form="cyl")
def kklot(u, v, yc, diam, farg): kbox(u, v, yc - diam / 2, diam, diam, diam, farg, form="klot")
def _ut(u, v, n, k): return (u + math.cos(n) * k, v + math.sin(n) * k)
def _o(u, v, a, du, dv):   # punkt du framåt (längs a) och dv åt sidan (a + 90°) från (u, v)
    return (u + du * math.cos(a) - dv * math.sin(a), v + du * math.sin(a) + dv * math.cos(a))
def kfonster(u, v, n, w, hh, yb, poster=1, bleck=True):
    """fönster på väggen genom (u, v) med utåtnormal n: vit karm, mörkt glas, poster och fönsterbleck"""
    a = n - math.pi / 2
    p = _ut(u, v, n, 0.03); kbox(p[0], p[1], yb - 0.07, w + 0.14, hh + 0.14, 0.06, KD_KARM, a)
    g = _ut(u, v, n, 0.055); kbox(g[0], g[1], yb, w, hh, 0.06, KD_GLAS, a)
    for k in range(1, poster):
        q = _o(g[0], g[1], a, -w / 2 + w * k / poster, 0.0); q = _ut(q[0], q[1], n, 0.015); kbox(q[0], q[1], yb, 0.06, hh, 0.05, KD_KARM, a)
    if bleck: p = _ut(u, v, n, 0.08); kbox(p[0], p[1], yb - 0.1, w + 0.2, 0.05, 0.12, KD_KARM, a)
N_N, N_S, N_O, N_V = -math.pi / 2, math.pi / 2, 0.0, math.pi   # utåtnormaler: norr (mot Kadriljvägen), söder, öster (mot Menuettvägen), väster
hu0, hu1, hv0, hv1 = KD_HUS

# --- gavlarna: vit stående lockpanel ovanför teglet, breda vita vindskivor, två fönster i en gemensam omfattning, spira på norra gaveln
for v0, n, fu in ((hv0, N_N, -4.4), (hv1, N_S, -4.7)):
    ut_ = math.sin(n)
    u_ = hu0 + 0.22
    while u_ < hu1 - 0.12:
        top = _kd_tak(u_) - 0.12
        for y0_, y1_ in (((2.22, 3.24), (4.76, top)) if abs(u_ - fu) < 1.18 else ((2.22, top),)):
            if y1_ - y0_ > 0.1: kbox(u_, v0 + ut_ * 0.075, y0_, 0.075, y1_ - y0_, 0.04, "#f7f6f1")
        u_ += 0.3
    kbox(fu, v0 + ut_ * 0.07, 3.27, 2.26, 1.46, 0.05, KD_KARM, n - math.pi / 2)
    for du in (-0.5, 0.5): kfonster(fu + du, v0 + ut_ * 0.07, n, 0.86, 1.14, 3.42, bleck=False)
    kbox(fu, v0 + ut_ * 0.14, 3.24, 2.36, 0.05, 0.13, KD_KARM, n - math.pi / 2)              # fönsterbleck
    kbox(fu, v0 + ut_ * 0.12, 4.73, 2.34, 0.05, 0.09, "#3a3a38", n - math.pi / 2)            # droppbleck
    for sg in (-1, 1):
        ue = (hu1 + 0.4) if sg > 0 else (hu0 - 0.4); ye = KD_FH - 0.4 * KD_LUT
        L = math.hypot(ue - KD_NOCK_U, KD_NOCK_Y - ye)
        kskiva((ue + KD_NOCK_U) / 2, v0 + ut_ * 0.49, (ye + KD_NOCK_Y) / 2 - 0.05, 0.05, L, 0.27, KD_KARM, N_O if sg > 0 else N_V, math.atan(KD_LUT))
kpinne(KD_NOCK_U, hv0 - 0.49, KD_NOCK_Y - 0.1, KD_NOCK_Y + 0.38, 0.05, "#2b2b2b"); kklot(KD_NOCK_U, hv0 - 0.49, KD_NOCK_Y + 0.4, 0.08, "#2b2b2b")

# --- taket: svart plåtklädd skorsten på östra takfallet, takstege upp till skorstenen, ventilationsrör, hängrännor och stuprör, tv-antenn
su, sv_ = -2.35, 4.2
kbox(su, sv_, _kd_tak(su + 0.3) - 0.05, 0.6, 6.45 - _kd_tak(su + 0.3) + 0.05, 0.6, "#55595e")
kbox(su, sv_, 6.45, 0.74, 0.07, 0.74, "#2a2c2f"); kbox(su, sv_, 6.64, 0.58, 0.05, 0.58, "#2a2c2f")
for du, dv in ((-0.22, -0.22), (0.22, -0.22), (-0.22, 0.22), (0.22, 0.22)): kpinne(su + du, sv_ + dv, 6.52, 6.64, 0.04, "#2a2c2f")
for vv in (4.66, 5.06):
    um = (0.32 - 1.98) / 2; kskiva(um, vv, _kd_tak(um) + 0.15, 0.04, (0.32 + 1.98) * math.hypot(1, KD_LUT), 0.05, "#8f9396", N_O, math.atan(KD_LUT))
uu = 0.15
while uu > -1.9:
    kbox(uu, 4.86, _kd_tak(uu) + 0.12, 0.03, 0.03, 0.42, "#8f9396"); uu -= 0.3
for vu, vv in ((-3.6, 1.6), (-3.85, 6.1), (-2.95, 7.4)):
    kpinne(vu, vv, _kd_tak(vu) - 0.1, _kd_tak(vu) + 0.48, 0.13, "#2c2c2c"); kbox(vu, vv, _kd_tak(vu) + 0.48, 0.18, 0.04, 0.18, "#2c2c2c")
for uu in (hu1 + 0.5, hu0 - 0.5):
    kbox(uu, (hv0 + hv1) / 2, 2.24, 0.12, 0.12, hv1 - hv0 + 0.9, "#2a2a2b")
for uu, vv in ((hu1 + 0.5, hv0 + 0.12), (hu1 + 0.5, hv1 - 0.12), (hu0 - 0.5, hv1 - 0.12)): kpinne(uu, vv, KD_MARK_Y, 2.3, 0.08, "#262626")
am = KD_W(KD_NOCK_U, 10.3); KD_STANGER.append({"x": am[0], "z": am[1], "y0": round(KD_NOCK_Y - 0.1, 2), "y1": round(KD_NOCK_Y + 2.1, 2), "farg": "#8e9194"})
kbox(KD_NOCK_U + 0.25, 10.3, KD_NOCK_Y + 1.85, 1.7, 0.035, 0.035, "#8e9194")
for k_ in range(7): kbox(KD_NOCK_U - 0.5 + k_ * 0.25, 10.3, KD_NOCK_Y + 1.85, 0.025, 0.025, 1.05 - k_ * 0.08, "#8e9194")
kbox(KD_NOCK_U + 0.1, 10.3, KD_NOCK_Y + 1.25, 1.1, 0.03, 0.03, "#8e9194", 0.5)
for k_ in range(4):
    q = _o(KD_NOCK_U + 0.1, 10.3, 0.5, -0.4 + k_ * 0.27, 0.0); kbox(q[0], q[1], KD_NOCK_Y + 1.25, 0.022, 0.022, 0.7, "#8e9194", 0.5)

# --- burspråket på gaveln mot Kadriljvägen: vit liggande panel nertill, svart sockel och fönsterbröstning, fönster runt om, valmat plåttak
bu0, bu1, bd, bf = -6.0, -2.6, 0.75, 1.0; bc = (bu0 + bu1) / 2
_bay_sidor = []
for sg in (-1, 1):
    pw = (bu1 if sg > 0 else bu0, 0.0); pf = (bc + sg * bf, -bd); du, dv = pf[0] - pw[0], pf[1] - pw[1]; L = math.hypot(du, dv)
    no = (sg * -dv / L, sg * du / L); _bay_sidor.append(((pw[0] + pf[0]) / 2, (pw[1] + pf[1]) / 2, L, math.atan2(dv, du), no))
def _bay_lager(y0, h, farg, grow=0.0):
    kbox(bc, -(bd + grow) / 2, y0, 2 * bf, h, bd + grow, farg)
    for mu, mv, L, a, no in _bay_sidor:
        kbox(mu + no[0] * (grow / 2 - 0.26), mv + no[1] * (grow / 2 - 0.26), y0, L + 0.02, h, 0.52 + grow, farg, a)
_bay_lager(KD_MARK_Y, 0.12, "#262628", 0.02)
_bay_lager(-0.13, 0.98, "#eeede6")
for yy in (0.1, 0.34, 0.58): _bay_lager(yy, 0.018, "#cac8c0", 0.008)
_bay_lager(0.85, 0.05, "#2a2a2a", 0.035)
_bay_lager(0.9, 1.45, "#f1f0ea")
_bay_lager(2.35, 0.1, KD_KARM, 0.06)
for du in (-0.42, 0.42): kfonster(bc + du, -bd, N_N, 0.72, 1.0, 0.98, bleck=False)
for mu, mv, L, a, no in _bay_sidor: kfonster(mu, mv, math.atan2(no[1], no[0]), 0.55, 1.0, 0.98, bleck=False)
_ry, _yf = 0.6, 2.45
kskiva(bc, -(bd + 0.08) / 2, _yf + _ry / 2 + 0.025, 2 * bf + 0.16, math.hypot(bd + 0.08, _ry), 0.05, "#2f3236", N_N, math.atan(_ry / (bd + 0.08)))
for k_ in range(6):
    kskiva(bc - bf + 0.15 + k_ * (2 * bf - 0.3) / 5, -(bd + 0.08) / 2, _yf + _ry / 2 + 0.06, 0.025, math.hypot(bd + 0.08, _ry), 0.02, "#4b5055", N_N, math.atan(_ry / (bd + 0.08)))
for mu, mv, L, a, no in _bay_sidor:
    kskiva(mu - no[0] * 0.32, mv - no[1] * 0.32, _yf + _ry / 2 + 0.025, L + 0.12, math.hypot(0.8, _ry), 0.05, "#2f3236", math.atan2(no[1], no[0]), math.atan(_ry / 0.8))
kbox(bc, -0.04, _yf + _ry - 0.06, bu1 - bu0 + 0.1, 0.1, 0.08, "#2f3236")
kpinne(bu1 + 0.08, -0.06, KD_MARK_Y, _yf, 0.08, "#262626")                     # stuprör från burspråkets tak

# --- gaveln i övrigt: vit panelparti med fönster väster om burspråket, husnummer och en liten blå skylt på teglet, gatunamnsskylt på panelen
wu0 = -7.35; wc = (wu0 + bu0) / 2; ww = bu0 - wu0
kbox(wc, -0.03, -0.13, ww, 2.35, 0.06, "#f1f0ea"); kbox(wc, -0.035, KD_MARK_Y, ww + 0.02, 0.12, 0.07, "#262628")
for yy in (0.1, 0.34, 0.58): kbox(wc, -0.062, yy, ww, 0.018, 0.01, "#cac8c0")
kbox(wc, -0.07, 0.85, ww + 0.02, 0.05, 0.08, "#2a2a2a")
kfonster(wc, -0.06, N_N, 0.8, 1.0, 0.98, bleck=False)
kbox(-0.75, -0.012, 1.9, 0.035, 0.22, 0.02, "#1d1d1d"); kbox(-0.725, -0.012, 2.07, 0.06, 0.03, 0.02, "#1d1d1d")   # husnummer 1
kbox(-1.5, -0.01, 1.9, 0.14, 0.14, 0.015, "#2e5aa7")
kbox(0.05, 0.4, 2.36, 0.1, 0.24, 0.2, "#c8262b")                                # rött larmskåp vid takfoten i nordöstra hörnet
kfonster(hu1, 9.9, N_O, 1.0, 1.1, 0.95)                                         # köksfönster mot nischen på baksidan
kfonster(hu0, 9.0, N_V, 1.2, 1.1, 0.95, poster=2)
kfonster(-6.6, hv1, N_S, 0.9, 2.0, 0.02, bleck=False)                           # altandörr mot trädgården
kfonster(-2.3, hv1, N_S, 1.4, 1.1, 0.95, poster=2)

# --- entrén: vit dörr med spröjsat glas mot öster, trappsten, lampa, krukor (blå kruka på en stubbe) och en svart soptunna vid garaghörnet
dv_ = 2.12
kbox(1.025, dv_, -0.1, 0.05, 2.2, 1.04, KD_KARM); kbox(1.05, dv_, -0.07, 0.04, 2.05, 0.88, "#f3f2ee")
for cv in (-0.15, 0.15):
    for ry in (1.06, 1.34, 1.62): kbox(1.072, dv_ + cv, ry, 0.02, 0.24, 0.24, KD_GLAS)
kbox(1.085, dv_ - 0.36, 0.95, 0.06, 0.04, 0.14, "#3a3a3a")
kbox(1.4, dv_, KD_MARK_Y, 0.8, 0.14, 1.1, "#b9b7b0")
kbox(1.05, dv_ - 0.66, 1.78, 0.1, 0.2, 0.12, "#1e1f21")
kbox(0.5, 1.6 - 0.03, 1.48, 1.0, 0.74, 0.06, "#f1f0ea"); kfonster(0.5, 1.6 - 0.06, N_N, 0.45, 0.36, 1.66, bleck=False)
kpinne(0.6, 0.5, KD_STEN_Y, 0.32, 0.3, "#7a5a3c"); kbox(0.6, 0.5, 0.32, 0.3, 0.26, 0.3, "#2552b0", form="cyl"); kklot(0.6, 0.5, 0.7, 0.34, "#3f7a35")
kbox(1.45, 1.15, KD_STEN_Y, 0.34, 0.36, 0.34, "#2d2d2d", form="cyl"); kklot(1.45, 1.15, 0.33, 0.42, "#8e4bb0"); kklot(1.38, 1.2, 0.24, 0.3, "#3f7a35")
# skärmtaket över nischen: mörkt tak i nivå med takfoten, vit takfotslist, vit undersida och en smal stolpe i hörnet
cu0, cu1, cv0, cv1 = 0.3, KD_GAR[0] + 0.04, -0.4, KD_GAR[2]
kskiva((cu0 + cu1) / 2, (cv0 + cv1) / 2, 2.56, cv1 - cv0, (cu1 - cu0) * 1.002, 0.1, KD_TAK, N_O, math.atan(0.1 / (cu1 - cu0)))
kbox((cu0 + cu1) / 2, cv0 - 0.02, 2.25, cu1 - cu0 + 0.04, 0.3, 0.04, KD_KARM); kbox(cu1 + 0.02, (cv0 + cv1) / 2, 2.25, 0.04, 0.3, cv1 - cv0, KD_KARM)
kbox((cu0 + cu1) / 2, (cv0 + cv1) / 2, 2.47, cu1 - cu0, 0.02, cv1 - cv0, "#efeee8")
kbox(cu1 - 0.06, cv0 + 0.06, KD_STEN_Y, 0.09, 2.4, 0.09, KD_KARM)

# --- garaget: vit sektionsport, två små liggande fönster mot Menuettvägen, liggande panel i övre bandet, stuprör, vedbod i söder, blå presenning
gu0, gu1, gv0, gv1 = KD_GAR; gc = (gu0 + gu1) / 2
kbox(gc, gv0 - 0.02, KD_STEN_Y - 0.02, 2.66, 2.3, 0.04, "#9c9b96")                      # skuggfog runt porten
kbox(gc, gv0 - 0.03, KD_STEN_Y - 0.02, 2.48, 2.2, 0.04, "#f1f0eb")                      # sektionsporten
for yy in (0.4, 0.92, 1.44): kbox(gc, gv0 - 0.052, yy, 2.46, 0.035, 0.02, "#a9a8a2")   # fogar mellan sektionerna
for yy in (0.15, 0.67, 1.19, 1.71): kbox(gc, gv0 - 0.05, yy, 2.46, 0.02, 0.015, "#d3d2cc")   # en ribba mitt på varje sektion
kbox(gc, gv0 - 0.035, 2.07, 2.7, 0.1, 0.06, KD_KARM)                                      # överstycke
kbox(gc, gv0 - 0.06, 0.12, 0.26, 0.05, 0.035, "#4a4c4e")
for vv in (11.67, 10.21): kfonster(gu1, vv, N_O, 0.8, 0.42, 1.43, bleck=False)
for yy in (1.88, 2.04):
    kbox(gu1 + 0.065, (gv0 + gv1) / 2, yy, 0.012, 0.02, gv1 - gv0, "#d2d0c8"); kbox(gc, gv0 - 0.065, yy, gu1 - gu0, 0.02, 0.012, "#d2d0c8")
for vv in (6.0, 9.4): kbox(gu1 + 0.07, vv, 1.72, 0.02, 0.48, 0.08, "#f6f5f0")
kpinne(gu0 - 0.05, gv0 - 0.06, KD_STEN_Y, 2.45, 0.08, "#262626")
lv0, lv1 = gv1, gv1 + 1.1; lc_ = (lv0 + lv1) / 2
kbox(gc, lc_, KD_MARK_Y, gu1 - gu0 + 0.04, 0.22, lv1 - lv0 + 0.02, "#3a3d40"); kbox(gc, lc_, -0.03, gu1 - gu0, 1.75, lv1 - lv0, "#e9e7df")
for k_ in range(1, 9): kbox(gu0 + k_ * (gu1 - gu0) / 9, lv1 + 0.012, 0.0, 0.03, 1.66, 0.012, "#d6d4cc")
for k_ in range(1, 3): kbox(gu1 + 0.012, lv0 + k_ * (lv1 - lv0) / 3, 0.0, 0.012, 1.7, 0.03, "#d6d4cc")
kskiva(gc, lc_ + 0.05, 1.86, gu1 - gu0 + 0.2, math.hypot(1.3, 0.25), 0.07, "#3b3d3f", N_S, math.atan(0.25 / 1.3))
kbox(gc, lv1 + 0.11, 1.55, gu1 - gu0 + 0.2, 0.16, 0.04, "#f1f0ea")
kbox(6.75, 13.3, KD_MARK_Y, 1.25, 0.85, 2.1, "#2a55b8", 0.06); kbox(6.75, 13.3, 0.58, 1.0, 0.28, 1.9, "#2f5fc4", 0.06)

# --- tillbyggnaden i väster: fönster åt norr och väster, glasdörr mot trädgården
kfonster(-11.25, KD_TILL[2], N_N, 1.0, 1.0, 0.95, poster=2); kfonster(KD_TILL[0], 3.3, N_V, 1.2, 1.0, 0.95, poster=2); kfonster(-11.6, KD_TILL[3], N_S, 0.85, 2.0, 0.02, bleck=False)

# --- gården: soptunnor, brevlåda, släpvagn med presenning, tältgarage, vit båt upp och ner, flaggstång med vimpel
def _soptunna(u, v, farg, a=0.0, y0=KD_STEN_Y, lapp=False):
    kbox(u, v, y0, 0.58, 0.92, 0.7, farg, a); lock = "#" + "".join("%02x" % int(int(farg[i:i + 2], 16) * 0.85) for i in (1, 3, 5))
    kbox(u, v, y0 + 0.92, 0.62, 0.05, 0.76, lock, a)
    p = _o(u, v, a, 0.0, 0.37); kbox(p[0], p[1], y0 + 0.82, 0.5, 0.04, 0.04, "#151515", a)
    for s_ in (-0.25, 0.25): p = _o(u, v, a, s_, 0.3); krör(p[0], p[1], y0 + 0.1, 0.2, 0.06, "#151515", a)
    if lapp: p = _o(u, v, a, 0.0, -0.1); kbox(p[0], p[1], y0 + 0.975, 0.22, 0.006, 0.1, "#f2f2ee", a)
_soptunna(0.35, -10.15, "#24402c", 0.0, lapp=True); _soptunna(-0.42, -9.5, "#1e1f20", 0.15); _soptunna(1.68, 2.25, "#1d1e1f", 0.0)
kbox(-2.1, -10.9, KD_MARK_Y, 0.7, 0.08, 0.55, "#b4b1aa"); kbox(-2.1, -10.9, -0.17, 0.38, 1.2, 0.34, "#1c1c1d"); kbox(-2.1, -10.9, 1.03, 0.42, 0.04, 0.38, "#151515")
kbox(-2.1, -11.075, 0.82, 0.24, 0.03, 0.01, "#050505"); kbox(-1.99, -11.076, 0.9, 0.08, 0.08, 0.006, "#c4202a")
# släpvagnen: galvad flakkorg på ram, grå presenning, två hjul med stänkskärmar, V-formad dragstång med kopplingshuvud och stödhjul
tu, tv, ta = -4.6, -7.0, math.atan2(-0.83, -0.55)
kbox(tu, tv, 0.2, 2.05, 0.35, 1.25, "#9ea3a6", ta); kbox(tu, tv, 0.08, 2.1, 0.12, 1.15, "#6f7478", ta)
kbox(tu, tv, 0.55, 2.12, 0.1, 1.31, "#b7bcbf", ta); kbox(tu, tv, 0.63, 2.0, 0.07, 0.7, "#c0c5c8", ta)
for s_ in (-0.72, 0.72):
    p = _o(tu, tv, ta, 0.0, s_); krör(p[0], p[1], 0.0, 0.5, 0.16, "#1f1f1f", ta + math.pi / 2); kbox(p[0], p[1], 0.27, 0.6, 0.04, 0.2, "#8c9194", ta)
for s_ in (-0.55, 0.55):
    a_ = _o(tu, tv, ta, 1.0, s_); b_ = _o(tu, tv, ta, 2.25, 0.0); m_ = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
    kbox(m_[0], m_[1], 0.12, math.hypot(b_[0] - a_[0], b_[1] - a_[1]), 0.06, 0.05, "#7b8084", math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
p = _o(tu, tv, ta, 2.32, 0.0); kbox(p[0], p[1], 0.08, 0.18, 0.1, 0.1, "#2a2a2a", ta)
p = _o(tu, tv, ta, 2.0, 0.0); kpinne(p[0], p[1], -0.05, 0.35, 0.05, "#6f7478"); krör(p[0], p[1], -0.04, 0.16, 0.05, "#1f1f1f", ta + math.pi / 2)
# tältgaraget i grå plast med gavelformat tak, längsaxeln mot Menuettvägen
tgu, tgv, tgL, tgB = -11.75, -8.45, 5.5, 3.1
kbox(tgu, tgv, KD_STEN_Y, tgL, 1.88, tgB, "#b3b8bb")
for yy, bb, hh in ((1.75, 2.5, 0.3), (2.05, 1.7, 0.25), (2.3, 0.9, 0.2)): kbox(tgu, tgv, yy, tgL, hh, bb, "#aab0b3")
for sg in (-1, 1): kskiva(tgu, tgv + sg * 0.8, 2.13, tgL + 0.1, math.hypot(1.6, 0.75), 0.04, "#c0c5c8", N_S if sg > 0 else N_N, math.atan(0.75 / 1.6))
for k_ in range(1, 5): kbox(tgu - tgL / 2 + 1.1 * k_, tgv - tgB / 2 - 0.012, KD_STEN_Y, 0.05, 1.86, 0.02, "#959a9d")
kbox(tgu + tgL / 2 + 0.012, tgv, KD_STEN_Y, 0.02, 1.84, 0.05, "#8d9295")
kbox(-12.9, -4.8, KD_MARK_Y, 2.3, 0.38, 1.15, "#f1f1ee"); kbox(-11.5, -4.8, KD_MARK_Y, 0.6, 0.34, 0.62, "#f1f1ee"); kbox(-12.6, -4.8, 0.13, 2.8, 0.04, 0.06, "#a3a39e")
# flaggstång i trädgården bakom huset med en svensk vimpel (syns över taket från Menuettvägen)
fu_, fv_ = -12.6, 9.6
kpinne(fu_, fv_, KD_MARK_Y, 9.2, 0.1, "#f2f2ee"); kklot(fu_, fv_, 9.28, 0.16, "#d9b23a")
for k_, (L_, hh_) in enumerate(((1.3, 0.34), (1.2, 0.26), (1.1, 0.18), (1.0, 0.11))):
    s0 = sum(q[0] for q in ((1.3, 0.34), (1.2, 0.26), (1.1, 0.18), (1.0, 0.11))[:k_]); mid = s0 + L_ / 2
    p = _o(fu_, fv_, 0.35, 0.06 + mid * 0.62, 0.0); yc = 9.0 - mid * 0.78
    kskiva(p[0], p[1], yc, 0.02, L_, hh_, "#1f5aa6", 0.35, math.atan2(0.78, 0.62))
    kskiva(p[0] + 0.002, p[1], yc, 0.022, L_, hh_ * 0.3, "#f2c41a", 0.35, math.atan2(0.78, 0.62))

# --- gatuhörnet: gatlykta, två elskåp med gul-svart markeringsstolpe, en liten springcykel mot lyktstolpen, röd skylt vid uppfarten
kpinne(6.0, -11.45, -0.6, 6.8, 0.14, "#8e9295"); kbox(6.0, -12.2, 6.62, 0.06, 0.06, 1.5, "#8e9295"); kbox(6.0, -12.85, 6.5, 0.3, 0.14, 0.56, "#d9d6c8")
kbox(6.0, -11.53, 1.0, 0.1, 0.16, 0.02, "#2e5aa7"); kbox(6.0, -11.53, 1.25, 0.08, 0.1, 0.02, "#f2f2ee")
for cu, cv, cb, ch, cd in ((7.1, -11.35, 0.82, 1.28, 0.46), (7.84, -11.3, 0.42, 1.12, 0.36)):
    kbox(cu, cv, KD_MARK_Y, cb, ch, cd, "#a7acac"); kbox(cu, cv, KD_MARK_Y + ch, cb + 0.04, 0.05, cd + 0.04, "#9aa0a0")
    kbox(cu, cv - cd / 2 - 0.006, KD_MARK_Y + 0.15, 0.015, ch - 0.3, 0.012, "#80868a")
kbox(7.0, -11.35 - 0.236, 0.85, 0.08, 0.04, 0.01, "#d9a520")
for y0_, y1_, f_ in ((KD_MARK_Y, 0.4, "#e8b81c"), (0.4, 0.9, "#1b1b1b"), (0.9, 1.35, "#e8b81c")): kpinne(6.75, -10.98, y0_, y1_, 0.08, f_)
# springcykeln (vit ram, rosa fälgar, svart sadel) lutad mot stolpen
cyu, cyv, cya = 6.35, -11.85, 0.25
for s_ in (-0.32, 0.32):
    p = _o(cyu, cyv, cya, s_, 0.0); krör(p[0], p[1], KD_MARK_Y + 0.17, 0.34, 0.05, "#1f1f1f", cya + math.pi / 2); krör(p[0], p[1], KD_MARK_Y + 0.17, 0.24, 0.056, "#e88ab0", cya + math.pi / 2)
p = _o(cyu, cyv, cya, 0.0, 0.0); kbox(p[0], p[1], KD_MARK_Y + 0.38, 0.62, 0.04, 0.04, "#f4f4f2", cya)
p = _o(cyu, cyv, cya, -0.12, 0.0); kbox(p[0], p[1], KD_MARK_Y + 0.46, 0.2, 0.04, 0.09, "#1a1a1a", cya)
p = _o(cyu, cyv, cya, 0.3, 0.0); kpinne(p[0], p[1], KD_MARK_Y + 0.17, KD_MARK_Y + 0.6, 0.03, "#f4f4f2"); kbox(p[0], p[1], KD_MARK_Y + 0.6, 0.03, 0.03, 0.4, "#1a1a1a", cya)
kbox(5.95, -1.0, KD_MARK_Y, 0.05, 1.15, 0.05, "#8a8d90"); kbox(5.95, -1.03, 0.55, 0.28, 0.35, 0.02, "#d9482b")

ANDRINGAR["H1234"] = {"namn": "Mormor", "adress": "Kadriljvägen 1", "alias": ["Mormors hus"], "typ": "villa", "van": 1, "fh": KD_FH, "tegel": "gul", "vagg": KD_VIT, "tak": "sadel", "taklutning": KD_LUT, "takfarg": KD_TAK,
                      "takUtsprang": 0.4, "takfotFarg": KD_KARM, "takUndersida": "#f1f0ea", "rekt": KD_R(*KD_HUS), "poly": KD_P(*KD_HUS), "sakerhet": "foto",
                      "band": [{"y0": -1.0, "y1": -0.13, "farg": "#3a3a38"}, {"y0": 2.2, "y1": KD_FH + 0.02, "farg": "#f0efe8"}],
                      "fasadBoxar": _kd, "stanger": KD_STANGER,
                      "skyltar": [{"vid": KD_W(-0.72, 0.0), "mot": KD_W(KD_NOCK_U, -40.0), "text": "Kadriljvägen", "bg": "#1b4f9c", "fg": "#ffffff", "hojd": 2.55, "hgt": 0.15, "bredd": 0.82, "utanTak": True, "ut": -0.02}],
                      "not": "1½-plansvilla i gult tegel med vit stående panel på gavlarna och brant mörkt tegeltak. Burspråk med plåttak på gaveln mot Kadriljvägen, "
                             "indragen entré under ett skärmtak mellan huset och det vita garaget. På uppfarten står en grå Peugeot kombi (påskägg, efter foton)."}
print('Kadriljvägen 1: fasadlådor', len(_kd))
# ================================================================== STOPP Köpcentrum (H044): fasaddetaljer längs fronten mot Östra Storgatan (efter foto, utkast 46)
class Lador:
    """fasadlådor i ett lokalt system (O, U) med u längs U och v åt vänster (V = U vriden 90°); y över husets golv g0.
    Riktningar anges som vinklar i u→v-planet (0 = +u, pi/2 = +v)."""
    def __init__(self, O, U):
        self.W = lokal(O, U)[0]; self.yaw = -math.atan2(U[1], U[0]); self.lista = []
    def box(self, u, v, y, b, h, d, farg, a=0.0, rx=0.0, form=None):
        x_, z_ = self.W(u, v); e = {"x": x_, "z": z_, "y": round(y, 3), "b": round(b, 3), "h": round(h, 3), "d": round(d, 3), "rot": round(self.yaw - a, 4), "farg": farg}
        if rx: e["rx"] = round(rx, 4)
        if form: e["form"] = form
        self.lista.append(e)
    def skiva(self, u, v, yc, bredd, langd, tjock, farg, fall, lut): self.box(u, v, yc - tjock / 2, bredd, tjock, langd, farg, fall - math.pi / 2, lut)
    def pinne(self, u, v, y0, y1, diam, farg): self.box(u, v, y0, diam, y1 - y0, diam, farg, form="cyl")
    def fonster(self, u, v, n, w, hh, yb, karm="#d9dcde", glas="#2b3540"):
        a = n - math.pi / 2; c, s_ = math.cos(n), math.sin(n)
        self.box(u + c * 0.03, v + s_ * 0.03, yb - 0.07, w + 0.14, hh + 0.14, 0.06, karm, a); self.box(u + c * 0.055, v + s_ * 0.055, yb, w, hh, 0.06, glas, a)
_st = Lador(ST_O, ST_U); sb = _st.box
ST_G = -0.25 + 0.16        # gångytan framför fasaden (stenlagd, 16 cm över marken)
UT = math.pi / 2           # fasadernas utåtnormal (mot parkeringen)
GRA_PLAT, MORK, GLAS_ = "#8a9096", "#2a2e33", "#33404a"
# --- mittdelen med Hemköp: skärmtak hela vägen med grå frontlist och stolpar, skyltfönster, skjutdörrar, grönt fönster och affischer
_st.skiva(13.0, 1.2, 3.66, 25.4, 2.42, 0.14, "#6f757b", UT, 0.05)
sb(13.0, 2.42, 3.02, 25.6, 0.6, 0.06, GRA_PLAT); sb(13.0, 1.2, 3.52, 25.4, 0.03, 2.4, "#c8cbcd")
for u_ in (0.7, 7.0, 13.0, 19.0, 25.3): _st.pinne(u_, 2.2, ST_G, 3.04, 0.1, "#5f6468")
sb(13.1, 0.02, ST_G, 2.45, 2.5, 0.04, "#b9bdc0"); sb(13.1, 0.045, ST_G, 2.2, 2.3, 0.04, MORK); sb(13.1, 0.07, ST_G, 0.05, 2.3, 0.02, "#b9bdc0")
sb(16.3, 0.03, 0.2, 2.6, 2.2, 0.04, "#58a83a"); sb(16.3, 0.055, 0.2, 2.6, 0.08, 0.02, "#e8e8e2")
for u_, f_ in ((7.6, "#d9473a"), (6.6, "#3a6db5")): sb(u_, 0.035, 0.45, 0.85, 1.25, 0.03, "#f2f0ea"); sb(u_, 0.055, 0.6, 0.65, 0.7, 0.01, f_)
for u_, v_ in ((9.6, -1.6), (11.0, -1.6), (20.5, -2.0)): sb(u_, v_, 4.4, 0.9, 0.7, 0.5, "#e4e6e6"); sb(u_, v_ + 0.26, 4.6, 0.5, 0.5, 0.02, "#9aa0a4")
# --- södra delen: vit glasad entré (vindfång) ut mot gångytan och en röd skylt i hörnet
sb(-11.4, -4.53, ST_G, 3.6, 2.75, 2.27, "#e9ebea")
sb(-11.4, -3.39, 0.1, 3.3, 2.3, 0.03, GLAS_)
for u_ in (-13.21, -9.59): sb(u_, -4.53, 0.1, 0.03, 2.3, 1.95, GLAS_)
for u_ in (-12.3, -11.4, -10.5): sb(u_, -3.37, 0.1, 0.08, 2.3, 0.04, "#f1f2f1")
sb(-11.4, -4.5, 2.62, 3.8, 0.12, 2.45, "#dfe1e0")
sb(-16.4, -5.64, 1.8, 2.1, 1.5, 0.06, "#c4262d"); sb(-16.4, -5.6, 2.35, 1.4, 0.18, 0.02, "#f2f2ee")
# --- tvåvåningsdelen: list över bottenvåningen, entré med glas och röda korgar under STOPP-skylten, fönster och skyltar på övervåningen
sb(30.95, 0.35, 2.98, 9.9, 0.55, 0.7, GRA_PLAT); sb(30.95, 0.35, 2.97, 9.8, 0.02, 0.66, "#c8cbcd")
sb(32.1, 0.02, ST_G, 1.8, 2.75, 0.04, "#191c20")
for u_ in (30.7, 33.5): sb(u_, 0.03, 0.0, 1.0, 2.6, 0.04, GLAS_)
for u_ in (30.2, 31.2, 33.0, 34.0): sb(u_, 0.05, ST_G, 0.07, 2.75, 0.05, "#c3c7ca")
sb(32.1, 0.05, 2.62, 3.9, 0.07, 0.05, "#c3c7ca")
for u_, hh_ in ((30.55, 0.62), (33.65, 0.78)): sb(u_, 0.55, ST_G, 0.45, hh_, 0.36, "#c8202a")
sb(34.7, 0.65, ST_G, 0.55, 1.0, 0.05, "#d0262f"); sb(34.7, 0.62, ST_G + 0.4, 0.4, 0.25, 0.02, "#f2f2ee")
for u_, w_ in ((27.6, 1.4), (29.1, 1.2), (32.9, 0.9), (33.9, 0.9), (35.25, 0.75)): _st.fonster(u_, 0.0, UT, w_, 1.0, 4.7)
_st.fonster(30.35, 0.0, UT, 0.45, 1.9, 4.0, karm="#eef0f0")
sb(35.25, 0.07, 4.75, 0.7, 0.9, 0.01, "#c9473f"); sb(35.25, 0.075, 4.95, 0.7, 0.12, 0.01, "#f2f2ee")   # röd-vit gardin
sb(28.9, 0.2, 3.62, 0.8, 0.55, 0.32, "#e2e4e4"); sb(28.9, 0.37, 3.7, 0.42, 0.42, 0.01, "#9aa0a4")
sb(28.0, 0.03, 6.35, 2.4, 0.34, 0.04, "#2a2c30"); sb(28.1, 0.055, 6.47, 1.9, 0.08, 0.01, "#e8e8e8")
sb(31.7, 0.03, 6.3, 2.0, 0.28, 0.04, "#3b62a3")
sb(33.3, 0.03, 6.48, 0.45, 0.34, 0.04, "#e2a128"); sb(34.45, 0.03, 6.54, 1.6, 0.22, 0.03, "#c9ccd0")
# trappavsats med räcke på mittdelens tak vid tvåvåningshusets södra gavel, med en dörr in till övervåningen
sb(25.2, -1.6, 4.45, 1.6, 0.08, 2.0, "#5c6166")
for v_ in (-2.55, -1.6, -0.65): _st.pinne(24.45, v_, 4.53, 5.55, 0.045, "#4a4f54")
_st.pinne(25.95, -0.65, 4.53, 5.55, 0.045, "#4a4f54")
for y_ in (5.05, 5.52): sb(24.45, -1.6, y_, 0.04, 0.04, 2.0, "#4a4f54"); sb(25.2, -0.65, y_, 1.55, 0.04, 0.04, "#4a4f54")
sb(25.98, -1.6, 4.53, 0.05, 2.0, 0.9, "#6e7378")
# trapphustornet: fönster på övervåningen och en servicedörr
for u_ in (37.3, 38.7, 40.7): _st.fonster(u_, 4.0, UT, 0.95, 1.0, 4.7)
sb(40.8, 4.03, ST_G, 1.0, 2.15, 0.05, "#6e7378"); sb(40.45, 4.07, 0.95, 0.05, 0.05, 0.1, "#2a2a2a")
# kundvagnsgaraget framför tornet: galvad ram, plastskivor bak och på sidorna, välvt tak och två rader kundvagnar
for u_ in (33.85, 36.7, 39.55):
    for v_ in (4.65, 7.25): _st.pinne(u_, v_, ST_G, 2.12, 0.07, "#9aa0a4")
sb(36.7, 4.66, 0.15, 5.7, 1.9, 0.03, "#cdd3d6")
for u_ in (33.86, 39.54): sb(u_, 5.95, 0.15, 0.03, 1.9, 2.55, "#cdd3d6")
sb(36.7, 5.95, 2.53, 5.9, 0.04, 1.22, "#e6eaec")
for v_, f_ in ((4.95, -UT), (6.95, UT)): _st.skiva(36.7, v_, 2.31, 5.9, 0.76, 0.04, "#e6eaec", f_, 0.62)
for u_ in (33.85, 36.7, 39.55): sb(u_, 5.95, 2.08, 0.05, 0.06, 2.62, "#9aa0a4")
for v_ in (5.5, 6.35):
    sb(36.6, v_, ST_G, 4.4, 0.14, 0.46, "#2a2a2a"); sb(36.6, v_, ST_G + 0.14, 4.4, 0.78, 0.52, "#99a0a5"); sb(36.6, v_, ST_G + 0.92, 4.4, 0.05, 0.56, "#c9252c")
# --- norra delen: litet skärmtak över en glasdörr, fönster, liten röd skylt, grå dörr, rad med bruna överljus och en mörk skylt
_st.skiva(45.0, 0.78, 2.78, 3.2, 1.62, 0.08, "#3a3d41", UT, 0.25)
sb(45.0, 0.03, ST_G, 1.4, 2.3, 0.05, "#2c3237"); sb(45.0, 0.05, ST_G, 0.05, 2.3, 0.02, "#9aa0a4")
sb(46.9, 0.03, 0.75, 1.0, 1.2, 0.04, GLAS_)
sb(48.6, 0.03, 1.6, 0.45, 0.55, 0.04, "#c8262d")
sb(50.4, 0.03, ST_G, 1.0, 2.1, 0.05, "#7b8085")
sb(51.8, 0.03, -0.25, 0.25, 5.45, 0.05, "#9da1a3")
sb(56.2, 0.03, 2.75, 7.4, 0.55, 0.04, "#6a4b3c")
for k_ in range(1, 6): sb(52.5 + k_ * 1.23, 0.055, 2.75, 0.06, 0.55, 0.01, "#3a2a22")
sb(56.4, 0.03, 3.62, 6.2, 0.75, 0.05, "#2c2e2b"); sb(56.4, 0.06, 3.86, 5.2, 0.27, 0.01, "#bdb93c")
for u_, v_ in ((47.0, -3.0), (55.0, -2.5)): sb(u_, v_, 5.2, 1.0, 0.6, 0.6, "#dcdedf")
ANDRINGAR["H044"] = {**ST_PLAT, "namn": "Stopp Köpcentrum", "fh": 4.4, "vagg": "#8b9197", "kantFarg": "#7f858b", "band": ST_SOCKEL, "sakerhet": "foto",
                     "rekt": ST_R(0.0, 26.0, -53.7, 0.0), "poly": ST_P(0.0, 26.0, -53.7, 0.0), "x": ST_R(0.0, 26.0, -53.7, 0.0)[0], "z": ST_R(0.0, 26.0, -53.7, 0.0)[1],
                     "skyltar": [_st_sk(7.0, text="Hemköp", bg="transparent", fg="#d3202d", kursiv=True, hojd=3.33, hgt=0.46, bredd=2.3, ut=2.37),
                                 _st_sk(19.6, text="Hemköp", bg="transparent", fg="#d3202d", kursiv=True, hojd=3.33, hgt=0.46, bredd=2.3, ut=2.37),
                                 _st_sk(3.3, bredd=4.2, **_BUTIK), _st_sk(9.7, bredd=3.4, **_BUTIK), _st_sk(21.9, bredd=4.4, **_BUTIK)],
                     "fasadBoxar": _st.lista,
                     "not": "Köpcentrum vid Östra Storgatan med Hemköp. Envåningshus i grå profilplåt med skärmtak längs fasaden; bara delen vid entrén "
                            "under skylten STOPP KÖPCENTRUM har två våningar (efter foto)."}
print('Stopp Köpcentrum: fasadlådor', len(_st.lista))

# ================================================================== Platåvägens början vid Nygatan 28 (efter foto från Nygatan, utkast 48)
# Husen som syns från korsningen färgas som på fotot: den grå villan med tegelgavlar och vit farstukvist (H736) och lekstugan (H737) till
# höger, det låga röda tegelhuset med ljust plåttak och en upphöjd fönsterrad (H751) till vänster, det gula huset med rött tak bakom det
# (H789) och den gula villan med ljust plåttak uppe i backen (H823). Där OSM-formen gav platta trevåningslådor har även våningar och tak rättats.
def _rekt_lokal(poly):
    """minsta omskrivna rektangel med en sida längs någon av polygonens kanter: (O, U, u0, u1, v0, v1)"""
    best = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]; L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1.0: continue
        U = ((b[0] - a[0]) / L, (b[1] - a[1]) / L); us = [(p[0] - a[0]) * U[0] + (p[1] - a[1]) * U[1] for p in poly]; vs = [(p[0] - a[0]) * -U[1] + (p[1] - a[1]) * U[0] for p in poly]
        A_ = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or A_ < best[0]: best = (A_, a, U, min(us), max(us), min(vs), max(vs))
    return best[1:]
_hus_id = {h_["osm"]: h_ for h_ in hus}
def _poly_av(oid): return _hus_id[oid]["poly"]
# --- H736: grå-blå stående panel, ett plan, sadeltak med mörka pannor och vita vindskivor, tegelgavlar, vita fönster och en vit farstukvist
# u längs fasaden mot Nygatan (ökar mot öster), v in i huset. Östra gaveln mot Platåvägen (foto därifrån, utkast 49): rött tegel ända ner till
# en låg grå sockel med källarfönster, grå-blå panel i gavelspetsen, vita vindskivor och en parabol vid nocken.
_p36 = Lador(P36_O, P36_U); pb = _p36.box; N_UT = -math.pi / 2
pb(P36_L - 0.5, -0.04, -1.25, 1.0, 4.0, 0.06, "#9a3b2d")                     # tegel runt hörnet i östra änden av långsidan
for v_ in (1.4, 3.1, 4.8, 6.5):                                             # källarfönster i östra gaveln
    pb(P36_L + 0.075, v_, -1.12, 0.04, 0.5, 0.95, "#f4f4f0"); pb(P36_L + 0.1, v_, -1.06, 0.03, 0.38, 0.83, "#2c353d")
_k36, _o36 = 0.42, 0.45                                                     # takets lutning och utsprång
_th = math.atan(_k36); _Lr = math.hypot(P36_D / 2 + _o36, (P36_D / 2 + _o36) * _k36)
for u_, ut_ in ((P36_L + 0.47, 1), (-0.47, -1)):                            # vita vindskivor på båda gavlarna
    for sg in (-1, 1):
        vc = P36_D / 2 + sg * (P36_D / 2 + _o36) / 2; yc = 2.75 + (P36_D / 2 - (P36_D / 2 + _o36) / 2) * _k36 - 0.12
        pb(u_, vc, yc - 0.11, 0.05, 0.22, _Lr, "#f4f4f0", 0.0, sg * _th)
_p36.pinne(P36_L - 0.35, P36_D / 2 - 0.4, 4.2, 5.35, 0.05, "#8d9196")      # parabolen vid nocken
_p36.box(P36_L - 0.2, P36_D / 2 - 0.1, 5.0, 0.62, 0.05, 0.62, "#d9dbdc", 0.0, 1.0, form="cyl")
for u_, w_, h_, yb_ in ((12.0, 1.15, 1.25, 0.75), (10.0, 0.85, 0.95, 1.0), (7.8, 0.8, 0.95, 1.0), (4.55, 0.85, 1.2, 0.8), (2.05, 0.85, 1.25, 0.75)):
    _p36.fonster(u_, 0.0, N_UT, w_, h_, yb_, karm="#f6f6f2", glas="#2f3a44")
    pb(u_, -0.05, yb_ - 0.12, w_ + 0.24, 0.06, 0.1, "#f6f6f2")
pb(6.9, -0.04, -0.2, 0.95, 2.15, 0.05, "#f3f3ef"); pb(6.9, -0.07, 0.95, 0.5, 0.75, 0.02, "#2f3a44")   # dörren
pb(6.05, -0.75, 0.0, 3.1, 0.55, 1.5, "#f3f3ef")                             # farstukvistens plattform
for u_ in (4.6, 7.5): _p36.pinne(u_, -1.4, 0.55, 2.55, 0.08, "#f6f6f2")
for sg in (-1, 1): _p36.skiva(6.05 + sg * 0.85, -0.75, 2.75, 1.7, 1.95, 0.06, "#3a3a3a", 0.0 if sg > 0 else math.pi, 0.35)   # litet sadeltak, gavel mot gatan
pb(6.05, -1.62, 2.5, 3.5, 0.18, 0.05, "#f6f6f2")
for k_ in range(3): pb(3.95 - k_ * 0.3, -0.75, -0.25 + k_ * 0.18, 0.3, 0.2, 1.3, "#f3f3ef")                 # trappan ner mot väster
for v_ in (-0.08, -1.42): pb(4.2, v_, 0.15, 1.2, 0.05, 0.05, "#f6f6f2", 0.0, 0.0); _p36.pinne(3.5, v_, -0.1, 0.7, 0.05, "#f6f6f2")
pb(5.3, -1.42, 0.85, 1.5, 0.05, 0.05, "#f6f6f2")
_p36.box(7.45, -1.55, 1.75, 0.5, 0.3, 0.02, "#2a64b4"); _p36.box(7.45, -1.56, 1.85, 0.5, 0.07, 0.022, "#f2c41a")          # liten svensk vimpel
_p36.box(5.2, -1.3, 1.9, 0.38, 0.32, 0.38, "#7a3f9c", form="klot")                                                     # blomampel
for u_, d_ in ((5.6, 1.7), (3.2, 1.3)): _p36.box(u_, -1.9, -0.25, d_, d_ * 0.8, d_, "#3d7a35", form="klot")             # runda buskar framför
pb(3.2, 5.2, 3.7, 0.55, 1.45, 0.55, "#3a3a3a"); pb(9.6, 2.4, 3.55, 0.14, 0.55, 0.14, "#2a2a2a")                       # skorsten och ventilationsrör
ANDRINGAR["H736"] = {"typ": "villa", "van": 1, "fh": 2.75, "vagg": "#5c6571", "panel": True, "utanFonster": True, "tak": "sadel", "taklutning": _k36,
                     "takfarg": "#363636", "takUtsprang": _o36, "takfotFarg": "#f2f2ee", "takUndersida": "#e8e8e4", "sakerhet": "foto",
                     "tegelSidor": [[P36_U[0], P36_U[1]], [-P36_U[0], -P36_U[1]]], "tegelSidorRen": True,
                     "rekt": P36_R(0.0, P36_L, 0.0, P36_D), "poly": P36_P(0.0, P36_L, 0.0, P36_D), "band": [{"y0": -3.0, "y1": -1.25, "farg": "#7b7d7c"}],
                     "fasadBoxar": _p36.lista, "not": "Enplansvilla i grå-blå stående panel med gavlar i rött tegel, mörkt tegeltak, vita fönster och vit farstukvist; "
                                                       "källarfönster och parabol på gaveln mot Platåvägen (efter foton från Nygatan 28 och Platåvägen)."}
# --- H737: lekstugan (foto från Platåvägen, utkast 49): grå-blå liggande panel med vita knutar, korrugerat mörkt plåttak, en tvärgavel med vita
# vindskivor över dörren och den lilla verandan i norra änden, vit dörr med romb, spröjsat fönster, vitt spjälstaket, vit stol och klätterrosor
P37_O, P37_U = (-834.6, 177.3), (-0.65291, 0.75745)                        # östra hörnet; u söderut längs långsidan mot vägen, v västerut
P37_W, P37_R, P37_P = lokal(P37_O, P37_U); _p37 = Lador(P37_O, P37_U); lb = _p37.box; VIT = "#f4f4f0"; L37, D37, K37 = 3.83, 3.69, 0.7
for u_ in (0.05, L37 - 0.05):
    for v_ in (0.05, D37 - 0.05): lb(u_, v_, -0.2, 0.13, 2.32, 0.13, VIT)            # knutar
_p37.fonster(1.75, 0.0, -math.pi / 2, 0.55, 0.72, 0.95, karm=VIT, glas="#3a4552")
lb(1.75, -0.09, 0.95, 0.04, 0.72, 0.02, VIT); lb(1.75, -0.09, 1.28, 0.55, 0.04, 0.02, VIT); lb(1.75, -0.07, 0.83, 0.75, 0.05, 0.08, VIT)
lb(0.75, -0.04, -0.06, 0.78, 1.88, 0.05, VIT); lb(0.75, -0.075, 1.3, 0.15, 0.15, 0.02, "#3a4552")                  # dörren med litet fönster
lb(1.27, -0.08, 1.55, 0.1, 0.18, 0.08, "#2a2a2a")                                                                   # lykta
lb(0.3, -0.48, -0.16, 3.3, 0.12, 0.95, "#8e8f8a"); lb(-0.68, 1.05, -0.16, 1.35, 0.12, 2.15, "#8e8f8a")             # trätrall framför och norr om
for k_ in range(2): lb(-0.95, -1.1 - k_ * 0.3, -0.28 - k_ * 0.12, 0.75, 0.1, 0.32, "#8e8f8a")                     # två trappsteg
# tvärgaveln: brantare tak (1:1) över dörren och verandan, nock i samma höjd som huvudtaket
_kn = 2.1 + D37 / 2 * K37; _gh = _kn - 2.1
for sg in (-1, 1):
    _p37.skiva(-0.05 + sg * (_gh + 0.1) / 2, (D37 - 0.6) / 2, _kn - (_gh + 0.1) / 2 + 0.03, D37 + 0.6, (_gh + 0.1) * 1.414, 0.06, "#4d5155", 0.0 if sg > 0 else math.pi, math.pi / 4)
    lb(-0.05 + sg * (_gh + 0.1) / 2, -0.62, _kn - (_gh + 0.1) / 2 - 0.2, 0.05, 0.2, (_gh + 0.1) * 1.414, VIT, -math.pi / 2, sg * math.pi / 4)
lb(-0.05, -0.55, 1.95, 2.6, 0.1, 0.1, VIT); _p37.pinne(-1.3, -0.5, -0.1, 2.0, 0.09, VIT)
for u_ in [x_ * 0.13 for x_ in range(-4, 16)]: lb(u_, -0.93, -0.1, 0.06, 0.85, 0.025, VIT)                         # spjälstaket framför
for v_ in [x_ * 0.13 for x_ in range(-6, 19)]: lb(-1.33, v_, -0.1, 0.025, 0.85, 0.06, VIT)                          # och mot norr
lb(0.72, -0.93, 0.15, 2.5, 0.05, 0.04, VIT); lb(0.72, -0.93, 0.55, 2.5, 0.05, 0.04, VIT)
lb(-1.33, 0.78, 0.15, 0.04, 0.05, 3.15, VIT); lb(-1.33, 0.78, 0.55, 0.04, 0.05, 3.15, VIT)
lb(-0.7, 0.9, 0.3, 0.46, 0.05, 0.46, VIT); lb(-0.7, 1.12, 0.3, 0.46, 0.55, 0.05, VIT)                               # vit plaststol
for u_, v_, y_, d_ in ((3.25, -0.3, 0.1, 0.75), (3.0, -0.25, 0.8, 0.7), (3.35, -0.25, 1.35, 0.6), (2.75, -0.2, 1.6, 0.45)):   # klätterros
    lb(u_, v_, y_, d_, d_, d_, "#4c7a3a", form="klot")
for u_, v_, y_ in ((3.1, -0.62, 0.55), (3.4, -0.55, 1.05), (2.9, -0.55, 1.4), (3.25, -0.5, 1.75), (2.7, -0.42, 1.9), (3.5, -0.6, 0.3)):
    lb(u_, v_, y_ + 0.25, 0.14, 0.14, 0.14, "#f6f0dc", form="klot")
ANDRINGAR["H737"] = {"typ": "bod", "van": 1, "fh": 2.1, "vagg": "#5b6573", "panel": "ligg", "utanFonster": True, "tak": "sadel", "taklutning": K37,
                     "takfarg": "#4d5155", "takUtsprang": 0.3, "takfotFarg": VIT, "takUndersida": "#e9e9e4", "sakerhet": "foto",
                     "rekt": P37_R(0.0, L37, 0.0, D37), "poly": P37_P(0.0, L37, 0.0, D37), "fasadBoxar": _p37.lista,
                     "not": "Lekstuga i grå-blå liggande panel med vita knutar, mörkt korrugerat plåttak, tvärgavel över dörren och verandan, vitt spjälstaket "
                            "och klätterrosor (efter foto från Platåvägen)."}
# --- H751: lågt rött tegelhus med svagt lutande ljust plåttak (takfoten mot Platåvägen) och en upphöjd del med fönsterrad i södra halvan
P51_O, P51_U = (-821.4, 205.2), (12.8 / 14.94, -7.7 / 14.94)
P51_W, P51_R, P51_P = lokal(P51_O, P51_U); _p51 = Lador(P51_O, P51_U); qb = _p51.box; P51_L, P51_D, P51_LUT = 14.94, 19.0, 0.22
qb(11.6, P51_D * 0.36, 3.1 + P51_D * 0.36 * P51_LUT - 0.3, 6.6, 1.65, 3.4, "#454b52")                                  # den upphöjda delen
for k_ in range(5): qb(8.9 + k_ * 1.32, P51_D * 0.36 - 1.72, 3.1 + P51_D * 0.36 * P51_LUT + 0.15, 1.05, 0.75, 0.03, "#6f8aa3")   # fönsterraden
_p51.skiva(11.6, P51_D * 0.36 + 0.2, 3.1 + P51_D * 0.36 * P51_LUT + 1.42, 7.0, 4.2, 0.08, "#a6abae", -math.pi / 2, 0.12)
qb(11.6, P51_D * 0.36 - 1.95, 3.1 + P51_D * 0.36 * P51_LUT + 1.18, 7.0, 0.16, 0.05, "#d8dbdc")
qb(9.25, -0.03, -0.2, 1.55, 2.25, 0.05, "#f2f2ee"); qb(9.25, -0.06, -0.15, 1.35, 2.1, 0.03, "#2f3a44"); qb(9.25, -0.08, -0.15, 0.06, 2.1, 0.02, "#f2f2ee")   # glasdörrar
for u_, w_, h_, yb_ in ((5.4, 0.95, 0.9, 1.0), (2.85, 1.4, 1.1, 0.8)): _p51.fonster(u_, 0.0, -math.pi / 2, w_, h_, yb_, karm="#f2f2ee")
qb(11.8, -0.04, 1.75, 1.6, 0.36, 0.04, "#f1f1ec"); qb(11.8, -0.065, 1.86, 1.2, 0.1, 0.01, "#5c6570")                    # skylt över uteplatsen
_p51.pinne(10.3, 3.4, 3.1 + 3.4 * P51_LUT - 0.1, 3.1 + 3.4 * P51_LUT + 0.9, 0.35, "#565b60")                           # ventilationshuv på taket
ANDRINGAR["H751"] = {"typ": "villa", "van": 1, "fh": 3.1, "tegel": "ren", "vagg": "#9b3d2e", "tak": "sadel", "takAxel": "kort", "taklutning": P51_LUT,
                     "takfarg": "#a6abae", "takUtsprang": 0.55, "takfotFarg": "#d8dbdc", "takUndersida": "#cfd2d3", "sakerhet": "foto",
                     "rekt": P51_R(0.0, P51_L, 0.0, P51_D), "poly": P51_P(0.0, P51_L, 0.0, P51_D), "fasadBoxar": _p51.lista,
                     "not": "Lågt hus i rött tegel med ljust, svagt lutande plåttak och en upphöjd del med fönsterrad; uteplats mot Platåvägen (efter foto från Nygatan 28)."}
# --- H789: ljusgult hus med rött tegeltak
ANDRINGAR["H789"] = {"vagg": "#efe2ad", "takfarg": "#a65136", "sakerhet": "foto", "not": "Ljusgult hus med rött tak (färger efter foto från Nygatan 28)."}
# --- H823 (utkast 49, foto från Platåvägen): gul trävilla i "Villa Villekulla"-stil. Brant ockragult plåttak (1:1,15) med gaveln mot gatan, vita
# knutar, vindskivor och gördelband, vindsfönster i gavelspetsen, spira på nocken, skorsten i rött tegel, ett burspråk mot norr och en svart
# stålbalkong med utvändig trappa i södra hörnet. Tvärhuset på baksidan (H1721) har ännu brantare tak med spira; utbyggnaden mot söder (H1722)
# har terrass med svart räcke på taket.
_p23 = Lador(P23_O, P23_U); zb = _p23.box; SV, VIT23, GUL23 = "#1e1e1e", "#ffffff", "#f0e2a6"; _k23, _o23 = 1.15, 0.5
def _racke(L, a, b, y, farg=SV, h=1.0, steg=0.2):
    """räcke mellan a=(u,v) och b=(u,v): överliggare, underliggare och tunna balusterpinnar"""
    du, dv = b[0] - a[0], b[1] - a[1]; Lx = math.hypot(du, dv); n = max(2, int(Lx / steg)); vin = math.atan2(dv, du)
    for yy, hh in ((y + h - 0.05, 0.05), (y + 0.1, 0.04)): L.box((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, yy, Lx, hh, 0.05, farg, vin)
    for k in range(n + 1): L.box(a[0] + du * k / n, a[1] + dv * k / n, y, 0.03, h, 0.03, farg)
for sg in (-1, 1):                                                          # vita vindskivor på gaveln mot gatan
    run = P23_B / 2 + _o23; zb(P23_B / 2 + sg * run / 2, -0.47, 6.0 + (P23_B / 2 - run / 2) * _k23 - 0.14 - 0.14, 0.06, 0.28, math.hypot(run, run * _k23), VIT23, -math.pi / 2, sg * math.atan(_k23))
_p23.pinne(P23_B / 2, -0.4, 6.0 + P23_B / 2 * _k23 - 0.1, 6.0 + P23_B / 2 * _k23 + 0.95, 0.07, VIT23)                 # spira
zb(P23_B / 2, -0.4, 6.0 + P23_B / 2 * _k23 + 0.85, 0.22, 0.22, 0.22, "#c9562e", form="klot")
_p23.fonster(4.35, 0.0, -math.pi / 2, 0.9, 1.3, 6.85, karm=VIT23, glas="#34404a"); zb(4.35, -0.09, 6.85, 0.04, 1.3, 0.02, VIT23)   # vindsfönster
_p23.fonster(5.95, 0.0, -math.pi / 2, 0.45, 0.95, 7.05, karm=VIT23, glas="#34404a")
zb(P23_B / 2, -0.05, 2.92, P23_B + 0.1, 0.16, 0.08, VIT23)                   # gördelband mellan våningarna
for u_ in (0.07, P23_B - 0.07): zb(u_, 0.07, -1.6, 0.22, 7.6, 0.22, VIT23)   # hörnknutar
zb(8.35, -0.04, -0.05, 1.05, 2.25, 0.05, VIT23); zb(8.35, -0.07, 0.95, 0.55, 0.9, 0.02, "#34404a")      # entrédörr under balkongen
zb(P23_B / 2, 8.6, 9.6, 0.75, 3.6, 0.95, "#b4533c"); zb(P23_B / 2, 8.6, 13.2, 0.95, 0.16, 1.15, "#5b5b5b")   # skorsten
# burspråk mot norr
zb(-0.6, 7.6, -2.2, 1.2, 7.5, 4.55, GUL23); zb(-0.62, 7.6, 5.3, 1.4, 0.14, 4.75, "#d8b866"); zb(-1.33, 7.6, 5.18, 0.04, 0.16, 4.75, VIT23)
for yb_, hh_ in ((0.85, 1.5), (3.7, 1.3)): _p23.fonster(-1.2, 7.6, math.pi, 1.0, hh_, yb_, karm=VIT23, glas="#34404a")
for v_ in (5.36, 9.84): zb(-1.15, v_, -1.6, 0.14, 6.9, 0.14, VIT23)
# svart stålbalkong i södra hörnet på gaveln, ihop med terrassen på utbyggnaden, och en utvändig trappa ner mot söder
zb(9.07, -0.8, 2.92, 6.13, 0.1, 1.6, SV); zb(11.04, 1.81, 2.92, 2.18, 0.1, 3.62, SV)
_racke(_p23, (6.0, -1.58), (12.1, -1.58), 3.02); _racke(_p23, (6.02, -1.58), (6.02, 0.0), 3.02); _racke(_p23, (12.1, 0.2), (12.1, 3.62), 3.02)
for u_ in (6.1, 12.05): _p23.pinne(u_, -1.5, -1.6, 2.92, 0.1, SV)
for k_ in range(14): zb(12.35 + k_ * 0.28, -0.8, 2.92 - (k_ + 1) * 0.21, 0.28, 0.05, 1.1, SV)
for v_ in (-0.27, -1.33): zb(14.17, v_, 1.34, 0.05, 0.22, 4.88, SV, -math.pi / 2, 0.646)
zb(14.17, -1.33, 2.3, 0.04, 0.04, 4.88, SV, -math.pi / 2, 0.646)
ANDRINGAR["H823"] = {**P23_ATTR, "van": 2, "fh": 3.0, "tak": "sadel", "taklutning": _k23, "takUtsprang": _o23, "sakerhet": "foto",
                     "rekt": P23_R(0.0, P23_B, 0.0, P23_FRAM, True), "poly": P23_P(0.0, P23_B, 0.0, P23_FRAM), "fasadBoxar": _p23.lista,
                     "not": "Gul trävilla med brant ockragult plåttak och gaveln mot Platåvägen, vita knutar och vindskivor, spira, skorsten, burspråk "
                            "och svart stålbalkong med utvändig trappa – lite Villa Villekulla (efter foto från Platåvägen)."}
_p23t = Lador(P23_O, P23_U)                                                   # tvärhuset: vindskivor, vindsfönster och spira på södra gaveln
_kt, _ot = 1.5, 0.4; _mt = (P23_FRAM + 19.68) / 2; _ht = (19.68 - P23_FRAM) / 2
for u_, n_ in ((P23_B + 0.5 + 0.47, 0.0), (-0.5 - 0.47, math.pi)):
    for sg in (-1, 1):
        run = _ht + _ot; _p23t.box(u_, _mt + sg * run / 2, 6.0 + (_ht - run / 2) * _kt - 0.28, 0.06, 0.28, math.hypot(run, run * _kt), VIT23, 0.0, sg * math.atan(_kt))
    _p23t.fonster(u_ - (0.47 if n_ == 0.0 else -0.47), _mt, n_, 0.8, 1.2, 6.9, karm=VIT23, glas="#34404a")
for u_ in (-0.43, P23_B + 0.43):
    for v_ in (P23_FRAM + 0.07, 19.61): _p23t.box(u_, v_, -1.6, 0.22, 7.6, 0.22, VIT23)
_p23t.pinne(P23_B + 0.9, _mt, 6.0 + _ht * _kt - 0.1, 6.0 + _ht * _kt + 1.1, 0.07, VIT23); _p23t.box(P23_B + 0.9, _mt, 6.0 + _ht * _kt + 1.0, 0.24, 0.24, 0.24, "#c9562e", form="klot")
_hus_id["h823_tvarhus"]["fasadBoxar"] = _p23t.lista
_p23v = Lador(P23_O, P23_U); _racke(_p23v, (12.1, 3.62), (12.1, P23_FRAM - 0.05), 3.06); _racke(_p23v, (P23_B + 0.5, P23_FRAM - 0.05), (12.1, P23_FRAM - 0.05), 3.06)
_hus_id["h823_utbyggnad"]["fasadBoxar"] = _p23v.lista
# --- H867 (foto från Platåvägen, utkast 49): ljust trähus i två våningar på grå sockel, låglutande sadeltak med stort utsprång och träpanel
# under, fönster med ockragula karmar och två vita balkonger på varandra i västra delen av gaveln mot norr
P67_O, P67_U = (-871.0, 246.1), (0.81988, 0.57262)
P67_W, P67_R, P67_P = lokal(P67_O, P67_U); _p67 = Lador(P67_O, P67_U); hb = _p67.box; P67_B, P67_L = 7.68, 26.4
for yb_ in (0.4, 3.4):
    hb(1.8, -0.6, yb_ - 0.15, 3.0, 0.15, 1.2, "#d9d6cc"); hb(1.8, -1.17, yb_, 3.0, 1.0, 0.06, "#f4f2ec")
    for u_ in (0.32, 3.28): hb(u_, -0.6, yb_, 0.06, 1.0, 1.2, "#f4f2ec")
    hb(2.6, -0.04, yb_, 0.9, 2.1, 0.05, "#3a4650"); hb(2.6, -0.06, yb_, 0.06, 2.1, 0.02, "#d4a24a")
for u_ in (0.35, 3.25): _p67.pinne(u_, -1.15, -1.2, 6.05, 0.1, "#f4f2ec")
ANDRINGAR["H867"] = {"typ": "flerbostad", "van": 2, "fh": 3.0, "vagg": "#e8e4d8", "panel": True, "karmFarg": "#d4a24a", "tak": "sadel", "taklutning": 0.3,
                     "takfarg": "#4f5356", "takUtsprang": 1.0, "gavelUtsprang": 1.0, "takfotFarg": "#e6e1d4", "takUndersida": "#c9b89a", "sakerhet": "foto",
                     "rekt": P67_R(0.0, P67_B, 0.0, P67_L), "poly": P67_P(0.0, P67_B, 0.0, P67_L), "band": [{"y0": -3.0, "y1": 0.4, "farg": "#a8a9a5"}],
                     "fasadBoxar": _p67.lista,
                     "not": "Ljust trähus i två våningar på grå sockel med låglutande sadeltak, stort takutsprång, ockragula karmar och vita balkonger mot norr (efter foto från Platåvägen)."}


# --- Circle K vid rondellen (utkast 50, efter foto från rondellen): butiken (H046), taket över pumparna (H1723) och H1318 som biltvätt
RODK, VITK, GLAS_K, KARM_K = "#d42027", "#ffffff", "#27313a", "#9da2a6"
_p46t = Lador(P46_O, P46_U); tb = _p46t.box                                  # taket: u 2..16, v 17..29, fris 4,95–6,0 m
tb(9.0, 23.0, 5.0, 14.0, 0.3, 12.0, "#f4f4f2"); tb(9.0, 23.0, 5.3, 13.8, 0.12, 11.8, "#cfd0cd")
for u_, v_, b_, d_ in ((9.0, 16.94, 14.24, 0.12), (9.0, 29.06, 14.24, 0.12), (1.94, 23.0, 0.12, 12.0), (16.06, 23.0, 0.12, 12.0)):
    tb(u_, v_, 4.95, b_, 1.05, d_, RODK); tb(u_, v_, 4.86, b_ + (0.02 if b_ > 1 else 0.02), 0.09, d_ + 0.02, VITK)
for u_ in (5.0, 9.0, 13.0):
    for v_ in (20.0, 26.0): tb(u_, v_, 4.96, 1.2, 0.04, 0.3, VITK)             # lysrör i taket
for v_ in (20.0, 26.0):                                                     # två pumpöar med pelare, pumpar, papperskorg och påkörningsskydd
    tb(9.0, v_, -0.25, 10.0, 0.4, 1.3, "#c9c9c4")
    for u_ in (6.0, 12.0): tb(u_, v_, -0.2, 0.45, 5.2, 0.45, "#e2e3e1")
    for u_ in (7.7, 10.3):
        tb(u_, v_, 0.15, 0.55, 1.75, 0.9, "#f2f2f0"); tb(u_, v_, 1.6, 0.57, 0.32, 0.92, RODK)
        for sg in (-1, 1): tb(u_, v_ + sg * 0.46, 1.05, 0.35, 0.3, 0.02, "#1f2830"); tb(u_ + 0.12, v_ + sg * 0.47, 0.7, 0.1, 0.28, 0.04, "#2b2b2b")
    tb(9.0, v_, 0.15, 0.4, 0.8, 0.4, "#3a3d40")
    for u_ in (4.3, 13.7): _p46t.pinne(u_, v_, 0.15, 1.05, 0.14, "#f2c41a")
_hus_id["circlek_tak"]["fasadBoxar"] = _p46t.lista
_hus_id["circlek_tak"]["skyltar"] = [{"text": "CIRCLE K", "mot": [962.0, 1000.0], "hojd": 5.475, "hgt": 0.72, "bredd": 4.6, "bg": RODK, "fg": VITK, "utanTak": True, "ut": 0.07},
                                     {"text": "CIRCLE K", "mot": [900.0, 950.0], "hojd": 5.475, "hgt": 0.72, "bredd": 4.6, "bg": RODK, "fg": VITK, "utanTak": True, "ut": 0.07}]
_p46 = Lador(P46_O, P46_U); kb = _p46.box                                    # butiken: u 0..13,85, v -1..15, framsidan (u = 13,85) mot rondellen
kb(13.88, 7.0, 0.25, 0.06, 2.45, 13.0, GLAS_K)
for k_ in range(9): kb(13.9, 0.5 + k_ * 1.625, 0.25, 0.08, 2.45, 0.08, KARM_K)
kb(13.91, 7.0, 2.68, 0.08, 0.1, 13.2, KARM_K)
for v_, f_ in ((2.0, "#f28c28"), (4.5, "#e3443c"), (9.4, "#f6c445"), (11.9, "#f28c28")): kb(13.92, v_, 0.55, 0.02, 1.3, 1.0, f_)   # affischer i fönstren
kb(13.93, 7.0, -0.05, 0.05, 2.55, 2.2, KARM_K); kb(13.96, 7.0, 0.0, 0.03, 2.4, 1.9, "#1d252d"); kb(14.5, 7.0, 2.75, 1.2, 0.16, 3.0, RODK)   # entré med litet tak
kb(13.9, 7.0, 3.35, 0.05, 0.4, 16.1, RODK); kb(6.925, 15.04, 3.35, 13.95, 0.4, 0.05, RODK)                                        # röd rand
kb(9.0, 15.03, 0.25, 6.0, 2.45, 0.06, GLAS_K)                                                                                    # fönster mot pumparna
kb(14.5, 0.8, 0.0, 0.8, 0.95, 1.6, "#f4f4f2"); kb(14.91, 0.8, 0.55, 0.02, 0.18, 1.5, "#2a6db5")                                   # frys för issäckar
kb(14.5, 13.8, 0.0, 0.8, 1.6, 1.6, "#8d9196")                                                                                    # gasolbur
kb(4.0, 4.0, 4.85, 1.6, 0.8, 1.2, "#9a9ea2"); kb(8.0, 10.0, 4.85, 1.2, 0.6, 1.0, "#9a9ea2")                                       # aggregat på taket
ANDRINGAR["H046"] = {"typ": "affar", "van": 1, "fh": 4.4, "vagg": "#c4c7c9", "panel": "ligg", "utanFonster": True, "tak": "platt", "takfarg": "#707377",
                     "kantFarg": "#b3b6b9", "kantHojd": 0.45, "sakerhet": "foto", "rekt": P46_R(0.0, 13.85, -1.0, 15.0), "poly": P46_P(0.0, 13.85, -1.0, 15.0),
                     "fasadBoxar": _p46.lista, "not": "Butiken på Circle K: ljusgrå plåt, platt tak, glasfasad med affischer och röd rand mot rondellen (efter foto)."}
P18_O, P18_U = (991.0, 912.6), (-0.33456, -0.94238)                           # H1318: u mot NNV längs långsidan, v mot ONO
P18_W, P18_R, P18_P = lokal(P18_O, P18_U); _p18 = Lador(P18_O, P18_U); wb = _p18.box
for u_, ut_ in ((0.0, -1), (18.73, 1)):                                       # tvättportar i båda gavlarna
    wb(u_ + ut_ * 0.03, 4.03, -0.05, 0.06, 3.6, 3.8, "#2d3238"); wb(u_ + ut_ * 0.05, 4.03, 3.55, 0.08, 0.2, 4.2, KARM_K)
    for k_ in range(1, 6): wb(u_ + ut_ * 0.065, 4.03, -0.05 + k_ * 0.6, 0.02, 0.05, 3.8, "#7d848b")
wb(9.365, -0.04, 3.5, 18.8, 0.35, 0.05, RODK); wb(-0.04, 4.03, 3.5, 0.05, 0.35, 8.1, RODK)
for k_ in range(6):                                                         # släpkärror att hyra i en rad öster om tvätten
    u_ = -14.0 + k_ * 2.3
    wb(u_, 13.0, 0.45, 1.4, 0.1, 2.6, "#8d9196")
    for sg in (-1, 1): wb(u_ + sg * 0.68, 13.0, 0.55, 0.04, 0.4, 2.6, "#c9ccce"); wb(u_ + sg * 0.8, 13.0, 0.0, 0.16, 0.56, 0.56, "#222222")
    wb(u_, 11.7 + 0.02, 0.55, 1.4, 0.4, 0.04, "#c9ccce"); wb(u_, 14.3 - 0.02, 0.55, 1.4, 0.4, 0.04, "#c9ccce"); wb(u_, 11.1, 0.42, 0.08, 0.08, 1.2, "#7a7d80")
ANDRINGAR["H1318"] = {"typ": "hall", "van": 1, "fh": 4.6, "vagg": "#c4c7c9", "panel": "ligg", "utanFonster": True, "tak": "platt", "takfarg": "#707377",
                      "kantFarg": "#b3b6b9", "kantHojd": 0.4, "sakerhet": "foto", "rekt": P18_R(0.0, 18.73, 0.0, 8.06), "poly": P18_P(0.0, 18.73, 0.0, 8.06),
                      "fasadBoxar": _p18.lista, "skyltar": [{"text": "BILTVÄTT", "mot": [960.0, 905.0], "hojd": 4.1, "hgt": 0.6, "bredd": 3.6, "bg": VITK, "fg": RODK, "utanTak": True}],
                      "not": "Grå hall vid Circle K, tolkad som biltvätten (portar i båda gavlarna), med släpkärror att hyra bredvid (efter foto)."}

# --- Backen mellan Ringvägen och Torggatan (utkast 53, foto från Torggatan 23)
# H337 uppe på krönet: faluröd villa i en och en halv våning med vita knutar och fönster, gråbrunt tak, en brant tvärgavel mot Torggatan med
# breda vita vindskivor och spira, en takkupa och en vit inglasad veranda i östra delen, svart skorsten. u längs framsidan mot VSV, v in i huset.
P37_O_, P37_U_ = (-637.0, -7.04), (-0.7955, 0.6061)
P337_W, P337_R, P337_P = lokal(P37_O_, P37_U_); _p337 = Lador(P37_O_, P37_U_); vb = _p337.box
ROD337, VIT337, TAK337, K337 = "#9e3a2f", "#ffffff", "#76706a", 1.05
_kg = (3.0 + 4.6 * K337 - 3.0) / 2.75; _tg = math.atan(_kg)                  # tvärgavelns lutning så att nocken hamnar i samma höjd som huvudtaket
vb(9.65, 1.1, -1.0, 5.5, 4.0, 2.2, ROD337)                                    # tvärgavelns utbyggnad framåt
vb(9.65, 3.4, 3.0, 5.5, 4.6 * K337, 6.8, ROD337, form="gavel")               # gavelspetsen
for sg in (-1, 1):
    run = 2.75 + 0.35; L_ = run / math.cos(_tg)
    _p337.skiva(9.65 + sg * run / 2, 3.175, 3.0 + 4.6 * K337 - run / 2 * _kg + 0.06, 7.25, L_, 0.1, TAK337, 0.0 if sg > 0 else math.pi, _tg)
    vb(9.65 + sg * run / 2, -0.47, 3.0 + 4.6 * K337 - run / 2 * _kg - 0.16 - 0.15, 0.07, 0.3, L_, VIT337, -math.pi / 2, sg * _tg)
_p337.pinne(9.65, -0.42, 3.0 + 4.6 * K337 - 0.1, 3.0 + 4.6 * K337 + 0.6, 0.06, VIT337); vb(9.65, -0.42, 3.0 + 4.6 * K337 + 0.55, 0.16, 0.16, 0.16, VIT337, form="klot")
_p337.fonster(9.65, 0.0, -math.pi / 2, 2.3, 1.0, 3.5, karm=VIT337, glas="#34404a")                     # tredelat fönster i gaveln
for du in (-0.38, 0.38): vb(9.65 + du, -0.09, 3.5, 0.06, 1.0, 0.02, VIT337)
vb(9.65, -0.04, 3.05, 5.6, 0.18, 0.06, VIT337)                                                         # vitt band under gavelfönstret
_p337.fonster(10.5, 0.0, -math.pi / 2, 1.9, 1.35, 0.75, karm=VIT337, glas="#34404a")                   # stort fönster i bottenvåningen
for du in (-0.32, 0.32): vb(10.5 + du, -0.09, 0.75, 0.06, 1.35, 0.02, VIT337)
_p337.fonster(7.7, 0.0, -math.pi / 2, 0.55, 1.4, 0.7, karm=VIT337, glas="#34404a")
for u_ in (6.95, 12.35): vb(u_, 0.05, -1.0, 0.14, 4.0, 0.14, VIT337)
for u_, v_ in ((0.05, 2.25), (0.05, 11.35), (12.35, 11.35)): vb(u_, v_, -1.0, 0.14, 4.0, 0.14, VIT337)
# inglasad veranda framför östra delen
vb(3.5, 1.25, -0.6, 6.2, 1.4, 1.9, VIT337)                                                             # bröstning
vb(3.5, 0.32, 0.8, 6.2, 1.3, 0.04, "#3a4650"); vb(0.42, 1.25, 0.8, 0.04, 1.3, 1.9, "#3a4650")
for u_ in (0.45, 2.0, 3.5, 5.0, 6.55): vb(u_, 0.33, 0.8, 0.1, 1.3, 0.1, VIT337)
vb(3.5, 1.25, 2.1, 6.3, 0.2, 2.0, VIT337)
_p337.skiva(3.5, 1.15, 2.42, 6.6, 2.1, 0.08, TAK337, -math.pi / 2, 0.12)
# takkupa på huvudtakets framsida och svart skorsten
vb(3.1, 4.3, 3.9, 3.0, 1.55, 2.0, ROD337); _p337.fonster(3.1, 3.3, -math.pi / 2, 2.0, 0.8, 4.3, karm=VIT337, glas="#34404a")
_p337.skiva(3.1, 4.2, 5.55, 3.4, 2.4, 0.08, TAK337, -math.pi / 2, 0.25)
vb(5.2, 6.8, 6.6, 0.6, 2.5, 0.8, "#2f2f2f")
ANDRINGAR["H337"] = {"typ": "villa", "van": 1, "fh": 3.0, "vagg": ROD337, "panel": True, "karmFarg": VIT337, "tak": "sadel", "taklutning": K337, "takfarg": TAK337,
                     "takUtsprang": 0.45, "takfotFarg": VIT337, "takUndersida": "#f2f0ea", "band": [{"y0": -3.0, "y1": -0.05, "farg": "#8f8e89"}], "sakerhet": "foto",
                     "rekt": P337_R(0.0, 12.4, 2.2, 11.4), "poly": P337_P(0.0, 12.4, 2.2, 11.4), "fasadBoxar": _p337.lista,
                     "not": "Faluröd villa på krönet mellan Torggatan och Ringvägen: brant tvärgavel med breda vita vindskivor mot Torggatan, takkupa, "
                            "vit inglasad veranda och svart skorsten (efter foto från Torggatan)."}
# H277: sutteränghus i orangebrunt tegel med låglutande tak, vit takfot och balkonger med mörkbruna träfronter mot ostsydost.
# u längs östra långsidan från nordöstra hörnet mot sydväst, v in i huset.
P277_O, P277_U = (-557.5, -30.4), (-0.6731, 0.7395)
P277_W, P277_R, P277_P = lokal(P277_O, P277_U); _p277 = Lador(P277_O, P277_U); bb = _p277.box
for u_ in (37.4, 28.6, 19.8, 11.0):
    for k_ in range(4):
        y_ = k_ * 2.9
        bb(u_, -0.75, y_ - 0.12, 5.0, 0.14, 1.5, "#e9e8e4"); bb(u_, -1.47, y_ + 0.02, 5.0, 1.0, 0.06, "#6e3c24"); bb(u_, -1.48, y_ + 1.0, 5.06, 0.06, 0.09, "#f2f2ee")
        for sg in (-1, 1): bb(u_ + sg * 2.47, -0.75, y_ + 0.02, 0.06, 1.0, 1.5, "#6e3c24")
        bb(u_, -0.04, y_, 0.95, 2.15, 0.05, "#3a4650")
_th277 = math.atan(0.25); _run277 = 18.05 / 2 + 0.6
for u_ in (-0.47, 42.19 + 0.47):
    for sg in (-1, 1): bb(u_, 9.025 + sg * _run277 / 2, 11.6 + (9.025 - _run277 / 2) * 0.25 - 0.12 - 0.11, 0.06, 0.22, math.hypot(_run277, _run277 * 0.25), "#f2f2ee", 0.0, sg * _th277)
ANDRINGAR["H277"] = {"typ": "flerbostad", "van": 4, "fh": 2.9, "tegel": "brun", "sutterang": True, "vagg": "#b5643f", "tak": "sadel", "taklutning": 0.25, "takfarg": "#5b5a58",
                     "takUtsprang": 0.6, "takfotFarg": "#f2f2ee", "sakerhet": "foto", "rekt": P277_R(0.0, 42.19, 0.0, 18.05), "poly": P277_P(0.0, 42.19, 0.0, 18.05),
                     "fasadBoxar": _p277.lista, "not": "Sutteränghus i orangebrunt tegel med låglutande tak och vit takfot, balkonger med mörkbruna träfronter (efter foto från Torggatan)."}

# --- Torggatan 17–25 (utkast 54, foto från Torggatan 17): fem likadana trevåningshus på södra sidan väster om Thulegatan (H310, H335, H380, H481, H599).
# Ljust beige tegel, låglutande mörkt tak med ljus takfot, ett ljust betongband över bottenvåningen och där under ett mörkbrunt panelband med
# fönster. Fyra trappuppgångar per hus (A–D) med smala lodräta trapphusfönster, orange nummer- och bokstavsskyltar, trappor med räcken och
# hortensior. Ovanvåningarna har stora fönster och små högt sittande fönster närmast trapphusen. Husnumren 19–25 är antagna (17 från fotot).
def _torghus(hid, nummer):
    h_ = next(x_ for x_ in hus if x_["id"] == hid); cx, cz, b_, d_, rot_ = h_["rekt"]
    if b_ < d_: b_, d_, rot_ = d_, b_, rot_ + math.pi / 2
    A_ = (math.cos(rot_), math.sin(rot_)); N_ = (-A_[1], A_[0])
    tg_ = min((p_ for g_ in gator if g_["namn"] == "Torggatan" for p_ in g_["pts"]), key=lambda p_: math.hypot(p_[0] - cx, p_[1] - cz))
    if (tg_[0] - cx) * N_[0] + (tg_[1] - cz) * N_[1] < 0: N_ = (-N_[0], -N_[1])          # N_ pekar ut mot gatan
    Vin = (-N_[0], -N_[1]); U_ = (Vin[1], -Vin[0])                                        # v in i huset, u åt vänster sett från gatan
    O_ = (cx + d_ / 2 * N_[0] - b_ / 2 * U_[0], cz + d_ / 2 * N_[1] - b_ / 2 * U_[1])
    W_, R_, P_ = lokal(O_, U_); L_ = Lador(O_, U_); x = L_.box; VIT_, GLAS_, MORK_ = "#ffffff", "#3f4a55", "#4a423c"
    Lm = b_ / 4; sk_ = []; mot_ = W_(b_ / 2, -40.0)
    x(b_ / 2, -0.015, 1.5, b_ - 0.2, 1.45, 0.02, MORK_)                                    # mörkt panelband i bottenvåningen mot gatan
    for vv, nn in ((-0.07, 1), (d_ + 0.07, -1)): x(b_ / 2, vv, 2.95, b_ + 0.12, 0.18, 0.14, "#e9e6dd")   # ljust betongband
    for m_ in range(4):
        uc = (m_ + 0.5) * Lm; s_ = Lm / 14.0; bokstav = "ABCD"[3 - m_]                       # A längst till vänster sett från gatan (störst u)
        for o_ in (-5.2, 5.2):
            for k_ in (1, 2): L_.fonster(uc + o_ * s_, 0.0, -math.pi / 2, 1.55, 1.15, 3.0 * k_ + 0.9, karm=VIT_, glas=GLAS_)
            L_.fonster(uc + o_ * s_, 0.0, -math.pi / 2, 2.2, 1.0, 1.72, karm=VIT_, glas=GLAS_)
            for du in (-0.36, 0.36): x(uc + o_ * s_ + du, -0.09, 1.72, 0.05, 1.0, 0.02, VIT_)
            for k_ in range(3): L_.fonster(uc + o_ * s_, d_, math.pi / 2, 1.5, 1.15, 3.0 * k_ + 0.9, karm=VIT_, glas=GLAS_)     # baksidan
        for o_ in (-2.4, 2.4):
            for k_ in (1, 2): L_.fonster(uc + o_ * s_, 0.0, -math.pi / 2, 1.1, 0.42, 3.0 * k_ + 1.63, karm=VIT_, glas=GLAS_)
            L_.fonster(uc + o_ * s_, 0.0, -math.pi / 2, 0.55, 0.9, 1.78, karm=VIT_, glas=GLAS_)
            for k_ in range(3): L_.fonster(uc + o_ * s_, d_, math.pi / 2, 1.1, 1.15, 3.0 * k_ + 0.9, karm=VIT_, glas=GLAS_)
        x(uc, -0.03, 3.3, 0.42, 5.45, 0.06, VIT_); x(uc, -0.065, 3.35, 0.26, 5.35, 0.02, GLAS_)   # trapphusets smala fönsterband
        for k_ in range(7): x(uc, -0.08, 3.35 + k_ * 0.86, 0.3, 0.05, 0.01, VIT_)
        x(uc, -0.02, -0.05, 1.45, 2.5, 0.03, "#d9d4c9"); x(uc, -0.045, -0.02, 1.1, 2.3, 0.04, "#7a5236")   # entrédörr
        x(uc, -0.75, -0.42, 2.0, 0.37, 1.4, "#b7b5ae")                                       # trappa: avsats och två steg
        for k_ in range(2): x(uc, -1.6 - k_ * 0.3, -0.6 - k_ * 0.17, 1.8, 0.17, 0.3, "#b7b5ae")
        for sg in (-1, 1):
            x(uc + sg * 0.95, -1.05, 0.45, 0.04, 0.04, 2.0, "#b9bcbf")
            for vv in (-0.2, -1.0, -1.85): L_.pinne(uc + sg * 0.95, vv, -0.6, 0.47, 0.04, "#b9bcbf")
        for o_ in (-3.6, -5.6, 3.6, 5.6):                                                   # hortensior längs fasaden
            x(uc + o_ * s_, -0.95, -0.55, 1.25, 1.1, 1.25, "#3f6f35", form="klot")
            for du, dv, dy in ((-0.3, -0.5, 0.35), (0.25, -0.55, 0.15), (0.0, -0.45, 0.55)): x(uc + o_ * s_ + du, -0.95 + dv, -0.55 + dy + 0.3, 0.2, 0.2, 0.2, "#f1f1e6")   # blomklasar som små lådor (sparar hörn)
        q1 = W_(uc + 1.15, -0.05); sk_.append({"text": str(nummer), "mot": mot_, "vid": q1, "hojd": 2.25, "hgt": 0.6, "bredd": 0.66, "bg": "#e8775a", "fg": "#ffffff", "utanTak": True})
        sk_.append({"text": bokstav, "mot": mot_, "vid": q1, "hojd": 1.55, "hgt": 0.6, "bredd": 0.66, "bg": "#f1ece6", "fg": "#e8775a", "utanTak": True})
    ANDRINGAR[hid] = {"typ": "flerbostad", "van": 3, "fh": 3.0, "tegel": "beige", "vagg": "#d3c4a6", "tak": "sadel", "taklutning": 0.18, "takfarg": "#3f3f3f",
                      "takUtsprang": 0.45, "takfotFarg": "#e6e2d8", "band": [{"y0": -3.0, "y1": -0.3, "farg": "#a7a6a0"}], "sakerhet": "foto",
                      "adress": "Torggatan %d" % nummer, "rekt": R_(0.0, b_, 0.0, d_), "poly": P_(0.0, b_, 0.0, d_), "fasadBoxar": L_.lista, "skyltar": sk_,
                      "not": "Trevåningshus i ljust beige tegel med mörkt panelband i bottenvåningen, ljust betongband, smala trapphusfönster och "
                             "orange skyltar vid uppgångarna A–D (efter foto från Torggatan 17; likadant som grannhusen 17–25)."}
for hid_, nr_ in (("H310", 17), ("H335", 19), ("H380", 21), ("H481", 23), ("H599", 25)): _torghus(hid_, nr_)

# --- Torggatans norra sida (utkast 56, foton från Torggatan 17 och 21)
# H269: hundra meter långt hus i ljust gult med tre hela våningar och en fjärde i ett mansardtak av grå-blå bandtäckt plåt med takkupor,
# vita balkonger, en vit uteplatsbröstning längs bottenvåningen och en hög grå sockel. u längs framsidan mot Torggatan från östra gaveln
# mot väster, v norrut in i huset. Mansarden byggs av lutande plåtskivor runt om och ett platt tak överst.
P269_O, P269_U = (-432.4, 58.9), (-0.9968, -0.0801)
P269_W, P269_R, P269_P = lokal(P269_O, P269_U); _p269 = Lador(P269_O, P269_U); mb = _p269.box; L269, D269 = 99.92, 14.17
ZINK, ZINK2, VIT269 = "#8a9aa2", "#a3b0b6", "#f6f6f2"
_mi, _mh = 1.2, 2.9; _ml = math.hypot(_mi, _mh); _ma = math.atan2(_mh, _mi)
_p269.skiva(L269 / 2, -0.3 + _mi / 2, 9.0 + _mh / 2, L269 + 0.6, _ml, 0.12, ZINK, -math.pi / 2, _ma)             # mansardens branta del mot gatan
_p269.skiva(L269 / 2, D269 + 0.3 - _mi / 2, 9.0 + _mh / 2, L269 + 0.6, _ml, 0.12, ZINK, math.pi / 2, _ma)        # och mot gården
_p269.skiva(-0.3 + _mi / 2, D269 / 2, 9.0 + _mh / 2, D269 + 0.6, _ml, 0.12, ZINK, math.pi, _ma)                  # valmade gavlar
_p269.skiva(L269 + 0.3 - _mi / 2, D269 / 2, 9.0 + _mh / 2, D269 + 0.6, _ml, 0.12, ZINK, 0.0, _ma)
mb(L269 / 2, D269 / 2, 9.0 + _mh - 0.05, L269 - 2 * (_mi - 0.3) + 0.2, 0.18, D269 - 2 * (_mi - 0.3) + 0.2, ZINK2)  # platt tak överst
mb(L269 / 2, -0.32, 8.92, L269 + 0.7, 0.16, 0.12, VIT269); mb(L269 / 2, D269 + 0.32, 8.92, L269 + 0.7, 0.16, 0.12, VIT269)   # vit takfot
for v_, n_, sg in ((-0.1, -math.pi / 2, -1), (D269 + 0.1, math.pi / 2, 1)):                                       # takkupor med fönsterband
    for k_ in range(23):
        u_ = 4.0 + k_ * 4.18; vc = v_ - sg * 0.7
        mb(u_, vc, 9.35, 1.8, 1.65, 1.4, "#7d8d95"); mb(u_, vc, 11.0, 2.0, 0.1, 1.6, ZINK)
        mb(u_, v_ + sg * 0.03, 9.7, 1.45, 1.0, 0.04, VIT269); mb(u_, v_ + sg * 0.05, 9.77, 1.25, 0.86, 0.02, "#3c4852"); mb(u_, v_ + sg * 0.06, 9.77, 0.05, 0.86, 0.02, VIT269)
# vita balkonger på våning två och tre, en uteplatsbröstning längs hela bottenvåningen mot gatan
for k_ in range(12):
    u_ = 6.0 + k_ * 8.0
    for y_ in (3.0, 6.0):
        mb(u_, -0.7, y_ - 0.15, 3.2, 0.16, 1.4, "#e7e7e2"); mb(u_, -1.38, y_, 3.2, 1.05, 0.06, VIT269)
        for sg in (-1, 1): mb(u_ + sg * 1.57, -0.7, y_, 0.06, 1.05, 1.4, VIT269)
        mb(u_, -0.03, y_ - 0.05, 0.95, 2.2, 0.05, "#3c4852")
mb(L269 / 2, -0.8, -0.25, L269 - 1.0, 0.18, 1.6, "#d8d8d2"); mb(L269 / 2, -1.58, -0.1, L269 - 1.0, 1.0, 0.07, VIT269)
for u_ in (0.55, L269 - 0.55): mb(u_, -0.8, -0.1, 0.07, 1.0, 1.6, VIT269)
ANDRINGAR["H269"] = {"typ": "flerbostad", "van": 3, "fh": 3.0, "vagg": "#ece4c2", "karmFarg": VIT269, "tak": "platt", "takfarg": ZINK2, "kantFarg": ZINK, "kantHojd": 0.05,
                     "golvLyft": 0.8, "band": [{"y0": -3.5, "y1": -0.25, "farg": "#7f8283"}], "sakerhet": "foto",
                     "rekt": P269_R(0.0, L269, 0.0, D269), "poly": P269_P(0.0, L269, 0.0, D269), "fasadBoxar": _p269.lista,
                     "not": "Långt ljusgult hus i tre våningar med en fjärde i grå-blått mansardtak med takkupor, vita balkonger, vit uteplatsbröstning "
                            "och hög grå sockel (efter foto från Torggatan 17)."}
# H370: liten bod i ljus stående panel med platt tak och mörk takkant, och den turkosa muren mellan trottoaren och parkeringen bredvid
_p370 = Lador((-591.6, 59.6), (-0.9969, 0.0789))                               # muren: från parkeringens infart västerut längs Torggatan
_p370.box(7.2, 0.15, -0.8, 14.4, 3.35, 0.26, "#9fd0c8"); _p370.box(7.2, 0.15, 2.55, 14.5, 0.08, 0.32, "#b6dcd6")
for k_ in range(4): _p370.box(1.5 + k_ * 3.9, 0.15, 2.63, 0.16, 0.16, 0.16, "#f4f4f0", form="klot")
_p370.pinne(-0.5, 0.9, -0.3, 0.4, 0.6, "#e8c84a")                             # gult betongblock vid infarten
ANDRINGAR["H370"] = {"typ": "bod", "van": 1, "fh": 2.4, "vagg": "#ece8d0", "panel": True, "utanFonster": True, "tak": "platt", "takfarg": "#4a4c4e",
                     "kantFarg": "#3d3f41", "kantHojd": 0.3, "sakerhet": "foto", "fasadBoxar": _p370.lista,
                     "not": "Liten bod i ljus stående panel med platt tak och mörk takkant, intill den turkosa muren mot parkeringen (efter foto från Torggatan 21)."}

# --- H326 vid Thuleparken (utkast 57, foto från Thulegatan 6): fyra våningar i ljust beige puts över en mörkgrå sockelvåning, platt tak,
# staplade inglasade balkonger med vita ramar på södra och västra sidorna (mot den stora gräsmattan och bollplanen)
H326_POLY = [(-351.8, 109.4), (-350.5, 127.2), (-359.6, 127.9), (-359.9, 125.1), (-370.2, 125.9), (-370.9, 117.3), (-373.6, 117.5), (-374.7, 102.7), (-360.8, 101.7), (-360.2, 110.1)]
VIT326, GLAS326 = "#f3f3ef", "#b8c8d0"
_l326 = []
def _balkong326(i0, antal):
    a_, b_ = H326_POLY[i0], H326_POLY[(i0 + 1) % len(H326_POLY)]; L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1]); U_ = ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_)
    lb = Lador(a_, U_); mb_ = lb.box; bw = 3.3
    for k_ in range(antal):
        u_ = L_ * (k_ + 0.5) / antal
        for y_ in (0.0, 3.0, 6.0, 9.0):
            mb_(u_, -0.7, y_ - 0.16, bw, 0.16, 1.4, "#dcdad4")                                          # balkongplatta
            mb_(u_, -1.37, y_, bw, 1.0, 0.06, VIT326)                                                   # vit bröstning
            for sg in (-1, 1): mb_(u_ + sg * (bw / 2 - 0.03), -0.7, y_, 0.06, 1.0, 1.4, VIT326)
            mb_(u_, -1.36, y_ + 1.0, bw - 0.1, 1.72, 0.03, GLAS326)                                     # inglasning ovanför
            for sg in (-1, 1): mb_(u_ + sg * (bw / 2 - 0.05), -0.7, y_ + 1.0, 0.03, 1.72, 1.3, GLAS326)
            for k2 in range(5): mb_(u_ - bw / 2 + 0.04 + k2 * (bw - 0.08) / 4, -1.38, y_ + 1.0, 0.07, 1.72, 0.07, VIT326)   # vita ramar
            mb_(u_, -1.38, y_ + 1.0, bw, 0.07, 0.08, VIT326); mb_(u_, -1.38, y_ + 2.68, bw, 0.08, 0.08, VIT326)
            mb_(u_, -0.03, y_, 0.95, 2.2, 0.05, "#3c4852")                                              # balkongdörr
        mb_(u_, -0.7, 11.84, bw + 0.1, 0.16, 1.45, "#dcdad4")                                           # tak över översta balkongen
    _l326.extend(lb.lista)
for i0_, n_ in ((1, 2), (3, 2), (4, 1), (6, 3)): _balkong326(i0_, n_)
ANDRINGAR["H326"] = {"typ": "flerbostad", "van": 4, "fh": 3.0, "vagg": "#e9dfc3", "karmFarg": VIT326, "tak": "platt", "takfarg": "#4c4c4a", "kantFarg": "#8e8e8a",
                     "kantHojd": 0.12, "golvLyft": 1.6, "band": [{"y0": -3.0, "y1": -0.05, "farg": "#55585a"}], "sakerhet": "foto", "fasadBoxar": _l326,
                     "not": "Fyra våningar i ljust beige puts över en mörkgrå sockelvåning, platt tak och staplade inglasade balkonger med vita ramar "
                            "mot gräsmattan och bollplanen i Thuleparken (efter foto från Thulegatan 6)."}

# --- Längan vid Kullagatan (H200 med delarna h200_mitt och h200_ost, utkast 59): fönster, balkongstaplar och gavlar som fasadlådor
VITK59, STAL59, GLAS59, DORR59 = "#f1efe8", "#b4b8bb", "#b8c8d0", "#3c4852"
def _kulla_fasad(k_, staplar, kolumner, topp, gavel_o=False, gavel_v=False):
    se, U_, L_, D_ = _kulla_ram(k_); lb = Lador(se, U_); x = lb.box; S = -math.pi / 2; bw = 3.4; rise = D_ / 2 * 0.5
    for u_ in kolumner:                                                                    # fönster mot Torggatan
        for vn in range(4): lb.fonster(u_, 0.0, S, 1.2, 1.3, 2.8 * vn + 0.95, karm=VITK59)
    for i_ in range(int((L_ - 2.4) / 3.4) + 1):                                            # och mot gården (antaget, syns inte på fotona)
        for vn in range(4): lb.fonster(1.7 + i_ * 3.4, D_, math.pi / 2, 1.2, 1.3, 2.8 * vn + 0.95, karm=VITK59)
    for si, u_ in enumerate(staplar):
        for vn in range(4):
            y_ = 2.8 * vn
            x(u_, -0.78, y_ - 0.14, bw, 0.14, 1.5, "#d9d7d0")                              # balkongplatta
            x(u_, -1.5, y_, bw, 1.0, 0.05, VITK59)                                          # vit front av profilerad plåt
            for sg in (-1, 1): x(u_ + sg * (bw / 2 - 0.03), -0.78, y_, 0.05, 1.0, 1.45, VITK59)
            x(u_ - 0.75, -0.03, y_ + 0.02, 0.9, 2.1, 0.05, DORR59); lb.fonster(u_ + 0.75, 0.0, S, 1.1, 1.3, y_ + 0.95, karm=VITK59)   # balkongdörr och fönster
            if (vn + si) % 2 == 1:                                                         # varannan balkong är inglasad
                x(u_, -1.49, y_ + 1.0, bw - 0.1, 1.55, 0.03, GLAS59)
                for sg in (-1, 1): x(u_ + sg * (bw / 2 - 0.05), -0.78, y_ + 1.0, 0.03, 1.55, 1.4, GLAS59)
                for k2 in range(4): x(u_ - bw / 2 + 0.04 + k2 * (bw - 0.08) / 3, -1.51, y_ + 1.0, 0.06, 1.55, 0.06, VITK59)
                x(u_, -1.51, y_ + 2.5, bw, 0.07, 0.07, VITK59)
        for sg in (-1, 1): x(u_ + sg * bw / 2, -1.5, -0.35, 0.07, 11.4, 0.07, STAL59)       # stålpelare från marken till taket
        if topp == "pergola":                                                              # bruna reglar med ljusa plastskivor över översta balkongen
            for sg in (-1, 1): x(u_ + sg * bw / 2, -0.8, 10.92, 0.09, 0.12, 1.75, "#6b4a3a")
            for v_ in (-1.6, -1.2, -0.8, -0.4): x(u_, v_, 11.04, bw + 0.3, 0.06, 0.07, "#6b4a3a")
            x(u_, -0.82, 11.1, bw + 0.3, 0.02, 1.7, "#d6cec2")
        else:
            x(u_, -0.78, 11.06, bw + 0.2, 0.12, 1.65, VITK59)                              # tak över översta balkongen
            if topp == "gavel":                                                            # frontespis: vit trekantig gavel med tegeltak bakom
                x(u_, 0.3, 11.18, bw + 0.5, 1.45, 3.9, KULLA_TAK, form="gavel"); x(u_, -1.63, 11.18, bw + 0.2, 1.3, 0.08, VITK59, form="gavel")
            else:                                                                          # vit rundbåge
                x(u_, 0.3, 11.18, bw + 0.4, 1.6, 3.9, "#d9d6cf", form="bage"); x(u_, -1.63, 11.18, bw + 0.2, 1.5, 0.08, VITK59, form="bage")
    if gavel_o:                                                                            # östra gaveln: en fönsterrad, ett smalt fönster och vit gavelspets
        for vn in range(4): lb.fonster(0.0, 2.6, math.pi, 1.2, 1.3, 2.8 * vn + 0.95, karm=VITK59); lb.fonster(0.0, 7.6, math.pi, 0.6, 0.9, 2.8 * vn + 1.2, karm=VITK59)
        x(-0.04, D_ / 2, 11.2 + rise - 1.15, 4.6, 1.1, 0.06, VITK59, a=math.pi / 2, form="gavel")
    if gavel_v:                                                                            # västra gaveln mot Kullagatan (antagen, syns inte på fotona)
        for vn in range(4):
            for v_ in (2.8, D_ - 2.8): lb.fonster(L_, v_, 0.0, 1.2, 1.3, 2.8 * vn + 0.95, karm=VITK59)
        x(L_ + 0.04, D_ / 2, 11.2 + rise - 1.15, 4.6, 1.1, 0.06, VITK59, a=math.pi / 2, form="gavel")
    return lb.lista
_seV, _uV, _lV, _dV = _kulla_ram("v"); _wV, _rV, _pV = lokal(_seV, _uV)
ANDRINGAR["H200"] = {**_kulla_attr(KULLA_GUL), "adress": "Kullagatan 4", "sakerhet": "foto", "rekt": _rV(0.0, _lV, 0.0, _dV), "poly": _pV(0.0, _lV, 0.0, _dV),
                     "x": _rV(0.0, _lV, 0.0, _dV)[0], "z": _rV(0.0, _lV, 0.0, _dV)[1],
                     "fasadBoxar": _kulla_fasad("v", (4.5, 15.25, 26.0), (1.7, 8.4, 11.3, 19.1, 22.1, 28.8), "gavel", gavel_v=True),
                     "not": "Västra delen av längan vid Kullagatan: gult tegel i fyra våningar, sadeltak i rött tegel och balkongstaplar med vit trekantig gavel överst (efter foto från Torggatan 12)."}
_hus_id["h200_mitt"]["fasadBoxar"] = _kulla_fasad("m", (4.5, 14.75, 25.0), (1.7, 8.2, 11.1, 18.4, 21.3, 27.8), "bage")
_hus_id["h200_ost"]["fasadBoxar"] = _kulla_fasad("o", (3.0, 9.4, 15.8, 22.2), (6.2, 12.6, 19.0, 25.2), "pergola", gavel_o=True)
for oid_, k_, u_, v_ in (("h200_trapp1", "m", 29.95, 14.2), ("h200_trapp2", "o", 28.85, 13.7)):     # port och trapphusfönster mot gården (antaget)
    _se, _u, _l, _d = _kulla_ram(k_); _lt = Lador(_se, _u); _lt.box(u_, v_ + 0.03, 0.0, 1.3, 2.2, 0.05, "#5a4034")
    for vn in range(1, 4): _lt.fonster(u_, v_, math.pi / 2, 1.0, 1.3, 2.8 * vn + 0.4, karm=VITK59)
    _hus_id[oid_]["fasadBoxar"] = _lt.lista
print("Kullagatan: fasadlådor", sum(len(_hus_id[o_]["fasadBoxar"]) for o_ in ("h200_mitt", "h200_ost", "h200_trapp1", "h200_trapp2")) + len(ANDRINGAR["H200"]["fasadBoxar"]))

# --- H283 söder om Torggatan (utkast 60, foto från Torggatan 5 mot söder): tre våningar i ljus puts över en mörkgrå sockelvåning, platt tak
# med mörk kant, inglasade balkonger med mörkgrå fronter i staplar mot Torggatan. Fasaden är förskjuten i tre steg; varje kant får sina lådor.
H283_POLY = [(-108.1, 123.5), (-102.9, 136.3), (-107.2, 138.1), (-106.8, 139.1), (-120.2, 144.6), (-119.7, 145.8), (-133.0, 151.2), (-132.7, 152.1),
             (-145.2, 157.2), (-150.3, 144.7), (-137.8, 139.6), (-138.3, 138.3), (-125.0, 132.8), (-125.5, 131.7), (-112.0, 126.2), (-112.5, 125.3)]
VIT283, GRA283, GLAS283, RUTA283 = "#f2f2ee", "#676b6a", "#a9bcc6", "#44535e"
_l283 = []
def _kant283(i0, balkonger, kolumner):
    """en fasadkant från hörn i0 till nästa; u längs kanten, v in i huset. balkonger och kolumner är lägen längs kanten (negativa räknas från slutet)."""
    a_, b_ = H283_POLY[i0], H283_POLY[(i0 + 1) % len(H283_POLY)]; L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1]); U_ = ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_)
    lb = Lador(a_, U_); x = lb.box; S = -math.pi / 2; bw = 4.4
    for u_ in kolumner:
        u_ = u_ if u_ >= 0 else L_ + u_
        for vn in range(3): lb.fonster(u_, 0.0, S, 1.3, 1.3, 2.9 * vn + 1.0, karm=VIT283, glas=RUTA283)
    for u_ in balkonger:
        u_ = u_ if u_ >= 0 else L_ + u_
        for vn in range(3):
            y_ = 2.9 * vn
            x(u_, -0.68, y_ - 0.12, bw, 0.12, 1.3, "#b9b7b0")                                    # balkongplatta
            x(u_, -1.3, y_ - 0.12, bw, 1.17, 0.06, GRA283)                                       # mörkgrå front
            for sg in (-1, 1): x(u_ + sg * (bw / 2 - 0.03), -0.68, y_, 0.06, 1.05, 1.3, GRA283)
            x(u_, -1.29, y_ + 1.05, bw - 0.1, 1.6, 0.03, GLAS283)                                # inglasning
            for sg in (-1, 1): x(u_ + sg * (bw / 2 - 0.04), -0.68, y_ + 1.05, 0.03, 1.6, 1.25, GLAS283)
            for k2 in range(6): x(u_ - bw / 2 + 0.03 + k2 * (bw - 0.06) / 5, -1.31, y_ + 1.05, 0.05, 1.6, 0.05, VIT283)
            x(u_, -1.31, y_ + 2.62, bw, 0.06, 0.06, VIT283)
            x(u_ - 0.9, -0.03, y_ + 0.02, 0.9, 2.1, 0.05, RUTA283); lb.fonster(u_ + 0.8, 0.0, S, 1.5, 1.3, y_ + 1.0, karm=VIT283, glas=RUTA283)
        x(u_, -0.68, 8.62, bw + 0.1, 0.12, 1.36, "#5a5e5d")                                      # tak över översta balkongen
    _l283.extend(lb.lista)
_kant283(15, (2.37,), ())                 # hörnet längst i öster mot Torggatan: en balkongstapel
_kant283(13, (), (4.6, 10.2))             # östra delen: två fönsterrader
_kant283(11, (2.6, -2.6), (6.1, 8.3))     # mittdelen: balkonger i båda ändar
_kant283(9, (-2.6,), (2.2, 5.2, 8.0))     # västra delen: balkong i östra änden
for i0_ in (3, 5, 7): _kant283(i0_, (), (2.0, 5.5, 9.0, 12.4))                                    # södra sidan (antagen, syns inte på fotot)
_kant283(1, (), (2.3,)); _kant283(0, (), (4.0, 9.8)); _kant283(8, (), (3.7, 9.8))                 # östra biten och gavlarna (antagna)
ANDRINGAR["H283"] = {"typ": "flerbostad", "van": 3, "fh": 2.9, "vagg": "#e4e0d4", "utanFonster": True, "tak": "platt", "takfarg": "#4c4f50", "kantFarg": "#454a49", "kantHojd": 0.22,
                     "golvLyft": 1.3, "band": [{"y0": -4.0, "y1": -0.02, "farg": "#5b5e5f"}], "sakerhet": "foto", "fasadBoxar": _l283,
                     "not": "Tre våningar i ljus puts över en mörkgrå sockelvåning, platt tak med mörk kant och inglasade balkonger med mörkgrå fronter "
                            "mot Torggatan (efter foto från Torggatan 5)."}
print("H283: fasadlådor", len(_l283))

# --- Torggatan 11, 13 och grannarna (H315, H321, H323, H325; utkast 62, foto från Torggatan 11): fyra likadana hus i ljusgul puts, tre
# våningar över en mörkgrå sockelvåning med garageportar i västra gaveln, platt tak med mörk kant. Varje hus är två förskjutna huskroppar
# med trapphus i innerhörnet (mörkt glasparti, port, tegelskorsten på taket). Alla fyra har samma hörnordning i OpenStreetMap:
# 0–1 östra fasaden, 1–2 och 3–4 söder, 4–5 och 6–7 väster, 7–8 norr (västra kroppen, mot Torggatan), 8–9 inre östfasad, 9–0 norr (östra kroppen).
T11_VIT, T11_RUTA, T11_SOCKEL, T11_PORT = "#f1efe6", "#3f4d58", "#50555c", "#3b4047"
def _torg11(hid):
    P_ = [tuple(p) for p in next(h for h in hus if h["id"] == hid)["poly"]]; lista = []; S = -math.pi / 2; FH = 2.8
    def kant(i0):
        a_, b_ = P_[i0], P_[(i0 + 1) % len(P_)]; L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1]); return Lador(a_, ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_)), L_
    def rader(lb, lagen, w=1.05, hgt=1.4, yb=0.9):
        for u_ in lagen:
            for vn in range(3): lb.fonster(u_, 0.0, S, w, hgt, FH * vn + yb, karm=T11_VIT, glas=T11_RUTA)
    # västra kroppens västfasad: hörnfönster, två fönster och ett smalt per våning, och fyra garageportar i sockeln
    lb, L_ = kant(6); rader(lb, (L_ - 1.0,), 1.1, 1.5, 0.8); rader(lb, (L_ - 5.4, L_ - 6.9, 3.4, 1.9)); rader(lb, (L_ - 8.9,), 0.45, 1.2, 1.0)
    for k_ in range(4):
        u_ = L_ - 1.9 - 3.0 * k_; lb.box(u_, -0.04, -2.3, 2.6, 2.05, 0.06, T11_PORT); lb.box(u_, -0.05, -0.25, 2.7, 0.07, 0.07, "#6c727a")
        for r_ in range(1, 4): lb.box(u_, -0.075, -2.3 + r_ * 0.5, 2.5, 0.03, 0.02, "#2c3036")
    lista += lb.lista
    # västra kroppens norrfasad mot Torggatan: hörnfönster vid nordvästra hörnet, och två portar i sockeln närmast trapphuset
    lb, L_ = kant(7); rader(lb, (1.0,), 1.1, 1.5, 0.8)
    for u_ in (L_ - 1.2, L_ - 2.6): lb.box(u_, -0.04, -2.3, 1.0, 2.1, 0.06, "#2e3238")
    lista += lb.lista
    lb, L_ = kant(8); rader(lb, (2.6, 5.6)); lista += lb.lista                                       # inre östfasaden (antagen)
    # östra kroppens norrfasad: trapphusets mörka glasparti med port i innerhörnet, ett smalt och ett brett fönster per våning
    lb, L_ = kant(9); lb.box(0.9, -0.05, 0.0, 1.3, 3 * FH - 0.3, 0.08, "#39414a"); lb.box(0.9, -0.04, -2.3, 1.1, 2.1, 0.06, "#2e3238")
    for vn in range(1, 3): lb.box(0.9, -0.07, FH * vn - 0.1, 1.4, 0.12, 0.08, "#8d9296")
    rader(lb, (3.6,), 0.45, 1.2, 1.0); rader(lb, (6.4,), 1.3, 1.4)
    for u_ in (3.6, 6.4): lb.fonster(u_, 0.0, S, 0.7, 0.5, -1.3, karm=T11_VIT, glas=T11_RUTA)
    lb.box(1.6, 2.6, 3 * FH, 1.3, 2.6, 1.3, "#8a4a3c"); lb.box(1.6, 2.6, 3 * FH + 2.6, 1.45, 0.12, 1.45, "#3a3a3a")   # tegelskorsten med plåthuv
    lb.box(3.6, 3.2, 3 * FH, 2.4, 1.3, 2.6, "#9a9d9e")                                               # grått fläkthus bredvid
    lista += lb.lista
    for i0_, lagen in ((0, (2.2, 5.4, 8.9, 12.4, 15.6)), (1, (2.4, 6.8)), (3, (2.6, 7.8)), (4, (2.8, 5.8))):   # övriga fasader (antagna)
        lb, L_ = kant(i0_); rader(lb, lagen); lista += lb.lista
    return lista
# adresser (utkast 66, användarens besked): de fem husen på södra sidan mellan centrum och Thulegatan är Torggatan 7–15 från öster
# till väster. Nummer 15 är H326 i hörnet mot Thulegatan (körskolan; byggt i utkast 57), och får sin adress här nedanför.
ADR62 = {"H315": "Torggatan 7", "H321": "Torggatan 9", "H323": "Torggatan 11", "H325": "Torggatan 13"}
ANDRINGAR["H326"]["adress"] = "Torggatan 15"
for hid_ in ("H315", "H321", "H323", "H325"):
    ANDRINGAR[hid_] = {**({"adress": ADR62[hid_]} if hid_ in ADR62 else {}),"typ": "flerbostad", "van": 3, "fh": 2.8, "vagg": "#d8cea4", "utanFonster": True, "tak": "platt", "takfarg": "#4a4a48", "kantFarg": "#3c3d3c", "kantHojd": 0.18,
                       "golvLyft": 2.3, "band": [{"y0": -5.0, "y1": -0.02, "farg": T11_SOCKEL}], "sakerhet": "foto", "fasadBoxar": _torg11(hid_),
                       "not": "Ljusgul puts i tre våningar över en mörkgrå sockelvåning med garageportar i västra gaveln, platt tak, trapphus med mörkt glasparti "
                              "och tegelskorsten (efter foto från Torggatan 11; alla fyra husen är byggda likadant)."}
print("Torggatan 11: fasadlådor per hus", len(ANDRINGAR["H321"]["fasadBoxar"]))

# --- Västra Storgatan 25 (H070 och garaget, utkast 64): stort vitt trähus i en och en halv våning med brant sadeltak i mörka pannor
VIT25, TAK25, RUTA25, TRA25 = "#f4f2ec", "#3f3d3c", "#3a4650", "#8b6b4a"
_l25 = Lador(V25_O, V25_U); _b25 = _l25.box
for u_ in (2.2, 5.6, 9.75, 13.9, 17.3):                                                   # långsidorna (antagna, skyms helt av träden på fotot)
    _l25.fonster(u_, 0.0, -math.pi / 2, 1.2, 1.3, 0.95, karm=VIT25, glas=RUTA25); _l25.fonster(u_, 9.07, math.pi / 2, 1.2, 1.3, 0.95, karm=VIT25, glas=RUTA25)
for u_, n_ in ((0.0, math.pi), (19.5, 0.0)):                                              # gavlarna: två fönster nere och två uppe i gavelspetsen
    for v_ in (2.4, 6.67): _l25.fonster(u_, v_, n_, 1.2, 1.3, 0.95, karm=VIT25, glas=RUTA25)
    for v_ in (3.5, 5.57): _l25.fonster(u_, v_, n_, 1.0, 1.2, 3.75, karm=VIT25, glas=RUTA25)
_b25(-1.5, 4.5, -0.25, 3.0, 0.2, 7.4, TRA25)                                              # altan i trä utanför västra gaveln, med räcke
for v_ in (0.85, 8.15): _b25(-1.5, v_, 0.9, 3.0, 0.08, 0.08, TRA25)
_b25(-2.96, 4.5, 0.9, 0.08, 0.08, 7.4, TRA25)
for v_ in (0.85, 2.7, 4.5, 6.3, 8.15): _b25(-2.96, v_, -0.05, 0.09, 1.0, 0.09, TRA25)
for u_ in (-1.5,): 
    for v_ in (0.85, 8.15): _b25(u_, v_, -0.05, 0.09, 1.0, 0.09, TRA25)
for v_ in (1.75, 3.6, 5.4, 7.25): _b25(-2.96, v_, 0.35, 0.03, 0.05, 1.7, TRA25)             # mellanliggare
_b25(-1.5, 4.5, -1.6, 0.12, 1.4, 0.12, TRA25); _b25(-2.9, 1.0, -1.6, 0.12, 1.4, 0.12, TRA25); _b25(-2.9, 8.0, -1.6, 0.12, 1.4, 0.12, TRA25)   # stolpar under altanen
_b25(14.0, 4.53, 7.0, 0.7, 1.3, 0.7, "#2e2e2e")                                           # skorsten
ANDRINGAR["H070"] = {"typ": "villa", "van": 1, "fh": 3.1, "vagg": VIT25, "panel": True, "utanFonster": True, "karmFarg": VIT25, "tak": "sadel", "taklutning": 1.0, "takfarg": TAK25,
                     "takUtsprang": 0.45, "takfotFarg": VIT25, "takUndersida": "#efede6", "band": [{"y0": -3.0, "y1": -0.05, "farg": "#8f8e89"}],
                     "adress": "Västra Storgatan 25", "sakerhet": "foto", "fasadBoxar": _l25.lista,
                     "not": "Stort vitt trähus i en och en halv våning med brant sadeltak i mörka pannor och altan vid västra gaveln (efter foto från infarten; "
                            "huset skyms nästan helt av träd, så fönster och altan är antagna). Numret 25 står på garaget."}
_g25 = Lador(V25_O, V25_U); _gb = _g25.box
_gb(-10.0, -2.04, 0.0, 3.5, 2.15, 0.06, "#3b4047")                                          # mörkgrå garageport
for r_ in range(1, 4): _gb(-10.0, -2.075, r_ * 0.54, 3.4, 0.03, 0.02, "#2b2f35")
_gb(-10.0, -2.05, 2.15, 3.7, 0.1, 0.07, VIT25)
_gb(-10.4, 5.6, 0.9, 3.2, 2.1, 2.4, VIT25); _gb(-10.4, 5.6, 3.0, 3.6, 0.1, 2.9, "#4a4a4a", rx=0.0)   # liten vit bod med pulpettak bakom garaget
for du in (-0.7, 0.0, 0.7): _gb(-10.4 + du, 4.38, 2.2, 0.28, 0.55, 0.04, RUTA25)
_hus_id["h070_garage"]["fasadBoxar"] = _g25.lista
_hus_id["h070_garage"]["skyltar"] = [{"text": "25", "mot": V25_W(-9.75, -40.0), "vid": V25_W(-7.6, -2.05), "hojd": 1.7, "hgt": 0.28, "bredd": 0.4, "bg": "#e4dfd0", "fg": "#2a2a2a", "utanTak": True}]

# --- H706 i hörnet Torggatan/Nygatan/Platåvägen (utkast 67, foton från korsningen och från infarten på Torggatan): sutteränghus med
# låglutande sadeltak i mörka pannor. Mot korsningen (väster, uppför) syns en våning i ljust blågrå panel; mot infarten (öster, nedför)
# två våningar i vitt tegel med balkong. Gaveln mot Torggatan har grå panel i gavelspetsen och ett förråd med pulpettak nedanför.
# u från norra hörnet längs östra fasaden (nocken går längs u), v västerut in i huset; Torggatan går längs v vid u ≈ −13,6.
T706_O, T706_U = (-788.3, 160.0), (0.5214, 0.8533)
T706_W, T706_R, T706_P = lokal(T706_O, T706_U)
TEG706, PAN706, GRA706, TAK706, VIT706, RUTA706 = "#e9e6dc", "#b3c1c6", "#a7abad", "#484543", "#f4f3ee", "#3a4650"
_l706 = Lador(T706_O, T706_U); _x = _l706.box; _L, _D, _FH = 12.67, 9.7, 2.6; _K = 0.45
_x(7.8, 10.4, 0.0, 6.0, _FH, 1.5, TEG706); _x(7.8, 10.4, _FH, 6.0, _FH, 1.5, PAN706)             # utbyggnaden på västra sidan
_l706.skiva(7.8, 10.75, 2 * _FH + 0.12, 6.5, 2.3, 0.1, TAK706, math.pi / 2, math.atan(_K))
for u0_, u1_ in ((0.0, 4.8), (10.8, _L)): _x((u0_ + u1_) / 2, _D + 0.03, _FH - 0.5, u1_ - u0_, _FH + 0.5, 0.06, PAN706)   # panel på västra fasadens övervåning
for u_ in (5.7, 7.1, 8.5, 9.9):                                                                  # fönsterraden med blomlådor under ett vitt skärmtak
    _l706.fonster(u_, 11.15, math.pi / 2, 1.0, 1.1, _FH + 1.0, karm=VIT706, glas=RUTA706); _x(u_, 11.3, _FH + 0.78, 0.9, 0.16, 0.2, "#b8433f")
_x(7.8, 11.6, 2 * _FH - 0.35, 5.9, 0.07, 0.9, VIT706)
_l706.fonster(2.4, _D, math.pi / 2, 1.2, 1.2, _FH + 0.95, karm=VIT706, glas=RUTA706); _l706.fonster(11.8, _D, math.pi / 2, 0.8, 1.2, _FH + 0.95, karm=VIT706, glas=RUTA706)
for u_, gn in ((-0.04, math.pi), (_L + 0.04, 0.0)): _x(u_, _D / 2, 2 * _FH, _D - 0.1, _D / 2 * _K - 0.1, 0.06, GRA706, a=math.pi / 2, form="gavel")   # grå panel i gavelspetsarna
for v_ in (2.6, 7.1):                                                                            # södra gaveln (antagen)
    for vn in range(2): _l706.fonster(_L, v_, 0.0, 1.2, 1.2, _FH * vn + 0.95, karm=VIT706, glas=RUTA706)
# östra fasaden: balkong med grå panelfront på övervåningen, dörr och fönster under
_x(3.9, -0.75, _FH - 0.14, 7.4, 0.14, 1.5, "#cfcdc6"); _x(3.9, -1.47, _FH, 7.4, 0.95, 0.06, "#b9bdc0"); _x(3.9, -1.47, _FH + 0.95, 7.4, 0.06, 0.08, VIT706)
for u_ in (0.23, 7.57): _x(u_, -0.75, _FH, 0.06, 0.95, 1.45, "#b9bdc0")
for u_ in (0.25, 3.9, 7.55): _x(u_, -1.45, 0.0, 0.09, _FH, 0.09, VIT706)
_x(3.0, -0.03, _FH + 0.02, 0.9, 2.05, 0.05, VIT706); _x(3.0, -0.045, _FH + 1.0, 0.6, 0.9, 0.03, RUTA706)
for u_ in (1.4, 5.3, 6.6): _l706.fonster(u_, 0.0, -math.pi / 2, 1.1, 1.2, _FH + 0.95, karm=VIT706, glas=RUTA706)
for u_ in (10.0, 11.6): _l706.fonster(u_, 0.0, -math.pi / 2, 1.1, 1.2, _FH + 0.95, karm=VIT706, glas=RUTA706)
_x(4.4, -0.03, 0.02, 0.9, 2.05, 0.05, VIT706); _x(4.4, -0.045, 1.0, 0.5, 0.8, 0.03, RUTA706)       # entrédörr i bottenvåningen
for u_ in (2.3, 6.4, 10.4): _l706.fonster(u_, 0.0, -math.pi / 2, 1.0, 1.2, 0.95, karm=VIT706, glas=RUTA706)
_x(6.4, -0.6, 0.0, 1.5, 0.45, 0.5, VIT706); _x(6.4, -0.38, 0.45, 1.5, 0.4, 0.06, VIT706)          # vit bänk vid väggen
# förrådet vid gaveln mot Torggatan: grå panel, fönsterband upptill och mörkt pulpettak
_x(-1.6, 5.6, 0.0, 3.2, 2.55, 7.6, GRA706); _l706.skiva(-1.75, 5.6, 2.78, 8.2, 3.7, 0.09, "#3c3a39", math.pi, 0.13)
_x(-3.22, 6.0, 1.75, 0.04, 0.5, 5.6, RUTA706)
for k_ in range(9): _x(-3.24, 3.3 + k_ * 0.675, 1.75, 0.05, 0.5, 0.05, VIT706)
_x(5.2, _D / 2, 2 * _FH + _D / 2 * _K - 0.35, 0.75, 1.2, 0.9, "#9a4a38"); _x(5.2, _D / 2, 2 * _FH + _D / 2 * _K + 0.85, 0.85, 0.08, 1.0, "#3a3a3a")   # tegelskorsten
_x(3.2, _D / 2 + 0.9, 2 * _FH + _D / 2 * _K - 0.6, 0.4, 0.75, 0.4, "#3f3f3f")                     # ventilationshuv
_r706 = T706_R(0.0, _L, 0.0, _D)
ANDRINGAR["H706"] = {"typ": "villa", "van": 2, "fh": _FH, "sutterang": True, "tegel": "ljus", "vagg": TEG706, "utanFonster": True, "karmFarg": VIT706, "tak": "sadel", "taklutning": _K,
                     "takfarg": TAK706, "takUtsprang": 0.55, "takfotFarg": VIT706, "takUndersida": "#efede6", "gavelUtsprang": 0.5,
                     "rekt": _r706, "poly": T706_P(0.0, _L, 0.0, _D), "x": _r706[0], "z": _r706[1], "sakerhet": "foto", "fasadBoxar": _l706.lista,
                     "not": "Sutteränghus i vitt tegel och ljust blågrå panel med låglutande sadeltak i mörka pannor: en våning mot korsningen, två våningar "
                            "med balkong mot infarten, och förråd med pulpettak vid gaveln mot Torggatan (efter foton från korsningen och från infarten)."}

# --- Västra Storgatan, södra sidan väster om centrum (utkast 68, tre foton från gatan mot söder). Marken stiger söderut, så husen är
# sutteränghus med två hela våningar mot gatan.
# H065: rött trähus i två våningar med vita knutar och foder, låglutande sadeltak, inbyggd balkong i mitten och en framskjuten del i väster.
# u österut längs norra fasaden från flygelns hörn, v söderut in i huset. Huvudkroppen är u −6,4…16 och v 0…8,65; flygeln v −2,5…0.
R65_O, R65_U = (-586.1, -162.0), (0.9914, 0.1309)
R65_W, R65_R, R65_P = lokal(R65_O, R65_U)
ROD65, VIT65, TAK65, RUTA65 = "#9a2c2a", "#f3f1ea", "#403c3a", "#3b4852"
_l65 = Lador(R65_O, R65_U); _x = _l65.box; _N, _S = -math.pi / 2, math.pi / 2; _FH = 2.6
_x(-3.25, -1.2, 0.0, 6.3, 2 * _FH - 0.15, 2.6, ROD65); _l65.skiva(-3.25, -1.5, 2 * _FH + 0.02, 6.9, 3.4, 0.1, TAK65, _N, 0.2)       # framskjuten del i väster
for vn in range(2): _l65.fonster(-3.25, -2.5, _N, 1.2, 1.3, _FH * vn + 0.95, karm=VIT65, glas=RUTA65)
for u_ in (-6.38, -0.12): _x(u_, -2.5, 0.0, 0.14, 2 * _FH - 0.15, 0.14, VIT65)
_x(15.95, -0.03, 0.0, 0.14, 2 * _FH, 0.14, VIT65)
for u_ in (12.3, 14.4): _l65.fonster(u_, 0.0, _N, 1.1, 1.3, _FH + 0.95, karm=VIT65, glas=RUTA65)                                       # östra delen
_x(12.0, -0.03, 0.02, 0.95, 2.05, 0.05, VIT65); _x(12.0, -0.045, 1.0, 0.5, 0.8, 0.03, RUTA65); _l65.fonster(14.2, 0.0, _N, 1.7, 1.3, 0.95, karm=VIT65, glas=RUTA65)
_x(5.9, -0.5, _FH - 0.14, 9.9, 0.14, 1.0, "#d8d5cd")                                                                                # balkongen i mitten
for k_ in range(4): _x(1.0 + 3.27 * k_, -0.97, 0.0, 0.12, 2 * _FH, 0.12, VIT65)
for k_ in range(3): _x(2.63 + 3.27 * k_, -0.97, _FH + 0.05, 3.0, 0.9, 0.05, ROD65)
_x(5.9, -0.97, _FH + 0.98, 9.9, 0.07, 0.09, VIT65); _x(5.9, -0.97, 2 * _FH - 0.16, 9.9, 0.16, 0.12, VIT65)
for u_ in (2.6, 5.9, 9.2): _l65.fonster(u_, 0.0, _N, 1.3, 1.3, _FH + 0.95, karm=VIT65, glas=RUTA65)
_x(7.6, -0.03, 0.02, 0.95, 2.05, 0.05, VIT65); _x(7.6, -0.045, 1.0, 0.5, 0.8, 0.03, RUTA65); _l65.fonster(3.4, 0.0, _N, 1.7, 1.3, 0.95, karm=VIT65, glas=RUTA65)
for u_ in (-3.0, 2.5, 8.0, 13.0): _l65.fonster(u_, 8.65, _S, 1.2, 1.3, _FH + 0.95, karm=VIT65, glas=RUTA65)                           # baksidan och gavlarna (antagna)
for v_ in (2.6, 6.0):
    _l65.fonster(16.0, v_, 0.0, 1.1, 1.3, _FH + 0.95, karm=VIT65, glas=RUTA65); _l65.fonster(-6.4, v_, math.pi, 1.1, 1.3, _FH + 0.95, karm=VIT65, glas=RUTA65)
_r65 = R65_R(-6.4, 16.0, 0.0, 8.65)
ANDRINGAR["H065"] = {"typ": "flerbostad", "van": 2, "fh": _FH, "sutterang": True, "vagg": ROD65, "panel": True, "utanFonster": True, "karmFarg": VIT65, "tak": "sadel", "taklutning": 0.3,
                     "takfarg": TAK65, "takUtsprang": 0.5, "takfotFarg": VIT65, "gavelUtsprang": 0.4, "rekt": _r65, "poly": R65_P(-6.4, 16.0, 0.0, 8.65), "x": _r65[0], "z": _r65[1],
                     "sakerhet": "foto", "fasadBoxar": _l65.lista,
                     "not": "Rött trähus i två våningar med vita knutar, låglutande sadeltak, inbyggd balkong i mitten och en framskjuten del i väster (efter foto från Västra Storgatan)."}
# H079: putsat hus med mörkgrå bottenvåning och ljusare övervåning, sadeltak i rött tegel med frontespis mot gatan, grön entrédörr.
# u österut längs fasaden mot gatan, v söderut in i huset.
G79_O, G79_U = (-625.1, -173.8), (0.9949, 0.1010)
G79_W, G79_R, G79_P = lokal(G79_O, G79_U)
OVR79, NED79, BRUN79, TEG79 = "#b5ad9e", "#7b7a76", "#3b2d26", "#8c4b3b"
_l79 = Lador(G79_O, G79_U); _x = _l79.box; _FH = 2.7; _L, _D, _K = 12.87, 10.45, 0.8
for u_, w_ in ((1.7, 1.4), (6.7, 1.1), (8.9, 1.1), (11.2, 1.0)): _l79.fonster(u_, 0.0, _N, w_, 1.3, 0.85, karm=VIT65, glas=RUTA65)
_x(3.7, -0.03, 0.0, 1.15, 2.2, 0.05, VIT65); _x(3.7, -0.05, 0.02, 0.95, 2.08, 0.04, "#2f6a40"); _x(3.7, -0.075, 1.25, 0.4, 0.5, 0.02, RUTA65)   # grön entrédörr
_x(4.9, -0.12, 1.2, 0.5, 0.65, 0.22, "#e8e8e4"); _x(12.87 / 2, -0.03, _FH - 0.04, 12.9, 0.08, 0.05, "#e8e6df")                        # elskåp och ljust band mellan våningarna
for u_, w_ in ((3.6, 1.6), (9.4, 1.3)): _l79.fonster(u_, 0.0, _N, w_, 1.25, _FH + 1.0, karm=BRUN79, glas=RUTA65)
_x(8.2, 1.2, 2 * _FH, 3.5, 1.9, 2.4, OVR79); _x(8.2, 1.3, 2 * _FH + 1.9, 4.0, 1.35, 2.9, TEG79, form="gavel")                         # frontespis
_x(8.2, -0.02, 2 * _FH + 1.9, 3.5, 1.15, 0.05, OVR79, form="gavel"); _l79.fonster(8.2, 0.0, _N, 1.5, 1.2, 2 * _FH + 0.45, karm=BRUN79, glas=RUTA65)
for v_, w_, yb in ((2.6, 0.6, _FH + 1.0), (6.4, 0.6, _FH + 1.0), (4.2, 0.6, 0.9), (7.6, 0.6, 0.9), (_D / 2, 0.9, 2 * _FH + 0.9)):       # östra gaveln
    _l79.fonster(_L, v_, 0.0, w_, 1.1, yb, karm=VIT65, glas=RUTA65)
for u_ in (2.5, 6.5, 10.5): _l79.fonster(u_, _D, _S, 1.2, 1.25, _FH + 1.0, karm=BRUN79, glas=RUTA65)                                   # baksidan (antagen)
_x(4.6, _D / 2, 2 * _FH + _D / 2 * _K - 0.3, 0.8, 1.3, 0.8, "#93503f"); _x(4.6, _D / 2, 2 * _FH + _D / 2 * _K + 1.0, 0.9, 0.08, 0.9, "#3a3a3a")   # skorsten
_r79 = G79_R(0.0, _L, 0.0, _D)
ANDRINGAR["H079"] = {"typ": "villa", "van": 2, "fh": _FH, "sutterang": True, "vagg": OVR79, "utanFonster": True, "karmFarg": VIT65, "tak": "sadel", "taklutning": _K, "takfarg": TEG79,
                     "takUtsprang": 0.4, "takfotFarg": VIT65, "gavelUtsprang": 0.35, "band": [{"y0": -3.0, "y1": _FH - 0.04, "farg": NED79}],
                     "rekt": _r79, "poly": G79_P(0.0, _L, 0.0, _D), "x": _r79[0], "z": _r79[1], "sakerhet": "foto", "fasadBoxar": _l79.lista,
                     "not": "Putsat hus med mörkgrå bottenvåning och ljusare övervåning, sadeltak i rött tegel med frontespis mot gatan och grön entrédörr (efter foton från Västra Storgatan)."}
# H095: tillbyggnaden väster om H079: vit profilerad plåt med ett brett brunt fönsterband en trappa upp, putsad bottenvåning med vit garageport.
T95_O, T95_U = (-633.5, -176.0), (0.9884, 0.1521)
T95_W = lokal(T95_O, T95_U)[0]
_l95 = Lador(T95_O, T95_U); _x = _l95.box
_x(4.7, -0.04, 0.0, 2.7, 2.35, 0.06, "#eeeeea"); _x(4.7, -0.07, 0.03, 2.45, 2.1, 0.03, "#fafaf7"); _x(4.7, -0.05, 2.35, 2.7, 0.5, 0.05, "#d5d5d0")     # garageport
_l95.fonster(1.7, 0.0, _N, 1.2, 1.2, 0.9, karm="#5a4638", glas="#d8d6cc")
_x(4.0, -0.04, _FH + 0.75, 5.7, 1.6, 0.06, BRUN79)
for k_ in range(3): _x(2.15 + k_ * 1.85, -0.07, _FH + 0.87, 1.65, 1.36, 0.03, RUTA65)
_x(3.95, -0.25, 2 * _FH - 0.02, 8.4, 0.14, 0.6, "#5a4638")                                                                           # brun takfot
_x(-3.5, 2.6, 0.0, 6.4, 2.3, 2.8, "#e2e2de"); _l95.skiva(-3.5, 2.3, 2.5, 6.9, 3.6, 0.1, "#b5553f", _N, 0.22)                           # vitt plåtskjul med rött tegeltak väster om
ANDRINGAR["H095"] = {"typ": "villa", "van": 2, "fh": _FH, "sutterang": True, "vagg": "#dcdcd7", "panel": True, "utanFonster": True, "tak": "platt", "takfarg": "#4a4644",
                     "kantFarg": "#5a4638", "kantHojd": 0.15, "band": [{"y0": -3.0, "y1": _FH, "farg": NED79}], "sakerhet": "foto", "fasadBoxar": _l95.lista,
                     "not": "Tillbyggnad till huset intill: vit plåt med brett fönsterband över en putsad bottenvåning med vit garageport, och ett plåtskjul med tegeltak väster om (efter foto)."}

# --- Fastigheten mittemot Värmlandsbergsgatan, norra sidan av Västra Storgatan (utkast 69, foton från gatan och från väster).
# Tre byggnader i rad: H1466 i väster (garagelänga), H1464 i mitten (carport) och H618 i öster (bostadshuset med brutet tak).
# Alla tre har ett lokalt system med origo i sydöstra hörnet, u västerut längs fasaden mot gatan och v norrut in i byggnaden.
V69_N, V69_S = -math.pi / 2, math.pi / 2           # utåtnormal för fasaden mot gatan (v = 0) respektive baksidan
# H618: bostadshus med brutet tak (mansard) i mörk plåt, ljus liggande panel i bottenvåningen och mörkbruna gavelspetsar.
S618_O, S618_U = (-896.1, -238.5), (-0.9873, -0.1592)
S618_W, S618_R, S618_P = lokal(S618_O, S618_U)
LJUS618, BRUN618, TAK618, KARM618, RUTA618 = "#ddd6c0", "#4a3729", "#3b3e40", "#6b5443", "#2f3a42"
_L618, _D618, _FH618 = 12.56, 9.83, 2.45
_l618 = Lador(S618_O, S618_U); _b618 = _l618.box
for u_, w_ in ((3.0, 1.15), (5.4, 1.15)): _l618.fonster(u_, 0.0, V69_N, w_, 0.8, 1.5, karm=KARM618, glas=RUTA618)   # små fönster i bottenvåningen mot gatan
_l618.fonster(9.4, 0.0, V69_N, 0.9, 0.8, 1.5, karm=KARM618, glas=RUTA618)
_b618(11.6, -0.03, 0.02, 0.95, 2.0, 0.05, "#7d8a80"); _b618(11.6, -0.055, 1.15, 0.5, 0.55, 0.03, RUTA618)                                               # dörr i västra änden
_l618.fonster(0.0, 4.9, math.pi, 1.0, 1.5, 3.2, karm=KARM618, glas=RUTA618)                        # tall fönster i östra gavelspetsen
_l618.fonster(_L618, 4.9, 0.0, 0.9, 1.2, 3.1, karm=KARM618, glas=RUTA618)
for v_ in (2.6, 7.2): _l618.fonster(0.0, v_, math.pi, 0.7, 0.7, 1.5, karm=KARM618, glas=RUTA618)
# brutet tak: branta nedre takfall utanpå långsidorna, från takfot strax under väggkrönet upp till brytpunkten vid krönet
for v_, fall_ in ((-0.62, V69_N), (_D618 + 0.62, V69_S)):
    _l618.skiva(_L618 / 2, v_, 3.62, _L618 + 0.7, 3.08, 0.12, TAK618, fall_, 1.132)
    _l618.box(_L618 / 2, v_ - 0.62 * (1 if fall_ < 0 else -1), 2.12, _L618 + 0.7, 0.16, 0.26, TAK618)   # takfot längst ner på det branta fallet
_b618(4.0, _D618 / 2, 2 * _FH618 + _D618 / 2 * 0.38 - 0.45, 0.8, 1.5, 0.8, "#8e5a44")               # tegelskorsten
_b618(4.0, _D618 / 2, 2 * _FH618 + _D618 / 2 * 0.38 + 1.05, 0.9, 0.08, 0.9, "#3a3a3a")
ANDRINGAR["H618"] = {"typ": "villa", "van": 2, "fh": _FH618, "vagg": LJUS618, "panel": "ligg", "utanFonster": True, "karmFarg": KARM618, "tak": "sadel", "taklutning": 0.38,
                     "takfarg": TAK618, "takUtsprang": 0.35, "takfotFarg": TAK618, "takUndersida": "#55504a", "gavelUtsprang": 0.3, "band": [{"y0": _FH618, "y1": 2 * _FH618 + 0.12, "farg": BRUN618}],
                     "sakerhet": "foto", "fasadBoxar": _l618.lista,
                     "skyltar": [{"text": "44", "vid": S618_W(10.4, -0.06), "mot": S618_W(10.4, -8.0), "hojd": 1.95, "hgt": 0.24, "bredd": 0.32, "bg": LJUS618, "fg": "#3a3328", "utanTak": True}],
                     "not": "Bostadshus med brutet tak i mörk plåt, ljus liggande panel i bottenvåningen, mörkbruna gavelspetsar och tegelskorsten. Numret 44 står på "
                            "fasaden mot gatan (efter foton från Västra Storgatan)."}
# H1464: carport i mörkbrun stående panel med öppen framsida mot gatan och mörkt grågrönt sadeltak.
C64_O, C64_U = (-914.3, -245.3), (-0.9957, -0.0955)
C64_W = lokal(C64_O, C64_U)[0]
BRUN64, MORK64 = "#4a3426", "#17130f"
_l64 = Lador(C64_O, C64_U); _b64 = _l64.box
_b64(4.6, 0.45, 0.0, 3.8, 2.25, 0.9, MORK64)                                                       # den öppna bilplatsen
for u_ in (2.6, 6.6): _b64(u_, -0.02, 0.0, 0.2, 2.5, 0.2, BRUN64)                                  # stolpar
_b64(4.6, -0.02, 2.25, 4.2, 0.28, 0.12, BRUN64)
_b64(1.3, -0.03, 0.02, 0.95, 2.0, 0.05, "#3a2a1e")                                                 # dörr i den slutna delen
ANDRINGAR["H1464"] = {"typ": "bod", "van": 1, "fh": 2.5, "vagg": BRUN64, "panel": True, "utanFonster": True, "tak": "sadel", "taklutning": 0.55, "takfarg": "#4e544a",
                      "takUtsprang": 0.35, "takfotFarg": "#3f392f", "gavelUtsprang": 0.3, "sakerhet": "foto", "fasadBoxar": _l64.lista,
                      "not": "Carport i mörkbrun stående panel med öppen bilplats mot gatan, dörr i den slutna delen och mörkt grågrönt sadeltak (efter foto från Västra Storgatan)."}
# H1466: lång garagelänga i ljus stående panel med tegelrött sadeltak och brun port i gaveln mot gatan.
G66_O, G66_U = (-926.2, -243.7), (-0.9892, -0.1439)
G66_W = lokal(G66_O, G66_U)[0]
VIT66, PORT66 = "#efece2", "#5a3b26"
_l66 = Lador(G66_O, G66_U); _b66 = _l66.box
_b66(2.9, -0.04, 0.0, 3.1, 2.55, 0.06, PORT66)                                                     # brun dubbelport i gaveln
_b66(2.9, -0.075, 0.0, 0.07, 2.55, 0.05, "#432c1d"); _b66(2.9, -0.06, 2.55, 3.3, 0.12, 0.1, VIT66)
_l66.fonster(2.9, 0.0, V69_N, 0.85, 0.65, 3.75, karm=VIT66, glas="#55606a")                        # litet fönster i gavelspetsen
for v_ in (3.5, 9.5): _l66.fonster(0.0, v_, math.pi, 0.8, 0.7, 2.3, karm=VIT66, glas="#55606a")     # fönster på östra långsidan
ANDRINGAR["H1466"] = {"typ": "bod", "van": 1, "fh": 3.5, "vagg": VIT66, "panel": True, "utanFonster": True, "tak": "sadel", "taklutning": 0.5, "takfarg": "#a85b3c",
                      "takUtsprang": 0.3, "takfotFarg": VIT66, "gavelUtsprang": 0.35, "sakerhet": "foto", "fasadBoxar": _l66.lista,
                      "not": "Lång garagelänga i ljus stående panel med tegelrött sadeltak och brun dubbelport i gaveln mot gatan (efter foto från Västra Storgatan)."}

# --- H555, huvudbyggnaden på fastigheten söder om Västra Storgatan mittemot Värmlandsbergsgatan (utkast 70, tre foton: från gatan i väster,
# från infarten och från Värmlandsbergsgatans början). Gult trähus i två våningar med liggande panel, vitt band mellan våningarna, mörkt
# sadeltak, hörntorn med spetsig huv i nordvästra hörnet, svart smidesbalkong och röda portar i bottenvåningen mot gatan.
# u österut längs fasaden mot gatan från nordvästra hörnet, v söderut in i huset.
S55_O, S55_U = (-884.1, -220.6), (0.982, 0.185)
S55_W, S55_R, S55_P = lokal(S55_O, S55_U)
GUL55, VIT55, ROD55, TAK55, RUTA55, SVART55 = "#d6c171", "#f4f2ea", "#8e2f28", "#3a3632", "#39414a", "#1b1b1b"
_L55, _D55, _FH55 = 12.42, 13.34, 3.0
N55, S55S, W55, E55 = -math.pi / 2, math.pi / 2, math.pi, 0.0
_l55 = Lador(S55_O, S55_U); _x55 = _l55.box
# fasaden mot gatan: fönster uppe, röd port, vit dörr och fönster nere
for u_ in (4.8, 6.8, 8.8, 11.0): _l55.fonster(u_, 0.0, N55, 1.15, 1.5, 3.4, karm=VIT55, glas=RUTA55)
for u_ in (4.6, 11.4): _l55.fonster(u_, 0.0, N55, 1.15, 1.35, 0.8, karm=VIT55, glas=RUTA55)
_x55(6.7, -0.04, 0.0, 2.3, 2.3, 0.06, ROD55); _x55(6.7, -0.07, 0.0, 0.07, 2.3, 0.05, "#6e241f")      # röd port
_x55(9.2, -0.04, 0.02, 1.0, 2.1, 0.06, VIT55); _x55(9.2, -0.065, 1.25, 0.5, 0.55, 0.03, RUTA55)      # vit dörr
# svart smidesbalkong på övervåningen
_x55(10.3, -0.55, 3.18, 2.7, 0.12, 1.1, "#cfcabc")
_x55(10.3, -0.03, 3.2, 0.95, 2.05, 0.05, VIT55); _x55(10.3, -0.055, 4.25, 0.6, 0.85, 0.03, RUTA55)
for du_ in (-1.33, 1.33): _x55(10.3 + du_, -0.58, 3.3, 0.05, 0.95, 1.1, SVART55)
_x55(10.3, -1.08, 3.3, 2.7, 0.95, 0.05, SVART55); _x55(10.3, -1.08, 4.25, 2.8, 0.08, 0.08, SVART55)
for k_ in range(9): _x55(9.0 + k_ * 0.325, -1.08, 3.3, 0.045, 0.95, 0.045, SVART55)
# gavlarna och baksidan (antagna)
for v_ in (5.6, 8.6, 11.4):
    _l55.fonster(0.0, v_, W55, 1.1, 1.5, 3.4, karm=VIT55, glas=RUTA55); _l55.fonster(_L55, v_, E55, 1.1, 1.5, 3.4, karm=VIT55, glas=RUTA55)
for v_ in (8.6, 11.4):
    _l55.fonster(0.0, v_, W55, 1.1, 1.35, 0.8, karm=VIT55, glas=RUTA55); _l55.fonster(_L55, v_, E55, 1.1, 1.35, 0.8, karm=VIT55, glas=RUTA55)
_x55(-0.03, 5.6, 0.02, 1.0, 2.1, 0.06, ROD55, a=math.pi / 2)                                          # röd dörr på västra gaveln
for u_ in (3.0, 6.5, 10.0):
    _l55.fonster(u_, _D55, S55S, 1.15, 1.5, 3.4, karm=VIT55, glas=RUTA55); _l55.fonster(u_, _D55, S55S, 1.15, 1.35, 0.8, karm=VIT55, glas=RUTA55)
# hörntornet i nordvästra hörnet, med vitt band, korsad spetsig huv och spira
_x55(1.35, 1.35, 0.0, 3.3, 6.7, 3.3, GUL55)
_x55(1.35, 1.35, 2.88, 3.42, 0.3, 3.42, VIT55)
for a_ in (0.0, math.pi / 2): _x55(1.35, 1.35, 6.7, 3.7, 3.0, 3.7, TAK55, a=a_, form="gavel")
_x55(1.35, 1.35, 9.7, 0.11, 0.85, 0.11, SVART55, form="cyl")
for u_, v_, n_ in ((1.35, -0.3, N55), (-0.3, 1.35, W55)):
    _l55.fonster(u_, v_, n_, 1.1, 1.5, 3.4, karm=VIT55, glas=RUTA55); _l55.fonster(u_, v_, n_, 1.1, 1.35, 0.8, karm=VIT55, glas=RUTA55)
_x55(5.0, _D55 / 2 - 0.4, 7.4, 0.85, 2.5, 0.85, "#8e5a44"); _x55(5.0, _D55 / 2 - 0.4, 9.9, 0.95, 0.1, 0.95, "#3a3a3a")   # skorsten
ANDRINGAR["H555"] = {"typ": "villa", "van": 2, "fh": _FH55, "vagg": GUL55, "panel": "ligg", "utanFonster": True, "karmFarg": VIT55, "tak": "sadel", "taklutning": 0.45,
                     "takfarg": TAK55, "takUtsprang": 0.3, "takfotFarg": VIT55, "takUndersida": "#6e6960", "gavelUtsprang": 0.05,
                     "band": [{"y0": 2.88, "y1": 3.18, "farg": VIT55}], "sakerhet": "foto", "fasadBoxar": _l55.lista,
                     "not": "Gult trähus i två våningar med liggande panel, vitt band mellan våningarna, mörkt sadeltak, hörntorn med spetsig huv, "
                            "svart smidesbalkong och röda portar i bottenvåningen (efter foton från Västra Storgatan)."}

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
TOPO_FIL = next((f for f in (os.path.join(HERE, 'data_topo_hojd.json'), os.path.join(HERE, 'data', 'topo_hojd.json')) if os.path.exists(f)), '')
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
# gräsmatta kring H226 och asfalterad uppställningsplats framför brandstationens portar mot Kullagatan (efter foton)
ytor.append({"typ": "gras", "namn": "", "poly": [[-262.5, 86.6], [-246.6, 89.4], [-244.6, 78.7], [-241.4, 78.4], [-240.4, 92.6], [-262.5, 90.6]]})
ytor.append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": [[-236.2, 19.0], [-224.6, 15.0], [-229.1, 35.5], [-232.8, 53.5], [-234.9, 65.2], [-246.1, 65.4], [-239.4, 30.9], [-238.2, 31.1], [-236.4, 21.9]]})
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
BORTTAGNA = {"H015": "Godsmagasinet/Auktionisten är rivet – asfaltsparkering i dag",
             "H084": "Rivet för ett par år sedan – gräsmatta, buskar och träd i dag (efter foto)",
             "H113": "Rivet för ett par år sedan – gräsmatta, buskar och träd i dag (efter foto)"}
_auk = next(h for h in hus if h["id"] == "H015")
hus = [h for h in hus if h["id"] not in BORTTAGNA]
# den stora asfaltsytan runt de rivna husen H084/H113 är borta; ytorna vid spåret där återvinningen står är fria från bilar
ytor[:] = [y for y in ytor if not (y["typ"] == "parkering" and y["poly"] and y["poly"][0] == [-404.2, -73.6])]
for y in ytor:
    if y["typ"] == "parkering" and y["poly"] and y["poly"][0] in ([-346.0, -137.3], [-380.9, -136.6]): y["ingaBilar"] = True
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

# ------------------------------------------------------------------ H068: fickparkering längs Västra Storgatan, trottoar och planteringar mot huset (efter foton)
# körbanans kant ligger vid v = -6.7; fickorna (2.4 m) går fram till trottoaren, med en planterad ö och ett ungt träd med trädskydd i var ände
_v_kant = -6.7
utan_trottoar.append([H068_W(8.0, -7.2), H068_W(73.0, -7.2), H068_W(73.0, -3.9), H068_W(8.0, -3.9)])
_pp = [H068_W(11.8, _v_kant), H068_W(68.6, _v_kant), H068_W(68.6, -4.3), H068_W(11.8, -4.3)]
ytor.append({"typ": "parkering", "namn": "", "poly": _pp, "ingaBilar": True})
for (u0, u1) in ((9.2, 11.8), (68.6, 71.6)):
    ytor.append({"typ": "torg", "namn": "", "poly": [H068_W(u0, _v_kant), H068_W(u1, _v_kant), H068_W(u1, -4.3), H068_W(u0, -4.3)]})
_n_fickor = 9; _fl = (68.6 - 11.8) / _n_fickor
for k_ in range(_n_fickor + 1):
    u_ = 11.8 + k_ * _fl; parkeringslinjer.append([round(c, 2) for c in H068_W(u_, _v_kant + 0.05) + H068_W(u_, -4.35)])
_bil_rikt = round(math.atan2(H068_U[0], H068_U[1]), 3)
for k_ in (0, 2, 5, 7):
    c_ = H068_W(11.8 + (k_ + 0.5) * _fl, -5.5); parkerade.append([c_[0], c_[1], _bil_rikt, 4])
_pskylt = H068_W(71.0, -3.95)
torg_skyltar.append({"x": _pskylt[0], "z": _pskylt[1], "rot": round(math.atan2(-H068_U[0], -H068_U[1]), 3), "typ": "P", "under": ["1 tim"], "pil": True})
# gångbanan längs huset flyttas in bakom fickorna
for g in gator:
    if g["osm"] == "638705139":
        for q in g["pts"]:
            du = (q[0] + 294.49) * H068_U[0] + (q[1] + 33.01) * H068_U[1]
            if 0.0 < du < 80.0: q[0], q[1] = H068_W(du, -3.1)
H068_BUSKAGE = [{"pts": [H068_W(u0, -0.95), H068_W(u1, -0.95)], "bredd": 1.3, "hojd": 1.15, "tujor": [], "blommor": ["#c9a2d8", "#f2f0ea", "#b88cc8"]}
                for (u0, u1) in ((9.3, 21.0), (23.2, 41.0), (42.9, 54.6), (56.6, 71.7))]
_rot_flagga = round(math.atan2(-(-H068_U[1]), -H068_U[0]) - 0.55, 3)   # flaggan vänd mot gatan, lite snett mot trafiken västerifrån
H068_FLAGGOR = [{"x": H068_W(u_, -1.25)[0], "z": H068_W(u_, -1.25)[1], "rot": _rot_flagga, "text": "ÖPPET", "bg": "#d4e86e", "fg": "#2c55b0"} for u_ in (49.8, 60.6)]
H068_TRAD = [{"x": H068_W(u_, -5.5)[0], "z": H068_W(u_, -5.5)[1], "h": 7.0, "r": 1.9, "smal": True, "skydd": True} for u_ in (10.5, 70.1)]
_gp = H068_W(37.8, -2.3)

# ------------------------------------------------------------------ där H084 och H113 stod: gräsmatta, buskage och träd; återvinningsstation vid spåret (efter foton)
_A, _d, _n = (-339.2, -148.6), (-0.874, -0.486), (-0.486, 0.874)   # norra kanten av asfaltsremsan längs spåret, _n in mot vägen
_P = lambda s_, o_: (round(_A[0] + _d[0] * s_ + _n[0] * o_, 2), round(_A[1] + _d[1] * s_ + _n[1] * o_, 2))
ATERVINNING = [{"x": _P(s_, 1.6)[0], "z": _P(s_, 1.6)[1], "rot": round(math.atan2(_n[0], _n[1]), 3)} for s_ in [12.0 + 2.2 * k for k in range(9)]]
CONTAINRAR = [{"x": _P(34.5, 2.6)[0], "z": _P(34.5, 2.6)[1], "rot": round(-math.atan2(_d[1], _d[0]), 3), "b": 6.0, "h": 1.5, "d": 2.4, "farg": "#2f5d3a"}]
RIVET_TRAD = [{"x": -401.9, "z": -80.0, "h": 15.0, "r": 3.6, "smal": True},          # hög pelarformad poppel vid infarten
              {"x": -383.0, "z": -88.0, "h": 13.0, "r": 6.0}, {"x": -366.0, "z": -112.0, "h": 11.0, "r": 5.0},
              {"x": -349.0, "z": -118.0, "h": 12.0, "r": 5.5}, {"x": -340.0, "z": -101.0, "h": 10.0, "r": 4.5}, {"x": -376.5, "z": -128.5, "h": 9.0, "r": 3.8}]
RIVET_BUSKAGE = [{"pts": [[-393.5, -103.5], [-384.0, -114.0], [-374.0, -124.5], [-362.0, -131.0]], "bredd": 4.0, "hojd": 2.6, "tujor": []},
                 {"pts": [[-362.0, -104.0], [-353.0, -99.0], [-344.0, -93.0]], "bredd": 3.5, "hojd": 2.3, "tujor": []},
                 {"pts": [[-404.5, -86.0], [-401.5, -93.0], [-399.0, -101.0], [-396.5, -108.0]], "bredd": 2.6, "hojd": 2.0, "tujor": []},
                 {"pts": [[-387.0, -97.0], [-380.0, -101.5]], "bredd": 3.0, "hojd": 1.8, "tujor": []},
                 {"pts": [[-354.0, -138.0], [-344.0, -131.5], [-335.0, -125.0]], "bredd": 3.0, "hojd": 2.2, "tujor": []}]
torg_skyltar.append({"x": -405.65, "z": -77.7, "rot": round(math.atan2(-0.588, 0.809), 3), "typ": "forbudInfart", "klotter": True})

# ------------------------------------------------------------------ Bistro Barens uteservering mot stationshusets västra gavel (efter foto från Gerdtmans)
# trädäck med grått brädstaket och glas med vita ramar, pulpettak mot gaveln, runda buskar och unga träd på gräsmattan runt om
_SA, _SU, _SN = (-19.94, 3.15), (0.0958, -0.9954), (-0.9954, -0.0958)   # gavelns sydvästra hörn, riktning norrut längs gaveln, normal västerut
_SP = lambda t_, d_: [round(_SA[0] + _SU[0] * t_ + _SN[0] * d_, 2), round(_SA[1] + _SU[1] * t_ + _SN[1] * d_, 2)]
TERRASSER = [{"a": _SP(0.6, 0), "b": _SP(11.6, 0), "n": list(_SN), "djup": 7.2, "dack": 0.45, "oppning": [5.0, 6.5], "skylt": "GNESTA BISTRO BAR",
              "bord": [[t_ - 0.6, d_] for t_ in (2.2, 4.4, 6.6, 8.8, 10.8) for d_ in (2.2, 5.1)]}]
# gång- och cykelvägen från Västra Storgatan (vid x -63, z -3) ner till gångtunneln under spåret: buskar på båda sidor (efter beskrivning, utkast 36)
def _sidolinjer(pts, offs, s0, s1, steg=2.2):
    """punkter längs båda sidor av en linje; offs är en funktion av sträckan s (avstånd från mittlinjen)"""
    ut = {1: [], -1: []}; tot = 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); dx, dz = (b[0] - a[0]) / L, (b[1] - a[1]) / L; s_ = max(0.0, s0 - tot)
        while s_ <= L and tot + s_ <= s1:
            o = offs(tot + s_)
            for sg in (1, -1): ut[sg].append([round(a[0] + dx * s_ - dz * o * sg, 2), round(a[1] + dz * s_ + dx * o * sg, 2)])
            s_ += steg
        tot += L
    return ut
_g014 = next(g for g in gator if g["osm"] == "38081233")["pts"]
_gvB = _sidolinjer(_g014, lambda s_: 3.0 if s_ < 36 else 3.7, 12.6, 63.0)
STN_BUSKAGE = [{"pts": [_SP(t_, 8.4) for t_ in (0.0, 2.4, 4.8, 7.2, 9.6, 12.0)], "bredd": 1.5, "hojd": 1.35, "tujor": []},
               {"pts": _gvB[1], "bredd": 1.7, "hojd": 1.5, "tujor": []}, {"pts": _gvB[-1], "bredd": 1.7, "hojd": 1.5, "tujor": []},
               {"pts": [_SP(12.6, d_) for d_ in (0.8, 3.6, 6.4)], "bredd": 1.4, "hojd": 1.3, "tujor": []},
               {"pts": [_SP(-0.7, 7.4), _SP(-0.7, 4.8)], "bredd": 1.2, "hojd": 1.2, "tujor": []}]
STN_TRAD = [{"x": _SP(-1.6, 10.2)[0], "z": _SP(-1.6, 10.2)[1], "h": 5.5, "r": 1.15, "smal": True},
            {"x": _SP(4.0, 17.0)[0], "z": _SP(4.0, 17.0)[1], "h": 7.0, "r": 3.2}, {"x": _SP(13.5, 10.5)[0], "z": _SP(13.5, 10.5)[1], "h": 6.0, "r": 1.7, "smal": True}]

torg_skyltar.append({"x": -64.3, "z": -3.3, "rot": -0.208, "typ": "gangCykel"})   # gång- och cykelbana där gångvägen mot tunneln börjar

# ------------------------------------------------------------------ PÅSKÄGG Granbackavägen 108: marken runt huset, parkeringen och trädgården planas till entréns nivå
# (huset står annars på en meterhög sockel mot parkeringen); höjdankare var 4:e meter, tonas ut av sig själva runt kanten
# (utkast 41) marken är plan hela vägen från infarten vid garagelängornas början fram till huset, i nivå med gång- och cykelvägen;
# bakom husen stiger skogsbacken mjukt upp igen
GB_MARK = 29.6
for _u in range(-12, 35, 4):
    for _v in range(-12, 43, 4):
        _p = GB_W(_u, _v); hojdankare.append([round(_p[0], 1), round(_p[1], 1), GB_MARK, 5, 1.0])
    for _v, _t in ((-16, GB_MARK + 0.9), (-20, GB_MARK + 1.9)):
        _p = GB_W(_u, _v); hojdankare.append([round(_p[0], 1), round(_p[1], 1), _t, 5, 1.0])
# grannlängan H1580 på samma plana nivå som 108, och H1593 på en egen avsats i slänten vid dörren mot grusvägen (utkast 43)
for _u in range(-2, 40, 4):
    for _v in range(3, -15, -4):
        _p = H80_W(_u, _v); hojdankare.append([round(_p[0], 1), round(_p[1], 1), GB_MARK, 5, 1.0])
for _s in (-H93_L / 2 - 1.0, -H93_L / 4, 0.0, H93_L / 4, H93_L / 2 + 1.0):
    for _t in (-H93_D / 2 - 1.0, 0.0, H93_D / 2 + 1.0):
        _p = H93_W(_s, _t); hojdankare.append([round(_p[0], 1), round(_p[1], 1), GB_MARK + 1.2, 4, 1.0])
# STOPP Köpcentrum (utkast 46): marken under köpcentret och gångytan framför planas till parkeringens nivå (golvet läggs annars på
# den högsta marken i fotavtrycket, nästan 3 m över parkeringen); bakom huset tar en slänt upp skillnaden mot skogsbacken
ST_MARK = 15.6
for _u in range(-18, 62, 4):
    for _v in range(-54, 9, 4):
        _p = ST_W(_u, _v); hojdankare.append([round(_p[0], 1), round(_p[1], 1), ST_MARK, 5, 1.0])
    _p = ST_W(_u, -58.0); hojdankare.append([round(_p[0], 1), round(_p[1], 1), ST_MARK + 1.0, 4, 1.0])
# ------------------------------------------------------------------ Menuettvägen och tomten vid Kadriljvägen 1 (utkast 45)
# Menuettvägen är plan från Dansutvägen fram till Kadriljvägen (användarens iakttagelse; den topografiska kartan ger 39–40 m hela vägen).
# Förut tonades kartan ut mot sin södra kant så att korsningen vid Dansutvägen hamnade ~8 m för lågt och Menuettvägen fick en brant backe.
# Nu ligger Menuettvägen i 39,4 m. Dansutvägen är kvar som en backe ner mot centrum i öster men stiger nu ända upp till korsningen,
# och västerut planar den ut i ett svagt krön innan den möter den gamla profilen. Tomten vid Kadriljvägen 1 planas i 39,5 m.
KD_GATA, KD_MARK = 39.4, 39.5
_mn = list(ways['41685709'][0]); _mn = _mn[:_mn.index('512636404') + 1]
_at, _L = _poly_s(_mn)
for k_ in range(int(_L / 5) + 1):
    x_, z_ = _at(k_ * 5.0); hojdankare.append([round(x_, 1), round(z_, 1), KD_GATA, 12, 1.0])
def _profil(chain, prof, steg=6.0, R=12):
    at_, L_ = _poly_s(chain); s_ = 0.0
    while s_ <= min(L_, prof[-1][0]):
        T_ = None
        for (s0, t0), (s1, t1) in zip(prof, prof[1:]):
            if s0 <= s_ <= s1:
                T_ = None if (t0 is None or t1 is None) else t0 + (t1 - t0) * (s_ - s0) / (s1 - s0)
                break
        x_, z_ = at_(s_); hojdankare.append([round(x_, 1), round(z_, 1), None if T_ is None else round(T_, 2), R, 1.0]); s_ += steg
_ds = list(ways['41521418'][0]); _j = _ds.index('512636389')
_profil(_ds[_j::-1], [(0, KD_GATA), (25, 39.1), (50, 37.9), (80, 35.8), (110, 33.5), (140, 31.0), (175, 28.4), (205, 26.3), (225, None)])          # österut ner mot centrum
_profil(_ds[_j:] + list(ways['165807594'][0])[1:], [(0, KD_GATA), (30, 39.6), (70, 39.9), (110, 39.7), (150, 39.0), (200, 37.9), (250, 37.0), (300, 36.6), (340, None)])   # västerut
for _u in range(-18, 12, 4):
    for _v in range(-11, 18, 4):
        _p = KD_W(_u, _v); hojdankare.append([round(_p[0], 1), round(_p[1], 1), KD_MARK, 5, 1.0])
# ------------------------------------------------------------------ PÅSKÄGG Granbackavägen 108: parkeringen norr om entrén med stenblock och den gröna sandlådan,
# tre utomhusplatser framför förrådets gavel med ett lågt trästaket, Samuels cyklar i ställ vid gaveln, cykelställ vid gångvägen, studsmatta med nät, träd och buskar
ytor.append({"typ": "parkering", "namn": "", "poly": [GB_W(-7.5, 6.0), GB_W(15.2, 6.0), GB_W(15.2, 17.4), GB_W(-0.6, 17.4), GB_W(-0.6, 20.0), GB_W(-7.5, 20.0)], "ingaBilar": True})
ytor.append({"typ": "parkering", "namn": "", "poly": GB_P(-1.45, 5.45, 17.2, 41.0), "ingaBilar": True})   # asfalt hela vägen mellan garagelängorna
# fyra parkeringsfickor bredvid förrådet: en grå Škoda Octavia kombi i fickan närmast det allmänna cykelstället, de tre andra tomma (utkast 42)
for k_ in range(5): parkeringslinjer.append([round(c, 2) for c in GB_W(9.6, 7.4 + 2.5 * k_) + GB_W(14.4, 7.4 + 2.5 * k_)])
_gb_bil = round(math.atan2(GB_U[0], GB_U[1]), 3)
_c = GB_W(12.05, 8.62)
fasta_bilar = [{"x": _c[0], "z": _c[1], "ang": round(_gb_bil + 0.012, 3), "typ": "octavia", "lack": "#83878a", "falg": "#aeb2b5", "text": "ŠKODA", "modell": "OCTAVIA", "reg": "GNS 108"}]
GB_STENAR = [{"x": GB_W(u_, 6.45)[0], "z": GB_W(u_, 6.45)[1], "r": r_} for u_, r_ in ((-1.3, 0.58), (7.7, 0.5), (-5.6, 0.62))]
GB_SANDLADOR = [{"x": GB_W(3.4, 6.95)[0], "z": GB_W(3.4, 6.95)[1], "rot": round(-math.atan2(GB_U[1], GB_U[0]), 3)}]
# Samuels cykelställ längs det stora fönstret bredvid farstukvisten, cyklarna med framhjulet mot husväggen; det allmänna stället vid gång- och cykelvägen
GB_STALL = [{"x": GB_W(1.6, 1.2)[0], "z": GB_W(1.6, 1.2)[1], "rot": round(math.atan2(-GB_V[0], -GB_V[1]), 3), "platser": 3, "cyklar": [[0, "#c6cf3a"], [2, "#2f5fb6"]]},
            {"x": GB_W(10.0, 6.3)[0], "z": GB_W(10.0, 6.3)[1], "rot": round(math.atan2(GB_V[0], GB_V[1]), 3), "platser": 6, "cyklar": [[1, "#263325"]]}]
GB_STUDS = [{"x": GB_W(-3.4, -3.4)[0], "z": GB_W(-3.4, -3.4)[1], "r": 1.8, "nat": True}]
GB_TRAD = [{"x": GB_W(-11.2, 0.4)[0], "z": GB_W(-11.2, 0.4)[1], "h": 5.6, "r": 2.1}]
GB_BUSKAGE = [{"pts": [GB_W(u_, 0.95)], "bredd": 0.95, "hojd": 0.8, "tujor": [], **({"blommor": ["#c8243a", "#e04a5f"]} if i_ % 3 == 1 else {})}
              for i_, u_ in enumerate([5.35, 9.6, 10.9, 15.6, 20.2, 21.4, 25.9, 30.2])]
GB_BUSKAGE.append({"pts": [GB_W(-4.0, 4.2), GB_W(-8.0, 4.0), GB_W(-11.5, 1.5)], "bredd": 1.6, "hojd": 1.2, "tujor": []})
staket_gb = {"pts": [GB_W(15.0, 9.6), GB_W(15.0, 17.3)], "hojd": 0.55, "farg": "#7a5a3c", "stil": "rails", "skyltar": 0}
# grusväg från gång- och cykelvägen mellan de två längornas tomter fram till dörren på H1593, och låga häckar som ramar in båda tomterna (utkast 43)
_gv = [GB_W(-8.6, 2.7), GB_W(-6.5, -12.0), GB_W(-4.3, -18.35)]
gator.append({"id": "G_GB_GRUS", "osm": "egen_granbacka_grus", "namn": "", "typ": "path", "pts": [[round(p_[0], 2), round(p_[1], 2)] for p_ in _gv],
              "bredd": 1.4, "trottoar": 0.0, "bro": False, "tunnel": False, "yta": "gravel", "bil": False})
def _skarning(p1, p2, p3, p4):
    d1 = (p2[0] - p1[0], p2[1] - p1[1]); d2 = (p4[0] - p3[0], p4[1] - p3[1]); den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / den; return [round(p1[0] + d1[0] * t, 2), round(p1[1] + d1[1] * t, 2)]
_hack = {"bredd": 0.9, "hojd": 0.85, "tujor": []}
# 108-längans tomt: längs grusvägen, bakom huset och längs västra gaveln
GB_BUSKAGE.append({"pts": [GB_W(-7.13, 1.58), GB_W(-5.21, -11.82), GB_W(-4.3, -14.5), GB_W(GB_L + 1.5, -14.5), GB_W(GB_L + 1.5, 0.3)], **_hack})
# grannlängans tomt (H1580): längs grusvägen, bakom huset och längs östra gaveln
_a, _b = GB_W(-9.7, 1.22), GB_W(-7.79, -12.18); _bak0, _bak1 = H80_W(H80_L + 6.0, -H80_D - 3.5), H80_W(-1.5, -H80_D - 3.5)
GB_BUSKAGE.append({"pts": [_a, _b, _skarning(_a, _b, _bak0, _bak1), _bak1, H80_W(-1.5, 0.3)], **_hack})
# buskar längs grannlängans entrésida, mellan farstukvistarna som hos 108
GB_BUSKAGE.extend({"pts": [H80_W(u_, 0.95)], "bredd": 0.95, "hojd": 0.8, "tujor": [], **({"blommor": ["#c8243a", "#e04a5f"]} if i_ % 3 == 2 else {})}
                  for i_, u_ in enumerate([1.0, 8.6, 11.2, 18.9, 21.5, 29.0, 31.6]))

# ------------------------------------------------------------------ STOPP Köpcentrum (utkast 46): stenlagd gångyta längs fasaden (bredare framför entrén och
# kundvagnsgaraget); kundparkeringen börjar först där, så att inga bilar ställs mot fasaden
def _st_lokal(x, z):
    dx, dz = x - ST_O[0], z - ST_O[1]; return (dx * ST_U[0] + dz * ST_U[1], dx * -ST_U[1] + dz * ST_U[0])
ST_FRAM = [(-18.4, -2.0), (0.6, -2.0), (0.6, 3.6), (33.2, 3.6), (33.2, 7.9), (40.6, 7.9), (40.6, 3.6), (60.5, 3.6)]   # gångytans ytterkant = parkeringens framkant
ST_GANG = [(-18.4, -5.67), (0.0, -5.67), (0.0, 0.0), (35.9, 0.0), (35.9, 4.0), (42.0, 4.0), (42.0, 0.0), (60.5, 0.0)] + ST_FRAM[::-1]
ytor.append({"typ": "torg", "namn": "", "hojd": 0.16, "poly": [ST_W(u_, v_) for u_, v_ in ST_GANG]})
for y in ytor:
    if y.get("namn") != "Kundparkering Stopp Köpcentrum": continue
    _loc = [_st_lokal(*p_) for p_ in y["poly"]]
    _i0 = min(range(len(_loc)), key=lambda k_: math.hypot(_loc[k_][0] + 17.9, _loc[k_][1] + 5.6))
    _i1 = min(range(len(_loc)), key=lambda k_: math.hypot(_loc[k_][0] - 60.5, _loc[k_][1] + 5.8))
    if _i0 < _i1:
        y["poly"] = y["poly"][:_i0 + 1] + [ST_W(u_, v_) for u_, v_ in ST_FRAM[:-1]] + y["poly"][_i1:]
        print('Kundparkeringen: framkanten flyttad ut från fasaden', _i0, _i1)
# fullt på kundparkeringen som på fotot: en rad med nosen mot huset längs gångytan (luckor vid entrén och kundvagnsgaraget) och två rader
# rygg mot rygg mellan de två körgångarna; ungefär en tredjedel av platserna är upptagna (vanliga färger, några skåpbilar; utkast 47: hälften så många)
_ST_FARGER = ['#a9adb1', '#a9adb1', '#c6c8c9', '#eceae5', '#eceae5', '#eceae5', '#18191b', '#18191b', '#3b3e42', '#1f3050', '#8c1a1a', '#b3262a', '#5d6a72', '#7d93a6']
def _st_bil(u, v, a, nyckel):
    r_ = h01(nyckel)
    if r_ < 0.70: return
    t_ = h01(nyckel + "t"); typ_ = "skap" if t_ < 0.1 else ("kombi" if t_ < 0.55 else "sedan")
    a_ = a + (math.pi if h01(nyckel + "v") < 0.25 else 0.0) + (h01(nyckel + "s") - 0.5) * 0.08
    du, dv = math.cos(a_), math.sin(a_); dx, dz = du * ST_U[0] + dv * -ST_U[1], du * ST_U[1] + dv * ST_U[0]
    x_, z_ = ST_W(u + (h01(nyckel + "x") - 0.5) * 0.3, v)
    lack = _ST_FARGER[int(h01(nyckel + "f") * len(_ST_FARGER)) % len(_ST_FARGER)] if typ_ != "skap" else ("#f1f0ec" if h01(nyckel + "f") < 0.7 else "#c6c8c9")
    fasta_bilar.append({"x": x_, "z": z_, "ang": round(math.atan2(dx, dz), 3), "typ": typ_, "lack": lack, "falg": "#b9bcc0" if h01(nyckel + "g") < 0.7 else "#3a3c3f",
                        **({"stotf": "#151618"} if typ_ == "skap" or h01(nyckel + "b") < 0.25 else {})})
_n0 = len(fasta_bilar)
for k_ in range(6): _st_bil(-16.2 + k_ * 2.55, 0.35, -math.pi / 2, "stA%d" % k_)
for k_ in range(13): _st_bil(1.9 + k_ * 2.45, 5.95, -math.pi / 2, "stB%d" % k_)
for k_ in range(7): _st_bil(42.2 + k_ * 2.55, 5.95, -math.pi / 2, "stC%d" % k_)
for rad_, v_, a_ in (("D", 13.95, -math.pi / 2), ("E", 19.05, math.pi / 2)):   # nosen mot var sin körgång
    for k_ in range(35): _st_bil(-25.0 + k_ * 2.55, v_, a_, "st%s%d" % (rad_, k_))
print('Kundparkeringen: parkerade bilar', len(fasta_bilar) - _n0)
# hastighetsvisaren vid Östra Storgatan (x 522, z 198): röd arg smiley över 40 km/h, grön glad smiley annars; visar mot trafiken från centrum
FARTSKYLTAR = [{"x": 522.0, "z": 198.0, "rot": round(math.atan2(-31.4, -40.9), 4), "grans": 40}]

# ------------------------------------------------------------------ PÅSKÄGG Kadriljvägen 1: uppfarten i betongplattor fram till garaget och entrén, grusad gårdsplan med
# släpvagnen och tältgaraget, lågt brädstaket längs Menuettvägen och runt hörnet mot Kadriljvägen, häck med gula blommor på låg kantsten mot
# Kadriljvägen, en hög häck på andra sidan gatan, träd vid tillbyggnaden, stenblock och prydnadsgräs innanför staketet och en grå Peugeot
# kombi på uppfarten (efter foton, utkast 45)
def _kd_lokal(x, z):
    dx, dz = x - KD_O[0], z - KD_O[1]; return (dx * KD_U[0] + dz * KD_U[1], dx * KD_V[0] + dz * KD_V[1])
_kad = [_kd_lokal(*P(n_)) for n_ in ways['41685711'][0]]                                    # Kadriljvägen från korsningen västerut
_men = [_kd_lokal(*P(n_)) for n_ in ways['41685709'][0][:3]]                                # Menuettvägen från Dansutvägen till Kadriljvägen
def _kd_vc(u):   # Kadriljvägens mittlinje (v) vid u
    for a_, b_ in zip(_kad, _kad[1:]):
        if min(a_[0], b_[0]) - 1e-6 <= u <= max(a_[0], b_[0]) + 1e-6: return a_[1] + (b_[1] - a_[1]) * (u - a_[0]) / ((b_[0] - a_[0]) or 1e-9)
    a_, b_ = _kad[0], _kad[1]; return a_[1] + (b_[1] - a_[1]) * (u - a_[0]) / (b_[0] - a_[0])
def _kd_uc(v):   # Menuettvägens mittlinje (u) vid v
    for a_, b_ in zip(_men, _men[1:]):
        if min(a_[1], b_[1]) - 1e-6 <= v <= max(a_[1], b_[1]) + 1e-6: return a_[0] + (b_[0] - a_[0]) * (v - a_[1]) / ((b_[1] - a_[1]) or 1e-9)
    a_, b_ = _men[-2], _men[-1]; return a_[0] + (b_[0] - a_[0]) * (v - a_[1]) / (b_[1] - a_[1])
ytor.append({"typ": "torg", "namn": "", "hojd": 0.12, "poly": [KD_W(u_, v_) for u_, v_ in ((1.25, -11.75), (6.05, -11.75), (5.75, -10.4), (5.75, 2.62), (1.0, 2.62), (1.0, 1.6),
                                                                                         (0.0, 1.6), (0.0, -0.45), (-0.9, -0.45), (-0.9, -3.4), (1.25, -4.5))]})
ytor.append({"typ": "grus", "namn": "", "poly": [KD_W(u_, v_) for u_, v_ in ((-1.6, -11.75), (1.25, -11.75), (1.25, -4.5), (-0.9, -3.4), (-15.0, -3.4), (-15.0, -10.3), (-1.6, -10.3))]})
_c = KD_W(3.65, -2.7)
fasta_bilar.append({"x": _c[0], "z": _c[1], "ang": round(math.atan2(KD_V[0], KD_V[1]) + 0.015, 3), "typ": "peugeot", "lack": "#7c8085", "falg": "#b4b8bb", "text": "PEUGEOT", "reg": "KDR 001"})
# häcken med gula blommor (ölandstok) längs Kadriljvägen väster om brevlådan, på en låg kantsten mot gatan
_hk = [(u_, _kd_vc(u_) + 4.0) for u_ in (-1.9, -4.9, -7.9, -10.9, -13.9, -17.0)]
KD_BUSKAGE = [{"pts": [KD_W(*q) for q in _hk], "bredd": 1.0, "hojd": 1.0, "tujor": [], "blommor": ["#f2d34a", "#f6df6a", "#f2d34a"]},
              {"pts": [KD_W(u_, _kd_vc(u_) - 3.95) for u_ in (9.5, 5.0, 0.0, -5.0, -10.0, -15.0, -20.0)], "bredd": 1.3, "hojd": 1.7, "tujor": []},
              {"pts": [KD_W(-14.2, -1.0), KD_W(-16.2, 0.8), KD_W(-16.6, 4.2)], "bredd": 1.4, "hojd": 1.3, "tujor": []},
              {"pts": [KD_W(7.5, -8.9), KD_W(8.1, -8.6)], "bredd": 0.8, "hojd": 0.65, "tujor": []}]
_a, _b = (_hk[0][0], _hk[0][1] - 0.62), (_hk[-1][0], _hk[-1][1] - 0.62)
kbox((_a[0] + _b[0]) / 2, (_a[1] + _b[1]) / 2, KD_MARK_Y, math.hypot(_b[0] - _a[0], _b[1] - _a[1]) + 0.3, 0.2, 0.12, "#a9a7a1", math.atan2(_b[1] - _a[1], _b[0] - _a[0]))
_hv = _kd_vc(10.0) + 3.65; _hu = _kd_uc(_hv) - 3.9; _hv = _kd_vc(_hu) + 3.65
KD_STAKET = {"pts": [KD_W(6.3, _kd_vc(6.3) + 3.65), KD_W(_hu, _hv), KD_W(_kd_uc(16.5) - 3.9, 16.5)], "hojd": 0.95, "farg": "#5f574e", "skyltar": 0}
KD_STENAR = [{"x": KD_W(8.7, -9.5)[0], "z": KD_W(8.7, -9.5)[1], "r": 0.42}]
KD_TRAD = [{"x": KD_W(-10.4, -1.9)[0], "z": KD_W(-10.4, -1.9)[1], "h": 4.6, "r": 2.1}]
print('Kadriljvägen 1: staketets hörn', KD_W(_hu, _hv), 'häck', len(_hk), 'punkter')

# ------------------------------------------------------------------ Gnesta Hem (H194): asfalt från fasaden ut till Thulegatan med raka platser (nosen mot huset),
# buskar längs fasaden och ett stort buskage i hörnet precis före övergångsstället över Torggatan (efter foton, utkast 39)
_p194 = [H194_W(8.5, 1.4), H194_W(57.5, 1.4), H194_W(57.5, 14.4), H194_W(8.5, 12.4)]
ytor.append({"typ": "parkering", "namn": "", "poly": _p194, "ingaBilar": True})
for k_ in range(0, 19):
    u_ = 9.0 + k_ * 2.65; parkeringslinjer.append([round(c, 2) for c in H194_W(u_, 1.5) + H194_W(u_, 6.4)])
    if k_ < 18:
        c_ = H194_W(u_ + 1.32, 3.9); parkerade.append([c_[0], c_[1], round(math.atan2(H194_U[1], -H194_U[0]), 3), 8])   # nosen mot fasaden (riktning -v), hög vikt så att platserna oftast har bilar
_o194 = H194_W(3.8, 9.2)
H194_BUSKAGE = [{"pts": [[round(_o194[0] + 3.0 * math.cos(a_) * 0.981 - 2.0 * math.sin(a_) * 0.191, 2), round(_o194[1] + 3.0 * math.cos(a_) * 0.191 + 2.0 * math.sin(a_) * 0.981, 2)] for a_ in [k_ * 2 * math.pi / 9 for k_ in range(10)]], "bredd": 2.8, "hojd": 1.3, "tujor": []},
                {"pts": [H194_W(u_, 0.75) for u_ in (8.5, 10.8, 13.1, 15.4, 17.7)], "bredd": 1.3, "hojd": 1.1, "tujor": []}]
H194_TRAD = [{"x": _o194[0], "z": _o194[1], "h": 5.5, "r": 1.3, "smal": True}]

# ------------------------------------------------------------------ Coop-parkeringen: en låg buskrad med ett träd längs parkeringsplanens södra kant,
# där trottoaren vid Torggatan möter planen (t.ex. vid x -30, z 70); infarten i väster lämnas öppen. Pallar med jordsäckar vid lastkajen i husets sydöstra hörn (efter foto, utkast 39)
_CA, _Cd, _Cn = (-17.1, 67.5), (-0.98091, 0.19447), (0.19447, 0.98091)   # planens södra kant österifrån, _Cn mot Torggatan
_CP = lambda s_, o_: [round(_CA[0] + _Cd[0] * s_ + _Cn[0] * o_, 2), round(_CA[1] + _Cd[1] * s_ + _Cn[1] * o_, 2)]
COOP_HACK = [_CP(s_, 0.7) for s_ in [0.6 + 2.0 * k_ for k_ in range(17)]]
ytor.append({"typ": "torg", "namn": "", "poly": [_CP(0.0, 1.4), _CP(36.0, 1.4), _CP(36.0, 4.6), _CP(0.0, 4.6)]})   # trottoaren mellan buskraden och fickorna
COOP_KAJ = [[-21.6, 49.0], [-15.9, 49.1], [-16.1, 55.6], [-22.4, 55.6], [-23.6, 52.9]]
try:
    from shapely.geometry import Polygon as _Poly
    for _y in [y for y in ytor if y["typ"] == "parkering" and y.get("fyllnad") == 0.24]:
        _rest = _Poly(_y["poly"]).difference(_Poly(COOP_KAJ).buffer(0.6, join_style=2))
        _delar = [g_ for g_ in getattr(_rest, "geoms", [_rest]) if g_.area > 20]
        if _delar: _y["poly"] = [[round(x, 2), round(z, 2)] for x, z in list(max(_delar, key=lambda g_: g_.area).exterior.coords)[:-1]]
except ImportError:
    print('varning: shapely saknas – Coop-parkeringen klipps inte runt lastkajen')
ytor.append({"typ": "ljus", "namn": "", "poly": COOP_KAJ})
COOP_PALLAR = [{"x": x_, "z": z_, "rot": 0.1, "b": 1.15, "h": 0.95, "d": 1.0, "farg": "#ebe8de"} for x_, z_ in ((-19.6, 50.6), (-18.3, 50.7), (-19.5, 51.9), (-18.2, 52.0), (-17.0, 50.8))]

# sökbara platser för "Hitta" i spelet (utkast 48): OSM-noder med adress eller en namngiven verksamhet; husens namn och adresser ligger i hus
PLATSER = []; _psett = set()
for _k in sorted(nodes, key=int):
    _la, _lo, _t = nodes[_k]; _nm = _t.get('name')
    _ad = "%s %s" % (_t['addr:street'], _t['addr:housenumber']) if _t.get('addr:street') and _t.get('addr:housenumber') else None
    if not (_ad or (_nm and any(k_ in _t for k_ in ('shop', 'amenity', 'tourism', 'leisure', 'office', 'craft', 'healthcare', 'railway', 'public_transport')))): continue
    _x, _z = proj(_la, _lo)
    if not (BOUNDS[0] <= _x <= BOUNDS[1] and BOUNDS[2] <= _z <= BOUNDS[3]): continue
    if _t.get('railway') or _t.get('public_transport'): _nm = "Gnesta station"
    _nyck = (_nm or "", _ad or "")
    if _nyck in _psett: continue
    _psett.add(_nyck); _r = {"namn": _nm or "", "x": round(_x, 1), "z": round(_z, 1)}
    if _ad: _r["adress"] = _ad
    PLATSER.append(_r)
print("sökbara platser", len(PLATSER))

# --- Mosebackes anslutning till Östra Storgatan vid (386, 47) (utkast 61): Mosebacke började 2–3 m över Storgatan redan i korsningen, så
# marken fick ett hack där gräset stack upp genom asfalten. Motorn låter nu Mosebacke börja i Storgatans höjd (terrang.anslut), och
# höjdankare längre upp ger backen en jämnare lutning i stället för en tvär kant de första metrarna.
ANSLUT = [[384.4, 43.8, 10.0]]
def _langs61(pts, steg):
    ut = []; s_ = 0.0
    for a, b in zip(pts, pts[1:]):
        L_ = math.hypot(b[0] - a[0], b[1] - a[1]); n_ = max(1, int(round(L_ / steg)))
        for k_ in range(n_): ut.append((a[0] + (b[0] - a[0]) * k_ / n_, a[1] + (b[1] - a[1]) * k_ / n_, s_ + L_ * k_ / n_))
        s_ += L_
    ut.append((pts[-1][0], pts[-1][1], s_)); return ut
# Storgatans egna ankare (R = 15) väger tungt här, så Mosebackes ankare ligger tätt och i tre rader tvärs gatan för att få övertaget.
# profilen: plant i Storgatans höjd de första sex metrarna, sedan ökar lutningen långsamt (2,5 procentenheter per meter) till 42 %.
# En tvärare knäck får terrängnätet (4 m rutor) att sticka upp genom asfalten, som ligger 12 cm över marken.
_S61 = [-1, 6, 8, 10, 12, 14, 16, 18, 20, 22.8, 34, 37.7]; _T61 = [19.33, 19.33, 19.38, 19.53, 19.78, 20.13, 20.58, 21.13, 21.78, 22.86, 27.56, 29.11]
_m61 = _langs61([(384.4, 43.8), (382.4, 47.7), (380.1, 52.3), (375.9, 60.0), (369.3, 74.2), (366.9, 77.0)], 1.1)
for k_, (x_, z_, s_) in enumerate(_m61):
    if s_ < 5.5: continue
    q_ = _m61[min(k_ + 1, len(_m61) - 1)]; p_ = _m61[max(k_ - 1, 0)]; L_ = math.hypot(q_[0] - p_[0], q_[1] - p_[1]) or 1.0; nx_, nz_ = -(q_[1] - p_[1]) / L_, (q_[0] - p_[0]) / L_
    T_ = round(float(np.interp(s_, _S61, _T61)), 2)
    for o_ in (-2.5, 0.0, 2.5): hojdankare.append([round(x_ + nx_ * o_, 1), round(z_ + nz_ * o_, 1), T_, 2.6 if s_ < 8 else 4.5, 1.0])
# själva korsningen: ett tätt nät av små ankare som gör marken plan i Storgatans höjd de första metrarna, så att terrängnätet inte
# sticker upp genom asfalten (u längs Mosebacke från Storgatans mitt, v tvärs)
_u61 = (-0.456, 0.890)
for i_ in range(-1, 13):
    for j_ in range(-15, 16):
        u_, v_ = i_ * 0.8 + 0.4, j_ * 0.8
        hojdankare.append([round(384.4 + _u61[0] * u_ - _u61[1] * v_, 2), round(43.8 + _u61[1] * u_ + _u61[0] * v_, 2),
                           round(float(np.interp(u_, _S61, _T61)) + 0.03 * v_ * float(np.interp(u_, [6, 11], [1, 0])), 2), 1.4, 1.0])   # Storgatan lutar svagt österut; följ den närmast gatan
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
        "hojdankare": hojdankare, "anslut": ANSLUT,
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
                      {"x": -476.0, "z": -91.5, "h": 12.5, "r": 4.8}, {"x": -467.5, "z": -90.0, "h": 9.0, "r": 3.4},
                      # stora lövträd i H058:s trädgård (efter foto)
                      {"x": -393.0, "z": -54.5, "h": 14.0, "r": 6.0},
                      # fyra höga, smala träd på torget mellan Apoteket och biblioteket (efter foto)
                      {"x": -91.0, "z": 68.0, "h": 16.0, "r": 3.2, "smal": True}, {"x": -86.5, "z": 58.0, "h": 15.0, "r": 3.0, "smal": True},
                      {"x": -71.0, "z": 59.0, "h": 15.5, "r": 3.1, "smal": True}, {"x": -66.5, "z": 66.5, "h": 16.5, "r": 3.2, "smal": True},
                      # stora träd vid H471 (efter foto)
                      {"x": 80.5, "z": 256.5, "h": 15.0, "r": 5.5}, {"x": 47.0, "z": 276.0, "h": 12.0, "r": 4.5}] + sma_trad,
        # lummig grönska (buskar och en tuja) mellan H058 och brädstaketet mot trottoaren (efter foto)
        "buskage": H068_BUSKAGE + RIVET_BUSKAGE + STN_BUSKAGE + H194_BUSKAGE + GB_BUSKAGE + [{"pts": COOP_HACK, "bredd": 1.2, "hojd": 0.85, "tujor": []}] + [{"pts": [[-388.5, -54.4], [-372.0, -51.3], [-361.8, -49.3], [-362.8, -43.0]], "bredd": 2.8, "hojd": 1.7, "tujor": [[-368.6, -50.2]]},
                    # lummig grönska runt hörntomten vid Ringvägens början, med lupiner och vildrosor (efter foton)
                    {"pts": [[-463.0, -99.6], [-449.0, -89.4], [-438.5, -81.6], [-436.3, -76.4], [-439.8, -71.6]], "bredd": 2.4, "hojd": 2.0, "tujor": [], "blommor": ["#e8d23a", "#d9579a", "#f4f2ec", "#e8d23a"]},
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
        "reklamskyltar": [{"x": H010_W(24.4, -1.1)[0], "z": H010_W(24.4, -1.1)[1], "rot": round(math.atan2(0.9836, 0.1808), 3), "typ": "glass"}, {"x": h189(-H189_R[2] / 2 + 55.4, H189_R[3] / 2 + 1.1)[0], "z": h189(-H189_R[2] / 2 + 55.4, H189_R[3] / 2 + 1.1)[1], "rot": round(math.atan2(-0.20728, -0.97828), 3), "typ": "glass"}],
        # rund anslagstavla (pelare med litet tak) på gågatan framför Apoteket (efter foto)
        "anslagspelare": [{"x": -95.5, "z": 73.8}],
        "gatupratare": [{"x": _gp[0], "z": _gp[1], "rot": round(math.atan2(H068_U[0], H068_U[1]), 3), "farg": "#f2f2ee"}, {"x": -426.0, "z": -68.4, "rot": 0.45, "farg": "#c4202a"}, {"x": -416.2, "z": -65.2, "rot": 0.45, "farg": "#e8e4dc"}, {"x": -7.6, "z": 24.6, "rot": 2.27, "farg": "#f2f2ee"}],
        "staket": [{"pts": [[-463.5, -41.5], [-465.5, -47.5], [-472.0, -50.5], [-484.0, -50.8]], "hojd": 1.8, "farg": "#4a3a30", "skyltar": 5},
                   {"pts": [[-390.3, -56.3], [-359.3, -50.1], [-360.9, -42.0]], "hojd": 1.15, "farg": "#8f8b83", "skyltar": 0},
                   {"pts": [H059_W(u_, -8.3) for u_ in (-23.5, -8.0, 8.0, 23.5)], "hojd": 1.1, "farg": "#9a9a94", "skyltar": 0},
                   # grå gärdsgård med grind mot Ringvägen och en bit längs Västra Storgatan (efter foton)
                   {"pts": [[-462.6, -64.8], [-468.4, -63.4]], "hojd": 1.2, "farg": "#8f8b82", "stil": "gardsgard", "grind": True},
                   {"pts": [[-441.0, -86.2], [-452.0, -94.2]], "hojd": 1.0, "farg": "#8f8b82", "stil": "gardsgard"},
                   # rött stängsel kring gräsmattan vid H226 (efter foto)
                   {"pts": [[-241.6, 78.6], [-240.9, 86.0], [-240.4, 92.8], [-248.0, 92.4], [-262.0, 90.8]], "hojd": 0.95, "farg": "#8a3a2a", "stil": "rails"}],
        "beachflaggor": H068_FLAGGOR,
        "atervinning": ATERVINNING, "containrar": CONTAINRAR + COOP_PALLAR, "terrasser": TERRASSER,
        "sandlador": GB_SANDLADOR, "cykelstall": GB_STALL, "studsmattor": GB_STUDS,
        "krukvaxter": [{"x": H008_W(u_, -0.7)[0], "z": H008_W(u_, -0.7)[1]} for u_ in (36.8, 38.0, 39.4, 40.6, 42.2, 43.4, 45.0, 46.4, 47.8, 48.9)],
        "picknickbord": [{"x": -253.0, "z": 90.6, "rot": -0.18}, {"x": -258.5, "z": 89.7, "rot": -0.18}],
        "brevlador": [{"x": -457.0, "z": -63.95, "rot": -2.92, "farg": "#2f7a4a"}],
        "parkeradeBilar": parkerade + parkerade_auk, "fastaBilar": fasta_bilar,
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
        "dorrar": [{"x": H059_W(u_, -5.64)[0], "z": H059_W(u_, -5.64)[1], "rot": round(math.atan2(_n059[0], _n059[1]), 4), "w": 1.2, "h": 2.1} for u_ in (-12.0, 0.0, 12.0)] + [{"x": -325.66, "z": -23.77, "rot": 2.944, "w": 1.9, "h": 2.4}, {"x": -9.9, "z": 28.45, "rot": 2.27, "w": 3.4, "h": 2.4}, {"x": 241.85, "z": 448.55, "rot": -3.0156, "w": 2.6, "h": 2.5},
                   {"x": -249.6, "z": 88.85, "rot": -0.18, "w": 1.8, "h": 2.3}],
        "papperskorgar": [{"x": -333.6, "z": -44.0}],
        "rabatter": [{"x": -345.0, "z": -36.5, "r": 2.6, "farg": "#d4384a"}],
        "uteplatser": [{"x": -419.3, "z": -99.5, "b": 9.0, "d": 6.5, "rot": 0.6634, "parasoll": "#d0262f"}],
        "skorstenar": [{"x": -453.0, "z": -147.4, "h": 24.0, "r": 1.05}],
        "fartskyltar": FARTSKYLTAR,
        "overgangar": [{"osm": "32552317", "nara": [5.9, 27.5]},
                       # övergångsstället från stationen till parken (efter foto): trafikljus åt båda hållen, refug med håll-höger-skylt, P-skylt vid parken
                       {"osm": "504799985", "nara": [16.0, 19.5], "trafikljus": True, "refug": True, "skyltar": [{"typ": "P", "sida": 1, "ds": 3.5}]},
                       # övergångsstället över Torggatan vid Gnesta Hems hörn mot Thulegatan (efter foto)
                       {"osm": "32552347", "nara": [-395.3, 78.9]},
                       # övergångsstället över Skolgatan vid H471 (efter foto)
                       {"osm": "256601471", "nara": [53.0, 252.5]}],
    },
    "hus": hus,
    "platser": PLATSER,
    "start": START,
}
# påskägget vid Kadriljvägen 1: häckar, buskar, staket, sten och träd (kontrolleras mot körbanorna som allt annat)
KARTA["detaljer"]["buskage"] += KD_BUSKAGE; KARTA["detaljer"]["staket"].append(KD_STAKET)
# Platåvägens början (utkast 49, efter foton): häck längs Nygatan och Platåvägen runt den grå villan och lekstugan, vitt staket söder om
# lekstugan och 30-skylten (gul, med reflexband på stolpen) vid vägkanten. Längre upp mot H823 och H867 står en hög häck på en låg stödmur.
_u_pl = lambda v_: 23.3 + 0.18 * (v_ - 1.0)                                # häckens linje längs Platåvägen i den grå villans system
PLATA_BUSKAGE = [{"pts": [P36_W(u_, -4.4) for u_ in (-4.0, 3.0, 10.0, 17.0)] + [P36_W(_u_pl(v_), v_) for v_ in (-4.4, 0.0, 4.0, 8.0, 12.0, 15.0)],
                  "bredd": 0.9, "hojd": 1.0, "tujor": []}]
KARTA["detaljer"]["staket"].append({"pts": [P36_W(21.1, 9.9), P36_W(21.1 + 0.18 * 10.1, 20.0)], "hojd": 0.95, "farg": "#f4f4f0", "skyltar": 0})
_s30 = P36_W(24.3, 1.1); _f30 = (-(0.18 * P36_U[0] + 0.98 * -P36_U[1]), -(0.18 * P36_U[1] + 0.98 * P36_U[0]))
KARTA["detaljer"]["vagskyltar"].append({"x": _s30[0], "z": _s30[1], "rot": round(math.atan2(_f30[0], _f30[1]), 3), "typ": "hastighet", "grans": 30, "bak": 2.6})
_g_pl = next(g_ for g_ in gator if g_["namn"] == "Platåvägen" and any(abs(p_[0] + 852.7) < 0.3 and abs(p_[1] - 240.6) < 0.3 for p_ in g_["pts"]))
def _vast_om(pts, z0, z1, lat, steg=3.0):
    """punkter längs vägen mellan z0 och z1, förskjutna lat meter åt höger (västerut när man kör söderut)"""
    ut = []
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(L / steg)); nx, nz = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        for k in range(n):
            x_, z_ = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
            if z0 <= z_ <= z1: ut.append([round(x_ + nx * lat, 2), round(z_ + nz * lat, 2)])
    return ut
PLATA_BUSKAGE.append({"pts": _vast_om(_g_pl["pts"], 215.0, 262.0, _g_pl["bredd"] / 2 + 1.55), "bredd": 1.2, "hojd": 1.75, "tujor": []})
KARTA["detaljer"]["stodmurar"].append({"gata": _g_pl["id"], "fran": [-842.2, 215.0], "till": [-860.5, 262.0], "sida": [-875.0, 240.0], "hojd": 0.7})
KARTA["detaljer"]["buskage"] += PLATA_BUSKAGE
# Circle K (utkast 50): prisskylten på gräsytan vid infarten, reklamskyltar mot rondellen och asfalterad plan innanför slingan
_ck_slinga = [[947.9, 907.2], [952.7, 932.0], [963.9, 946.5], [979.2, 953.2], [989.9, 942.5], [993.9, 926.5], [985.9, 907.2], [972.6, 899.3]]
_ckc = (sum(p_[0] for p_ in _ck_slinga) / 8, sum(p_[1] for p_ in _ck_slinga) / 8)
_ck_yta = [[round(p_[0] + (_ckc[0] - p_[0]) * 2.4 / math.hypot(_ckc[0] - p_[0], _ckc[1] - p_[1]), 2), round(p_[1] + (_ckc[1] - p_[1]) * 2.4 / math.hypot(_ckc[0] - p_[0], _ckc[1] - p_[1]), 2)] for p_ in _ck_slinga]
KARTA["ytor"].append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": _ck_yta})
# rondellkonst (utkast 52): en egen design – jätteplockepinn, ett tjugotal stora pinnar i klassiska plockepinnfärger som ligger och lutar
# huller om buller på rondellön, som om någon just släppt dem (ingen kopia av den riktiga skulpturen i rondellen)
import random as _random_pp
_rng_pp = _random_pp.Random(52); _pp = []
_pp_farg = ["#c8322b", "#2f5fb5", "#2f8a46", "#e8c22e", "#222222", "#c9a26b"]
for k_ in range(22):
    L_ = _rng_pp.uniform(5.0, 7.0); rx_ = _rng_pp.uniform(1.15, 1.48) if k_ % 4 else _rng_pp.uniform(0.75, 1.0)
    bas_ = 0.08 + (k_ / 22) * 0.9 * _rng_pp.random()                          # pinnar längre upp i högen vilar på dem under
    r_, a_ = 2.2 * math.sqrt(_rng_pp.random()), _rng_pp.uniform(0, 2 * math.pi)
    yc_ = bas_ + L_ / 2 * math.cos(rx_)
    _pp.append({"form": "cyl", "x": round(r_ * math.cos(a_), 2), "z": round(r_ * math.sin(a_), 2), "y": round(yc_ - L_ / 2, 3), "b": round(_rng_pp.uniform(0.13, 0.18), 3),
                "h": round(L_, 2), "rot": round(_rng_pp.uniform(0, 2 * math.pi), 3), "rx": round(rx_, 3), "farg": _pp_farg[k_ % len(_pp_farg)]})
KARTA["detaljer"]["skulpturer"] = [{"namn": "Jätteplockepinn", "x": RONDELL_C[0], "z": RONDELL_C[1], "lyft": 0.19, "delar": _pp}]
# Backen mellan Ringvägen och Torggatan (utkast 53): låg stenmur längs gångvägen nedanför villan på krönet, flaggstång väster om villan,
# en bänk på gräsmattan vid gångvägen längs Torggatan, och marken under villan planas lite så att den inte står på en hög sockel
_g355 = next(g_ for g_ in gator if any(abs(p_[0] + 640.0) < 1.5 and abs(p_[1] - 7.0) < 1.5 for p_ in g_["pts"]) and not g_["bil"])
KARTA["detaljer"]["stodmurar"].append({"gata": _g355["id"], "fran": [-662.0, 17.0], "till": [-616.0, -14.0], "sida": [-640.0, -5.0], "hojd": 0.7})
_fl = P337_W(16.0, 2.0); KARTA["detaljer"]["flaggstanger"].append({"x": round(_fl[0], 2), "z": round(_fl[1], 2), "h": 9.0, "flagga": None})
KARTA["detaljer"]["bankar"].append({"x": -606.0, "z": 56.8, "rot": round(math.atan2(0.21, 0.98), 3)})
hojdankare.append([-645.4, -8.2, 23.6, 7, 1.0]); hojdankare.append([-642.3, -3.1, 23.4, 5, 1.0])
KARTA["detaljer"]["tradfritt"] = [[[-668.0, 62.0], [-640.0, 66.5], [-612.0, 61.0], [-604.0, 50.0], [-605.0, 20.0], [-611.0, -12.0], [-626.0, 1.0], [-640.0, 10.0],
                                     [-655.0, 17.0], [-672.0, 24.0], [-676.0, 40.0], [-674.0, 58.0]]]   # den öppna gräsbacken nedanför villan
# H277 är ett sutteränghus: backen bakom (mot villan på krönet) höjs ungefär en våning så att baksidan bara visar tre våningar
for u_ in range(2, 42, 5):
    for v_, T_ in ((19.0, 21.3), (24.0, 21.6)):
        q_ = P277_W(u_, v_); hojdankare.append([round(q_[0], 1), round(q_[1], 1), T_, 5, 1.0])
KARTA["detaljer"]["prisskyltar"] = [{"x": 948.5, "z": 937.0, "rot": round(math.atan2(0.355, 0.935), 3), "text": "CIRCLE K", "bredd": 1.7, "hojd": 7.2,
                                     "priser": [["Bensin 95", "18.79"], ["Bensin 98", "19.89"], ["Diesel", "19.29"], ["HVO100", "24.49"]]}]
_rot_ck = round(math.atan2(P46_U[0], P46_U[1]), 3)
for (u_, v_), typ_ in (((26.0, 22.0), "tavla"), ((26.0, 16.0), "tavla"), ((27.0, 11.0), "glass")):
    q_ = P46_W(u_, v_); KARTA["detaljer"]["reklamskyltar"].append({"x": round(q_[0], 2), "z": round(q_[1], 2), "rot": _rot_ck, "typ": typ_, "text": "KAFFE + BULLE" if v_ > 20 else "VARM KORV"})
# --- Thuleparken (utkast 57, foto från övergångsstället på Thulegatan): bollplan i konstgräs med låg brun sarg och högt nätstängsel,
# betongblock med gul skylt "Thuleparken", bajamaja och papperskorg vid entrén, svarta pollare med gula band vid övergångsstället.
# Runt planen: mycket öppen gräsmatta mot H326, bänkar, gungor, lektorn med rutschkana, fjädergungor, sandlåda och en fågelbogunga.
# De stora sandfärgade lekplatsytorna från OSM tas bort; bara små sandytor under lekredskapen blir kvar.
_tp_c = (-358.0, 185.0)
def _cent(pl): return (sum(q[0] for q in pl) / len(pl), sum(q[1] for q in pl) / len(pl))
_plan_tp = next(y_ for y_ in KARTA["ytor"] if y_["typ"] == "plan" and math.hypot(_cent(y_["poly"])[0] + 384.6, _cent(y_["poly"])[1] - 176.9) < 3)
KARTA["ytor"] = [y_ for y_ in KARTA["ytor"] if not (y_ is _plan_tp or (y_["typ"] == "lekplats" and math.hypot(_cent(y_["poly"])[0] - _tp_c[0], _cent(y_["poly"])[1] - _tp_c[1]) < 45))]
_pq = _plan_tp["poly"]; _pc = _cent(_pq)
_lang = max(((_pq[i], _pq[(i + 1) % 4]) for i in range(4)), key=lambda e: math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]))
_ld = (_lang[1][0] - _lang[0][0], _lang[1][1] - _lang[0][1]); _L_tp = math.hypot(*_ld); _ld = (_ld[0] / _L_tp, _ld[1] / _L_tp)
_B_tp = min(math.hypot(_pq[(i + 1) % 4][0] - _pq[i][0], _pq[(i + 1) % 4][1] - _pq[i][1]) for i in range(4))
_rot_tp = math.atan2(_ld[0], _ld[1])
KARTA["detaljer"]["bollplaner"] = [{"x": round(_pc[0], 2), "z": round(_pc[1], 2), "rot": round(_rot_tp, 4), "L": round(_L_tp - 0.3, 2), "B": round(_B_tp - 0.3, 2), "staket": 4.0, "sarg": 1.0}]
class _Grupp:
    """lekredskap som skulptur: lokal x längs vinkeln r (som M4:s yaw), lokal z vinkelrätt; y = underkant över marken"""
    def __init__(self, x, z, r): self.x, self.z, self.r, self.c, self.s, self.delar = x, z, r, math.cos(r), math.sin(r), []
    def box(self, lx, y, lz, b, h, d, farg, a=0.0, rx=0.0, form=None):
        dd = {"x": round(lx * self.c + lz * self.s, 3), "y": round(y, 3), "z": round(-lx * self.s + lz * self.c, 3), "b": b, "h": h, "d": d, "rot": round(self.r + a, 4), "farg": farg}
        if rx: dd["rx"] = round(rx, 4)
        if form: dd["form"] = form
        self.delar.append(dd)
    def stang(self, p0, p1, diam, farg, form="cyl"):   # cylinder (eller fyrkantsrör) mellan två lokala punkter
        dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]; L = math.sqrt(dx * dx + dy * dy + dz * dz); hl = math.hypot(dx, dz)
        a = math.atan2(dx, dz) if hl > 1e-6 else 0.0; rx = math.atan2(hl, dy)
        self.box((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - L / 2, (p0[2] + p1[2]) / 2, diam, round(L, 3), diam, farg, a, rx, form if form != "box" else None)
    def planka(self, p0, p1, b, t, farg):   # platt skiva mellan två lokala punkter (bredd b, tjocklek t)
        dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]; L = math.sqrt(dx * dx + dy * dy + dz * dz); hl = math.hypot(dx, dz)
        self.box((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - t / 2, (p0[2] + p1[2]) / 2, b, t, round(L, 3), farg, math.atan2(dx, dz), math.atan2(-dy, hl))
    def ut(self, namn, tradR=5.0): return {"namn": namn, "x": round(self.x, 2), "z": round(self.z, 2), "tradR": tradR, "delar": self.delar}
    def W(self, lx, lz): return [round(self.x + lx * self.c + lz * self.s, 2), round(self.z - lx * self.s + lz * self.c, 2)]
GRON, GUL, ROD, BLA, TRA, SVART = "#3f7a46", "#e8c22e", "#c8402e", "#2f5fb5", "#8a6a48", "#222222"
_r_lang = math.atan2(-_ld[1], _ld[0])          # grupper med lokal x längs planens långsida
_tp_sk, _tp_sand = [], []
def _gungor(x, z, sitsar, namn):
    g = _Grupp(x, z, _r_lang); B2 = 1.9
    g.box(0, 2.34, 0, 2 * B2 + 0.2, 0.12, 0.12, GRON)
    for sx in (-B2, B2):
        for sz in (-0.95, 0.95): g.stang((sx, 0.0, sz), (sx, 2.4, 0.0), 0.1, GRON)
        g.box(sx, 0.0, 0, 0.1, 0.06, 1.9, GRON)
    for lx in sitsar:
        for d_ in (-0.21, 0.21): g.stang((lx + d_, 2.34, 0), (lx + d_, 0.47, 0), 0.03, "#9a9da0")
        g.box(lx, 0.43, 0, 0.46, 0.05, 0.2, SVART)
    _tp_sk.append(g.ut(namn)); _tp_sand.append([g.W(-B2 - 0.6, -3.0), g.W(B2 + 0.6, -3.0), g.W(B2 + 0.6, 3.0), g.W(-B2 - 0.6, 3.0)])
_gungor(-362.5, 178.0, (-0.9, 0.9), "Gungor")
# lektorn: fyra stolpar, plattform på 1,2 m, blå räckesskivor, rött sadeltak, gul rutschkana åt +x och stege åt -z
g = _Grupp(-360.5, 191.0, _r_lang)
for sx in (-0.7, 0.7):
    for sz in (-0.7, 0.7): g.box(sx, 0.0, sz, 0.11, 2.95, 0.11, TRA)
g.box(0, 1.16, 0, 1.55, 0.08, 1.55, TRA)
g.box(-0.72, 1.3, 0, 0.04, 0.75, 1.3, BLA); g.box(0, 1.3, 0.72, 1.3, 0.75, 0.04, BLA)
g.box(0.72, 1.3, -0.45, 0.04, 0.75, 0.5, BLA); g.box(0, 1.3, -0.72, 0.4, 0.75, 0.04, BLA, ); g.box(-0.5, 1.3, -0.72, 0.35, 0.75, 0.04, BLA); g.box(0.5, 1.3, -0.72, 0.35, 0.75, 0.04, BLA)
g.box(0, 2.9, 0, 1.75, 0.75, 1.8, ROD, form="gavel")
g.planka((0.75, 1.24, 0.25), (3.45, 0.3, 0.25), 0.5, 0.05, GUL)
for d_ in (0.0, 0.5): g.planka((0.75, 1.42, d_), (3.45, 0.48, d_), 0.04, 0.2, GUL)
g.box(3.7, 0.25, 0.25, 0.5, 0.05, 0.5, GUL, form=None)
for sx in (-0.25, 0.25): g.stang((sx, 0.0, -1.55), (sx, 1.25, -0.78), 0.06, TRA, "box")
for k_ in range(1, 5): t_ = k_ / 5; g.box(0, 1.25 * t_ - 0.02, -1.55 + 0.77 * t_, 0.5, 0.04, 0.05, TRA)
_tp_sk.append(g.ut("Lektorn")); _tp_sand.append([g.W(-1.8, -2.4), g.W(4.6, -2.4), g.W(4.6, 2.0), g.W(-1.8, 2.0)])
# fjädergungor och en sandlåda med träram bredvid tornet
for (lx_, lz_), farg_ in (((-3.2, 2.6), ROD), ((-1.6, 3.4), GUL)):
    q_ = g.W(lx_, lz_); f_ = _Grupp(q_[0], q_[1], _r_lang + 0.4)
    f_.box(0, 0.0, 0, 0.14, 0.45, 0.14, "#9a9da0", form="cyl"); f_.box(0, 0.43, 0, 0.7, 0.3, 0.26, farg_); f_.box(0.32, 0.6, 0, 0.26, 0.32, 0.24, farg_)
    f_.box(0.18, 0.85, 0, 0.05, 0.05, 0.4, SVART); _tp_sk.append(f_.ut("Fjädergunga", 2.0))
q_ = g.W(-4.6, -1.0); s_ = _Grupp(q_[0], q_[1], _r_lang)
for sz in (-1.4, 1.4): s_.box(0, -0.05, sz, 3.0, 0.3, 0.12, TRA); s_.box(sz, -0.05, 0, 0.12, 0.3, 2.68, TRA)
_tp_sk.append(s_.ut("Sandlåda", 2.5)); _tp_sand.append([s_.W(-1.45, -1.45), s_.W(1.45, -1.45), s_.W(1.45, 1.45), s_.W(-1.45, 1.45)])
# fågelbogunga på andra sidan gångvägen, där OSM har en mindre lekplats
g = _Grupp(-333.5, 186.0, _r_lang + 0.3); B2 = 1.6
g.box(0, 2.34, 0, 2 * B2 + 0.2, 0.12, 0.12, GRON)
for sx in (-B2, B2):
    for sz in (-0.95, 0.95): g.stang((sx, 0.0, sz), (sx, 2.4, 0.0), 0.1, GRON)
for sx, sz in ((-0.5, -0.4), (-0.5, 0.4), (0.5, -0.4), (0.5, 0.4)): g.stang((sx * 0.6, 2.34, 0), (sx, 0.62, sz), 0.03, "#9a9da0")
g.box(0, 0.52, 0, 1.1, 0.1, 1.1, "#e07a2c", form="cyl"); g.box(0, 0.55, 0, 0.9, 0.08, 0.9, "#3a3a3a", form="cyl")
_tp_sk.append(g.ut("Fågelbogunga")); _tp_sand.append([g.W(-2.4, -2.8), g.W(2.4, -2.8), g.W(2.4, 2.8), g.W(-2.4, 2.8)])
# entrén vid övergångsstället: betongblock med gul skylt, bajamaja, papperskorg och pollare
_r_sk = math.atan2(-0.8, -0.6)
KARTA["detaljer"]["stenskyltar"] = [{"x": -400.5, "z": 163.7, "rot": round(_r_sk, 4), "text": "Thuleparken", "b": 2.3, "h": 0.75, "d": 0.55}]
g = _Grupp(-392.4, 151.2, math.atan2(-0.62, 0.78))
g.box(0, 0.0, 0, 1.15, 2.25, 1.15, "#8d9297"); g.box(0, 2.25, 0, 1.25, 0.1, 1.25, "#b4b8bb"); g.box(0, 0.05, 0.58, 0.78, 1.95, 0.03, "#767b80")
g.box(0.42, 2.0, -0.3, 0.1, 0.55, 0.1, "#55595d", form="cyl"); g.box(0, 1.65, 0.6, 0.24, 0.07, 0.02, "#2fa04a")
_tp_sk.append(g.ut("Bajamaja", 1.5))
for q_ in ((-399.4, 157.6), (-399.6, 158.7), (-399.8, 159.8)):
    g = _Grupp(q_[0], q_[1], 0.0); g.box(0, 0.0, 0, 0.15, 0.95, 0.15, "#1c1c1c", form="cyl")
    for y_ in (0.62, 0.78): g.box(0, y_, 0, 0.16, 0.07, 0.16, GUL, form="cyl")
    g.box(0, 0.9, 0, 0.15, 0.15, 0.15, "#1c1c1c", form="klot"); _tp_sk.append(g.ut("Pollare", 0.8))
KARTA["detaljer"]["skulpturer"] += _tp_sk
for pl_ in _tp_sand: KARTA["ytor"].append({"typ": "lekplats", "namn": "", "poly": pl_})
KARTA["detaljer"]["overgangar"].append({"osm": "41556702", "nara": [-403.2, 158.0]})
KARTA["detaljer"]["vagskyltar"].append({"x": -399.1, "z": 154.7, "rot": round(-math.pi / 2, 4), "typ": "P"})   # P-skylt mot Thulegatan vid entrén
_ben = lambda x, z, dx, dz: {"x": x, "z": z, "rot": round(math.atan2(-dx, -dz), 3), "farg": "#4f5a50"}
KARTA["detaljer"]["bankar"] += [_ben(-383.0, 152.4, 0, 1), _ben(-373.0, 153.4, 0, 1), _ben(-351.3, 184.0, -1, 0), _ben(-351.6, 191.5, -1, 0),
                                _ben(-367.5, 172.5, 1, 0.1), _ben(-367.2, 186.0, 1, 0.1), _ben(-338.0, 181.0, -0.6, 0.8)]
KARTA["detaljer"]["picknickbord"] += [{"x": -357.0, "z": 172.0, "rot": round(_r_lang, 3)}, {"x": -330.5, "z": 192.0, "rot": round(_r_lang + 0.3, 3)}]
KARTA["detaljer"]["papperskorgar"] += [{"x": -393.7, "z": 152.9}, {"x": -351.6, "z": 187.8}, {"x": -366.8, "z": 169.6}]
KARTA["detaljer"]["storaTrad"] += [{"x": -389.0, "z": 150.0, "h": 15.0, "r": 6.5}, {"x": -364.0, "z": 157.0, "h": 13.0, "r": 6.0}, {"x": -352.5, "z": 160.5, "h": 14.0, "r": 6.5},
                                   {"x": -398.6, "z": 140.0, "h": 12.0, "r": 5.0}, {"x": -380.0, "z": 203.5, "h": 13.0, "r": 6.0}]
KARTA["detaljer"]["tradfritt"].append([[-394.0, 129.0], [-348.0, 129.0], [-347.0, 166.0], [-370.0, 162.0], [-372.0, 157.0], [-394.0, 155.0]])   # den stora gräsmattan mot H326
KARTA["detaljer"]["tradfritt"].append([[-372.0, 158.0], [-348.5, 167.0], [-351.0, 200.0], [-376.0, 198.0]])                                   # lekytan öster om planen
# kontroll: avstånd från det som ställts ut till närmaste gång- eller bilväg (kant inklusive trottoar)
def _vagkant(x, z):
    bast = (1e9, None)
    for g_ in gator:
        if g_.get("tunnel"): continue
        k_ = g_["bredd"] / 2 + (g_.get("trottoar") or 0.0)
        for a, b in zip(g_["pts"], g_["pts"][1:]):
            dx, dz = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dz * dz or 1e-9; t = max(0, min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / L2))
            d_ = math.hypot(x - a[0] - dx * t, z - a[1] - dz * t) - k_
            if d_ < bast[0]: bast = (d_, g_["id"])
    return bast
_tp_koll = [(o_["namn"], o_["x"], o_["z"]) for o_ in _tp_sk] + [("skylt", -400.5, 163.7)] + [("bänk", b_["x"], b_["z"]) for b_ in KARTA["detaljer"]["bankar"][-7:]] \
           + [("bord", -357.0, 172.0), ("bord", -330.5, 192.0), ("korg", -393.7, 152.9), ("korg", -351.6, 187.8), ("korg", -366.8, 169.6)]
print("Thuleparken: plan %.1f x %.1f m, rot %.3f;" % (_L_tp, _B_tp, _rot_tp), "närmast väg:", ", ".join("%s %.1f (%s)" % (n_, *_vagkant(x_, z_)) for n_, x_, z_ in _tp_koll))
# --- Gräsmattan mellan längan vid Kullagatan och gångvägen längs Torggatan (utkast 59, foto från Torggatan 12): tre träd och en grön bänk
KARTA["detaljer"]["tradfritt"].append([[-228.5, 85.0], [-138.5, 93.6], [-139.5, 99.0], [-229.5, 96.5]])
for x_, z_, h_, r_ in ((-214.0, 93.5, 10.5, 4.6), (-191.0, 96.2, 8.0, 3.2), (-162.5, 97.4, 8.5, 3.4)): KARTA["detaljer"]["storaTrad"].append({"x": x_, "z": z_, "h": h_, "r": r_})
KARTA["detaljer"]["bankar"].append({"x": -179.0, "z": 98.7, "rot": round(math.pi, 3), "farg": "#3f6b4a"})
# --- Parkeringen mellan Torggatan och H283 (utkast 60, foto från Torggatan 5): en rad tvärställda platser direkt mot gatan, sedan gräs med
# tre träd fram till gångvägen, och en häck längs husets sockel. u österut längs Torggatan från knäcken vid (-139.3, 106.2), v söderut.
P283_W, P283_R, P283_P = lokal((-139.3, 106.2), (0.9784, -0.2067))
KARTA["ytor"].append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": P283_P(-9.0, 30.0, 2.7, 8.0)})
KARTA["detaljer"]["utanTrottoar"].append(P283_P(-9.6, 30.6, 2.0, 5.2))
KARTA["detaljer"]["lyktFlytt"] = [{"poly": P283_P(-9.6, 30.6, 2.0, 8.2), "d": 3.6}]                 # gatlyktorna ställs bakom parkeringsraden
for k_ in range(16): KARTA["detaljer"]["parkeringslinjer"].append(P283_W(-9.0 + k_ * 2.6, 2.85) + P283_W(-9.0 + k_ * 2.6, 7.9))
_ut283 = round(math.atan2(-0.2067, -0.9784), 3)                                    # nosen mot gatan
for k_ in (0, 1, 3, 4, 5, 7, 9, 10, 12, 14):
    c_ = P283_W(-9.0 + (k_ + 0.5) * 2.6, 5.45); KARTA["detaljer"]["parkeradeBilar"].append([c_[0], c_[1], _ut283 if k_ % 4 else round(_ut283 + math.pi, 3), 4])
_ps = P283_W(31.0, 8.6); KARTA["detaljer"]["vagskyltar"].append({"x": _ps[0], "z": _ps[1], "rot": _ut283, "typ": "P"})
KARTA["detaljer"]["tradfritt"].append([P283_W(-12.0, 8.0), P283_W(32.5, 8.0), P283_W(32.5, 22.5), P283_W(-20.0, 34.0)])
for u_, v_, h_, r_ in ((2.5, 12.6, 10.5, 3.6), (12.0, 13.0, 11.0, 3.4), (22.0, 12.4, 10.0, 3.8)):
    c_ = P283_W(u_, v_); KARTA["detaljer"]["storaTrad"].append({"x": c_[0], "z": c_[1], "h": h_, "r": r_})
for i0_, u0_, u1_ in ((9, 0.8, 10.4), (11, 5.2, 9.2)):                                 # häck längs sockeln framför västra delen och mitten
    a_, b_ = H283_POLY[i0_], H283_POLY[i0_ + 1]; L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1]); W_ = lokal(a_, ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_))[0]
    n_ = int((u1_ - u0_) / 2.3) + 1
    KARTA["detaljer"]["buskage"].append({"pts": [W_(u0_ + (u1_ - u0_) * k_ / n_, -1.5) for k_ in range(n_ + 1)], "bredd": 1.2, "hojd": 1.0, "tujor": []})
# --- Garagegårdar och parkering vid Torggatan 11-husen (utkast 62): en asfalterad infart från Torggatan längs varje hus västra gavel fram
# till garageportarna, och fyra tvärställda platser på infartens västra sida. Bara sju bilar på de fyra gårdarna (minnet).
_tg62 = next(r_ for r_ in KARTA["korbar"]["rutter"] if r_["namn"] == "Thulegatan–Torggatan")["pts"]
def _d62(x_, z_):
    return min(math.hypot(x_ - (a[0] + (b[0] - a[0]) * t_), z_ - (a[1] + (b[1] - a[1]) * t_)) for a, b in zip(_tg62, _tg62[1:])
               for t_ in [max(0.0, min(1.0, ((x_ - a[0]) * (b[0] - a[0]) + (z_ - a[1]) * (b[1] - a[1])) / ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 or 1.0)))])
for hid_, bilar_ in (("H315", (0, 3)), ("H321", (1, 2)), ("H323", (0,)), ("H325", (1, 3))):
    P_ = next(h for h in KARTA["hus"] if h["id"] == hid_)["poly"]; a_, b_ = P_[6], P_[7]; L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1])
    W_, R_, PP_ = lokal(tuple(a_), ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_))                     # u norrut längs västra gaveln, v österut in i huset
    um_ = L_
    while um_ < L_ + 40 and _d62(*W_(um_, -3.5)) > 2.9: um_ += 0.25                                   # infarten når fram till Torggatans kant
    ub1_ = min(um_ - 1.5, L_ + 11.4); ub0_ = ub1_ - 10.4
    KARTA["ytor"].append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": PP_(0.5, um_, -6.8, -0.3)})
    KARTA["ytor"].append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": PP_(ub0_, ub1_, -11.9, -6.7)})
    KARTA["detaljer"]["utanTrottoar"].append(PP_(um_ - 4.5, um_ + 2.0, -7.4, 0.3))
    KARTA["detaljer"]["tradfritt"].append(PP_(-1.0, um_ + 1.0, -13.0, 0.5))                          # inga träd på infarten och platserna
    for k_ in range(5): KARTA["detaljer"]["parkeringslinjer"].append(W_(ub0_ + k_ * 2.6, -7.0) + W_(ub0_ + k_ * 2.6, -11.8))
    _fr = W_(0.0, 1.0); _or = W_(0.0, 0.0); _ang = round(math.atan2(_fr[0] - _or[0], _fr[1] - _or[1]), 3)   # nosen österut mot infarten
    for k_ in bilar_:
        c_ = W_(ub0_ + (k_ + 0.5) * 2.6, -9.3); KARTA["detaljer"]["parkeradeBilar"].append([c_[0], c_[1], _ang, 3])
    _ps = W_(ub1_ + 0.7, -11.6); KARTA["detaljer"]["vagskyltar"].append({"x": _ps[0], "z": _ps[1], "rot": _ang, "typ": "P"})
    print("Torggatan 11-gård", hid_, "infart", round(um_ - L_, 1), "m, platser u", round(ub0_ - L_, 1), "till", round(ub1_ - L_, 1))
# --- Tomten vid Västra Storgatan 25 (utkast 64, foto från infarten): huset ligger på en höjd över gatan. Grusad infart upp till garaget,
# trappa med räcke till vänster om infarten, stenmur vid trappans fot, svart brevlåda och soptunna, hög häck till höger om infarten
# och täta träd mellan huset och gatan.
for u_ in (1.5, 5.6, 9.75, 13.9, 18.0): hojdankare.append(V25_W(u_, 4.5) + [20.5, 6.0, 1.0])
hojdankare.append(V25_W(-2.5, 4.5) + [20.3, 4.0, 1.0]); hojdankare.append(V25_W(-9.75, 1.1) + [19.7, 4.5, 1.0]); hojdankare.append(V25_W(-9.75, -5.5) + [19.1, 3.0, 1.0])
KARTA["ytor"].append({"typ": "grus", "namn": "", "poly": [V25_W(-12.4, -2.0), V25_W(-7.1, -2.0), V25_W(-7.1, -9.0), V25_W(-6.3, -11.6), V25_W(-13.2, -11.6), V25_W(-12.4, -9.0)]})
KARTA["detaljer"]["tradfritt"].append([V25_W(-14.5, -12.0), V25_W(-3.6, -12.0), V25_W(-3.6, 9.5), V25_W(-14.5, 9.5)])
_r25 = math.atan2(-V25_U[1], V25_U[0])
for k_ in range(9):                                                                       # trappsteg som följer slänten, med svart räcke mot infarten
    c_ = V25_W(-5.9, -10.4 + k_ * 0.85); _s = _Grupp(c_[0], c_[1], _r25)
    _s.box(0, -0.12, 0, 1.3, 0.3, 0.86, "#9b9892"); _s.box(-0.62, 0.15, 0, 0.04, 0.8, 0.04, "#1e1e1e"); _s.box(-0.62, 0.93, 0, 0.04, 0.04, 0.9, "#1e1e1e")
    KARTA["detaljer"]["skulpturer"].append(_s.ut("Trappa", 2.0))
for k_ in range(9):                                                                       # låg mur av natursten vid trappans fot
    c_ = V25_W(-4.6 + k_ * 0.75, -10.3 + (k_ % 2) * 0.25); KARTA["detaljer"]["stenblock"].append({"x": c_[0], "z": c_[1], "r": 0.42 + (k_ % 3) * 0.06})
_bl = V25_W(-4.3, -11.2); KARTA["detaljer"]["brevlador"].append({"x": _bl[0], "z": _bl[1], "rot": round(_r25, 3), "farg": "#1c1c1c"})
_st = V25_W(-2.9, -11.1); _s = _Grupp(_st[0], _st[1], _r25); _s.box(0, 0, 0, 0.58, 1.0, 0.7, "#1c1c1c"); _s.box(0, 1.0, 0.02, 0.62, 0.07, 0.76, "#262626")
KARTA["detaljer"]["skulpturer"].append(_s.ut("Soptunna", 2.0))
KARTA["detaljer"]["buskage"].append({"pts": [V25_W(-13.9, -11.0 + k_ * 2.0) for k_ in range(8)], "bredd": 1.6, "hojd": 2.4, "tujor": []})
for u_, v_, h_, r_ in ((-2.2, -5.2, 9.5, 2.6), (2.5, -6.8, 8.5, 3.6), (7.5, -5.0, 10.0, 3.9), (12.5, -6.5, 9.0, 3.7), (17.5, -5.2, 9.5, 3.8), (5.0, -2.6, 7.0, 3.0)):
    c_ = V25_W(u_, v_); KARTA["detaljer"]["storaTrad"].append({"x": c_[0], "z": c_[1], "h": h_, "r": r_})
# --- Tomten vid H706 (utkast 67): grusad infart från Torggatan till husets östra sida, häck längs Torggatan och runt hörnet mot
# Nygatan, svart brevlåda och soptunna vid infarten, en parkerad bil och ett stort buskträd i hörnet mot korsningen.
KARTA["ytor"].append({"typ": "grus", "namn": "", "hojd": 0.16, "poly": [T706_W(-10.6, -9.5), T706_W(9.5, -7.5), T706_W(9.5, -0.35), T706_W(0.0, -0.35), T706_W(-3.6, 1.3), T706_W(-10.6, 0.5)]})
KARTA["detaljer"]["tradfritt"].append([T706_W(-10.5, -10.5), T706_W(14.5, -10.5), T706_W(14.5, 18.0), T706_W(-10.5, 22.0)])
KARTA["detaljer"]["buskage"].append({"pts": [T706_W(-8.4, 2.2 + k_ * 2.0) for k_ in range(10)] + [T706_W(-7.0, 22.0), T706_W(-3.5, 22.3), T706_W(0.5, 21.2), T706_W(4.5, 20.0), T706_W(8.5, 18.8)],
                                     "bredd": 1.3, "hojd": 1.0, "tujor": []})
# marken: uppe mot korsningen ligger den i höjd med övervåningens golv (en våning syns därifrån), nere vid infarten i höjd med bottenvåningen
for v_ in (8.0, 11.2, 14.0):
    for u_ in (-1.0, 2.5, 6.0, 9.5, 13.0): hojdankare.append(T706_W(u_, v_) + [27.8, 2.4, 1.0])
for u_ in (-6.0, 0.5, 6.0, 11.5): hojdankare.append(T706_W(u_, -3.5) + [25.35, 3.5, 1.0])
_r706g = math.atan2(-T706_U[1], T706_U[0])
_bl = T706_W(-8.6, 0.9); KARTA["detaljer"]["brevlador"].append({"x": _bl[0], "z": _bl[1], "rot": round(_r706g + math.pi / 2, 3), "farg": "#1c1c1c"})
_st = T706_W(-7.6, -0.2); _s = _Grupp(_st[0], _st[1], _r706g); _s.box(0, 0, 0, 0.58, 1.0, 0.7, "#2c3a33"); _s.box(0, 1.0, 0.02, 0.62, 0.07, 0.76, "#26302b")
KARTA["detaljer"]["skulpturer"].append(_s.ut("Soptunna", 2.0))
_pb = T706_W(1.8, -2.6); KARTA["detaljer"]["parkeradeBilar"].append([_pb[0], _pb[1], round(math.atan2(T706_U[0], T706_U[1]), 3), 4])
_tr = T706_W(-4.5, 13.5); KARTA["detaljer"]["storaTrad"].append({"x": _tr[0], "z": _tr[1], "h": 6.5, "r": 3.4})
# --- Tomterna vid H065, H079 och H095 (utkast 68): planen framför det röda huset med rött trästaket på släntkrönet, asfalterad
# förgård framför det grå huset, häck öster om det och en röd container väster om skjulet.
for u_ in (-5.0, 1.0, 7.0, 13.0, 18.5): hojdankare.append(R65_W(u_, -3.6) + [21.45, 3.0, 1.0])
KARTA["ytor"].append({"typ": "grus", "namn": "", "hojd": 0.16, "poly": [R65_W(-6.6, -6.4), R65_W(21.0, -6.4), R65_W(21.0, -0.3), R65_W(-6.6, -0.3)]})
KARTA["detaljer"]["staket"].append({"pts": [R65_W(-13.0, -7.6)] + [R65_W(-10.0 + k_ * 3.0, -7.2) for k_ in range(11)] + [R65_W(23.5, -8.0), R65_W(27.0, -9.6)], "hojd": 1.0, "farg": "#8e3029", "stil": "rails"})
for u_, v_ in ((18.6, -3.2), (4.5, -4.4)):
    c_ = R65_W(u_, v_); KARTA["detaljer"]["parkeradeBilar"].append([c_[0], c_[1], round(math.atan2(R65_U[0], R65_U[1]), 3), 4])
KARTA["detaljer"]["tradfritt"].append([R65_W(-14.0, -11.0), R65_W(28.0, -11.0), R65_W(28.0, 0.0), R65_W(-14.0, 0.0)])
KARTA["ytor"].append({"typ": "parkering", "namn": "", "ingaBilar": True, "poly": [G79_W(-8.6, -5.2), G79_W(13.2, -5.2), G79_W(13.2, -0.25), G79_W(0.0, -0.25), G79_W(-0.4, -2.5), G79_W(-8.6, -3.6)]})
_pb = G79_W(6.0, -2.7); KARTA["detaljer"]["parkeradeBilar"].append([_pb[0], _pb[1], round(math.atan2(G79_U[0], G79_U[1]), 3), 4])
KARTA["detaljer"]["tradfritt"].append([G79_W(-27.0, -8.0), G79_W(24.0, -8.0), G79_W(24.0, 0.0), G79_W(-27.0, 0.0)])
KARTA["detaljer"]["buskage"].append({"pts": [G79_W(15.0 + k_ * 2.0, -3.6) for k_ in range(5)], "bredd": 1.5, "hojd": 1.7, "tujor": []})
_ct = T95_W(-12.5, 2.0); KARTA["detaljer"]["containrar"].append({"x": _ct[0], "z": _ct[1], "rot": round(math.atan2(-T95_U[1], T95_U[0]), 3), "b": 6.0, "h": 2.5, "d": 2.4, "farg": "#8e3a34"})
# --- Tomten framför de tre byggnaderna vid Västra Storgatan (utkast 69): grusad uppfart fram till carporten med två bilar, soptunna,
# stort buskage mellan carporten och bostadshuset, och ett lågt trästaket framför bostadshuset.
KARTA["ytor"].append({"typ": "grus", "namn": "", "hojd": 0.16, "poly": [C64_W(-3.5, -12.5), C64_W(9.0, -11.0), C64_W(9.0, -0.3), C64_W(-3.5, -0.3)]})
KARTA["detaljer"]["tradfritt"].append([C64_W(-9.0, -13.5), C64_W(11.0, -13.5), C64_W(11.0, 0.0), C64_W(-9.0, 0.0)])
KARTA["detaljer"]["tradfritt"].append([S618_W(-2.0, -9.0), S618_W(14.0, -9.0), S618_W(14.0, 0.0), S618_W(-2.0, 0.0)])
_v69 = round(math.atan2(C64_U[0], C64_U[1]), 3)                                                    # nosen västerut, mot carporten
for u_, v_ in ((5.4, -4.6), (2.0, -7.0)):
    c_ = C64_W(u_, v_); KARTA["detaljer"]["parkeradeBilar"].append([c_[0], c_[1], _v69, 4])
_st69 = C64_W(0.2, -1.2); _s = _Grupp(_st69[0], _st69[1], _v69); _s.box(0, 0, 0, 0.58, 1.0, 0.7, "#2f6033"); _s.box(0, 1.0, 0.02, 0.62, 0.07, 0.76, "#2a5a2e")
KARTA["detaljer"]["skulpturer"].append(_s.ut("Soptunna", 2.0))
KARTA["detaljer"]["buskage"].append({"pts": [S618_W(13.6 + k_ * 1.5, -3.0) for k_ in range(3)], "bredd": 2.6, "hojd": 3.0, "tujor": []})
KARTA["detaljer"]["staket"].append({"pts": [S618_W(12.4, -1.6), S618_W(8.0, -1.4), S618_W(3.0, -1.2)], "hojd": 0.9, "farg": "#8a7a62", "stil": "rails"})
_bl69 = C64_W(-1.4, -9.2); KARTA["detaljer"]["brevlador"].append({"x": _bl69[0], "z": _bl69[1], "rot": round(_v69 + math.pi / 2, 3), "farg": "#2a2a2a"})
# --- Fastigheten kring H555 (utkast 70): tomten planad kring huset, häck längs Västra Storgatan med en öppning för infarten väster om
# huset, grusad infart söderut och två bilar. VS_W följer gatan (u österut från korsningen med Värmlandsbergsgatan, v söderut).
VS_W = lokal((-916.0, -232.8), (0.9865, 0.1634))[0]
for u_ in (1.0, 5.0, 9.0, 13.0):
    for v_ in (0.0, 6.0, 12.0): hojdankare.append(S55_W(u_, v_) + [21.9, 5.0, 1.0])
for u_ in (1.0, 6.0, 11.0):
    hojdankare.append(S55_W(u_, 17.0) + [22.6, 5.0, 1.0]); hojdankare.append(S55_W(u_, 21.5) + [23.4, 5.0, 1.0])
KARTA["ytor"].append({"typ": "grus", "namn": "", "hojd": 0.16, "poly": [VS_W(26.6, 4.2), VS_W(33.4, 4.2), VS_W(33.4, 26.0), VS_W(26.6, 26.0)]})
KARTA["detaljer"]["tradfritt"].append([VS_W(14.0, 4.0), VS_W(58.0, 4.0), VS_W(58.0, 24.0), VS_W(14.0, 24.0)])
for u0_, u1_ in ((15.0, 26.0), (34.0, 57.0)):                                                      # häck längs gatan, med öppning för infarten
    n_ = int((u1_ - u0_) / 2.0)
    KARTA["detaljer"]["buskage"].append({"pts": [VS_W(u0_ + (u1_ - u0_) * k_ / n_, 5.0) for k_ in range(n_ + 1)], "bredd": 1.5, "hojd": 1.35, "tujor": []})
_vs69 = round(math.atan2(-VS_W(1, 0)[0] + VS_W(0, 0)[0], -VS_W(1, 0)[1] + VS_W(0, 0)[1]), 3)       # nosen västerut, mot infarten
for u_, v_ in ((29.0, 9.0), (31.6, 14.5)):
    c_ = VS_W(u_, v_); KARTA["detaljer"]["parkeradeBilar"].append([c_[0], c_[1], _vs69, 3])
_bl55 = VS_W(26.0, 5.6); KARTA["detaljer"]["brevlador"].append({"x": _bl55[0], "z": _bl55[1], "rot": round(_vs69 + math.pi / 2, 3), "farg": "#2f4a3a"})
print("Platåvägen: häckar", [len(b_["pts"]) for b_ in PLATA_BUSKAGE], "30-skylt", _s30)
KARTA["detaljer"]["stenblock"] += KD_STENAR; KARTA["detaljer"]["storaTrad"] += KD_TRAD
# ------------------------------------------------------------------ kontroll: inga buskar, staket eller trädstammar i körbanan
# varje punkt flyttas ut från närmaste bilväg tills den ligger utanför körbana + trottoar + en marginal (buskarnas halva bredd)
_bilvagar = [g for g in gator if g.get("bil") and not g.get("tunnel") and not g.get("bro")]
_vsegs = [(a, b, g["bredd"] / 2 + (g.get("trottoar") or 0.0), g) for g in _bilvagar for a, b in zip(g["pts"], g["pts"][1:])]
def _fri_punkt(x, z, marg):
    for _ in range(4):
        flyttad = False
        for a, b, kant, g in _vsegs:
            if abs(x - a[0]) > 40 and abs(x - b[0]) > 40: continue
            if abs(z - a[1]) > 40 and abs(z - b[1]) > 40: continue
            dx, dz = b[0] - a[0], b[1] - a[1]; L2 = dx * dx + dz * dz or 1e-9; t = max(0.0, min(1.0, ((x - a[0]) * dx + (z - a[1]) * dz) / L2))
            px, pz = a[0] + dx * t, a[1] + dz * t; d = math.hypot(x - px, z - pz); krav = kant + marg
            if d >= krav or d < 1e-3: continue
            x, z = px + (x - px) / d * krav, pz + (z - pz) / d * krav; flyttad = True
        if not flyttad: break
    return round(x, 2), round(z, 2)
_D = KARTA["detaljer"]; _n_flytt = 0
_huspaths = [Path(h["poly"]) for h in hus if h.get("poly") and len(h["poly"]) >= 3]
def _flytta_lista(pts, marg):
    global _n_flytt
    ut = []
    for q in pts:
        nx_, nz_ = _fri_punkt(q[0], q[1], marg)
        if math.hypot(nx_ - q[0], nz_ - q[1]) > 0.05: _n_flytt += 1
        ut.append([nx_, nz_])
    return ut
for bu in _D.get("buskage", []):
    tät = []
    for a, b in zip(bu["pts"], bu["pts"][1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(L / 2.0))
        tät += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(n)]
    tät.append(list(bu["pts"][-1]))
    bu["pts"] = [q for q in _flytta_lista(tät, bu["bredd"] / 2 + 0.9) if not any(_hp.contains_point(q, radius=0.6) or _hp.contains_point(q, radius=-0.6) for _hp in _huspaths)]
    bu["tujor"] = _flytta_lista(bu.get("tujor", []), 1.4)
for st in _D.get("staket", []):
    tät = []
    for a, b in zip(st["pts"], st["pts"][1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(L / 2.0))
        tät += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(n)]
    tät.append(list(st["pts"][-1]))
    st["pts"] = _flytta_lista(tät, 0.35)
for lista, marg in (("storaTrad", 0.9), ("bankar", 0.5), ("brevlador", 0.3), ("stenblock", 0.6), ("gatupratare", 0.4), ("papperskorgar", 0.3)):
    for it in _D.get(lista, []):
        x_, z_ = _fri_punkt(it["x"], it["z"], marg + (it.get("r", 0) if lista == "stenblock" else 0))
        if math.hypot(x_ - it["x"], z_ - it["z"]) > 0.05: _n_flytt += 1
        it["x"], it["z"] = x_, z_
print('detaljer flyttade ut från körbanor:', _n_flytt, 'punkter')
_vc = GB_W(3.2, 12.6)
KARTA["korbar"]["rutter"].append({"namn": "Vändplan Granbackavägen", "pts": [[round(_vc[0] + 4.2 * math.cos(a_), 2), round(_vc[1] + 4.2 * math.sin(a_), 2)] for a_ in [k_ * 2 * math.pi / 20 for k_ in range(21)]],
                                  "bredd": 5.0, "trottoar": 0.0, "capStart": False, "capEnd": False, "utanLyktor": True})
_D["storaTrad"] += H068_TRAD
_D["storaTrad"] += [dict(t_, **dict(zip(("x", "z"), _fri_punkt(t_["x"], t_["z"], 0.9)))) for t_ in RIVET_TRAD + STN_TRAD]
_D["storaTrad"].append({"x": _CP(8.0, 0.7)[0], "z": _CP(8.0, 0.7)[1], "h": 7.5, "r": 3.4})   # trädet i buskraden längs Coop-parkeringens södra kant
_D["storaTrad"] += H194_TRAD + GB_TRAD
_D["stenblock"] += GB_STENAR   # stenblocken vid Granbackavägen 108 står där de står
_D["staket"].append(staket_gb)   # trädet i buskraden vid Coops lastkaj   # unga träd på planteringsöarna mellan fickorna och körbanan (ska stå där de står)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write("// EPA-Gnesta – kartdata (utkast 2). Genererad från OpenStreetMap-export.\n")
    f.write("// Kartdata © OpenStreetMap-bidragsgivare, tillgänglig under ODbL (openstreetmap.org/copyright).\n")
    f.write("export const KARTA = ")
    f.write(json.dumps(KARTA, ensure_ascii=False, separators=(",", ":")))
    f.write(";\n")
import os
print('skrev', OUT, os.path.getsize(OUT) // 1024, 'kB')
