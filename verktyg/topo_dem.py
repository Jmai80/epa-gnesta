"""Läser av höjder ur en topografisk färgkarta (färgskala 6–52 m) och gör ett höjdgrid i spelets koordinater.
Användning: python3 topo_dem.py bild.png reg.json ut.json [norr_z]
reg.json = {"s": px per meter, "ox": px för x=0, "oz": px för z=0}; för Gnesta-bilden (2424x1048 px) gav
kartpassningen s=0.814, ox=1073, oz=151. Med norr_z (t.ex. -455) förlängs rutnätet norr om bildens överkant.
Ut-filen läggs i data/topo_hojd.json."""
import sys, json, base64, colorsys, numpy as np
from PIL import Image, ImageFilter
bild, regf, ut = sys.argv[1:4]
reg = json.load(open(regf))
im = np.asarray(Image.open(bild).convert('RGB')).astype(np.float32) / 255
Hh, Ww = im.shape[:2]
# legendens färger (avlästa ur bilden) -> nyans
LEG = [(52, (240, 117, 92)), (49, (242, 151, 99)), (47, (244, 177, 105)), (44, (249, 218, 116)), (42, (253, 246, 124)), (39, (229, 254, 125)),
       (37, (208, 253, 124)), (34, (181, 253, 122)), (32, (167, 252, 122)), (29, (154, 252, 121)), (27, (152, 252, 121)), (24, (152, 252, 133)),
       (22, (152, 252, 148)), (19, (152, 252, 177)), (17, (152, 252, 197)), (15, (152, 252, 217)), (12, (152, 252, 247)), (10, (145, 240, 253)),
       (8, (136, 221, 251)), (6, (129, 206, 251))]
lh = np.array([colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[0] * 360 for _, rgb in LEG]); lz = np.array([h for h, _ in LEG], float)
lh = np.maximum.accumulate(lh)   # monoton nyans
mx = im.max(2); mn = im.min(2); sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
r, g, b = im[..., 0], im[..., 1], im[..., 2]; d = np.maximum(mx - mn, 1e-6)
hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
hojd = np.interp(hue, lh, lz)
w = np.clip((sat - 0.08) / 0.12, 0, 1) * (mx > 0.55)
w[:, 2280:] = 0; w[:345, :125] = 0; w[985:, :200] = 0; w[1030:, :] = 0      # legend, knappar, skalstock, attribution
from scipy.ndimage import gaussian_filter
def blur(a, s):
    return gaussian_filter(a.astype(np.float32), s)
num = blur(hojd * w, 5); den = blur(w, 5); H5 = np.where(den > 1e-3, num / np.maximum(den, 1e-6), np.nan)
s, ox, oz = reg['s'], reg['ox'], reg['oz']
steg = 8.0
x0 = (0 - ox) / s; x1 = (2280 - ox) / s; z0 = (0 - oz) / s; z1 = (1030 - oz) / s
nx = int((x1 - x0) // steg) + 1; nz = int((z1 - z0) // steg) + 1
xs = x0 + np.arange(nx) * steg; zs = z0 + np.arange(nz) * steg
px = np.clip((xs * s + ox).round().astype(int), 0, Ww - 1); pz = np.clip((zs * s + oz).round().astype(int), 0, Hh - 1)
G = H5[np.ix_(pz, px)]
# fyll hål (t.ex. under legenden) med närmaste värden
from collections import deque
if np.isnan(G).any():
    mask = np.isnan(G); q = deque((j, i) for j in range(nz) for i in range(nx) if not mask[j, i])
    while q:
        j, i = q.popleft()
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jj, ii = j + dj, i + di
            if 0 <= jj < nz and 0 <= ii < nx and mask[jj, ii]: G[jj, ii] = G[j, i]; mask[jj, ii] = False; q.append((jj, ii))
# norr om bildens överkant (Västra Storgatan väster om centrum) finns ingen avläsning: förläng rutnätet norrut.
# Marken där sluttar ner mot dalgången längs Västra Storgatan/järnvägen (högst ~20,5 m), tonat över 60 m.
NORR_Z = float(sys.argv[4]) if len(sys.argv) > 4 else None
if NORR_Z is not None and NORR_Z < z0:
    extra = int(np.ceil((z0 - NORR_Z) / steg)); kant = G[:2].mean(0)
    rader = []
    for k in range(extra, 0, -1):
        d = k * steg; t = np.clip(d / 60, 0, 1); t = t * t * (3 - 2 * t)
        rader.append(kant + (np.minimum(kant, 20.5) - kant) * t)
    G = np.vstack([np.array(rader), G]); z0 -= extra * steg; nz += extra
data = np.round(G * 10).astype('<i2')
json.dump({"x0": round(float(x0), 2), "z0": round(float(z0), 2), "steg": steg, "nx": nx, "nz": nz, "data": base64.b64encode(data.tobytes()).decode(),
           "kalla": "Höjder avlästa ur topografisk färgkarta (skala 6–52 m) som användaren bifogade"}, open(ut, 'w'))
print('grid', nx, 'x', nz, 'x:', round(x0), round(x1), 'z:', round(z0), round(z1), 'min/max', round(float(np.nanmin(G)), 1), round(float(np.nanmax(G)), 1))
np.save(ut.replace('.json', '.npy'), G); json.dump({"x0": float(x0), "z0": float(z0), "steg": steg}, open(ut.replace('.json', '_meta.json'), 'w'))
