// EPA-Gnesta – utkast 2 (gator, hus, järnväg och vatten från OpenStreetMap)
// Koordinater: meter, origo = Gnesta station, x = öster, z = söder, y = meter över havet.
import * as THREE from './three.module.js';
import { KARTA } from './karta.js';

const K = KARTA;
const T = K.terrang;
const VATTEN = T.vatten;
const $ = (id) => document.getElementById(id);
const status = (t) => { const e = $('laddtext'); if (e) e.textContent = t; };

// =====================================================================
// Hjälpfunktioner
// =====================================================================
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
function smoothstep(a, b, x) { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); }
function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function hash2(ix, iz) {
  let h = Math.imul(ix | 0, 374761393) + Math.imul(iz | 0, 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h = h ^ (h >>> 16);
  return (h >>> 0) / 4294967295;
}
function vnoise(x, z) {
  const ix = Math.floor(x), iz = Math.floor(z); const fx = x - ix, fz = z - iz;
  const ux = fx * fx * (3 - 2 * fx), uz = fz * fz * (3 - 2 * fz);
  const a = hash2(ix, iz), b = hash2(ix + 1, iz), c = hash2(ix, iz + 1), d = hash2(ix + 1, iz + 1);
  return (a + (b - a) * ux + (c - a) * uz + (a - b - c + d) * ux * uz) * 2 - 1;
}
function fbm(x, z, oct = 4) { let s = 0, a = 0.5, f = 1; for (let i = 0; i < oct; i++) { s += a * vnoise(x * f, z * f); f *= 2.03; a *= 0.5; } return s; }

// Catmull-Rom – samma algoritm som i tools/bygg_karta.py
function crSmooth(pts, step) {
  const out = []; const n = pts.length;
  if (n < 2) return pts.map(p => [p[0], p[1]]);
  for (let i = 0; i < n - 1; i++) {
    const p1 = pts[i], p2 = pts[i + 1];
    const p0 = i > 0 ? pts[i - 1] : [2 * p1[0] - p2[0], 2 * p1[1] - p2[1]];
    const p3 = i + 2 < n ? pts[i + 2] : [2 * p2[0] - p1[0], 2 * p2[1] - p1[1]];
    const L = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
    const k = Math.max(2, Math.ceil(L / step));
    for (let j = 0; j < k; j++) {
      const t = j / k, t2 = t * t, t3 = t2 * t;
      out.push([
        0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
      ]);
    }
  }
  out.push([pts[n - 1][0], pts[n - 1][1]]);
  return out;
}
function withMeta(sm) {
  const out = []; let s = 0;
  for (let i = 0; i < sm.length; i++) {
    if (i > 0) s += Math.hypot(sm[i][0] - sm[i - 1][0], sm[i][1] - sm[i - 1][1]);
    const a = sm[Math.max(0, i - 1)], b = sm[Math.min(sm.length - 1, i + 1)];
    let tx = b[0] - a[0], tz = b[1] - a[1]; const l = Math.hypot(tx, tz) || 1;
    out.push({ x: sm[i][0], z: sm[i][1], s, tx: tx / l, tz: tz / l });
  }
  return out;
}
function bbox(poly) { let a = [1e9, 1e9, -1e9, -1e9]; for (const p of poly) { a[0] = Math.min(a[0], p[0]); a[1] = Math.min(a[1], p[1]); a[2] = Math.max(a[2], p[0]); a[3] = Math.max(a[3], p[1]); } return a; }
function pointInPoly(x, z, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], zi = poly[i][1], xj = poly[j][0], zj = poly[j][1];
    if (((zi > z) !== (zj > z)) && (x < (xj - xi) * (z - zi) / (zj - zi + 1e-12) + xi)) inside = !inside;
  }
  return inside;
}
function segDist(px, pz, ax, az, bx, bz) {
  const dx = bx - ax, dz = bz - az; const L2 = dx * dx + dz * dz;
  const t = L2 === 0 ? 0 : clamp(((px - ax) * dx + (pz - az) * dz) / L2, 0, 1);
  const cx = ax + dx * t, cz = az + dz * t;
  return [Math.hypot(px - cx, pz - cz), t, cx, cz];
}
// signerat avstånd till polygon (negativt innanför) + närmaste kantindex. Snabbt ut om långt bort.
function makeSD(poly) {
  const bb = bbox(poly);
  return function (x, z, maxd) {
    if (x < bb[0] - maxd || x > bb[2] + maxd || z < bb[1] - maxd || z > bb[3] + maxd) return [maxd + 1, 0];
    let best = 1e18, bi = 0;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      const d = segDist(x, z, a[0], a[1], b[0], b[1])[0];
      if (d < best) { best = d; bi = i; }
    }
    return [pointInPoly(x, z, poly) ? -best : best, bi];
  };
}

// Spatialt index för linjesegment (gator m.m.)
class SegIndex {
  constructor(cell = 24) { this.cell = cell; this.map = new Map(); this.segs = []; this.stamp = new Int32Array(0); this.q = 1; }
  key(ix, iz) { return (ix + 4096) * 8192 + (iz + 4096); }
  add(ax, az, bx, bz, data) {
    const id = this.segs.length; this.segs.push({ ax, az, bx, bz, data }); const c = this.cell;
    const x0 = Math.floor(Math.min(ax, bx) / c), x1 = Math.floor(Math.max(ax, bx) / c);
    const z0 = Math.floor(Math.min(az, bz) / c), z1 = Math.floor(Math.max(az, bz) / c);
    for (let x = x0; x <= x1; x++) for (let z = z0; z <= z1; z++) { const k = this.key(x, z); let a = this.map.get(k); if (!a) { a = []; this.map.set(k, a); } a.push(id); }
  }
  done() { this.stamp = new Int32Array(this.segs.length); }
  near(x, z, r, cb) {
    const c = this.cell; this.q++;
    const x0 = Math.floor((x - r) / c), x1 = Math.floor((x + r) / c), z0 = Math.floor((z - r) / c), z1 = Math.floor((z + r) / c);
    for (let ix = x0; ix <= x1; ix++) for (let iz = z0; iz <= z1; iz++) {
      const a = this.map.get(this.key(ix, iz)); if (!a) continue;
      for (const id of a) { if (this.stamp[id] === this.q) continue; this.stamp[id] = this.q; cb(this.segs[id]); }
    }
  }
}


// =====================================================================
// Terräng – höjderna är uppskattade: centrum ~15 m, Gnestahöjden ~60 m vid gamla vattentornet,
// förkastningsbrant mot norr (Harsprånget). Strandlinjer från OpenStreetMap.
// =====================================================================
function decodeGrid(g, Typ) { const bin = atob(g.data); const u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i); return Typ === Uint8Array ? u8 : new Typ(u8.buffer); }
const SDF = decodeGrid(T.sdf, Int16Array), SDFG = decodeGrid(T.sdfGrov, Int16Array);
const LCG = K.marktacke; const LCA = decodeGrid(LCG, Uint8Array);
function gridBil(arr, g, x, z) {
  const fx = (x - g.x0) / g.res, fz = (z - g.z0) / g.res; const i = Math.floor(fx), j = Math.floor(fz);
  if (i < 0 || j < 0 || i >= g.nx - 1 || j >= g.nz - 1) return null;
  const tx = fx - i, tz = fz - j; const k = j * g.nx + i;
  const a = arr[k], b = arr[k + 1], c = arr[k + g.nx], d = arr[k + g.nx + 1];
  return (a + (b - a) * tx + (c - a) * tz + (a - b - c + d) * tx * tz) / 4;
}
function waterSD(x, z) { let v = gridBil(SDF, T.sdf, x, z); if (v === null) v = gridBil(SDFG, T.sdfGrov, x, z); return v === null ? 800 : v; }
function lcAt(x, z) { const i = Math.round((x - LCG.x0) / LCG.res), j = Math.round((z - LCG.z0) / LCG.res); if (i < 0 || j < 0 || i >= LCG.nx || j >= LCG.nz) return -1; return LCA[j * LCG.nx + i]; }
const RAM = K.ram; // [x0, x1, z0, z1] för OSM-utdraget
const inRam = (x, z, m = 0) => x > RAM[0] - m && x < RAM[1] + m && z > RAM[2] - m && z < RAM[3] + m;
const sdPlata = makeSD(T.plata);
const maxPlataW = Math.max(...T.plataBredd);

function baseHeight(x, z, sd) {
  if (sd === undefined) sd = waterSD(x, z);
  let h = T.bas + T.lutning * clamp(sd, 0, T.maxAvst);
  const dc = Math.hypot(x - 200, z - 330);
  const m = smoothstep(1250, 2100, dc);
  if (m > 0) h += m * (fbm(x / 420 + 3.1, z / 420 - 7.7, 4) * 12);
  h += fbm(x / 95 + 7, z / 95 - 3, 3) * 1.0 * smoothstep(15, 70, sd);
  for (const k of T.kullar) { const d2 = (x - k[0]) ** 2 + (z - k[1]) ** 2; const s2 = 2 * k[2] * k[2]; if (d2 < s2 * 9) h += k[3] * Math.exp(-d2 / s2); }
  const [sdp, ei] = sdPlata(x, z, maxPlataW + 5);
  if (sdp < maxPlataW) {
    const wb = T.plataBredd[ei];
    const f = 1 - smoothstep(-15, wb, sdp);
    let hill = T.plataHojd * f;
    if (sdp < 0) hill += (fbm(x / 60 + 11, z / 60 + 5, 3) * 0.5 + 0.5) * 4.0 * smoothstep(0, -40, sdp);
    const tp = T.topp; const d2 = (x - tp[0]) ** 2 + (z - tp[1]) ** 2;
    hill += tp[3] * Math.exp(-d2 / (2 * tp[2] * tp[2])) * f;
    h += hill;
  }
  return h;
}
let carves = [];
function heightNC(x, z) {
  const sd = waterSD(x, z);
  let h = baseHeight(x, z, sd);
  if (sd < 16) {
    if (sd >= 0) h = lerp(VATTEN - 0.6, h, smoothstep(0, 16, sd));
    else h = VATTEN - 0.6 - Math.min(6, -sd * 0.06);
  }
  return h;
}
function H(x, z) {
  let h = heightNC(x, z);
  for (const c of carves) {
    if (Math.abs(x - c.cx) > c.R || Math.abs(z - c.cz) > c.R) continue;
    let best = 1e9, bs = 0;
    for (let i = 0; i < c.pts.length - 1; i++) {
      const a = c.pts[i], b = c.pts[i + 1];
      const [d, t] = segDist(x, z, a.x, a.z, b.x, b.z);
      if (d < best) { best = d; bs = lerp(a.s, b.s, t); }
    }
    const along = Math.abs(bs - c.s0);
    h -= c.djup * (1 - smoothstep(c.langd * 0.3, c.langd, along)) * (1 - smoothstep(c.bredd * 0.5, c.bredd * 0.5 + (c.kant ?? 9), best));
  }
  return h;
}

// Linjär omsampling av en polylinje med tangenter (gerning i hörnen)
function resample(pts, step) {
  const out = []; let s = 0; const n = pts.length; const dirs = [];
  for (let i = 0; i < n - 1; i++) { const dx = pts[i + 1][0] - pts[i][0], dz = pts[i + 1][1] - pts[i][1]; const L = Math.hypot(dx, dz) || 1e-6; dirs.push([dx / L, dz / L, L]); }
  if (!dirs.length) return [{ x: pts[0][0], z: pts[0][1], s: 0, tx: 1, tz: 0, m: 1 }];
  for (let i = 0; i < n - 1; i++) {
    const [dx, dz, L] = dirs[i]; const k = Math.max(1, Math.ceil(L / step));
    for (let j = 0; j < k; j++) {
      const t = j / k; let tx = dx, tz = dz, m = 1;
      if (j === 0 && i > 0) {
        const [px, pz] = dirs[i - 1]; let ax = px + dx, az = pz + dz; const l = Math.hypot(ax, az);
        if (l > 1e-6) { ax /= l; az /= l; tx = ax; tz = az; m = 1 / Math.max(0.55, ax * dx + az * dz); }
      }
      out.push({ x: pts[i][0] + dx * L * t, z: pts[i][1] + dz * L * t, s: s + L * t, tx, tz, m });
    }
    s += L;
  }
  const last = dirs[n - 2]; out.push({ x: pts[n - 1][0], z: pts[n - 1][1], s, tx: last[0], tz: last[1], m: 1 });
  return out;
}

// =====================================================================
// Gator (förberedelse)
// =====================================================================
const gator = K.gator.map((g, i) => ({ ...g, idx: i, sm: resample(g.pts, 2.0) }));
const gataById = Object.fromEntries(gator.map(g => [g.id, g]));
const roadIndex = new SegIndex(24);
for (const g of gator) { if (g.tunnel) continue; for (let i = 0; i < g.sm.length - 1; i++) roadIndex.add(g.sm[i].x, g.sm[i].z, g.sm[i + 1].x, g.sm[i + 1].z, { g, i }); }
roadIndex.done();
function nearestRoad(x, z, r, filter) {
  let best = null;
  roadIndex.near(x, z, r, (sg) => {
    if (filter && !filter(sg.data.g)) return;
    const [d, t] = segDist(x, z, sg.ax, sg.az, sg.bx, sg.bz);
    if (!best || d < best.d) best = { d, g: sg.data.g, i: sg.data.i, t };
  });
  return best;
}
for (const sk of T.skarningar) {
  const g = gataById[sk.gata]; if (!g) continue; let bi = 0, bd = 1e9;
  g.sm.forEach((p, i) => { const d = Math.hypot(p.x - sk.x, p.z - sk.z); if (d < bd) { bd = d; bi = i; } });
  const s0 = g.sm[bi].s;
  carves.push({ pts: g.sm.filter(p => Math.abs(p.s - s0) < sk.langd + 25), s0, cx: sk.x, cz: sk.z, R: sk.langd + 40, djup: sk.djup, langd: sk.langd, bredd: sk.bredd });
}
// gång- och cykeltunnlar under spåret: sänka längs gångvägen, full djup under spåren och ramper på båda sidor
for (const gt of (K.detaljer && K.detaljer.gangtunnlar) || []) {
  const sm = resample(gt.pts, 1.5); const s0 = (gt.t0 + gt.t1) / 2; const half = (gt.t1 - gt.t0) / 2; const langd = half / 0.3;
  const mid = sm.reduce((b, p) => Math.abs(p.s - s0) < Math.abs(b.s - s0) ? p : b, sm[0]);
  carves.push({ pts: sm.filter(p => Math.abs(p.s - s0) < langd + 25), s0, cx: mid.x, cz: mid.z, R: langd + 40, djup: gt.djup, langd, bredd: gt.bredd, kant: gt.kant, gang: gt, half });
}


// =====================================================================
// Renderare, scen, himmel, ljus
// =====================================================================
const canvas = $('scen');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;

const scene = new THREE.Scene();
const HORISONT = new THREE.Color('#cfdbe3');
scene.fog = new THREE.FogExp2(HORISONT.clone(), 0.00040);
const camera = new THREE.PerspectiveCamera(62, window.innerWidth / window.innerHeight, 0.3, 14000);
camera.position.set(-600, 60, 120);

const SOL = new THREE.Vector3(-0.58, 0.46, 0.67).normalize();
function skyMaterial() {
  return new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { sol: { value: SOL } },
    vertexShader: `varying vec3 vDir; void main(){ vDir = normalize(position); vec4 p = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position = p.xyww; }`,
    fragmentShader: `uniform vec3 sol; varying vec3 vDir;
      void main(){ float y = max(vDir.y, -0.1);
        vec3 zen = vec3(0.16,0.33,0.62); vec3 hor = vec3(0.70,0.78,0.84); vec3 warm = vec3(1.0,0.80,0.58);
        float s = max(dot(normalize(vDir), sol), 0.0);
        vec3 c = mix(hor, zen, pow(clamp(y,0.0,1.0), 0.55));
        c = mix(c, warm, pow(s, 6.0)*0.45*(1.0-clamp(y*1.5,0.0,1.0)));
        c += vec3(1.0,0.92,0.75) * pow(s, 900.0) * 6.0;
        if (vDir.y < 0.0) c = mix(hor, vec3(0.45,0.5,0.45), clamp(-vDir.y*4.0,0.0,1.0));
        gl_FragColor = vec4(c, 1.0); }`,
  });
}
const sky = new THREE.Mesh(new THREE.SphereGeometry(9000, 32, 16), skyMaterial());
sky.frustumCulled = false; sky.renderOrder = -10;
scene.add(sky);
{ // omgivningskarta för reflexer
  const pm = new THREE.PMREMGenerator(renderer);
  const s2 = new THREE.Scene(); s2.add(new THREE.Mesh(new THREE.SphereGeometry(50, 32, 16), skyMaterial()));
  scene.environment = pm.fromScene(s2, 0.02).texture;
  scene.environmentIntensity = 0.55;
}
const hemi = new THREE.HemisphereLight(0xcfe0ff, 0x4f5e3a, 0.85); scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff0dc, 2.4);
sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 10; sun.shadow.camera.far = 900;
sun.shadow.bias = -0.0006; sun.shadow.normalBias = 0.6;
scene.add(sun); scene.add(sun.target);
function setShadowBox(r) { const c = sun.shadow.camera; c.left = -r; c.right = r; c.top = r; c.bottom = -r; c.updateProjectionMatrix(); }
setShadowBox(110);

// =====================================================================
// Texturer
// =====================================================================
function canvasTex(w, h, draw, srgb = true, repeat = true) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c); if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy()); return t;
}
const rnd = mulberry32(42);
const texAsfalt = canvasTex(256, 256, (g, w, h) => {
  g.fillStyle = '#5b5d60'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 9000; i++) { const v = 70 + rnd() * 50 | 0; g.fillStyle = `rgb(${v},${v},${v + 3})`; g.fillRect(rnd() * w, rnd() * h, 1 + rnd() * 1.5, 1 + rnd() * 1.5); }
  g.globalAlpha = 0.08; for (let i = 0; i < 30; i++) { g.fillStyle = rnd() < 0.5 ? '#000' : '#999'; g.beginPath(); g.ellipse(rnd() * w, rnd() * h, 10 + rnd() * 40, 6 + rnd() * 20, rnd() * 3, 0, 7); g.fill(); }
});
const texTrottoar = canvasTex(128, 128, (g, w, h) => {
  g.fillStyle = '#a7a59f'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 2500; i++) { const v = 150 + rnd() * 40 | 0; g.fillStyle = `rgb(${v},${v - 2},${v - 6})`; g.fillRect(rnd() * w, rnd() * h, 1, 1); }
  g.strokeStyle = 'rgba(60,60,60,0.35)'; g.lineWidth = 2; g.strokeRect(0, 0, w, h); g.beginPath(); g.moveTo(w / 2, 0); g.lineTo(w / 2, h); g.stroke();
});
const texSten = canvasTex(256, 256, (g, w, h) => {
  g.fillStyle = '#7d776e'; g.fillRect(0, 0, w, h);
  const s = 16;
  for (let y = 0; y < h; y += s) for (let x = 0; x < w; x += s) {
    const v = 120 + rnd() * 50 | 0; g.fillStyle = `rgb(${v},${v - 6},${v - 14})`;
    g.beginPath(); g.roundRect(x + 1 + ((y / s) % 2) * 4, y + 1, s - 3, s - 3, 4); g.fill();
  }
});
const texMark = canvasTex(256, 256, (g, w, h) => {
  const id = g.createImageData(w, h);
  for (let i = 0; i < w * h; i++) { const v = 205 + (rnd() * 50 | 0); id.data[i * 4] = v; id.data[i * 4 + 1] = v; id.data[i * 4 + 2] = v; id.data[i * 4 + 3] = 255; }
  g.putImageData(id, 0, 0);
  for (let i = 0; i < 600; i++) { g.fillStyle = `rgba(${rnd() < .5 ? 255 : 120},${rnd() < .5 ? 255 : 130},${rnd() < .5 ? 255 : 100},0.12)`; g.beginPath(); g.arc(rnd() * w, rnd() * h, 2 + rnd() * 8, 0, 7); g.fill(); }
}, true);
// Fasadtextur: r = väggljus, g = fönstermask, b = glas/karm-ljus (läses som data)
const texFasad = canvasTex(128, 128, (g, w, h) => {
  const id = g.createImageData(w, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4; let r = 235 + (hash2(x, y) * 20 | 0), gg = 0, b = 0;
    const inX = x >= 38 && x < 90, inY = y >= 24 && y < 98;
    if (inX && inY) {
      gg = 255;
      const frame = x < 42 || x >= 86 || y < 28 || y >= 94 || (x >= 62 && x < 66) || (y >= 50 && y < 53);
      b = frame ? 255 : 20 + ((y - 24) / 74 * 40 | 0) + (x - 38 < 20 ? 20 : 0);
    }
    if (y >= 122) r = 200; // våningsband
    id.data[i] = r; id.data[i + 1] = gg; id.data[i + 2] = b; id.data[i + 3] = 255;
  }
  g.putImageData(id, 0, 0);
}, false);
texFasad.magFilter = THREE.LinearFilter;

function textTex(text, o = {}) {
  const w = o.w || 512, h = o.h || 128;
  return canvasTex(w, h, (g) => {
    g.fillStyle = o.bg || '#1d4f9c'; g.fillRect(0, 0, w, h);
    if (o.border) { g.strokeStyle = o.border; g.lineWidth = o.bw || 10; g.strokeRect(o.bw / 2 || 5, o.bw / 2 || 5, w - (o.bw || 10), h - (o.bw || 10)); }
    g.fillStyle = o.fg || '#fff'; g.font = o.font || `bold ${Math.round(h * 0.56)}px "Trebuchet MS", Arial, sans-serif`;
    if (o.fit) { const it = o.italic ? 'italic ' : ''; let fs = h * 0.64; g.font = `${it}bold ${fs}px "Trebuchet MS", Arial, sans-serif`; const mw = g.measureText(text).width; if (mw > w * 0.92) fs *= w * 0.92 / mw; g.font = `${it}bold ${Math.round(fs)}px "Trebuchet MS", Arial, sans-serif`; }
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, w / 2, h / 2 + (o.dy || 0));
  }, true, false);
}


// =====================================================================
// Terrängnät + vatten
// =====================================================================
const C = (h) => new THREE.Color(h);
const colGras = C('#6d8c45'), colGras2 = C('#86a352'), colSkogsmark = C('#4b5e33'), colBerg = C('#8a857a'), colSand = C('#b9a879'), colBotten = C('#4f5c47'), colAker = C('#b1ad66'), colAker2 = C('#9c8d5a');
const LCF = { 0: C('#7b9450'), 1: C('#4c5f35'), 2: C('#80a64d'), 3: C('#78964f'), 4: C('#b4ad6a'), 5: C('#8e897d'), 6: C('#8c8f78'), 7: C('#6e7746'), 8: C('#cdbb8a'), 9: C('#6a9a46') };
function skogUte(x, z) { const n = fbm(x / 260 + 40, z / 260 - 12, 3) * 0.5 + 0.5; return smoothstep(0.48, 0.64, n); }
function terrainColor(x, z, y, ny, tmp) {
  const n1 = fbm(x / 60, z / 60, 2) * 0.5 + 0.5;
  const lc = lcAt(x, z);
  if (lc >= 0) {
    tmp.copy(LCF[lc] || LCF[0]); tmp.offsetHSL(0, 0, (n1 - 0.5) * 0.07);
    const e = Math.min(x - RAM[0], RAM[1] - x, z - RAM[2], RAM[3] - z); // mjuk övergång mot ramen
    if (e < 60) { const o = new THREE.Color().copy(colGras).lerp(colGras2, n1).lerp(colSkogsmark, skogUte(x, z) * 0.85); tmp.lerp(o, 1 - smoothstep(0, 60, e)); }
  } else {
    tmp.copy(colGras).lerp(colGras2, n1); const sk = skogUte(x, z); tmp.lerp(colSkogsmark, sk * 0.85);
    if (sk < 0.2) { const f = fbm(x / 300 + 9, z / 300 + 2, 3); if (f > 0.12) tmp.lerp(n1 > 0.5 ? colAker : colAker2, smoothstep(0.12, 0.25, f) * 0.85); }
  }
  const slope = 1 - ny; if (slope > 0.22) tmp.lerp(colBerg, smoothstep(0.22, 0.45, slope));
  if (y < VATTEN + 0.8 && y > VATTEN - 0.4) tmp.lerp(colSand, 0.6);
  if (y <= VATTEN - 0.4) tmp.copy(colBotten);
}
function buildTerrain(x0, x1, z0, z1, step, inner) {
  const nx = Math.round((x1 - x0) / step) + 1, nz = Math.round((z1 - z0) / step) + 1;
  const pos = new Float32Array(nx * nz * 3), uv = new Float32Array(nx * nz * 2);
  for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++) {
    const x = x0 + i * step, z = z0 + j * step; const k = j * nx + i;
    let y = H(x, z);
    if (inner && x > inner[0] && x < inner[1] && z > inner[2] && z < inner[3]) y -= 8;
    pos[k * 3] = x; pos[k * 3 + 1] = y; pos[k * 3 + 2] = z; uv[k * 2] = x / 7; uv[k * 2 + 1] = z / 7;
  }
  const idx = new Uint32Array((nx - 1) * (nz - 1) * 6); let o = 0;
  for (let j = 0; j < nz - 1; j++) for (let i = 0; i < nx - 1; i++) { const a = j * nx + i, b = a + 1, c = a + nx, d = c + 1; idx[o++] = a; idx[o++] = c; idx[o++] = b; idx[o++] = b; idx[o++] = c; idx[o++] = d; }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); geo.setIndex(new THREE.BufferAttribute(idx, 1));
  geo.computeVertexNormals();
  const nor = geo.attributes.normal.array; const col = new Float32Array(nx * nz * 3); const tmp = new THREE.Color();
  for (let k = 0; k < nx * nz; k++) { terrainColor(pos[k * 3], pos[k * 3 + 2], pos[k * 3 + 1], nor[k * 3 + 1], tmp); col[k * 3] = tmp.r; col[k * 3 + 1] = tmp.g; col[k * 3 + 2] = tmp.b; }
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return geo;
}
const matMark = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.97, metalness: 0, map: texMark });
const CORE = [-1420, 1480, -520, 1240];

// =====================================================================
// Byggare av geometri
// =====================================================================
class MB {
  constructor() { this.p = []; this.n = []; this.uv = []; this.c = []; this.owner = []; }
  tri(a, b, c, col, ua, ub, uc, owner, hint) {
    let ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    if (hint && nx * hint[0] + ny * hint[1] + nz * hint[2] < 0) { [b, c] = [c, b]; [ub, uc] = [uc, ub]; nx = -nx; ny = -ny; nz = -nz; }
    const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
    for (const [v, u] of [[a, ua], [b, ub], [c, uc]]) { this.p.push(v[0], v[1], v[2]); this.n.push(nx, ny, nz); this.uv.push(u ? u[0] : 0.05, u ? u[1] : 0.05); this.c.push(col.r, col.g, col.b); }
    this.owner.push(owner);
  }
  quad(a, b, c, d, col, ua, ub, uc, ud, owner, hint) { this.tri(a, b, c, col, ua, ub, uc, owner, hint); this.tri(a, c, d, col, ua, uc, ud, owner, hint); }
  geometry() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2)); g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    return g;
  }
}
function bake(parts) {
  let n = 0; const gs = parts.map(p => { const g = (p.g.index ? p.g.toNonIndexed() : p.g.clone()); g.applyMatrix4(p.m); n += g.attributes.position.count; return g; });
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), col = new Float32Array(n * 3); let o = 0;
  gs.forEach((g, k) => {
    const cnt = g.attributes.position.count; pos.set(g.attributes.position.array, o * 3); nor.set(g.attributes.normal.array, o * 3);
    const c = parts[k].c; for (let i = 0; i < cnt; i++) { col[(o + i) * 3] = c.r; col[(o + i) * 3 + 1] = c.g; col[(o + i) * 3 + 2] = c.b; }
    o += cnt; g.dispose();
  });
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3)); out.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); out.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return out;
}
const M4 = (x = 0, y = 0, z = 0, ry = 0, sx = 1, sy = 1, sz = 1, rx = 0, rz = 0) => new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz, 'YXZ')), new THREE.Vector3(sx, sy, sz));
function ribbon(pts, latA, latB, yfn, opts = {}) {
  if (latA < latB && !opts.keepNormals) { [latA, latB] = [latB, latA]; opts = { ...opts, uA: opts.uB, uB: opts.uA, yA: opts.yB, yB: opts.yA }; }
  const pos = [], uv = [], idx = []; let vi = 0; let prevOk = false;
  const vScale = opts.vScale || 6; const ok = opts.filter || (() => true);
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i]; const mm = p.m || 1; const nx = -p.tz * mm, nz = p.tx * mm;
    const ax = p.x + nx * latA, az = p.z + nz * latA, bx = p.x + nx * latB, bz = p.z + nz * latB;
    const good = ok(i, p);
    const ya = opts.yA ? opts.yA(ax, az, i, p) : yfn(ax, az, i, p), yb = opts.yB ? opts.yB(bx, bz, i, p) : yfn(bx, bz, i, p);
    pos.push(ax, ya, az, bx, yb, bz); uv.push(opts.uA ?? 0, p.s / vScale, opts.uB ?? 1, p.s / vScale);
    if (i > 0 && good && prevOk) { const a = vi - 2, b = vi - 1, c = vi, d = vi + 1; idx.push(a, c, b, b, c, d); }
    prevOk = good; vi += 2;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx); g.computeVertexNormals();
  if (!opts.keepNormals) { const n = g.attributes.normal.array; for (let i = 0; i < n.length; i += 3) if (n[i + 1] < 0) { n[i] *= -1; n[i + 1] *= -1; n[i + 2] *= -1; } }
  return g;
}
function mergeGeos(list) {
  list = list.filter(g => g && g.attributes.position.count > 0);
  let nv = 0, ni = 0; for (const g of list) { nv += g.attributes.position.count; ni += g.index ? g.index.count : 0; }
  const pos = new Float32Array(nv * 3), nor = new Float32Array(nv * 3), uv = new Float32Array(nv * 2), idx = new Uint32Array(ni); let vo = 0, io = 0;
  for (const g of list) {
    pos.set(g.attributes.position.array, vo * 3); nor.set(g.attributes.normal.array, vo * 3); if (g.attributes.uv) uv.set(g.attributes.uv.array, vo * 2);
    if (g.index) { const a = g.index.array; for (let i = 0; i < a.length; i++) idx[io + i] = a[i] + vo; io += a.length; }
    vo += g.attributes.position.count; g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3)); out.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); out.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); out.setIndex(new THREE.BufferAttribute(idx, 1));
  return out;
}
// Polygon som draperas över marken (trianguleras och delas tills kanterna är korta)
function polyDecal(poly, yfn, maxEdge = 5, uvScale = 8, hal = false) {
  const contour = poly.map(p => new THREE.Vector2(p[0], p[1]));
  let tris;
  try { tris = THREE.ShapeUtils.triangulateShape(contour, []); } catch (e) { return null; }
  const out = [];
  const split = (a, b, c, depth) => {
    const l1 = Math.hypot(a[0] - b[0], a[1] - b[1]), l2 = Math.hypot(b[0] - c[0], b[1] - c[1]), l3 = Math.hypot(c[0] - a[0], c[1] - a[1]);
    if (depth > 5 || Math.max(l1, l2, l3) <= maxEdge) { if (hal && (iGangDike(a[0], a[1]) || iGangDike(b[0], b[1]) || iGangDike(c[0], c[1]))) return; out.push(a, b, c); return; }
    const ab = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], bc = [(b[0] + c[0]) / 2, (b[1] + c[1]) / 2], ca = [(c[0] + a[0]) / 2, (c[1] + a[1]) / 2];
    split(a, ab, ca, depth + 1); split(ab, b, bc, depth + 1); split(ca, bc, c, depth + 1); split(ab, bc, ca, depth + 1);
  };
  for (const [i, j, k] of tris) {
    let a = poly[i], b = poly[j], c = poly[k];
    const cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    if (cr > 0) [b, c] = [c, b]; // uppåtvänd
    split(a, b, c, 0);
  }
  const pos = new Float32Array(out.length * 3), uv = new Float32Array(out.length * 2);
  out.forEach((p, i) => { pos[i * 3] = p[0]; pos[i * 3 + 1] = yfn(p[0], p[1]); pos[i * 3 + 2] = p[1]; uv[i * 2] = p[0] / uvScale; uv[i * 2 + 1] = p[1] / uvScale; });
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); g.computeVertexNormals();
  const n = g.attributes.normal.array; for (let i = 0; i < n.length; i += 3) if (n[i + 1] < 0) { n[i] *= -1; n[i + 1] *= -1; n[i + 2] *= -1; }
  return g;
}
function nonIndexedMerge(list) { return mergeGeos(list.filter(Boolean).map(g => { if (!g.index) { const n = g.attributes.position.count; const idx = []; for (let i = 0; i < n; i++) idx.push(i); g.setIndex(idx); } return g; })); }

// =====================================================================
// Material
// =====================================================================
const world = { hus: [], pickables: [] };
const matAsfalt = new THREE.MeshStandardMaterial({ map: texAsfalt, roughness: 0.92, metalness: 0, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
const matTrott = new THREE.MeshStandardMaterial({ map: texTrottoar, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
const matGang = new THREE.MeshStandardMaterial({ map: texTrottoar, color: 0xc9c6bd, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
const matGrus = new THREE.MeshStandardMaterial({ map: texMark, color: 0xa89a7c, roughness: 1, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
const matLinje = new THREE.MeshStandardMaterial({ color: 0xf2f0e6, roughness: 0.6, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
const matSten = new THREE.MeshStandardMaterial({ map: texSten, roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
const matBetong = new THREE.MeshStandardMaterial({ color: 0xa5a29a, roughness: 0.9, side: THREE.DoubleSide });
const matVagg = new THREE.MeshStandardMaterial({ vertexColors: true, map: texFasad, roughness: 0.85, metalness: 0 });
matVagg.onBeforeCompile = (sh) => {
  sh.fragmentShader = sh.fragmentShader.replace('#include <map_fragment>', '').replace('#include <color_fragment>', `
      vec4 fas = texture2D( map, vMapUv );
      vec3 wallc = diffuseColor.rgb * vColor.rgb * fas.r;
      vec3 winc = vec3(0.03,0.045,0.06) + fas.b * vec3(0.92,0.93,0.95);
      diffuseColor.rgb = mix(wallc, winc, fas.g);`);
};
const matTak = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75, metalness: 0.05 });
const matDetalj = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.1 });
const matVattenYta = new THREE.MeshStandardMaterial({ color: 0x3e6a78, roughness: 0.1, metalness: 0.05, polygonOffset: true, polygonOffsetFactor: -2 });

// =====================================================================
// Järnväg
// =====================================================================
const railTracks = []; const railIdx = new SegIndex(20);
function trackProfile(sm, bro) {
  const raw = sm.map(p => { const h = heightNC(p.x, p.z); const overWater = waterSD(p.x, p.z) < 4; return (bro && overWater) || h < VATTEN + 1 ? Math.max(h + 0.45, VATTEN + 3.6) : h + 0.45; });
  return raw.map((v, i) => { let s = 0, n = 0; for (let k = -8; k <= 8; k++) { const j = clamp(i + k, 0, raw.length - 1); s += raw[j]; n++; } return Math.max(s / n, raw[i] - 0.15); });
}
function railBedNear(x, z, r = 6) {
  let best = null; railIdx.near(x, z, r, (sg) => { const [d, t] = segDist(x, z, sg.ax, sg.az, sg.bx, sg.bz); if (d < r && (!best || d < best.d)) { const tr = sg.data.tr; best = { d, y: lerp(tr.bed[sg.data.i], tr.bed[sg.data.i + 1], t) }; } });
  return best ? best.y : null;
}
function prepRail() {
  for (const sp of K.jarnvag.spar) {
    if (sp.pts.length < 2) continue;
    const sm = resample(sp.pts, 3); const bed = trackProfile(sm, sp.bro);
    const tr = { sm, bed, sido: sp.sido, bro: sp.bro }; railTracks.push(tr);
    for (let i = 0; i < sm.length - 1; i++) railIdx.add(sm[i].x, sm[i].z, sm[i + 1].x, sm[i + 1].z, { tr, i });
  }
  railIdx.done();
}
const nearCarve = (x, z, r) => carves.some(c => Math.hypot(x - c.cx, z - c.cz) < r);
function buildRailway() {
  const matBallast = new THREE.MeshStandardMaterial({ color: 0x75695e, roughness: 1 });
  const matBank = new THREE.MeshStandardMaterial({ color: 0x6b6a4a, roughness: 1, side: THREE.DoubleSide });
  const matRals = new THREE.MeshStandardMaterial({ color: 0x8d8a86, metalness: 0.75, roughness: 0.35 });
  const ball = [], sides = [], rals = [];
  let sleepers = [];
  for (const tr of railTracks) {
    const { sm, bed } = tr; const inside = (p) => inRam(p.x, p.z, 900);
    const over = (i) => tr.bro && (waterSD(sm[i].x, sm[i].z) < 6 || nearCarve(sm[i].x, sm[i].z, 14));
    ball.push(ribbon(sm, 2.4, -2.4, (x, z, i) => bed[i] - 0.02, { filter: (i, p) => inside(p) }));
    for (const sgn of [1, -1]) sides.push(ribbon(sm, sgn * 2.4, sgn * 5.6, null, { yA: (x, z, i) => bed[i] - 0.02, yB: (x, z) => H(x, z) - 0.4, filter: (i, p) => inside(p) && !over(i) && !nearCarve(p.x, p.z, 16), keepNormals: true }));
    for (const rl of [-0.72, 0.72]) rals.push(ribbon(sm, rl + 0.045, rl - 0.045, (x, z, i) => bed[i] + 0.33, { filter: (i, p) => inside(p) }));
    for (let i = 0; i < sm.length - 1; i++) {
      const a = sm[i]; if (!inRam(a.x, a.z, 300)) continue; const L = sm[i + 1].s - a.s;
      for (let s = 0; s < L; s += 0.65) { const t = s / L; sleepers.push([lerp(a.x, sm[i + 1].x, t), lerp(bed[i], bed[i + 1], t) + 0.2, lerp(a.z, sm[i + 1].z, t), Math.atan2(a.tx, a.tz)]); }
    }
  }
  const mB = new THREE.Mesh(mergeGeos(ball), matBallast); mB.receiveShadow = true; scene.add(mB);
  const mS = new THREE.Mesh(mergeGeos(sides), matBank); mS.receiveShadow = true; scene.add(mS);
  scene.add(new THREE.Mesh(mergeGeos(rals), matRals));
  const sMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(2.6, 0.16, 0.26), new THREE.MeshStandardMaterial({ color: 0x6d675f, roughness: 1 }), sleepers.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), one = new THREE.Vector3(1, 1, 1), v = new THREE.Vector3();
  sleepers.forEach(([x, y, z, a], i) => { q.setFromAxisAngle(up, a); m.compose(v.set(x, y, z), q, one); sMesh.setMatrixAt(i, m); });
  sMesh.receiveShadow = true; sMesh.frustumCulled = false; scene.add(sMesh);
  // kontaktledning längs huvudspåren
  const stolpar = [];
  for (const tp of [tagA, tagB]) {
    const other = tp === tagA ? tagB : tagA;
    for (let i = 0; i < tp.sm.length; i += 18) {
      const p = tp.sm[i]; if (!inRam(p.x, p.z, 200) || waterSD(p.x, p.z) < 6) continue;
      const o = nearestOnPolyline(other.sm, p.x, p.z); const side = o ? Math.sign((o.cx - p.x) * -p.tz + (o.cz - p.z) * p.tx) || 1 : 1;
      const lat = -side * 3.4; const bx = p.x - p.tz * lat, bz = p.z + p.tx * lat; const y = tp.bed[i]; const ang = Math.atan2(p.tx, p.tz);
      stolpar.push({ g: new THREE.BoxGeometry(0.3, 8, 0.3), m: M4(bx, y + 4, bz, ang), c: C('#5d6166') });
      stolpar.push({ g: new THREE.BoxGeometry(4.2, 0.15, 0.15), m: M4(p.x - p.tz * lat * 0.5, y + 7.2, p.z + p.tx * lat * 0.5, ang + Math.PI / 2), c: C('#5d6166') });
    }
    const pts = []; for (let i = 0; i < tp.sm.length; i += 2) { const p = tp.sm[i]; if (!inRam(p.x, p.z, 200)) continue; pts.push(new THREE.Vector3(p.x, tp.bed[i] + 6.0, p.z)); }
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x2a2a2a })));
  }
  const mSt = new THREE.Mesh(bake(stolpar), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.4 })); mSt.castShadow = true; scene.add(mSt);
  // perronger
  const tops = [], walls = [];
  for (const pr of K.jarnvag.perronger) {
    const poly = pr.poly; if (poly.length < 3) continue;
    const c = poly.reduce((a, p) => [a[0] + p[0] / poly.length, a[1] + p[1] / poly.length], [0, 0]);
    const rb = pr.buss ? null : railBedNear(c[0], c[1], 25);
    const top = rb !== null ? rb + 0.6 : null;
    const yfn = (x, z) => top !== null ? top : H(x, z) + 0.18;
    tops.push(polyDecal(poly, yfn, 6, 2));
    if (top !== null) for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute([a[0], top, a[1], b[0], top, b[1], b[0], heightNC(b[0], b[1]) - 0.3, b[1], a[0], heightNC(a[0], a[1]) - 0.3, a[1]], 3)); g.setIndex([0, 1, 2, 0, 2, 3]); g.computeVertexNormals(); walls.push(g); }
  }
  const mp = new THREE.Mesh(nonIndexedMerge(tops), new THREE.MeshStandardMaterial({ map: texTrottoar, color: 0xd8d6d0, roughness: 0.9 })); mp.receiveShadow = true; scene.add(mp);
  if (walls.length) scene.add(new THREE.Mesh(mergeGeos(walls), matBetong));
  // broar: över vatten och viadukten över Mariefredsvägen
  const parts = [];
  for (const tr of railTracks) {
    if (!tr.bro) continue;
    for (let i = 0; i < tr.sm.length - 1; i++) {
      const p = tr.sm[i]; const ang = Math.atan2(p.tx, p.tz); const y = tr.bed[i];
      if (waterSD(p.x, p.z) < 6) {
        parts.push({ g: new THREE.BoxGeometry(5.6, 1.4, 3.2), m: M4(p.x, y - 0.75, p.z, ang), c: C('#8f8b84') });
        for (const sgn of [-1, 1]) parts.push({ g: new THREE.BoxGeometry(0.35, 1.0, 3.2), m: M4(p.x - p.tz * sgn * 2.8, y + 0.5, p.z + p.tx * sgn * 2.8, ang), c: C('#47566a') });
        if (i % 5 === 0) parts.push({ g: new THREE.BoxGeometry(4.5, y - (VATTEN - 4), 1.8), m: M4(p.x, (y + VATTEN - 4) / 2 - 0.7, p.z, ang), c: C('#7f7b74') });
      }
    }
  }
  for (const c of carves) {
    if (c.gang) continue; const rb = railBedNear(c.cx, c.cz, 12); if (rb === null) continue;
    let bt = null; railIdx.near(c.cx, c.cz, 12, (sg) => { if (!bt) bt = sg; });
    const ang = bt ? Math.atan2(bt.bx - bt.ax, bt.bz - bt.az) : 0;
    parts.push({ g: new THREE.BoxGeometry(7, 1.5, 20), m: M4(c.cx, rb - 0.8, c.cz, ang), c: C('#a9a59c') });
    const r = c.pts[Math.floor(c.pts.length / 2)];
    for (const sgn of [-1, 1]) {
      const off = 7.2; const ax = c.cx - r.tz * sgn * off, az = c.cz + r.tx * sgn * off; const gy = H(ax, az) - 0.6;
      parts.push({ g: new THREE.BoxGeometry(1.8, rb - 1.5 - gy, 10), m: M4(ax, (rb - 1.5 + gy) / 2, az, Math.atan2(r.tx, r.tz)), c: C('#9d998f') });
    }
  }
  if (parts.length) { const mb = new THREE.Mesh(bake(parts), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85 })); mb.castShadow = true; mb.receiveShadow = true; scene.add(mb); }
}
// tågens körspår
let tagA, tagB;
function prepTrainPaths() {
  const mk = (pts) => { const sm = resample(pts, 3); return { sm, bed: trackProfile(sm, true), total: sm[sm.length - 1].s }; };
  tagA = mk(K.jarnvag.tagA); tagB = mk(K.jarnvag.tagB);
}
function trackPoint(tp, s, lat = 0) {
  const sm = tp.sm; let lo = 0, hi = sm.length - 1; s = clamp(s, 0, sm[hi].s);
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (sm[mid].s < s) lo = mid; else hi = mid; }
  const a = sm[lo], b = sm[hi]; const t = (s - a.s) / ((b.s - a.s) || 1);
  return { x: lerp(a.x, b.x, t), z: lerp(a.z, b.z, t), y: lerp(tp.bed[lo], tp.bed[hi], t) };
}

// =====================================================================
// Gator, broar, trappor
// =====================================================================
const roadStyle = (g) => {
  const grus = /gravel|ground|dirt|unpaved|compacted|earth|sand|grass|wood/.test(g.yta || '');
  if (['footway', 'cycleway', 'path', 'track', 'bridleway', 'pedestrian'].includes(g.typ)) return { mat: grus || g.typ === 'path' || g.typ === 'track' ? 'grus' : g.typ === 'pedestrian' ? 'sten' : 'gang', yo: 0.05 };
  const rk = g.typ === 'secondary' || g.typ === 'primary' ? 3 : g.typ === 'service' ? 1 : 2;
  return { mat: grus ? 'grus' : 'asfalt', yo: 0.07 + rk * 0.025 };
};
const roadYfn = new Map();
function prepRoadHeights() {
  // broar: rak profil mellan ändarna, minst 6,4 m över rälsen där bron korsar spår
  const ramps = new Map(); const keyOf = (p) => Math.round(p[0] * 5) + ',' + Math.round(p[1] * 5);
  for (const g of gator) {
    if (!g.bro) continue; const st = roadStyle(g); const a = g.sm[0], b = g.sm[g.sm.length - 1]; const L = b.s || 1;
    const ya = H(a.x, a.z) + st.yo, yb = H(b.x, b.z) + st.yo; let need = -1e9;
    for (const p of g.sm) { const rb = railBedNear(p.x, p.z, 4); if (rb !== null) need = Math.max(need, rb + 6.6); }
    const deck = (s) => Math.max(lerp(ya, yb, s / L), need);
    roadYfn.set(g.id, (x, z, i, p) => deck(p.s));
    g.deck = deck;
    if (need > -1e8) { ramps.set(keyOf(g.pts[0]), deck(0)); ramps.set(keyOf(g.pts[g.pts.length - 1]), deck(L)); }
  }
  for (const g of gator) {
    if (g.bro) continue; const st = roadStyle(g); const L = g.sm[g.sm.length - 1].s || 1;
    const r0 = ramps.get(keyOf(g.pts[0])), r1 = ramps.get(keyOf(g.pts[g.pts.length - 1]));
    if (r0 === undefined && r1 === undefined) continue;
    const b0 = H(g.sm[0].x, g.sm[0].z) + st.yo, b1 = H(g.sm[g.sm.length - 1].x, g.sm[g.sm.length - 1].z) + st.yo;
    g.ramp = true;
    roadYfn.set(g.id, (x, z, i, p) => { let y = H(x, z) + st.yo; const s = p.s; if (r0 !== undefined) y = Math.max(y, H(x, z) + st.yo + (r0 - b0) * (1 - Math.min(1, s / Math.min(L, 45)))); if (r1 !== undefined) y = Math.max(y, H(x, z) + st.yo + (r1 - b1) * (1 - Math.min(1, (L - s) / Math.min(L, 45)))); return y; });
  }
}
function roadY(g, x, z, i, p) { const f = roadYfn.get(g.id); return f ? f(x, z, i, p) : H(x, z) + roadStyle(g).yo; }
const utanTrott = (x, z) => ((K.detaljer && K.detaljer.utanTrottoar) || []).some(pl => pointInPoly(x, z, pl));
function buildRoads() {
  const lists = { asfalt: [], gang: [], grus: [], sten: [] }; const trott = [], linjer = [], murar = [], racken = [];
  const nearOther = (g, p, lat, pad = 0.6) => {
    const x = p.x - p.tz * lat, z = p.z + p.tx * lat; let bad = false;
    roadIndex.near(x, z, 14, (sg) => { const o = sg.data.g; if (bad || o === g || !o.bil) return; const d = segDist(x, z, sg.ax, sg.az, sg.bx, sg.bz)[0]; if (d < o.bredd / 2 + pad) bad = true; });
    return bad;
  };
  for (const g of gator) {
    if (g.tunnel || g.sm.length < 2) continue;
    if (!g.sm.some(p => inRam(p.x, p.z, 400))) continue;
    const st = roadStyle(g); const half = g.bredd / 2;
    const yfn = (x, z, i, p) => roadY(g, x, z, i, p);
    lists[st.mat].push(ribbon(g.sm, half, -half, yfn, { uA: 0, uB: g.bredd / 6, vScale: 6 }));
    if (g.trottoar > 0) for (const sgn of [1, -1]) {
      const a = sgn * half, b = sgn * (half + g.trottoar);
      trott.push(ribbon(g.sm, a, b, (x, z, i, p) => yfn(x, z, i, p) + 0.09, { filter: (i, p) => !nearOther(g, p, sgn * (half + g.trottoar * 0.5)) && !utanTrott(p.x - p.tz * sgn * (half + g.trottoar * 0.5), p.z + p.tx * sgn * (half + g.trottoar * 0.5)), uA: 0, uB: g.trottoar / 1.6, vScale: 1.6 }));
    }
    if (g.typ === 'secondary' || g.typ === 'primary') linjer.push(ribbon(g.sm, 0.08, -0.08, (x, z, i, p) => yfn(x, z, i, p) + 0.03, { filter: (i, p) => (p.s % 12) < 3.2 && !nearOther(g, p, 0, 1.5) && !nearOther(g, p, 3.5) && !nearOther(g, p, -3.5) }));
    if (g.bro || g.ramp) {
      const hi = (i, p) => yfn(p.x, p.z, i, p) - H(p.x, p.z) > 0.7;
      for (const sgn of [1, -1]) {
        murar.push(ribbon(g.sm, sgn * (half + 0.05), sgn * (half + 0.05), null, { yA: (x, z, i, p) => yfn(x, z, i, p) + (g.bro ? 0.9 : 0.05), yB: (x, z, i, p) => g.bro ? yfn(x, z, i, p) - 1.0 : H(x, z) - 0.3, filter: (i, p) => g.bro || hi(i, p), keepNormals: true }));
      }
      if (g.bro) murar.push(ribbon(g.sm, half + 0.05, -half - 0.05, (x, z, i, p) => yfn(x, z, i, p) - 1.0, { keepNormals: true }));
    }
  }
  const add = (geos, mat) => { const gg = mergeGeos(geos); if (!gg.attributes.position.count) return; const m = new THREE.Mesh(gg, mat); m.receiveShadow = true; scene.add(m); };
  add(lists.asfalt, matAsfalt); add(lists.gang, matGang); add(lists.grus, matGrus); add(lists.sten, matSten); add(trott, matTrott); add(linjer, matLinje);
  if (murar.length) { const m = new THREE.Mesh(mergeGeos(murar), matBetong); m.castShadow = true; m.receiveShadow = true; scene.add(m); }
}
function buildSteps(pts, width, bi) {
  const iVag = (p) => { let bad = false; roadIndex.near(p.x, p.z, 12, (sg) => { const o = sg.data.g; if (bad || !o.bil || o.tunnel) return; if (segDist(p.x, p.z, sg.ax, sg.az, sg.bx, sg.bz)[0] < o.bredd / 2 + (o.trottoar || 0) + width / 2 + 0.2) bad = true; }); return bad; };
  const smp = resample(pts, 0.32).filter(p => !iVag(p)); if (smp.length < 2) return null;
  const a = smp[0], b = smp[smp.length - 1]; const up = H(b.x, b.z) >= H(a.x, a.z);
  const list = up ? smp : smp.slice().reverse();
  const im = new THREE.InstancedMesh(new THREE.BoxGeometry(width, 0.7, 0.34), new THREE.MeshStandardMaterial({ color: 0x9a948a, roughness: 0.95 }), list.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), ax = new THREE.Vector3(0, 1, 0), one = new THREE.Vector3(1, 1, 1);
  let prev = -1e9; let top = 0; const rail = [];
  list.forEach((p, i) => {
    let y = Math.max(H(p.x, p.z) + 0.12, prev); prev = y; top = y;
    q.setFromAxisAngle(ax, Math.atan2(p.tx, p.tz)); m.compose(new THREE.Vector3(p.x, y - 0.35, p.z), q, one); im.setMatrixAt(i, m);
    if (i % 6 === 0) for (const sg of [-1, 1]) rail.push({ g: new THREE.BoxGeometry(0.06, 1.0, 0.06), m: M4(p.x - p.tz * sg * (width / 2 + 0.05), y + 0.5, p.z + p.tx * sg * (width / 2 + 0.05)), c: C('#2c2f33') });
  });
  im.castShadow = true; im.receiveShadow = true; scene.add(im);
  if (bi !== undefined) { im.userData.bidx = bi; world.pickables.push(im); }
  if (rail.length) { const mr = new THREE.Mesh(bake(rail), matDetalj); if (bi !== undefined) { mr.userData.bidx = bi; world.pickables.push(mr); } scene.add(mr); }
  return top;
}

// =====================================================================
// Ytor: torg, parkeringar, planer, bryggor, dammar
// =====================================================================
const flaggor = [];
function buildYtor() {
  const groups = { torg: [], parkering: [], plan: [], lekplats: [], brygga: [], gras: [], skolgard: [] };
  const fontaner = [];
  for (const y of K.ytor) {
    if (!y.poly.some(p => inRam(p[0], p[1], 50))) continue;
    if (y.typ === 'fontan') { fontaner.push(y); continue; }
    const yo = { torg: 0.22, parkering: 0.115, plan: 0.06, lekplats: 0.07, brygga: 0.4, gras: 0.26, skolgard: 0.12 }[y.typ] ?? 0.1;
    const yfn = y.typ === 'brygga' ? (x, z) => Math.max(H(x, z), VATTEN) + yo : (x, z) => H(x, z) + yo;
    groups[y.typ]?.push(polyDecal(y.poly, yfn, 5, y.typ === 'torg' ? 6 : 8, true));
  }
  const add = (list, mat) => { const g = nonIndexedMerge(list); if (!g.attributes.position.count) return; const m = new THREE.Mesh(g, mat); m.receiveShadow = true; scene.add(m); };
  add(groups.torg, matSten); add(groups.parkering, matAsfalt); add(groups.skolgard, matAsfalt);
  add(groups.plan, new THREE.MeshStandardMaterial({ color: 0x5f8f45, roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -1 }));
  add(groups.lekplats, new THREE.MeshStandardMaterial({ color: 0xc8b48a, roughness: 1, polygonOffset: true, polygonOffsetFactor: -1 }));
  add(groups.brygga, new THREE.MeshStandardMaterial({ color: 0x8d6e4c, roughness: 0.9 }));
  add(groups.gras, new THREE.MeshStandardMaterial({ map: texMark, color: 0x7aa84a, roughness: 1, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }));
  // dammar
  add(K.vatten.dammar.filter(p => p.some(q => inRam(q[0], q[1], 300))).map(p => polyDecal(p, (x, z) => H(x, z) + 0.12, 6)), matVattenYta);
  // bryggor (linjer)
  const br = []; for (const pts of K.bryggor) { if (pts.length < 2) continue; br.push(ribbon(resample(pts, 1), 0.9, -0.9, (x, z) => Math.max(H(x, z), VATTEN) + 0.45)); }
  add(br, new THREE.MeshStandardMaterial({ color: 0x8d6e4c, roughness: 0.9 }));
  // fontän + bänkar + lyktor på Stora Torget
  const parts = [];
  for (const f of fontaner) {
    const [cx, cz, b, d] = f.rekt; const r = Math.max(2.2, Math.min(b, d) / 2); const fy = H(cx, cz) + 0.22;
    parts.push({ g: new THREE.CylinderGeometry(r, r + 0.2, 0.7, 32), m: M4(cx, fy + 0.35, cz), c: C('#a9a49a') });
    parts.push({ g: new THREE.CylinderGeometry(r - 0.35, r - 0.35, 0.1, 32), m: M4(cx, fy + 0.62, cz), c: C('#4f7f95') });
    parts.push({ g: new THREE.CylinderGeometry(0.3, 0.45, 2.2, 12), m: M4(cx, fy + 1.4, cz), c: C('#8f897d') });
    parts.push({ g: new THREE.SphereGeometry(0.6, 14, 10), m: M4(cx, fy + 2.7, cz), c: C('#8f897d') });
    for (let k = 0; k < 4; k++) {
      const a = k * Math.PI / 2 + Math.PI / 4;
      const lx = cx + Math.cos(a + Math.PI / 4) * (r + 7), lz = cz + Math.sin(a + Math.PI / 4) * (r + 7); const ly = H(lx, lz);
      parts.push({ g: new THREE.CylinderGeometry(0.08, 0.12, 4.5, 8), m: M4(lx, ly + 2.25, lz), c: C('#2f3236') });
      parts.push({ g: new THREE.SphereGeometry(0.35, 10, 8), m: M4(lx, ly + 4.6, lz), c: C('#f2ead2') });
    }
  }
  // bänkar och konstverk från OpenStreetMap
  for (const mb of K.moblering) {
    if (!inRam(mb.x, mb.z)) continue; const y = H(mb.x, mb.z) + 0.26;
    const nr = nearestRoad(mb.x, mb.z, 25); const ang = nr ? Math.atan2(nr.g.sm[nr.i + 1].x - nr.g.sm[nr.i].x, nr.g.sm[nr.i + 1].z - nr.g.sm[nr.i].z) + Math.PI / 2 : 0;
    if (mb.typ === 'bank') {
      parts.push({ g: new THREE.BoxGeometry(1.9, 0.08, 0.5), m: M4(mb.x, y + 0.45, mb.z, ang), c: C('#7a5536') });
      parts.push({ g: new THREE.BoxGeometry(1.9, 0.4, 0.07), m: M4(mb.x - Math.sin(ang) * 0.25, y + 0.75, mb.z - Math.cos(ang) * 0.25, ang), c: C('#7a5536') });
      for (const sx of [-0.8, 0.8]) parts.push({ g: new THREE.BoxGeometry(0.08, 0.45, 0.5), m: M4(mb.x + Math.cos(ang) * sx, y + 0.22, mb.z - Math.sin(ang) * sx, ang), c: C('#2f3236') });
    } else {
      parts.push({ g: new THREE.BoxGeometry(1.2, 0.5, 1.2), m: M4(mb.x, y + 0.25, mb.z), c: C('#8f897d') });
      parts.push({ g: new THREE.TorusKnotGeometry(0.55, 0.16, 48, 8), m: M4(mb.x, y + 1.35, mb.z, 0.6), c: C('#7c6a4f') });
    }
  }
  // fruktträd på gräsmattan mellan fontänen och stationshuset
  const fr = mulberry32(5);
  for (const [x, z] of K.frukttrad) {
    const y = H(x, z) + 0.26; const sc = 0.85 + fr() * 0.3;
    parts.push({ g: new THREE.CylinderGeometry(0.1, 0.14, 1.6 * sc, 7), m: M4(x, y + 0.8 * sc, z), c: C('#5a4636') });
    parts.push({ g: new THREE.IcosahedronGeometry(1.5 * sc, 1), m: M4(x, y + 2.3 * sc, z, fr() * 6, 1, 0.8, 1), c: C('#5e8f3a') });
    for (let k = 0; k < 9; k++) { const a = fr() * 6.28, e = (fr() - 0.3) * 1.1; const rr = 1.42 * sc; parts.push({ g: new THREE.SphereGeometry(0.11, 6, 5), m: M4(x + Math.cos(a) * Math.cos(e) * rr, y + 2.3 * sc + Math.sin(e) * rr * 0.8, z + Math.sin(a) * Math.cos(e) * rr), c: C(k % 3 ? '#c0302a' : '#d9b23a') }); }
  }
  if (parts.length) { const m = new THREE.Mesh(bake(parts), matDetalj); m.castShadow = true; m.receiveShadow = true; scene.add(m); }
  // parkerade bilar nära körsträckan
  const bilar = []; const pr = mulberry32(99); const farger = ['#b8b8b2', '#2c3e57', '#8a1c1c', '#e8e6e0', '#1f1f1f', '#5f7b8a', '#7a6a4a', '#3d5a3a', '#c9c4b8'];
  const rutt = K.korbar.rutter.flatMap(r => r.pts);
  const nearRutt = (x, z, r) => { for (const p of rutt) if (Math.abs(p[0] - x) < r && Math.abs(p[1] - z) < r) return true; return false; };
  const iVag = (x, z) => { const nr = nearestRoad(x, z, 12, g => g.bil); return !!nr && nr.d < nr.g.bredd / 2 + (nr.g.typ === 'service' ? 0.05 : 0.3); };
  // husens fotavtryck i ett rutnät så att inga bilar ställs inne i en byggnad
  const HC = 24, husGrid = new Map();
  const horn = (rk) => { const [x, z, b, d, rot] = rk; const c = Math.cos(rot), s = Math.sin(rot); const W = (lx, lz) => [x + lx * c - lz * s, z + lx * s + lz * c]; return [W(-b / 2, -d / 2), W(b / 2, -d / 2), W(b / 2, d / 2), W(-b / 2, d / 2)]; };
  for (const hh of K.hus) { if (hh.typ === 'trappa') continue; const P = hh.rekt ? horn(hh.rekt) : hh.poly; const bb = bbox(P);
    for (let i = Math.floor(bb[0] / HC); i <= Math.floor(bb[2] / HC); i++) for (let j = Math.floor(bb[1] / HC); j <= Math.floor(bb[3] / HC); j++) { const k = i + ',' + j; if (!husGrid.has(k)) husGrid.set(k, []); husGrid.get(k).push(P); } }
  const iHus = (x, z) => { const L = husGrid.get(Math.floor(x / HC) + ',' + Math.floor(z / HC)); return !!L && L.some(P => pointInPoly(x, z, P)); };
  const bilFri = (x, z, ang) => { const fx = Math.sin(ang), fz = Math.cos(ang); for (const [a, b] of [[0, 0], [2.3, 0.95], [2.3, -0.95], [-2.3, 0.95], [-2.3, -0.95], [0, 0.95], [0, -0.95]]) if (iHus(x + fx * a + fz * b, z + fz * a - fx * b)) return false; return true; };
  const bil = (x, z, ang, col) => { const yy = H(x, z);
    bilar.push({ g: new THREE.BoxGeometry(1.76, 0.72, 4.4), m: M4(x, yy + 0.66, z, ang), c: col });
    bilar.push({ g: new THREE.BoxGeometry(1.5, 0.5, 2.1), m: M4(x - Math.sin(ang) * 0.2, yy + 1.26, z - Math.cos(ang) * 0.2, ang), c: C('#3c4652') });
    bilar.push({ g: new THREE.BoxGeometry(1.42, 0.07, 1.7), m: M4(x - Math.sin(ang) * 0.3, yy + 1.54, z - Math.cos(ang) * 0.3, ang), c: col });
    bilar.push({ g: new THREE.BoxGeometry(1.7, 0.36, 3.6), m: M4(x, yy + 0.2, z, ang), c: C('#111') }); };
  for (const y of K.ytor) {
    if (y.typ !== 'parkering' || !y.rekt || y.ingaBilar) continue;
    const [cx, cz, b, d, rot] = y.rekt; if (!nearRutt(cx, cz, 320)) continue;
    const c = Math.cos(rot), s = Math.sin(rot);
    const long = b >= d; const L = long ? b : d, Wd = long ? d : b; // bilar ställs tvärs längdriktningen
    const ux = long ? [c, s] : [-s, c], uz = long ? [-s, c] : [c, s];
    // rader läggs där de faktiskt får plats: inom ytan, utanför körbanor och husväggar, utan att överlappa varandra
    const platser = []; const ang0 = Math.atan2(uz[0], uz[1]);
    const iYta = (x, z) => pointInPoly(x, z, y.poly);
    for (let lz = -Wd / 2 + 2.3; lz <= Wd / 2 - 2.3; lz += 0.8) for (let lx = -L / 2 + 1.3; lx <= L / 2 - 1.3; lx += 2.6) {
      if (platser.some(q => Math.abs(q[2] - lz) < 4.9 && Math.abs(q[3] - lx) < 2.5)) continue;
      const x = cx + ux[0] * lx + uz[0] * lz, z = cz + ux[1] * lx + uz[1] * lz;
      let ok = true; for (const [a, b] of [[0, 0], [2.1, 0.85], [2.1, -0.85], [-2.1, 0.85], [-2.1, -0.85]]) if (!iYta(x + uz[0] * a + ux[0] * b, z + uz[1] * a + ux[1] * b)) { ok = false; break; }
      if (!ok) continue;
      const ex = Math.sin(ang0) * 2.2, ez = Math.cos(ang0) * 2.2; if (iVag(x, z) || iVag(x + ex, z + ez) || iVag(x - ex, z - ez) || !bilFri(x, z, ang0)) continue;
      platser.push([x, z, lz, lx]);
    }
    for (const [x, z] of platser) { if (pr() > 0.6) continue; const ang = ang0 + (pr() < 0.5 ? Math.PI : 0); bil(x, z, ang, C(farger[Math.floor(pr() * farger.length)])); }
  }
  for (const [x, z, ang] of (K.detaljer && K.detaljer.parkeradeBilar) || []) { if (pr() > 0.8 || !bilFri(x, z, ang)) continue; bil(x, z, ang, C(farger[Math.floor(pr() * farger.length)])); }
  // målade parkeringsrutor
  { const q = []; for (const [x0, z0, x1, z1] of (K.detaljer && K.detaljer.parkeringslinjer) || []) { const L = Math.hypot(x1 - x0, z1 - z0) || 1; const nx = -(z1 - z0) / L * 0.06, nz = (x1 - x0) / L * 0.06;
      const P = (x, z) => [x, H(x, z) + 0.135, z]; q.push([P(x0 - nx, z0 - nz), P(x1 - nx, z1 - nz), P(x1 + nx, z1 + nz), P(x0 + nx, z0 + nz), [0, 0], [1, 0], [1, 1], [0, 1]]); }
    if (q.length) { const m = new THREE.Mesh(quadGeo(q), matLinje.clone()); m.material.side = THREE.DoubleSide; m.receiveShadow = true; scene.add(m); } }
  if (bilar.length) { const mb = new THREE.Mesh(bake(bilar), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.35, metalness: 0.3 })); mb.castShadow = true; mb.receiveShadow = true; scene.add(mb); }
}

// =====================================================================
// Byggnader
// =====================================================================
const KLASSNAMN = { villa: 'Villa / småhus', bod: 'Bod, garage eller förråd', flerbostad: 'Flerbostadshus', centrum: 'Centrumhus', affar: 'Affärshus', hall: 'Hall / verksamhet', radhus: 'Radhus', school: 'Skola', kindergarten: 'Förskola', sports_hall: 'Idrottshall', station: 'Stationshus', church: 'Kyrka', vattentorn_gammalt: 'Vattentorn', trappa: 'Trappa' };
const SPECIAL_ONLY = new Set(['vattentorn_gammalt', 'trappa', 'tak']);
function buildHouses() {
  const walls = new MB(), roofs = new MB(); const details = [], bandDelar = [];
  K.hus.forEach((h, bi) => {
    let cs, rk = h.rekt;
    if (rk) { const [x, z, b, d, rot] = rk; const c = Math.cos(rot), s = Math.sin(rot); const W = (lx, lz) => [x + lx * c - lz * s, z + lx * s + lz * c]; cs = [W(-b / 2, -d / 2), W(b / 2, -d / 2), W(b / 2, d / 2), W(-b / 2, d / 2)]; }
    else cs = h.poly;
    const step = Math.max(1, Math.floor(cs.length / 12));
    const gs = []; for (let i = 0; i < cs.length; i += step) gs.push(H(cs[i][0], cs[i][1])); gs.push(H(h.x, h.z));
    const gmin = Math.min(...gs), gmax = Math.max(...gs);
    let g0 = Math.min(gmax, gmin + 4) + 0.25; const y0 = gmin - 0.6;
    if (h.fasad && h.fasad.a) { const m = [(h.fasad.a[0] + h.fasad.b[0]) / 2, (h.fasad.a[1] + h.fasad.b[1]) / 2]; g0 = H(m[0] + (h.fasad.vag[0] - m[0]) * 0.05, m[1] + (h.fasad.vag[1] - m[1]) * 0.05) + 0.1; }
    const hojd = h.hojd || Math.max(1, h.van) * h.fh; const y1 = g0 + hojd;
    const info = { ...h, idx: bi, g0, gmin, y1, top: y1, corners: cs, b: rk ? rk[2] : null, d: rk ? rk[3] : null };
    world.hus.push(info);
    if (SPECIAL_ONLY.has(h.typ) || h.typ === 'station' || (h.fasad && h.fasad.typ === 'indiska')) { info.top = g0 + 6; return; }
    const wc = new THREE.Color(h.vagg); const fh = h.fh; const bay = h.typ === 'hall' ? 6 : 3.2;
    for (let i = 0; i < cs.length; i++) {
      const a = cs[i], b = cs[(i + 1) % cs.length]; const L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 0.05) continue;
      const hint = rk ? [(a[0] + b[0]) / 2 - rk[0], 0, (a[1] + b[1]) / 2 - rk[1]] : [b[1] - a[1], 0, -(b[0] - a[0])];
      const v0 = (y0 - g0) / fh, v1 = (y1 - g0) / fh; const uL = Math.max(1, Math.round(L / bay));
      if (h.utanFonster) { const F = [0.05, 0.02]; walls.quad([a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], y1, b[1]], [a[0], y1, a[1]], wc, F, F, F, F, bi, hint); continue; }
      walls.quad([a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], y1, b[1]], [a[0], y1, a[1]], wc, [0, v0], [uL, v0], [uL, v1], [0, v1], bi, hint);
    }
    const rc = new THREE.Color(h.takfarg); const UP = [0, 1, 0];
    // extra volymer (t.ex. högre lagerdel) och färgband runt fasaden
    for (const vo of h.volymer || []) {
      const vc = new THREE.Color(vo.vagg || h.vagg), vcs = vo.poly, vy1 = g0 + vo.h; let vx = 0, vz = 0; vcs.forEach(q => { vx += q[0]; vz += q[1]; }); vx /= vcs.length; vz /= vcs.length;
      for (let i = 0; i < vcs.length; i++) { const a = vcs[i], b = vcs[(i + 1) % vcs.length]; const L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 0.05) continue;
        const v0 = (y0 - g0) / fh, v1 = (vy1 - g0) / fh, uL = Math.max(1, Math.round(L / bay));
        walls.quad([a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], vy1, b[1]], [a[0], vy1, a[1]], vc, [0, v0], [uL, v0], [uL, v1], [0, v1], bi, [(a[0] + b[0]) / 2 - vx, 0, (a[1] + b[1]) / 2 - vz]); }
      let tr = []; try { tr = THREE.ShapeUtils.triangulateShape(vcs.map(q => new THREE.Vector2(q[0], q[1])), []); } catch (e) { }
      for (const [i, j, k] of tr) roofs.tri([vcs[i][0], vy1, vcs[i][1]], [vcs[j][0], vy1, vcs[j][1]], [vcs[k][0], vy1, vcs[k][1]], rc, null, null, null, bi, UP);
      details.push({ cs: vcs, y: vy1, c: vc.clone().multiplyScalar(0.78) }); info.top = Math.max(info.top, vy1);
    }
    for (const bd of h.band || []) { let cx = 0, cz = 0; cs.forEach(q => { cx += q[0]; cz += q[1]; }); cx /= cs.length; cz /= cs.length;
      for (let i = 0; i < cs.length; i++) { const a = cs[i], b = cs[(i + 1) % cs.length]; const L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 0.3) continue;
        const ux = (b[0] - a[0]) / L, uz = (b[1] - a[1]) / L; let nx = uz, nz = -ux; const mx = (a[0] + b[0]) / 2, mz = (a[1] + b[1]) / 2; if (nx * (mx - cx) + nz * (mz - cz) < 0) { nx = -nx; nz = -nz; }
        bandDelar.push({ g: new THREE.BoxGeometry(L + 0.1, bd.y1 - bd.y0, 0.05), m: M4(mx + nx * 0.035, g0 + (bd.y0 + bd.y1) / 2, mz + nz * 0.035, Math.atan2(-uz, ux)), c: C(bd.farg) }); } }
    if (!rk || h.tak === 'platt') {
      const contour = cs.map(p => new THREE.Vector2(p[0], p[1])); let tris = [];
      try { tris = THREE.ShapeUtils.triangulateShape(contour, []); } catch (e) { }
      for (const [i, j, k] of tris) roofs.tri([cs[i][0], y1, cs[i][1]], [cs[j][0], y1, cs[j][1]], [cs[k][0], y1, cs[k][1]], rc, null, null, null, bi, UP);
      details.push({ cs, y: y1, c: new THREE.Color(h.vagg).multiplyScalar(0.78) });
      return;
    }
    const [x, z, b, d, rot] = rk; const c = Math.cos(rot), s = Math.sin(rot);
    const W = (lx, lz) => [x + lx * c - lz * s, z + lx * s + lz * c];
    const o = 0.45; let along = b >= d; if (h.takAxel === 'kort') along = !along; const Ll = along ? b : d, Ww = along ? d : b;
    const P = (u, v, y) => { const lx = along ? u : v, lz = along ? v : u; const w = W(lx, lz); return [w[0], y, w[1]]; };
    if (h.tak === 'pulpet') {
      const rise = Ww * 0.16;
      roofs.quad(P(-Ll / 2 - o, -Ww / 2 - o, y1), P(Ll / 2 + o, -Ww / 2 - o, y1), P(Ll / 2 + o, Ww / 2 + o, y1 + rise), P(-Ll / 2 - o, Ww / 2 + o, y1 + rise), rc, null, null, null, null, bi, UP);
      for (const sg of [-1, 1]) walls.tri(P(sg * Ll / 2, -Ww / 2, y1), P(sg * Ll / 2, Ww / 2, y1), P(sg * Ll / 2, Ww / 2, y1 + rise), wc, null, null, null, bi, along ? [sg * c, 0, sg * s] : [-sg * s, 0, sg * c]);
      info.top = y1 + rise;
    } else if (h.tak === 'valm') {
      const pitch = h.typ === 'station' ? 0.8 : 0.5; const rise = Ww / 2 * pitch; const r = Math.max(0, Ll / 2 - Ww / 2); const yr = y1 + rise;
      roofs.quad(P(-Ll / 2 - o, -Ww / 2 - o, y1), P(Ll / 2 + o, -Ww / 2 - o, y1), P(r, 0, yr), P(-r, 0, yr), rc, null, null, null, null, bi, UP);
      roofs.quad(P(Ll / 2 + o, Ww / 2 + o, y1), P(-Ll / 2 - o, Ww / 2 + o, y1), P(-r, 0, yr), P(r, 0, yr), rc, null, null, null, null, bi, UP);
      roofs.tri(P(Ll / 2 + o, -Ww / 2 - o, y1), P(Ll / 2 + o, Ww / 2 + o, y1), P(r, 0, yr), rc, null, null, null, bi, UP);
      roofs.tri(P(-Ll / 2 - o, Ww / 2 + o, y1), P(-Ll / 2 - o, -Ww / 2 - o, y1), P(-r, 0, yr), rc, null, null, null, bi, UP);
      info.top = yr;
    } else {
      const pitch = h.typ === 'church' ? 0.95 : h.typ === 'hall' ? 0.28 : h.typ === 'radhus' ? 0.45 : 0.62;
      const rise = Ww / 2 * pitch; const yr = y1 + rise;
      roofs.quad(P(-Ll / 2 - o, -Ww / 2 - o, y1 - o * pitch), P(Ll / 2 + o, -Ww / 2 - o, y1 - o * pitch), P(Ll / 2 + o, 0, yr), P(-Ll / 2 - o, 0, yr), rc, null, null, null, null, bi, UP);
      roofs.quad(P(Ll / 2 + o, Ww / 2 + o, y1 - o * pitch), P(-Ll / 2 - o, Ww / 2 + o, y1 - o * pitch), P(-Ll / 2 - o, 0, yr), P(Ll / 2 + o, 0, yr), rc, null, null, null, null, bi, UP);
      for (const sg of [-1, 1]) { const out = along ? [sg * c, 0, sg * s] : [-sg * s, 0, sg * c]; walls.tri(P(sg * Ll / 2, -Ww / 2, y1), P(sg * Ll / 2, Ww / 2, y1), P(sg * Ll / 2, 0, yr), wc, [0.05, 0.02], [0.1, 0.02], [0.07, 0.02], bi, out); }
      info.top = yr;
    }
  });
  const mW = new THREE.Mesh(walls.geometry(), matVagg); mW.castShadow = true; mW.receiveShadow = true; mW.userData.owner = walls.owner; scene.add(mW);
  const mR = new THREE.Mesh(roofs.geometry(), matTak); mR.castShadow = true; mR.receiveShadow = true; mR.userData.owner = roofs.owner; scene.add(mR);
  world.pickables.push(mW, mR);
  // takkanter på platta tak
  const kant = new MB();
  for (const dt of details) for (let i = 0; i < dt.cs.length; i++) { const a = dt.cs[i], b = dt.cs[(i + 1) % dt.cs.length]; kant.quad([a[0], dt.y, a[1]], [b[0], dt.y, b[1]], [b[0], dt.y + 0.45, b[1]], [a[0], dt.y + 0.45, a[1]], dt.c, null, null, null, null, -1, [b[1] - a[1], 0, -(b[0] - a[0])]); }
  const mk = new THREE.Mesh(kant.geometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, side: THREE.DoubleSide })); mk.castShadow = true; scene.add(mk);
  if (bandDelar.length) { const mb = new THREE.Mesh(bake(bandDelar), matDetalj); mb.castShadow = true; mb.receiveShadow = true; scene.add(mb); }
  buildSpecials();
}
function addSpecial(parts, bi, mat = matDetalj, cast = true) { const m = new THREE.Mesh(bake(parts), mat); m.castShadow = cast; m.receiveShadow = true; m.userData.bidx = bi; scene.add(m); world.pickables.push(m); return m; }
function signMesh(tex, w, h, x, y, z, ry, bi) { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.6, side: THREE.DoubleSide })); m.position.set(x, y, z); m.rotation.y = ry; if (bi !== undefined) { m.userData.bidx = bi; world.pickables.push(m); } scene.add(m); return m; }
// ---- Frejaskolan, huvudentrén (modellerad efter foto) ----
const texFlygel = canvasTex(1024, 794, (g, W, Hh) => {
  const sx = W / 8, sy = Hh / 6.2; const Y = (m) => Hh - m * sy; // m över mark -> pixel
  g.fillStyle = '#d8c48a'; g.fillRect(0, 0, W, Hh);
  g.strokeStyle = 'rgba(150,125,70,0.35)'; g.lineWidth = 1;
  for (let m = 0.9, r = 0; m < 3.0; m += 0.08, r++) { g.beginPath(); g.moveTo(0, Y(m)); g.lineTo(W, Y(m)); g.stroke(); for (let x = (r % 2) * 16; x < W; x += 32) { g.beginPath(); g.moveTo(x, Y(m)); g.lineTo(x, Y(m + 0.08)); g.stroke(); } }
  g.fillStyle = '#a9b6be'; g.fillRect(0, Y(0.85), W, Y(0) - Y(0.85));
  const opening = (x0, x1, y0, y1, door) => {
    g.fillStyle = '#2f5f9f'; g.fillRect(x0 * sx, Y(y1), (x1 - x0) * sx, (y1 - y0) * sy);
    const f = 0.09; const gr = g.createLinearGradient(0, Y(y1), 0, Y(y0)); gr.addColorStop(0, '#3a4c5a'); gr.addColorStop(1, '#1d262e');
    g.fillStyle = gr; g.fillRect((x0 + f) * sx, Y(y1 - f), (x1 - x0 - 2 * f) * sx, (y1 - y0 - 2 * f) * sy);
    g.fillStyle = '#2f5f9f'; const mx = (x0 + x1) / 2; g.fillRect((mx - 0.04) * sx, Y(y1), 0.08 * sx, (y1 - y0) * sy);
    if (door) { g.fillStyle = '#c9cdd0'; g.fillRect((mx - 0.35) * sx, Y(1.15), 0.12 * sx, 0.3 * sy); }
  };
  opening(0.5, 2.3, 0.3, 2.6, false); opening(4.7, 6.3, 0.0, 2.45, true);
  g.fillStyle = '#f1f0ea'; g.fillRect(0, Y(4.15), W, (4.15 - 3.0) * sy);
  for (let x = 0.12; x < 8; x += 1.0) { const gr = g.createLinearGradient(0, Y(4.0), 0, Y(3.12)); gr.addColorStop(0, '#c7d6e2'); gr.addColorStop(1, '#7d93a6'); g.fillStyle = gr; g.fillRect(x * sx, Y(4.03), 0.82 * sx, 0.9 * sy); }
  g.fillStyle = '#e6e5df'; g.fillRect(0, Y(4.35), W, 0.2 * sy);
  g.fillStyle = '#a7b4bf'; g.fillRect(0, 0, W, Y(4.35));
  g.strokeStyle = 'rgba(110,125,138,0.7)'; g.lineWidth = 3; for (let x = 0; x < W; x += sx * 0.2) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, Y(4.35)); g.stroke(); }
  g.fillStyle = 'rgba(255,255,255,0.18)'; for (let x = 4; x < W; x += sx * 0.2) g.fillRect(x, 0, 4, Y(4.35));
}, true, true);
const texRodPanel = canvasTex(256, 512, (g, W, Hh) => { g.fillStyle = '#8e2a24'; g.fillRect(0, 0, W, Hh); g.strokeStyle = '#6e1f1a'; g.lineWidth = 3; for (let x = 0; x < W; x += 16) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, Hh); g.stroke(); } }, true, true);
const texTornFram = canvasTex(512, 1040, (g, W, Hh) => {
  const sx = W / 4.4, sy = Hh / 8.9; const Y = (m) => Hh - (m + 0.3) * sy;
  g.fillStyle = '#8e2a24'; g.fillRect(0, 0, W, Hh); g.strokeStyle = '#6e1f1a'; g.lineWidth = 3; for (let x = 0; x < W; x += 18) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, Hh); g.stroke(); }
  g.fillStyle = '#efefe9'; g.fillRect(0.75 * sx, Y(3.75), 2.9 * sx, 3.75 * sy + 0.3 * sy);
  const glas = (x0, x1, y0, y1) => { const gr = g.createLinearGradient(0, Y(y1), 0, Y(y0)); gr.addColorStop(0, '#4a5d6c'); gr.addColorStop(1, '#1d262e'); g.fillStyle = gr; g.fillRect(x0 * sx, Y(y1), (x1 - x0) * sx, (y1 - y0) * sy); };
  g.fillStyle = '#2f5f9f'; g.fillRect(0.95 * sx, Y(3.55), 2.5 * sx, 3.55 * sy);
  glas(1.05, 2.15, 0.08, 2.35); glas(2.25, 3.35, 0.08, 2.35); glas(1.05, 3.35, 2.5, 3.45);
  g.fillStyle = '#c9cdd0'; g.beginPath(); g.arc(2.0 * sx, Y(1.15), 0.18 * sx, 0, 7); g.lineWidth = 6; g.strokeStyle = '#c9cdd0'; g.stroke(); g.beginPath(); g.arc(2.4 * sx, Y(1.15), 0.18 * sx, 0, 7); g.stroke();
  for (const cy of [5.35, 6.75]) {
    g.fillStyle = '#f2f1ec'; g.beginPath(); g.arc(2.2 * sx, Y(cy), 0.66 * sx, 0, 7); g.fill();
    const gr = g.createRadialGradient(2.0 * sx, Y(cy + 0.2), 4, 2.2 * sx, Y(cy), 0.56 * sx); gr.addColorStop(0, '#e8eef2'); gr.addColorStop(1, '#8fa2b2');
    g.fillStyle = gr; g.beginPath(); g.arc(2.2 * sx, Y(cy), 0.55 * sx, 0, 7); g.fill();
    g.fillStyle = '#f2f1ec'; g.fillRect(1.6 * sx, Y(cy) - 3, 1.2 * sx, 6);
  }
}, true, false);
const texTegelGul = canvasTex(256, 256, (g, W, Hh) => { g.fillStyle = '#d6c48c'; g.fillRect(0, 0, W, Hh); g.strokeStyle = 'rgba(150,125,70,0.45)'; g.lineWidth = 1; for (let y = 0, r = 0; y < Hh; y += 8, r++) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); for (let x = (r % 2) * 12; x < W; x += 24) { g.beginPath(); g.moveTo(x, y); g.lineTo(x, y + 8); g.stroke(); } } }, true, true);
function buildFrejaskolan(h) {
  const F = h.fasad, bi = h.idx; const A = F.a, B = F.b; const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const dx = (B[0] - A[0]) / L, dz = (B[1] - A[1]) / L;
  let nx = -dz, nz = dx; if ((F.vag[0] - A[0]) * nx + (F.vag[1] - A[1]) * nz < 0) { nx = -nx; nz = -nz; }
  const P = (u, v) => [A[0] + dx * u + nx * v, A[1] + dz * u + nz * v];
  const ry = Math.atan2(nx, nz); const g = h.g0; const top = h.y1;
  const ue = (F.entre[0] - A[0]) * dx + (F.entre[1] - A[1]) * dz;
  const pick = (m) => { m.userData.bidx = bi; world.pickables.push(m); m.castShadow = true; m.receiveShadow = true; scene.add(m); return m; };
  const plane = (u0, u1, y0, y1, v, mat) => { const c = P((u0 + u1) / 2, v); const m = new THREE.Mesh(new THREE.PlaneGeometry(u1 - u0, y1 - y0), mat); m.position.set(c[0], (y0 + y1) / 2, c[1]); m.rotation.y = ry; return pick(m); };
  const parts = []; const box = (u, v, y, w, hgt, d, col, rx = 0) => { const c = P(u, v); parts.push({ g: new THREE.BoxGeometry(w, hgt, d), m: M4(c[0], y, c[1], ry, 1, 1, 1, rx), c: C(col) }); };
  // flyglar: gult tegel, blå fönster/dörrar, fönsterband och ljusblå plåt
  const wing = (u0, u1) => { const t = texFlygel.clone(); t.repeat.set((u1 - u0) / 8, 1); t.offset.set(u0 / 8, 0); t.needsUpdate = true; plane(u0, u1, g - 0.3, g + 5.9, 0.09, new THREE.MeshStandardMaterial({ map: t, roughness: 0.8 }));
    for (let u = u0 + 1.2; u < u1 - 0.5; u += 3.0) box(u, 0.6, g + 3.75, 0.1, 1.5, 0.1, '#4a3a2e', 0.76);
    box((u0 + u1) / 2, 0.75, g + 4.32, u1 - u0, 0.07, 1.25, '#4a3a2e');
    box((u0 + u1) / 2, 0.2, g + 6.0, u1 - u0, 0.25, 0.45, '#7f8c96'); };
  const eu0 = ue - 2.2, eu1 = ue + 2.2;
  wing(0, eu0 - 2.1); wing(eu1, Math.min(L, L - 0.2));
  // gul putsad del vänster om entrétornet
  box(eu0 - 1.05, 0.3, g + 3.3, 2.1, 7.2, 0.6, '#d9a640');
  box(eu0 - 1.05, 0.62, g + 3.4, 0.6, 3.6, 0.05, '#25303a');
  // rött entrétorn med runda fönster, skylt och blå dörrar
  { const c = P(ue, 1.2); const mat = new THREE.MeshStandardMaterial({ map: texRodPanel, roughness: 0.75 });
    const mats = [mat, mat, new THREE.MeshStandardMaterial({ color: 0x3a3532 }), mat, new THREE.MeshStandardMaterial({ map: texTornFram, roughness: 0.6 }), mat];
    const m = new THREE.Mesh(new THREE.BoxGeometry(4.4, 8.9, 2.5), mats); m.position.set(c[0], g - 0.3 + 4.45, c[1]); m.rotation.y = ry; pick(m);
    box(ue, 1.2, g + 8.65, 4.7, 0.22, 2.8, '#d9d6cf');
    const sp = P(ue, 2.47); signMesh(textTex('FREJASKOLAN', { bg: '#f4f3ee', fg: '#1b1b1b', border: '#2a2a2a', bw: 6, w: 768, h: 150, fit: true }), 2.8, 0.55, sp[0], g + 4.05, sp[1], ry, bi);
    box(ue + 1.05, 2.55, g + 2.7, 0.35, 0.35, 0.06, '#2f6fbf'); }
  // litet entrétak med blå kant på vänster flygel
  { const uc = eu0 - 12; box(uc, 0.1, g + 1.2, 1.1, 2.4, 0.05, '#2f5f9f');
    for (const sg of [-1, 1]) { const c = P(uc + sg * 0.66, 1.0); parts.push({ g: new THREE.BoxGeometry(1.45, 0.07, 2.0), m: M4(c[0], g + 3.15, c[1], ry, 1, 1, 1, 0, -sg * 0.45), c: C('#8a2a22') });
      const e = P(uc + sg * 1.3, 1.0); parts.push({ g: new THREE.BoxGeometry(0.08, 0.16, 2.05), m: M4(e[0], g + 2.86, e[1], ry), c: C('#2f6fbf') }); box(uc + sg * 1.25, 1.9, g + 1.4, 0.1, 2.8, 0.1, '#2f6fbf'); }
    box(uc, 1.95, g + 3.18, 2.7, 0.62, 0.06, '#8a2a22'); }
  // grå dörrar på höger flygel
  plane(L - 6.2, L - 3.8, g, g + 2.5, 0.12, new THREE.MeshStandardMaterial({ color: 0x9fb0c0, roughness: 0.6 }));
  // högt tegeltorn med utskjutande tak och mast
  { const t = F.torn; const tg = H(t[0], t[1]); const tt = texTegelGul.clone(); tt.repeat.set(1.2, 4); tt.needsUpdate = true;
    const m = new THREE.Mesh(new THREE.BoxGeometry(3.6, 15.5, 3.6), new THREE.MeshStandardMaterial({ map: tt, roughness: 0.85 })); m.position.set(t[0], Math.min(tg, g) - 0.3 + 7.75, t[1]); m.rotation.y = ry; pick(m);
    const ty = Math.min(tg, g) - 0.3 + 15.5;
    parts.push({ g: new THREE.BoxGeometry(4.8, 0.3, 4.8), m: M4(t[0], ty + 1.15, t[1], ry), c: C('#4a4f55') });
    for (const [a, b] of [[-1.9, -1.9], [1.9, -1.9], [-1.9, 1.9], [1.9, 1.9]]) { const ox = Math.cos(ry) * a + Math.sin(ry) * b, oz = -Math.sin(ry) * a + Math.cos(ry) * b; parts.push({ g: new THREE.BoxGeometry(0.12, 1.0, 0.12), m: M4(t[0] + ox, ty + 0.5, t[1] + oz, ry), c: C('#4a4f55') }); }
    parts.push({ g: new THREE.CylinderGeometry(0.05, 0.05, 3.2, 6), m: M4(t[0] + 1.2, ty + 2.9, t[1], 0), c: C('#9a9da0') });
    parts.push({ g: new THREE.BoxGeometry(0.7, 0.05, 0.05), m: M4(t[0] + 1.2, ty + 4.3, t[1], 0.4), c: C('#9a9da0') });
    h.top = Math.max(h.top, ty + 4.5); }
  // gården: picknickbord, unga träd med stöd, planteringslådor, pollare
  for (const k of [0, 1, 2]) { const u = eu0 - 18 + k * 4.4, v = 4.6, y = H(...P(u, v)) + 0.12;
    box(u, v, y + 0.74, 2.0, 0.06, 0.8, '#2f6b4a'); for (const sv of [-0.72, 0.72]) box(u, v + sv, y + 0.45, 2.0, 0.05, 0.3, '#2f6b4a');
    for (const su of [-0.75, 0.75]) box(u + su, v, y + 0.37, 0.08, 0.74, 1.7, '#2b2f33'); }
  for (const [u, v] of [[eu0 - 0.9, 2.4], [eu1 + 1.3, 2.2]]) { const y = H(...P(u, v)) + 0.12;
    box(u, v, y + 1.4, 0.09, 2.8, 0.09, '#5a4636'); { const c = P(u, v); parts.push({ g: new THREE.ConeGeometry(0.75, 2.6, 7), m: M4(c[0], y + 3.3, c[1]), c: C('#3f6034') }); }
    for (const sv of [-0.35, 0.35]) box(u + sv, v, y + 0.8, 0.07, 1.6, 0.07, '#b89a6a'); box(u, v, y + 1.35, 0.8, 0.06, 0.06, '#b89a6a'); }
  for (const u of [ue - 1.6, ue + 1.6]) { const y = H(...P(u, 3.4)) + 0.12; box(u, 3.4, y + 0.25, 1.0, 0.5, 0.45, '#a07a4f'); }
  for (const [u, v] of [[ue - 4.5, 5.2], [ue + 4.8, 4.8], [ue + 9, 5.5]]) { const y = H(...P(u, v)) + 0.12; box(u, v, y + 0.45, 0.13, 0.9, 0.13, '#22262a'); }
  const md = new THREE.Mesh(bake(parts), matDetalj); md.castShadow = true; md.receiveShadow = true; md.userData.bidx = bi; world.pickables.push(md); scene.add(md);
}
// utskjutande tak på stolpar (OSM building=roof), ev. med uteservering
function farghusTex(text) {
  return canvasTex(1024, 248, (g, W, Hh) => {
    g.fillStyle = '#f7f6f2'; g.fillRect(0, 0, W, Hh); g.strokeStyle = '#c9c6bd'; g.lineWidth = 4; g.strokeRect(2, 2, W - 4, Hh - 4);
    const dots = [['#2f6fd0', '#f2c12e', '#8a4fc0'], ['#e0352b', '#3aa655', '#2f6fd0']];
    dots.forEach((row, j) => row.forEach((c, i) => { g.fillStyle = c; g.beginPath(); g.arc(70 + i * 62, 70 + j * 62, 27, 0, 7); g.fill(); }));
    g.fillStyle = '#7a2a6a'; g.font = 'bold 92px "Trebuchet MS", Arial, sans-serif'; g.textBaseline = 'middle'; g.textAlign = 'left';
    let fs = 92; while (g.measureText(text).width > W - 300 && fs > 40) { fs -= 4; g.font = `bold ${fs}px "Trebuchet MS", Arial, sans-serif`; }
    g.fillText(text, 270, 105);
    g.fillStyle = '#6b6b6b'; g.font = 'bold 26px Arial, sans-serif'; g.fillText('FÄRG  ·  TAPETER  ·  GOLV  ·  VERKTYG  ·  RÅD', 272, 190);
  }, true, false);
}
function buildCanopy(h) {
  const bi = h.idx; let x, z, b, d, rot;
  if (h.rekt) [x, z, b, d, rot] = h.rekt; else { x = h.x; z = h.z; b = d = Math.sqrt(h.area); rot = 0; }
  const long = b >= d; const L = long ? b : d, D = long ? d : b; const yaw = long ? rot : rot + Math.PI / 2;
  const ux = Math.cos(yaw), uz = Math.sin(yaw), vx = -uz, vz = ux; // u längs, v tvärs
  const P = (u, v) => [x + ux * u + vx * v, z + uz * u + vz * v];
  const roadD = (p) => { const nr = nearestRoad(p[0], p[1], 40, g => g.bil); return nr ? nr.d : 99; };
  const so = h.so ?? (roadD(P(0, D / 2)) < roadD(P(0, -D / 2)) ? 1 : -1); // ytterkant mot gatan
  const g0 = h.g0; const stor = h.area > 150;
  const yi = g0 + (h.kh ? h.kh[0] : stor ? 4.8 : 3.3), yo = g0 + (h.kh ? h.kh[1] : stor ? 4.8 : 2.75);
  const ry = -yaw; const pitch = so * Math.atan2(yi - yo, D);
  const parts = []; const rc = C(h.takfarg || '#8a3a2c'), wc = C(h.vagg || '#f1f0ea');
  const c0 = P(0, 0); parts.push({ g: new THREE.BoxGeometry(L + 0.3, 0.14, D / Math.cos(pitch) + 0.3), m: M4(c0[0], (yi + yo) / 2 + 0.05, c0[1], ry, 1, 1, 1, pitch), c: rc });
  const fe = P(0, so * (D / 2 + 0.12)); parts.push({ g: new THREE.BoxGeometry(L + 0.3, 0.28, 0.06), m: M4(fe[0], yo - 0.05, fe[1], ry), c: wc });
  const np = Math.max(2, Math.round(L / 3.2) + 1);
  for (let k = 0; k < np; k++) { const u = -L / 2 + 0.2 + k * (L - 0.4) / (np - 1); const p = P(u, so * (D / 2 - 0.15)); const gy = H(p[0], p[1]); parts.push({ g: new THREE.BoxGeometry(0.13, yo - gy, 0.13), m: M4(p[0], (yo + gy) / 2, p[1], ry), c: wc }); }
  h.top = yi + 0.3;
  if (h.uteservering) {
    const [u0, u1] = h.uteservering; const r = mulberry32(31);
    // vitt staket längs ytterkanten med öppning i mitten
    const um = (u0 + u1) / 2;
    for (let u = u0; u <= u1 + 0.01; u += 1.5) { if (Math.abs(u - um) < 1.2) continue; const p = P(u, so * (D / 2 - 0.05)); const y = H(p[0], p[1]); parts.push({ g: new THREE.BoxGeometry(0.08, 1.0, 0.08), m: M4(p[0], y + 0.5, p[1], ry), c: C('#f4f3ee') }); }
    for (const [a, bb] of [[u0, um - 1.2], [um + 1.2, u1]]) for (const hy of [0.45, 0.95]) { const p = P((a + bb) / 2, so * (D / 2 - 0.05)); const y = H(p[0], p[1]); parts.push({ g: new THREE.BoxGeometry(bb - a, 0.06, 0.06), m: M4(p[0], y + hy, p[1], ry), c: C('#f4f3ee') }); }
    // bord och stolar
    for (let u = u0 + 1.3; u < u1 - 0.8; u += 2.9) { if (Math.abs(u - um) < 1.0) continue; const p = P(u, so * (D / 2 - 1.3) * 0.2); const y = H(p[0], p[1]) + 0.12;
      parts.push({ g: new THREE.CylinderGeometry(0.38, 0.38, 0.04, 14), m: M4(p[0], y + 0.72, p[1]), c: C('#2c2c2c') });
      parts.push({ g: new THREE.CylinderGeometry(0.04, 0.05, 0.72, 6), m: M4(p[0], y + 0.36, p[1]), c: C('#2c2c2c') });
      for (const sg of [-1, 1]) { const q = P(u + sg * 0.7, so * (D / 2 - 1.3) * 0.2); parts.push({ g: new THREE.BoxGeometry(0.42, 0.05, 0.42), m: M4(q[0], y + 0.45, q[1], ry), c: C('#2c2c2c') }); const bk = P(u + sg * 0.9, so * (D / 2 - 1.3) * 0.2); parts.push({ g: new THREE.BoxGeometry(0.05, 0.45, 0.42), m: M4(bk[0], y + 0.68, bk[1], ry), c: C('#2c2c2c') }); for (const lx of [-0.18, 0.18]) for (const lz of [-0.18, 0.18]) { const lq = P(u + sg * 0.7 + lx, so * (D / 2 - 1.3) * 0.2 + lz); parts.push({ g: new THREE.BoxGeometry(0.03, 0.45, 0.03), m: M4(lq[0], y + 0.22, lq[1]), c: C('#2c2c2c') }); } }
      const bl = P(u + 0.1, so * (D / 2 - 1.3) * 0.2); parts.push({ g: new THREE.CylinderGeometry(0.12, 0.09, 0.22, 8), m: M4(bl[0], y + 0.85, bl[1]), c: C('#c0703a') }); parts.push({ g: new THREE.SphereGeometry(0.16, 8, 6), m: M4(bl[0], y + 1.02, bl[1]), c: C('#4f8a3a') }); }
    // vimplar och ballonger längs takkanten
    const fl = ['#3aa655', '#f2c12e', '#3a7bd5', '#f08a24', '#e55b9a', '#8bd0e8'];
    for (let u = u0, k = 0; u <= u1; u += 0.42, k++) { if (Math.abs(u - um) < 1.9) continue; const p = P(u, so * (D / 2 + 0.05)); const sag = 0.18 * Math.sin(((u - u0) % 3) / 3 * Math.PI); parts.push({ g: new THREE.ConeGeometry(0.14, 0.32, 3), m: M4(p[0], yo - 0.42 - sag, p[1], ry, 1, 1, 0.15, Math.PI), c: C(fl[k % fl.length]) }); }
    const bc = ['#e33b3b', '#f08a24', '#f2d22e', '#a05bd5', '#ef7fb0', '#f5f0e0'];
    for (let u = u0 + 0.6; u < u1; u += 1.35) { const ur = u + (r() - 0.5) * 0.3, br = r(), bk = r(); if (Math.abs(ur - um) < 2.0) continue; const p = P(ur, so * (D / 2 + 0.1)); parts.push({ g: new THREE.SphereGeometry(0.2, 10, 8), m: M4(p[0], yo - 0.85 - br * 0.15, p[1], 0, 1, 1.18, 1), c: C(bc[Math.floor(bk * bc.length)]) }); }
    // gatupratare och papperskorg
    { const p = P(um + 0.2, so * (D / 2 + 1.0)); const y = H(p[0], p[1]); for (const sg of [-1, 1]) parts.push({ g: new THREE.BoxGeometry(0.6, 1.0, 0.04), m: M4(p[0], y + 0.5, p[1], ry, 1, 1, 1, sg * 0.2), c: C('#c8302a') }); }
    { const p = P(um - 2.2, so * (D / 2 + 0.7)); const y = H(p[0], p[1]); parts.push({ g: new THREE.CylinderGeometry(0.25, 0.22, 0.8, 12), m: M4(p[0], y + 0.4, p[1]), c: C('#c8302a') }); }
  }
  const m = new THREE.Mesh(bake(parts), matDetalj); m.castShadow = true; m.receiveShadow = true; m.userData.bidx = bi; world.pickables.push(m); scene.add(m);
}
// skärmtak längs den fasad som vetter mot k.mot (från rättningar)
function buildKapellPa(h, k) {
  const cs = h.corners; const n = cs.length; let cx = 0, cz = 0; cs.forEach(q => { cx += q[0]; cz += q[1]; }); cx /= n; cz /= n;
  let best = null;
  for (let i = 0; i < n; i++) { const a = cs[i], b = cs[(i + 1) % n]; const L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 3) continue;
    const mx = (a[0] + b[0]) / 2, mz = (a[1] + b[1]) / 2; let nx = (b[1] - a[1]) / L, nz = -(b[0] - a[0]) / L; if (nx * (mx - cx) + nz * (mz - cz) < 0) { nx = -nx; nz = -nz; }
    const tx = k.mot[0] - mx, tz = k.mot[1] - mz, tl = Math.hypot(tx, tz) || 1; const sc = (nx * tx + nz * tz) / tl;
    if (!best || sc > best.sc) best = { sc, a, b, L, nx, nz }; }
  if (!best) return;
  const { a, b, nx, nz } = best; const ux = (b[0] - a[0]) / best.L, uz = (b[1] - a[1]) / best.L; const tr = k.trim ?? 0.3;
  let s0 = tr, s1 = best.L - tr;
  if (k.nara && k.langd) { const sp = (k.nara[0] - a[0]) * ux + (k.nara[1] - a[1]) * uz; s0 = Math.max(s0, sp - k.langd / 2); s1 = Math.min(s1, sp + k.langd / 2); }
  const D = k.djup || 2.6; if (s1 - s0 < D + 0.5) return; const sm = (s0 + s1) / 2;
  const c = [a[0] + ux * sm + nx * D / 2, a[1] + uz * sm + nz * D / 2]; const yaw = Math.atan2(uz, ux);
  const so = (nx * -Math.sin(yaw) + nz * Math.cos(yaw)) > 0 ? 1 : -1;
  buildCanopy({ idx: h.idx, rekt: [c[0], c[1], s1 - s0, D, yaw], area: (s1 - s0) * D, g0: h.g0, takfarg: k.takfarg || '#9a3a2a', vagg: k.vagg || '#f1f0ea', so, kh: k.hojd, uteservering: k.uteservering });
}
// metallräcke med cykelställ mellan bilväg och skolgård
function buildRacke(r) {
  const pts = resample(r.pts, 0.5); if (pts.length < 2) return; const parts = []; const metal = '#9da3a8';
  const side = (p) => { const nx = -p.tz, nz = p.tx; return ((r.mot[0] - p.x) * nx + (r.mot[1] - p.z) * nz) > 0 ? 1 : -1; };
  let last = -1e9;
  for (const p of pts) { if (p.s - last < 2.0) continue; last = p.s; const y = H(p.x, p.z) + 0.1; parts.push({ g: new THREE.BoxGeometry(0.07, 1.0, 0.07), m: M4(p.x, y + 0.5, p.z), c: C(metal) }); }
  for (const hy of [0.5, 0.95]) for (let i = 0; i < pts.length - 1; i++) { const a = pts[i], b = pts[i + 1]; const ya = H(a.x, a.z) + 0.1 + hy, yb = H(b.x, b.z) + 0.1 + hy; const L = Math.hypot(b.x - a.x, b.z - a.z);
    parts.push({ g: new THREE.BoxGeometry(0.045, 0.045, L + 0.02), m: M4((a.x + b.x) / 2, (ya + yb) / 2, (a.z + b.z) / 2, Math.atan2(b.x - a.x, b.z - a.z), 1, 1, 1, -Math.atan2(yb - ya, L)), c: C(metal) }); }
  // cykelställ (bågar) på gårdssidan, två grupper nära entrén
  const rb = mulberry32(17); const cykelfarg = ['#1f3f8a', '#b8b8b8', '#202020', '#8a1c1c', '#2f6b4a', '#d0c060'];
  for (const p of pts) {
    const near = Math.abs(p.z - 418) < 7 || Math.abs(p.z - 432) < 4.5; if (!near || Math.round(p.s * 2) % 2) continue;
    const sg = side(p); const nx = -p.tz * sg, nz = p.tx * sg; const bx = p.x + nx * 0.9, bz = p.z + nz * 0.9; const y = H(bx, bz) + 0.1; const ang = Math.atan2(nx, nz);
    for (const o of [-0.3, 0.3]) parts.push({ g: new THREE.BoxGeometry(0.05, 0.8, 0.05), m: M4(bx + nx * o, y + 0.4, bz + nz * o, ang), c: C(metal) });
    parts.push({ g: new THREE.BoxGeometry(0.05, 0.05, 0.65), m: M4(bx, y + 0.8, bz, ang), c: C(metal) });
    if (rb() < 0.45) { // en cykel i stället
      const col = C(cykelfarg[Math.floor(rb() * cykelfarg.length)]); const tx = p.tx, tz = p.tz; const cx = bx + nx * 0.25 + tx * 0.25, cz = bz + nz * 0.25 + tz * 0.25;
      for (const o of [-0.55, 0.55]) parts.push({ g: new THREE.TorusGeometry(0.33, 0.025, 6, 18), m: M4(cx + nx * o, y + 0.34, cz + nz * o, ang + Math.PI / 2), c: C('#1a1a1a') });
      parts.push({ g: new THREE.BoxGeometry(0.04, 0.04, 1.0), m: M4(cx, y + 0.55, cz, ang), c: col });
      parts.push({ g: new THREE.BoxGeometry(0.04, 0.45, 0.04), m: M4(cx - nx * 0.18, y + 0.62, cz - nz * 0.18, ang, 1, 1, 1, 0.3), c: col });
      parts.push({ g: new THREE.BoxGeometry(0.5, 0.04, 0.04), m: M4(cx + nx * 0.5, y + 0.98, cz + nz * 0.5, ang), c: C('#1a1a1a') });
      parts.push({ g: new THREE.BoxGeometry(0.12, 0.05, 0.25), m: M4(cx - nx * 0.35, y + 0.88, cz - nz * 0.35, ang), c: C('#1a1a1a') });
    }
  }
  const m = new THREE.Mesh(bake(parts), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4, metalness: 0.5 })); m.castShadow = true; scene.add(m);
}
// =====================================================================
// Byggnader modellerade efter foton: stationshuset och huset med Gnesta Indiska
// Allt byggs i ett lokalt system (u längs huset, y uppåt, v ut från framsidan)
// som placeras med en basmatris.
// =====================================================================
function tegel(g, x0, y0, w, h, ppm, bas, seed) {
  const r = mulberry32(seed || 3); g.save(); g.beginPath(); g.rect(x0, y0, w, h); g.clip();
  g.fillStyle = bas; g.fillRect(x0, y0, w, h);
  const bh = 0.077 * ppm, bw = 0.25 * ppm; let row = 0;
  for (let y = y0 + h; y > y0 - bh; y -= bh, row++) for (let x = x0 - (row % 2) * bw / 2; x < x0 + w; x += bw) {
    g.fillStyle = r() < 0.45 ? `rgba(60,18,8,${0.06 + r() * 0.16})` : `rgba(255,175,125,${0.04 + r() * 0.12})`; g.fillRect(x + 1, y - bh + 1, bw - 1.5, bh - 1.5);
  }
  g.fillStyle = 'rgba(214,192,165,0.5)'; row = 0;
  for (let y = y0 + h; y > y0 - bh; y -= bh, row++) { g.fillRect(x0, y - 1, w, 1); for (let x = x0 - (row % 2) * bw / 2; x < x0 + w; x += bw) g.fillRect(x, y - bh, 1, bh); }
  g.restore();
}
function glasYta(g, x, y, w, h) {
  const gr = g.createLinearGradient(0, y, 0, y + h); gr.addColorStop(0, '#9fb2c0'); gr.addColorStop(0.35, '#4d6170'); gr.addColorStop(1, '#1d262d');
  g.fillStyle = gr; g.fillRect(x, y, w, h);
  g.fillStyle = 'rgba(255,255,255,0.10)'; g.beginPath(); g.moveTo(x + w * 0.15, y); g.lineTo(x + w * 0.45, y); g.lineTo(x + w * 0.1, y + h); g.lineTo(x - w * 0.2, y + h); g.closePath(); g.fill();
}
const TEGEL_STN = '#b4573a', VIT_KARM = '#eeebe2', GRON_DORR = '#2e5b47';
function stnFonster(g, X, Y, ppm, u0, u1, y0, y1) {
  g.fillStyle = '#cfc6b4'; g.fillRect(X(u0 - 0.08), Y(y0), (u1 - u0 + 0.16) * ppm, 0.1 * ppm);
  g.fillStyle = '#933f29'; g.fillRect(X(u0 - 0.06), Y(y1 + 0.26), (u1 - u0 + 0.12) * ppm, 0.26 * ppm);
  g.strokeStyle = 'rgba(225,190,160,0.55)'; g.lineWidth = 1; const um = (u0 + u1) / 2;
  for (let u = u0 - 0.05; u <= u1 + 0.06; u += 0.1) { g.beginPath(); g.moveTo(X(u), Y(y1)); g.lineTo(X(u + (u - um) * 0.12), Y(y1 + 0.26)); g.stroke(); }
  g.fillStyle = VIT_KARM; g.fillRect(X(u0), Y(y1), (u1 - u0) * ppm, (y1 - y0) * ppm);
  const f = 0.07; glasYta(g, X(u0 + f), Y(y1 - f), (u1 - u0 - 2 * f) * ppm, (y1 - y0 - 2 * f) * ppm);
  g.fillStyle = VIT_KARM; const ym = y0 + (y1 - y0) * 0.7;
  g.fillRect(X(u0), Y(ym + 0.05), (u1 - u0) * ppm, 0.1 * ppm);
  g.fillRect(X(um - 0.04), Y(y1), 0.08 * ppm, (y1 - y0) * ppm);
  for (let k = 1; k < 3; k++) { const yy = y0 + (ym - y0) * k / 3; g.fillRect(X(u0), Y(yy + 0.02), (u1 - u0) * ppm, 0.04 * ppm); }
  for (const t of [0.25, 0.75]) g.fillRect(X(u0 + (u1 - u0) * t - 0.02), Y(y1), 0.04 * ppm, (y1 - ym) * ppm);
}
function stnDorr(g, X, Y, ppm, u0, u1, y0, y1, yt) {
  g.fillStyle = '#933f29'; g.fillRect(X(u0 - 0.1), Y(yt + 0.36), (u1 - u0 + 0.2) * ppm, 0.28 * ppm);
  g.fillStyle = VIT_KARM; g.fillRect(X(u0 - 0.08), Y(yt + 0.08), (u1 - u0 + 0.16) * ppm, (yt + 0.08 - y0) * ppm);
  glasYta(g, X(u0), Y(yt), (u1 - u0) * ppm, (yt - y1 - 0.08) * ppm);
  g.fillStyle = VIT_KARM; g.fillRect(X((u0 + u1) / 2 - 0.03), Y(yt), 0.06 * ppm, (yt - y1) * ppm);
  const um = (u0 + u1) / 2;
  for (const [a, b] of [[u0, um - 0.02], [um + 0.02, u1]]) {
    g.fillStyle = GRON_DORR; g.fillRect(X(a), Y(y1), (b - a) * ppm, (y1 - y0) * ppm);
    g.fillStyle = '#244a3a'; g.fillRect(X(a + 0.1), Y(y0 + 0.95), (b - a - 0.2) * ppm, 0.75 * ppm);
    glasYta(g, X(a + 0.12), Y(y1 - 0.15), (b - a - 0.24) * ppm, (y1 - y0 - 1.25) * ppm);
    g.fillStyle = GRON_DORR; g.fillRect(X(a + 0.12), Y((y1 - 0.15 + y0 + 1.1) / 2 + 0.02), (b - a - 0.24) * ppm, 0.04 * ppm); g.fillRect(X((a + b) / 2 - 0.02), Y(y1 - 0.15), 0.04 * ppm, (y1 - y0 - 1.25) * ppm);
  }
  g.fillStyle = '#c9a54a'; g.fillRect(X(um - 0.12), Y(y0 + 1.15), 0.06 * ppm, 0.2 * ppm); g.fillRect(X(um + 0.06), Y(y0 + 1.15), 0.06 * ppm, 0.2 * ppm);
}
const STN = { E: 5.2, p: 0.95, rw: 10.3, rd: 1.3, steg: 0.68, Y0: -1.2 };
function stnVaggTex(len, items, seed) {
  const ppm = 56, y1 = STN.E, y0 = STN.Y0; const Wp = Math.max(16, Math.ceil(len * ppm)), Hp = Math.ceil((y1 - y0) * ppm);
  return canvasTex(Wp, Hp, (g) => {
    const X = (u) => u * ppm, Y = (y) => (y1 - y) * ppm;
    tegel(g, 0, 0, Wp, Hp, ppm, TEGEL_STN, seed);
    g.fillStyle = '#8f8b84'; g.fillRect(0, Y(0.55), Wp, Hp - Y(0.55)); g.fillStyle = '#aaa59c'; g.fillRect(0, Y(0.55), Wp, 0.07 * ppm);
    g.fillStyle = 'rgba(50,48,44,0.35)'; for (let u = 0.45; u < len; u += 0.9) g.fillRect(X(u), Y(0.48), 1.5, 0.48 * ppm);
    const fy = STN.E - 0.62; g.fillStyle = '#93412b'; g.fillRect(0, Y(fy + 0.32), Wp, 0.32 * ppm);
    g.fillStyle = 'rgba(40,12,6,0.6)'; for (let u = 0; u < len; u += 0.25) { g.beginPath(); g.moveTo(X(u), Y(fy + 0.3)); g.lineTo(X(u + 0.125), Y(fy + 0.02)); g.lineTo(X(u + 0.25), Y(fy + 0.3)); g.closePath(); g.fill(); }
    g.fillStyle = '#9f4a32'; g.fillRect(0, Y(STN.E), Wp, 0.24 * ppm);
    for (const it of items) {
      if (it.k === 'f') stnFonster(g, X, Y, ppm, it.u - 0.58, it.u + 0.58, 1.6, 3.85);
      else stnDorr(g, X, Y, ppm, it.u - 0.75, it.u + 0.75, STN.steg, 3.0, 3.75);
    }
  }, true, false);
}
// silhuetten på mittpartiets gavel (u, y), höger halva
const STN_GAVEL = (() => { const hw = STN.rw / 2; return { hw, pts: [[hw, 7.4], ['c', hw - 0.9, 7.55, 3.3, 9.55, 2.55, 9.75], [2.55, 10.05], [2.15, 10.05], [2.15, 10.3], [0, 11.55]] }; })();
function gavelPath(g, X, Y, y0) {
  const { hw, pts } = STN_GAVEL; g.beginPath(); g.moveTo(X(-hw), Y(y0)); g.lineTo(X(hw), Y(y0));
  for (const p of pts) if (p[0] === 'c') g.bezierCurveTo(X(p[1]), Y(p[2]), X(p[3]), Y(p[4]), X(p[5]), Y(p[6])); else g.lineTo(X(p[0]), Y(p[1]));
  // spegla vänster halva
  const L = [[-2.15, 10.3], [-2.15, 10.05], [-2.55, 10.05], [-2.55, 9.75]]; for (const q of L) g.lineTo(X(q[0]), Y(q[1]));
  g.bezierCurveTo(X(-3.3), Y(9.55), X(-(hw - 0.9)), Y(7.55), X(-hw), Y(7.4)); g.closePath();
}
function stnRisalitTex(fram) {
  const ppm = 72, top = 11.6, y0 = STN.Y0, rw = STN.rw; const Wp = Math.ceil(rw * ppm), Hp = Math.ceil((top - y0) * ppm);
  const t = canvasTex(Wp, Hp, (g) => {
    const X = (u) => (u + rw / 2) * ppm, Y = (y) => (top - y) * ppm;
    tegel(g, 0, 0, Wp, Hp, ppm, TEGEL_STN, fram ? 11 : 12);
    g.fillStyle = '#8f8b84'; g.fillRect(0, Y(0.55), Wp, Hp - Y(0.55)); g.fillStyle = '#aaa59c'; g.fillRect(0, Y(0.55), Wp, 0.07 * ppm);
    const aw = 1.0, yS = 4.6, st = STN.steg;
    const archPath = (cx, ya, r) => { g.beginPath(); g.moveTo(X(cx - r), Y(ya)); g.lineTo(X(cx - r), Y(yS)); g.arc(X(cx), Y(yS), r * ppm, Math.PI, 0); g.lineTo(X(cx + r), Y(ya)); g.closePath(); };
    for (const cx of [-3.1, 0, 3.1]) {
      const mid = cx === 0; const ya = mid ? st : 1.65;
      // valvbåge av tegel med radiella fogar
      g.fillStyle = '#9a4430'; g.beginPath(); g.arc(X(cx), Y(yS), (aw + 0.34) * ppm, Math.PI, 0); g.lineTo(X(cx + aw), Y(yS)); g.arc(X(cx), Y(yS), aw * ppm, 0, Math.PI, true); g.closePath(); g.fill();
      g.strokeStyle = 'rgba(225,190,160,0.6)'; g.lineWidth = 1.2; for (let a = Math.PI; a <= 2 * Math.PI + 0.01; a += Math.PI / 16) { g.beginPath(); g.moveTo(X(cx) + Math.cos(a) * aw * ppm, Y(yS) + Math.sin(a) * aw * ppm); g.lineTo(X(cx) + Math.cos(a) * (aw + 0.34) * ppm, Y(yS) + Math.sin(a) * (aw + 0.34) * ppm); g.stroke(); }
      if (!mid) { g.fillStyle = '#cfc6b4'; g.fillRect(X(cx - aw - 0.08), Y(ya), (2 * aw + 0.16) * ppm, 0.1 * ppm); }
      g.save(); archPath(cx, ya, aw); g.clip();
      g.fillStyle = VIT_KARM; g.fillRect(X(cx - aw), Y(yS + aw), 2 * aw * ppm, (yS + aw - ya) * ppm);
      archPath(cx, ya, aw - 0.08); g.save(); g.clip(); glasYta(g, X(cx - aw), Y(yS + aw), 2 * aw * ppm, (yS + aw - ya) * ppm); g.restore();
      g.fillStyle = VIT_KARM; g.strokeStyle = VIT_KARM;
      const gy0 = mid ? 3.1 : ya;
      for (const du of [-0.33, 0.33]) g.fillRect(X(cx + du - 0.025), Y(yS), 0.05 * ppm, (yS - gy0) * ppm);
      for (let yy = gy0 + 0.5; yy < yS; yy += 0.5) g.fillRect(X(cx - aw), Y(yy + 0.02), 2 * aw * ppm, 0.04 * ppm);
      g.fillRect(X(cx - aw), Y(yS + 0.04), 2 * aw * ppm, 0.08 * ppm);
      g.lineWidth = 0.05 * ppm; for (let k = 1; k < 6; k++) { const a = Math.PI + k * Math.PI / 6; g.beginPath(); g.moveTo(X(cx), Y(yS)); g.lineTo(X(cx) + Math.cos(a) * aw * ppm, Y(yS) + Math.sin(a) * aw * ppm); g.stroke(); }
      g.beginPath(); g.arc(X(cx), Y(yS), 0.42 * ppm, Math.PI, 0); g.stroke();
      if (mid) {
        // gröna pardörrar, tvärpost och fält för skylten
        const d0 = cx - aw + 0.08, d1 = cx + aw - 0.08, dm = cx;
        for (const [a, b] of [[d0, dm - 0.02], [dm + 0.02, d1]]) {
          g.fillStyle = GRON_DORR; g.fillRect(X(a), Y(2.95), (b - a) * ppm, (2.95 - st) * ppm);
          g.fillStyle = '#244a3a'; g.fillRect(X(a + 0.1), Y(st + 0.85), (b - a - 0.2) * ppm, 0.65 * ppm);
          glasYta(g, X(a + 0.12), Y(2.8), (b - a - 0.24) * ppm, 1.1 * ppm);
          g.fillStyle = GRON_DORR; g.fillRect(X((a + b) / 2 - 0.025), Y(2.8), 0.05 * ppm, 1.1 * ppm); g.fillRect(X(a + 0.12), Y(2.27), (b - a - 0.24) * ppm, 0.05 * ppm);
        }
        g.fillStyle = '#c9a54a'; g.fillRect(X(dm - 0.14), Y(st + 1.15), 0.07 * ppm, 0.22 * ppm); g.fillRect(X(dm + 0.07), Y(st + 1.15), 0.07 * ppm, 0.22 * ppm);
        g.fillStyle = VIT_KARM; g.fillRect(X(cx - aw), Y(3.12), 2 * aw * ppm, 0.17 * ppm);
        g.fillStyle = fram ? '#f6d31c' : '#3a4a56'; g.fillRect(X(cx - aw + 0.04), Y(3.62), (2 * aw - 0.08) * ppm, 0.5 * ppm);
      } else if (fram) {
        // Pressbyråns gula dekaler längst ner i fönstren
        g.fillStyle = '#f2c414'; for (let u = cx - aw + 0.12; u < cx + aw - 0.05; u += 0.26) { g.beginPath(); g.arc(X(u + 0.1), Y(ya + 0.08), 0.12 * ppm, Math.PI, 0); g.fill(); }
      }
      g.restore();
      g.strokeStyle = VIT_KARM; g.lineWidth = 0.08 * ppm; archPath(cx, ya, aw - 0.04); g.stroke();
    }
    // gavelns dekor: tandsnitt, två små rundbågefönster, rutmönster
    const tand = (y) => { g.fillStyle = '#93412b'; g.fillRect(0, Y(y + 0.22), Wp, 0.22 * ppm); g.fillStyle = 'rgba(40,12,6,0.6)'; for (let u = -rw / 2; u < rw / 2; u += 0.25) { g.beginPath(); g.moveTo(X(u), Y(y + 0.2)); g.lineTo(X(u + 0.125), Y(y + 0.02)); g.lineTo(X(u + 0.25), Y(y + 0.2)); g.closePath(); g.fill(); } };
    tand(8.05); tand(9.45);
    for (const cx of [-0.42, 0.42]) {
      const p = () => { g.beginPath(); g.moveTo(X(cx - 0.25), Y(8.4)); g.lineTo(X(cx - 0.25), Y(8.9)); g.arc(X(cx), Y(8.9), 0.25 * ppm, Math.PI, 0); g.lineTo(X(cx + 0.25), Y(8.4)); g.closePath(); };
      g.fillStyle = VIT_KARM; p(); g.fill(); g.save(); p(); g.clip(); glasYta(g, X(cx - 0.19), Y(9.1), 0.38 * ppm, 0.66 * ppm); g.restore();
      g.fillStyle = VIT_KARM; g.fillRect(X(cx - 0.02), Y(9.1), 0.04 * ppm, 0.7 * ppm); g.fillRect(X(cx - 0.25), Y(8.86), 0.5 * ppm, 0.04 * ppm);
    }
    g.strokeStyle = 'rgba(60,18,8,0.55)'; g.lineWidth = 2;
    for (const cx of [-1.55, 1.55]) { g.save(); g.beginPath(); g.rect(X(cx - 0.45), Y(9.1), 0.9 * ppm, 0.65 * ppm); g.clip(); g.fillStyle = '#a24b33'; g.fill(); for (let k = -2; k < 4; k += 0.25) { g.beginPath(); g.moveTo(X(cx - 0.45 + k * 0.6), Y(8.45)); g.lineTo(X(cx - 0.45 + k * 0.6 + 0.65), Y(9.1)); g.stroke(); g.beginPath(); g.moveTo(X(cx - 0.45 + k * 0.6 + 0.65), Y(8.45)); g.lineTo(X(cx - 0.45 + k * 0.6), Y(9.1)); g.stroke(); } g.restore(); }
    // täckplåt längs gavelns kant
    g.strokeStyle = '#5f5c58'; g.lineWidth = 0.22 * ppm; gavelPath(g, X, Y, -5); g.stroke();
  }, true, false);
  t.repeat.set(1 / rw, 1 / (top - y0)); t.offset.set(0.5, -y0 / (top - y0)); return t;
}
const texSkiffer = canvasTex(256, 256, (g, W, Hh) => {
  g.fillStyle = '#4a4f56'; g.fillRect(0, 0, W, Hh); const r = mulberry32(21);
  for (let y = 0, row = 0; y < Hh; y += 32, row++) for (let x = -(row % 2) * 24; x < W; x += 48) {
    const k = 0.85 + r() * 0.3; g.fillStyle = `rgb(${Math.round(74 * k)},${Math.round(79 * k)},${Math.round(86 * k)})`; g.fillRect(x + 1, y + 1, 46, 30);
    g.fillStyle = 'rgba(0,0,0,0.28)'; g.fillRect(x + 1, y + 27, 46, 4);
  }
}, true, true);
const texTegelLos = canvasTex(256, 256, (g, W, Hh) => tegel(g, 0, 0, W, Hh, 128, TEGEL_STN, 5), true, true);
function pressbyranTex(e) {
  return canvasTex(1024, 228, (g, W, Hh) => {
    g.fillStyle = e.bg || '#f6d31c'; g.fillRect(0, 0, W, Hh); g.strokeStyle = 'rgba(150,110,0,0.5)'; g.lineWidth = 8; g.strokeRect(4, 4, W - 8, Hh - 8);
    g.fillStyle = e.fg || '#1e5aa8'; g.font = 'italic bold 150px "Trebuchet MS", Arial, sans-serif'; g.textBaseline = 'middle'; g.textAlign = 'left';
    let fs = 150; while (g.measureText(e.skylt).width > W - 250 && fs > 60) { fs -= 6; g.font = `italic bold ${fs}px "Trebuchet MS", Arial, sans-serif`; }
    g.fillText(e.skylt, 40, Hh / 2 + 6);
    const cx = W - 105, cy = Hh / 2; g.fillStyle = '#ef5b25'; g.beginPath(); g.arc(cx, cy, 72, 0, 7); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.35)'; g.beginPath(); g.arc(cx - 22, cy - 22, 26, 0, 7); g.fill();
  }, true, false);
}
// enkel BufferGeometry från fyrhörningar med UV
function quadGeo(quads) {
  const pos = [], uv = [];
  for (const [a, b, c, d, ta, tb, tc, td] of quads) { pos.push(...a, ...b, ...c, ...a, ...c, ...d); uv.push(...ta, ...tb, ...tc, ...ta, ...tc, ...td); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.computeVertexNormals(); return g;
}
// lokalt koordinatsystem för ett hus: u längs ax, v längs fv (framsidan), högerhänt bas
function husRam(h, framMot) {
  const [x, z, b, d, rot] = h.rekt; const along = b >= d; const L = along ? b : d, D = along ? d : b;
  const c = Math.cos(rot), s = Math.sin(rot);
  let ax = along ? [c, s] : [-s, c], fv = along ? [-s, c] : [c, s];
  if (framMot && (framMot[0] - x) * fv[0] + (framMot[1] - z) * fv[1] < 0) fv = [-fv[0], -fv[1]];
  if ((-ax[1]) * fv[0] + ax[0] * fv[1] < 0) ax = [-ax[0], -ax[1]]; // ax × upp = fv
  const W2 = (u, v) => [x + ax[0] * u + fv[0] * v, z + ax[1] * u + fv[1] * v];
  return { x, z, L, D, ax, fv, W2 };
}
function husGrupp(R, y0) {
  const grp = new THREE.Group(); grp.matrixAutoUpdate = false;
  grp.matrix.makeBasis(new THREE.Vector3(R.ax[0], 0, R.ax[1]), new THREE.Vector3(0, 1, 0), new THREE.Vector3(R.fv[0], 0, R.fv[1])); grp.matrix.setPosition(R.x, y0, R.z);
  scene.add(grp); grp.updateMatrixWorld(true); return grp;
}
function vaggPlan(pA, pB, y0, y1, ty0, ty1, mat) {
  // pA,pB = [u,v]; texturen täcker höjden ty0..ty1, utanför kläms den
  const v0 = (y0 - ty0) / (ty1 - ty0), v1 = (y1 - ty0) / (ty1 - ty0);
  return new THREE.Mesh(quadGeo([[[pA[0], y0, pA[1]], [pB[0], y0, pB[1]], [pB[0], y1, pB[1]], [pA[0], y1, pA[1]], [0, v0], [1, v0], [1, v1], [0, v1]]]), mat);
}

function buildStation(h) {
  const bi = h.idx;
  const R = (() => { // framsidan = sidan bort från spåren (mot torget)
    const R0 = husRam(h); const nr = (sg) => railBedNear(...R0.W2(0, sg * (R0.D / 2 + 6)), 40) !== null;
    return husRam(h, (nr(1) || !nr(-1)) ? R0.W2(0, -R0.D) : R0.W2(0, R0.D));
  })();
  const { L, D, W2 } = R; const { E, p, rw, rd, steg } = STN; const hL = L / 2, hD = D / 2;
  const fr = W2(0, hD + 3.5); const gF = H(fr[0], fr[1]) + 0.22; h.g0 = gF;
  let gmin = Infinity; for (const [u, v] of [[-hL, -hD], [hL, -hD], [hL, hD], [-hL, hD], [0, 0]]) gmin = Math.min(gmin, H(...W2(u, v)));
  const yb = Math.min(STN.Y0, gmin - gF - 0.4);
  const grp = husGrupp(R, gF);
  const add = (m, cast = true) => { m.castShadow = cast; m.receiveShadow = true; m.userData.bidx = bi; world.pickables.push(m); grp.add(m); return m; };
  const parts = []; const box = (u, y, v, w, hh, d, col, rx = 0, rz = 0, ry = 0) => parts.push({ g: new THREE.BoxGeometry(w, hh, d), m: M4(u, y, v, ry, 1, 1, 1, rx, rz), c: C(col) });
  // väggar (flyglar, baksida och gavlar)
  const seg = (a, b, items, seed) => { const len = Math.hypot(b[0] - a[0], b[1] - a[1]); const dir = [(b[0] - a[0]) / len, (b[1] - a[1]) / len];
    const rel = items.map(it => ({ k: it.k, u: (it.u - a[0]) * dir[0] }));
    const mat = new THREE.MeshStandardMaterial({ map: stnVaggTex(len, rel, seed), roughness: 0.86, side: THREE.DoubleSide });
    add(vaggPlan(a, b, yb, E, STN.Y0, E, mat)); };
  const F = (u) => ({ k: 'f', u }), Dd = (u) => ({ k: 'd', u });
  seg([-hL, hD], [-rw / 2, hD], [F(-6.3), F(-8.1), Dd(-10.3), F(-12.7), F(-15.2), F(-17.7)], 1);
  seg([rw / 2, hD], [hL, hD], [Dd(9.7), F(12.0), F(14.5), F(17.0)], 2);
  seg([-hL, -hD], [-rw / 2, -hD], [F(-6.4), F(-8.4), Dd(-10.6), F(-12.8), F(-15.2), F(-17.6)], 3);
  seg([rw / 2, -hD], [hL, -hD], [F(6.4), F(8.4), Dd(10.6), F(12.8), F(15.2), F(17.6)], 4);
  // gavlarna: u-koordinaten längs väggen räknas från första hörnet
  for (const sg of [-1, 1]) { const a = [sg * hL, -hD], b = [sg * hL, hD]; const mat = new THREE.MeshStandardMaterial({ map: stnVaggTex(D, [F(2.9), F(D / 2), F(D - 2.9)], 6 + sg), roughness: 0.86, side: THREE.DoubleSide }); add(vaggPlan(a, b, yb, E, STN.Y0, E, mat)); }
  // tak: brant valmat skiffertak
  const ro = 0.55, ye = E - ro * p, yr = E + hD * p, r = hL - hD, k = Math.sqrt(1 + p * p) / 2;
  const tq = [];
  for (const sg of [-1, 1]) {
    const a = [-hL - ro, ye, sg * (hD + ro)], b = [hL + ro, ye, sg * (hD + ro)], c2 = [r, yr, 0], d2 = [-r, yr, 0];
    tq.push([a, b, c2, d2, [a[0] / 2, 0], [b[0] / 2, 0], [r / 2, (hD + ro) * k], [-r / 2, (hD + ro) * k]]);
    const e1 = [sg * (hL + ro), ye, -(hD + ro)], e2 = [sg * (hL + ro), ye, hD + ro], e3 = [sg * r, yr, 0];
    tq.push([e1, e2, e3, e3, [-(hD + ro) / 2, 0], [(hD + ro) / 2, 0], [0, (hD + ro) * k], [0, (hD + ro) * k]]);
  }
  const takMat = new THREE.MeshStandardMaterial({ map: texSkiffer, roughness: 0.75, metalness: 0.05, side: THREE.DoubleSide });
  add(new THREE.Mesh(quadGeo(tq), takMat));
  // takfot: rödbruna vindskivor och undersida
  for (const sg of [-1, 1]) { box(0, ye - 0.06, sg * (hD + ro), L + 2 * ro + 0.1, 0.3, 0.07, '#7a2f22'); box(0, ye + 0.02, sg * (hD + ro / 2), L + 2 * ro, 0.05, ro, '#5e2a20');
    box(sg * (hL + ro), ye - 0.06, 0, 0.07, 0.3, D + 2 * ro + 0.1, '#7a2f22'); box(sg * (hL + ro / 2), ye + 0.02, 0, ro, 0.05, D + 2 * ro, '#5e2a20'); }
  // takkupor
  const kupa = (u, sg) => { const zf = sg * (hD - 0.7), zb = sg * (hD - 3.3);
    box(u, 6.05, (zf + zb) / 2, 1.9, 2.1, Math.abs(zf - zb), '#4b5057');
    box(u, 6.17, zf + sg * 0.02, 1.5, 1.5, 0.06, VIT_KARM); box(u, 6.17, zf + sg * 0.05, 1.24, 1.24, 0.04, '#33424e');
    box(u, 6.17, zf + sg * 0.08, 0.06, 1.24, 0.03, VIT_KARM); box(u, 6.17, zf + sg * 0.08, 1.24, 0.06, 0.03, VIT_KARM);
    for (const s2 of [-1, 1]) box(u + s2 * 0.5, 7.33, (zf + zb) / 2 + sg * 0.15, 1.28, 0.08, Math.abs(zf - zb) + 0.3, '#43474d', 0, -s2 * 0.55);
    box(u, 7.02, zf + sg * 0.1, 2.0, 0.12, 0.06, '#7a2f22'); };
  [-7.2, -11.8, 16.0].forEach(u => kupa(u, 1)); [-15.5, -9, 9, 15.5].forEach(u => kupa(u, -1));
  // skorstenar och takryttare
  for (const u of [-L * 0.3, L * 0.3]) { box(u, yr - 0.1, -0.8, 0.9, 2.6, 0.9, '#9c4a33'); box(u, yr + 1.25, -0.8, 1.05, 0.14, 1.05, '#4f4f4d'); }
  box(0, yr + 0.9, -0.6, 2.2, 2.4, 2.2, '#e9e2d0'); parts.push({ g: new THREE.ConeGeometry(1.9, 4.4, 4), m: M4(0, yr + 4.3, -0.6, Math.PI / 4), c: C('#3e5a4c') });
  // mittpartier (risaliter) med svängda gavlar, fram och bak
  const sh = new THREE.Shape(); const { hw, pts } = STN_GAVEL; sh.moveTo(-hw, yb); sh.lineTo(hw, yb);
  for (const q of pts) if (q[0] === 'c') sh.bezierCurveTo(q[1], q[2], q[3], q[4], q[5], q[6]); else sh.lineTo(q[0], q[1]);
  sh.lineTo(-2.15, 10.3); sh.lineTo(-2.15, 10.05); sh.lineTo(-2.55, 10.05); sh.lineTo(-2.55, 9.75); sh.bezierCurveTo(-3.3, 9.55, -(hw - 0.9), 7.55, -hw, 7.4); sh.closePath();
  const rGeo = new THREE.ExtrudeGeometry(sh, { depth: rd, bevelEnabled: false, curveSegments: 12 });
  const sidaTex = texTegelLos.clone(); sidaTex.repeat.set(0.5, 0.5); sidaTex.needsUpdate = true; const sidaMat = new THREE.MeshStandardMaterial({ map: sidaTex, roughness: 0.86 });
  for (const sg of [1, -1]) {
    const m = new THREE.Mesh(rGeo, [new THREE.MeshStandardMaterial({ map: stnRisalitTex(sg === 1), roughness: 0.82 }), sidaMat]);
    m.position.set(0, 0, sg * hD); if (sg < 0) m.rotation.y = Math.PI; add(m);
    // korstak bakom gaveln
    const zf = sg * (hD + rd - 0.08), zb = sg * 0.3, ey = 7.35, ry2 = ey + 5.5 * 0.64;
    const cq = [];
    for (const s2 of [-1, 1]) { const a = [s2 * 5.5, ey, zf], b = [s2 * 5.5, ey, zb], c2 = [0, ry2, zb], d2 = [0, ry2, zf]; cq.push([a, b, c2, d2, [0, 0], [Math.abs(zf - zb) / 2, 0], [Math.abs(zf - zb) / 2, 3.2], [0, 3.2]]); }
    add(new THREE.Mesh(quadGeo(cq), takMat));
    for (const s2 of [-1, 1]) { box(s2 * 5.5, ey - 0.05, (zf + zb) / 2 + sg * 0.6, 0.07, 0.28, Math.abs(zf - zb) - 1.2, '#7a2f22');
      const bl = 2.6; box(s2 * (5.5 - bl / 2 * 0.84), ey + bl / 2 * 0.54, zf + sg * 0.03, bl, 0.26, 0.07, '#7a2f22', 0, -s2 * 0.57); }
    // namnskylt på gaveln
    const sn = new THREE.Mesh(new THREE.PlaneGeometry(3.1, 0.58), new THREE.MeshStandardMaterial({ map: textTex('GNESTA', { bg: '#f4f1e8', fg: '#1d3a6b', w: 640, h: 120 }), roughness: 0.6 }));
    sn.position.set(0, 7.66, sg * (hD + rd + 0.03)); if (sg < 0) sn.rotation.y = Math.PI; add(sn, false);
  }
  const zf = hD + rd;
  // urtavla på framsidan
  { const cz = zf + 0.03, cy = 6.55;
    parts.push({ g: new THREE.CylinderGeometry(0.47, 0.47, 0.08, 32), m: M4(0, cy, cz, 0, 1, 1, 1, Math.PI / 2), c: C('#262626') });
    parts.push({ g: new THREE.CylinderGeometry(0.41, 0.41, 0.09, 32), m: M4(0, cy, cz + 0.01, 0, 1, 1, 1, Math.PI / 2), c: C('#f5f3ec') });
    for (let k2 = 0; k2 < 12; k2++) { const a = k2 / 12 * Math.PI * 2; box(Math.sin(a) * 0.34, cy + Math.cos(a) * 0.34, cz + 0.06, 0.03, k2 % 3 ? 0.05 : 0.09, 0.01, '#1a1a1a', 0, -a); }
    const hand = (ang, len, wdt) => box(Math.sin(ang) * len / 2, cy + Math.cos(ang) * len / 2, cz + 0.07, wdt, len, 0.015, '#111', 0, -ang);
    hand((11 + 25 / 60) / 12 * Math.PI * 2, 0.22, 0.045); hand(25 / 60 * Math.PI * 2, 0.33, 0.03); }
  // tre kronor på baksidan mot sjön
  for (const u of [-0.95, 0, 0.95]) { const v = -(zf + 0.25);
    parts.push({ g: new THREE.CylinderGeometry(0.34, 0.26, 0.34, 8), m: M4(u, 6.45, v), c: C('#d4a62a') });
    for (let k2 = 0; k2 < 5; k2++) { const a = k2 / 5 * Math.PI * 2; parts.push({ g: new THREE.ConeGeometry(0.07, 0.22, 5), m: M4(u + Math.cos(a) * 0.28, 6.72, v + Math.sin(a) * 0.28), c: C('#d4a62a') }); }
    parts.push({ g: new THREE.SphereGeometry(0.08, 8, 6), m: M4(u, 6.9, v), c: C('#d4a62a') }); }
  // Pressbyrån ovanför de gröna dörrarna
  if (h.entre) { const sp = new THREE.Mesh(new THREE.PlaneGeometry(1.92, 0.46), new THREE.MeshStandardMaterial({ map: pressbyranTex(h.entre), roughness: 0.5 })); sp.position.set(0, 3.37, zf + 0.04); add(sp, false); }
  // trappa med vilplan, vangar och ledstång
  { const sw = 5.8; const ys = (y) => (y - yb) / 2 + yb;
    box(0, ys(steg), zf + 0.45, sw, steg - yb, 0.9, '#a3a099');
    for (let k2 = 1; k2 <= 4; k2++) { const top = steg - k2 * 0.17; const d2 = 0.9 + k2 * 0.3; box(0, ys(top), zf + d2 / 2, sw, top - yb, d2, k2 % 2 ? '#9d9a93' : '#a6a39c'); }
    for (const s2 of [-1, 1]) { box(s2 * (sw / 2 + 0.17), ys(steg + 0.22), zf + 0.6, 0.34, steg + 0.22 - yb, 1.2, '#8f8c86'); box(s2 * (sw / 2 + 0.17), ys(0.5), zf + 1.6, 0.34, 0.5 - yb, 0.9, '#8f8c86'); }
    for (const du of [-0.08, 0.08]) { box(du, steg + 0.45, zf + 0.35, 0.05, 0.9, 0.05, '#1c1c1c'); box(du, 0.45, zf + 2.0, 0.05, 0.9, 0.05, '#1c1c1c'); }
    for (const du of [-0.08, 0.08]) box(du, (steg + 0.9 + 0.9) / 2 + 0.02, zf + 1.18, 0.05, 0.05, 1.72, '#1c1c1c', Math.atan2(steg, 1.65));
    // Pressbyråns gula gatupratare på vilplanet
    for (const s2 of [-1, 1]) box(-2.1, steg + 0.45, zf + 0.42 + s2 * 0.12, 0.55, 0.9, 0.04, '#f2c414', s2 * 0.2);
    // små trappor till flygelns dörrar
    for (const u of [-10.3, 9.7]) for (let k2 = 0; k2 < 4; k2++) { const top = steg - k2 * 0.17; box(u, ys(top), hD + 0.25 + k2 * 0.15, 2.0, top - yb, 0.5 + k2 * 0.3, '#9d9a93'); }
  }
  // bänkar, papperskorgar, lyktor och vimplar
  for (const u of [-7.0, 6.6]) { const v = hD + 0.65; box(u, 0.45, v, 1.9, 0.06, 0.46, '#a8774a'); box(u, 0.74, v - 0.24, 1.9, 0.36, 0.05, '#a8774a', -0.12);
    for (const s2 of [-0.75, 0.75]) box(u + s2, 0.22, v, 0.14, 0.44, 0.52, '#d8d5cc'); }
  parts.push({ g: new THREE.CylinderGeometry(0.28, 0.25, 0.85, 14), m: M4(3.75, 0.42, zf + 0.35), c: C('#8b8c88') });
  parts.push({ g: new THREE.CylinderGeometry(0.22, 0.22, 0.8, 12), m: M4(5.6, 0.4, hD + 0.45), c: C('#222') });
  const lykta = (u, y, v) => { box(u, y + 0.25, v + 0.3, 0.05, 0.05, 0.6, '#1c1c1c'); box(u, y + 0.05, v + 0.12, 0.04, 0.4, 0.04, '#1c1c1c', 0.6);
    box(u, y - 0.08, v + 0.58, 0.24, 0.34, 0.24, '#202020'); box(u, y - 0.08, v + 0.58, 0.18, 0.26, 0.26, '#f3e3a8'); box(u, y + 0.13, v + 0.58, 0.3, 0.06, 0.3, '#202020'); };
  lykta(-4.55, 4.9, zf); lykta(4.55, 4.9, zf); lykta(-14, 4.3, hD); lykta(13.2, 4.3, hD);
  box(-5.45, 3.65, hD + 0.4, 0.34, 0.8, 0.02, '#c8302a'); box(-5.45, 4.12, hD + 0.25, 0.04, 0.04, 0.5, '#1c1c1c');
  box(5.45, 3.65, hD + 0.4, 0.34, 0.8, 0.02, '#2f4fa8'); box(5.45, 4.12, hD + 0.25, 0.04, 0.04, 0.5, '#1c1c1c');
  add(new THREE.Mesh(bake(parts), matDetalj));
  h.top = gF + yr + 6.8;
}

// ---- huset med Gnesta Indiska: fönsterband, tegelgavlar, uteservering (efter foto) ----
function indiskaSkyltTex() {
  return canvasTex(1024, 128, (g, W, Hh) => {
    g.fillStyle = '#f7f7f4'; g.fillRect(0, 0, W, Hh); g.strokeStyle = '#c9c9c4'; g.lineWidth = 4; g.strokeRect(2, 2, W - 4, Hh - 4);
    g.font = 'italic bold 80px "Trebuchet MS", Arial, sans-serif'; g.textBaseline = 'alphabetic'; g.textAlign = 'left';
    const a = 'Gnesta ', b = 'Indiska'; const wa = g.measureText(a).width, wb = g.measureText(b).width; const x0 = (W - wa - wb) / 2;
    g.fillStyle = '#22356b'; g.fillText(a, x0, 84); g.fillStyle = '#d0262f'; g.fillText(b, x0 + wa, 84);
    g.font = 'bold 20px Arial, sans-serif'; g.fillStyle = '#22356b'; g.textAlign = 'center'; g.fillText('R E S T A U R A N G', W / 2, 116);
  }, true, false);
}
const IND = { y1: 9.3, Y0: -1.5 };
function indiskaTex(len, butik, ru) {
  const ppm = 40, y1 = IND.y1, y0 = IND.Y0; const Wp = Math.ceil(len * ppm), Hp = Math.ceil((y1 - y0) * ppm);
  return canvasTex(Wp, Hp, (g) => {
    const X = (u) => u * ppm, Y = (y) => (y1 - y) * ppm; const mid = len / 2;
    g.fillStyle = '#e4e3dd'; g.fillRect(0, 0, Wp, Hp);
    g.fillStyle = 'rgba(0,0,0,0.06)'; for (const yy of [3.85, 6.25, 8.5]) g.fillRect(0, Y(yy), Wp, 1.5);
    const band = (ya, yb2) => { glasYta(g, 0, Y(yb2), Wp, (yb2 - ya) * ppm); g.fillStyle = '#ecebe5';
      for (let u = 1.25; u < len; u += 1.25) g.fillRect(X(u - 0.04), Y(yb2), 0.08 * ppm, (yb2 - ya) * ppm);
      g.fillRect(0, Y(ya + 0.05), Wp, 0.07 * ppm); g.fillRect(0, Y(yb2), Wp, 0.06 * ppm); };
    band(4.3, 5.8); band(6.7, 8.2);
    g.fillStyle = '#efeee8'; for (let u = 2.5; u < len - 0.5; u += 2.5) g.fillRect(X(u - 0.15), Y(8.2), 0.3 * ppm, (8.2 - 3.45) * ppm);
    g.fillStyle = '#7e3527'; g.fillRect(0, 0, Wp, Y(8.8));
    if (butik) {
      glasYta(g, 0, Y(2.8), Wp, 2.8 * ppm); g.fillStyle = 'rgba(20,24,28,0.45)'; g.fillRect(0, Y(2.8), Wp, 2.8 * ppm);
      g.fillStyle = '#9aa0a3'; for (let u = 0; u < len; u += 1.6) g.fillRect(X(u), Y(2.8), 0.07 * ppm, 2.8 * ppm); g.fillRect(0, Y(2.3), Wp, 0.06 * ppm);
      g.fillStyle = '#3cae4a'; g.fillRect(X(mid + ru * 3.7 - 0.55), Y(2.8), 1.1 * ppm, 2.8 * ppm);
      const du = mid + ru * 6.3; g.fillStyle = '#f2f2ee'; g.fillRect(X(du - 0.6), Y(2.5), 1.2 * ppm, 2.5 * ppm); glasYta(g, X(du - 0.45), Y(2.35), 0.9 * ppm, 2.2 * ppm);
      g.fillStyle = '#d4d5d1'; g.fillRect(0, Y(3.45), Wp, 0.65 * ppm); g.fillStyle = '#8f9190'; g.fillRect(0, Y(2.84), Wp, 0.05 * ppm);
    } else { g.fillStyle = '#e4e3dd'; g.fillRect(0, Y(3.45), Wp, 3.45 * ppm); band(0.9, 2.4); }
    for (const [a, b] of [[0, 0.9], [len - 0.9, len]]) tegel(g, X(a), 0, 0.9 * ppm, Hp, ppm, '#9a4a35', 9);
    g.fillStyle = '#8d8d88'; g.fillRect(0, Y(0), Wp, Hp - Y(0));
  }, true, false);
}
const texTegelMork = canvasTex(256, 256, (g, W, Hh) => tegel(g, 0, 0, W, Hh, 128, '#9a4a35', 4), true, true);
function buildIndiska(h) {
  const bi = h.idx; const R = husRam(h, h.fasad.mot); const { L, D, W2 } = R; const hL = L / 2, hD = D / 2;
  const ru = ((h.fasad.vag[0] - R.x) * R.ax[0] + (h.fasad.vag[1] - R.z) * R.ax[1]) >= 0 ? 1 : -1;
  const gF = H(...W2(0, hD + 2)) + 0.05; h.g0 = gF;
  let gmin = Infinity; for (const [u, v] of [[-hL, -hD], [hL, -hD], [hL, hD], [-hL, hD], [0, 0]]) gmin = Math.min(gmin, H(...W2(u, v)));
  const yb = Math.min(IND.Y0, gmin - gF - 0.4); const y1 = IND.y1;
  const grp = husGrupp(R, gF);
  const add = (m, cast = true) => { m.castShadow = cast; m.receiveShadow = true; m.userData.bidx = bi; world.pickables.push(m); grp.add(m); return m; };
  const parts = []; const box = (u, y, v, w, hh, d, col, rx = 0, rz = 0, ry = 0) => parts.push({ g: new THREE.BoxGeometry(w, hh, d), m: M4(u, y, v, ry, 1, 1, 1, rx, rz), c: C(col) });
  const mf = (t) => new THREE.MeshStandardMaterial({ map: t, roughness: 0.8, side: THREE.DoubleSide });
  add(vaggPlan([-hL, hD], [hL, hD], yb, y1, IND.Y0, y1, mf(indiskaTex(L, true, ru))));
  add(vaggPlan([hL, -hD], [-hL, -hD], yb, y1, IND.Y0, y1, mf(indiskaTex(L, false, -ru))));
  for (const sg of [-1, 1]) { const t = texTegelMork.clone(); t.repeat.set(D / 2, (y1 - yb) / 2); t.needsUpdate = true; add(vaggPlan([sg * hL, -hD], [sg * hL, hD], yb, y1, yb, y1, mf(t))); }
  // platt tak med rödbrun plåtkant
  box(0, y1 - 0.25, 0, L, 0.2, D, '#5d6062');
  for (const sg of [-1, 1]) { box(0, y1 - 0.2, sg * (hD + 0.06), L + 0.24, 0.5, 0.12, '#7e3527'); box(sg * (hL + 0.06), y1 - 0.2, 0, 0.12, 0.5, D + 0.24, '#7e3527'); }
  box(-ru * 4, y1 + 0.3, -1.5, 1.2, 0.8, 1.2, '#8c8f91');
  // skylt, blå markis
  { const s = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 0.65), new THREE.MeshStandardMaterial({ map: indiskaSkyltTex(), roughness: 0.5 })); s.position.set(-ru * 4.5, 3.12, hD + 0.05); add(s, false); }
  { const du = ru * 6.3; box(du, 3.02, hD + 0.55, 2.7, 0.05, 1.15, '#1f4fa0', 0.38); box(du, 2.7, hD + 1.08, 2.7, 0.3, 0.03, '#1f4fa0');
    for (const s2 of [-1, 1]) box(du + s2 * 1.33, 2.85, hD + 0.55, 0.03, 0.4, 1.05, '#1f4fa0'); }
  // uteservering på trädäck med svart räcke
  { const ua = Math.min(-ru * 12.5, ru * 2.0), ub = Math.max(-ru * 12.5, ru * 2.0), dz = 3.4, top = 0.32;
    const yd = Math.min(-0.3, H(...W2((ua + ub) / 2, hD + dz)) - gF - 0.2);
    box((ua + ub) / 2, (top + yd) / 2, hD + dz / 2, ub - ua, top - yd, dz, '#7d5f43');
    for (let u = ua + 0.3; u < ub; u += 0.6) box(u, top + 0.005, hD + dz / 2, 0.02, 0.01, dz, '#5f4630');
    const gap = ru * 0.9; const ze = hD + dz - 0.05;
    for (let u = ua; u <= ub + 0.01; u += 1.45) { if (Math.abs(u - gap) < 0.7) continue; box(u, top + 0.5, ze, 0.06, 1.0, 0.06, '#1c1c1c'); }
    for (const [a, b] of [[ua, gap - 0.7], [gap + 0.7, ub]]) for (const hy of [0.55, 1.0]) box((a + b) / 2, top + hy, ze, b - a, 0.05, 0.05, '#1c1c1c');
    for (const ue of [ua, ub]) for (const hy of [0.55, 1.0]) box(ue, top + hy, hD + dz / 2, 0.05, 0.05, dz, '#1c1c1c');
    for (let u = ua + 1.4; u < ub - 0.8; u += 2.3) { if (Math.abs(u - gap) < 1.0) continue; const z = hD + 1.75;
      box(u, top + 0.74, z, 0.75, 0.04, 0.75, '#222'); box(u, top + 0.37, z, 0.06, 0.74, 0.06, '#222');
      for (const s2 of [-1, 1]) { box(u, top + 0.45, z + s2 * 0.62, 0.45, 0.05, 0.42, '#3a3a3a'); box(u, top + 0.7, z + s2 * 0.85, 0.45, 0.45, 0.05, '#3a3a3a'); } }
    for (const u of [-ru * 9.0, -ru * 3.6]) { box(u, top + 1.4, hD + 1.75, 0.06, 2.8, 0.06, '#d8d8d2');
      parts.push({ g: new THREE.ConeGeometry(0.3, 1.9, 10), m: M4(u, top + 1.95, hD + 1.75), c: C('#2f5b3a') }); }
    for (const u of [ua + 0.4, ub - 0.4]) { box(u, top + 0.25, hD + dz - 0.4, 0.6, 0.5, 0.6, '#5b5b58'); parts.push({ g: new THREE.IcosahedronGeometry(0.42, 1), m: M4(u, top + 0.75, hD + dz - 0.4), c: C('#4f8a3a') }); } }
  add(new THREE.Mesh(bake(parts), matDetalj));
  h.top = gF + y1 + 1;
}

// ---- detaljer runt Tingshusbacken: berghäll, stort lövträd, övergångsställen ----
const texOvergang = canvasTex(128, 128, (g, W, Hh) => {
  g.fillStyle = '#1d5fb0'; g.fillRect(0, 0, W, Hh); g.strokeStyle = '#fff'; g.lineWidth = 5; g.strokeRect(5, 5, W - 10, Hh - 10);
  g.fillStyle = '#fff'; g.beginPath(); g.moveTo(64, 16); g.lineTo(114, 106); g.lineTo(14, 106); g.closePath(); g.fill();
  g.fillStyle = '#111'; g.beginPath(); g.arc(66, 46, 6, 0, 7); g.fill(); g.strokeStyle = '#111'; g.lineWidth = 6; g.lineCap = 'round';
  for (const [a, b, c, d] of [[65, 54, 61, 76], [61, 76, 52, 94], [61, 76, 72, 93], [64, 60, 52, 70], [64, 60, 76, 68]]) { g.beginPath(); g.moveTo(a, b); g.lineTo(c, d); g.stroke(); }
  for (let x = 30; x < 100; x += 14) g.fillRect(x, 98, 8, 4);
}, true, false);
function buildBerg(bg) {
  const c = Math.cos(bg.rot), s = Math.sin(bg.rot); const r = mulberry32(Math.round(bg.x * 31 + bg.z * 17));
  const nb = Math.ceil(bg.b / 0.55), nd = Math.ceil(bg.d / 0.55);
  const hgt = (a, b) => { const e = Math.pow(Math.pow(Math.abs(a), 4) + Math.pow(Math.abs(b), 4), 0.25); const t = Math.min(1, Math.max(0, (1 - e) / 0.32)); const m = t * t * (3 - 2 * t);
    const n = 0.09 * Math.sin(a * 7.1 + b * 4.3) + 0.06 * Math.sin(a * 15.3 - b * 9.1) + 0.05 * Math.cos(b * 11 + a * 5); return bg.h * m * (0.88 + n + 0.12 * a); };
  const V = []; for (let j = 0; j <= nd; j++) { const row = []; for (let i = 0; i <= nb; i++) { const a = -1 + 2 * i / nb, b = -1 + 2 * j / nd;
    const edge = Math.abs(a) > 0.999 || Math.abs(b) > 0.999; const lx = a * bg.b / 2 + (edge ? 0 : (r() - 0.5) * 0.3), lz = b * bg.d / 2 + (edge ? 0 : (r() - 0.5) * 0.3);
    const wx = bg.x + lx * c - lz * s, wz = bg.z + lx * s + lz * c; row.push([wx, H(wx, wz) - 0.35 + hgt(a, b), wz, hgt(a, b)]); } V.push(row); }
  const pos = [], col = []; const base = new THREE.Color('#807c75'), lav = new THREE.Color('#7f8a62'), mork = new THREE.Color('#5d5a55');
  const pc = (p) => { const k = r(); const cc = base.clone().multiplyScalar(0.85 + k * 0.3); if (r() < 0.12 && p[3] > bg.h * 0.6) cc.lerp(lav, 0.6); if (p[3] < bg.h * 0.25) cc.lerp(mork, 0.3); return cc; };
  for (let j = 0; j < nd; j++) for (let i = 0; i < nb; i++) { const a = V[j][i], b = V[j][i + 1], c2 = V[j + 1][i + 1], d = V[j + 1][i];
    for (const tri of [[a, b, c2], [a, c2, d]]) { const cc = pc(tri[0]); for (const q of tri) { pos.push(q[0], q[1], q[2]); col.push(cc.r, cc.g, cc.b); } } }
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); geo.computeVertexNormals();
  const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, flatShading: true, side: THREE.DoubleSide })); m.castShadow = true; m.receiveShadow = true; scene.add(m);
  const parts = [];
  for (let k = 0; k < (bg.trad || 0); k++) { const a = (r() - 0.5) * 1.1, b = (r() - 0.5) * 1.0; const lx = a * bg.b / 2, lz = b * bg.d / 2; const wx = bg.x + lx * c - lz * s, wz = bg.z + lx * s + lz * c; const y = H(wx, wz) - 0.35 + hgt(a, b); const sc = 0.8 + r() * 0.5;
    parts.push({ g: new THREE.CylinderGeometry(0.15, 0.22, 3.5 * sc, 7), m: M4(wx, y + 1.75 * sc, wz), c: C('#5a4a3a') });
    for (let q = 0; q < 4; q++) parts.push({ g: new THREE.IcosahedronGeometry((1.6 + r()) * sc, 1), m: M4(wx + (r() - 0.5) * 1.6, y + (4.2 + r() * 1.5) * sc, wz + (r() - 0.5) * 1.6, r() * 6, 1, 0.85, 1), c: C(q % 2 ? '#4f7a32' : '#5f8c3c') }); }
  if (parts.length) { const mt = new THREE.Mesh(bake(parts), matDetalj); mt.castShadow = true; scene.add(mt); }
}
function buildDetaljer() {
  const DT = K.detaljer; if (!DT) return;
  for (const bg of DT.berg || []) buildBerg(bg);
  const parts = [];
  for (const t of DT.storaTrad || []) { const y = H(t.x, t.z); const r = mulberry32(Math.round(t.x * 7 + t.z * 3));
    parts.push({ g: new THREE.CylinderGeometry(0.35, 0.6, t.h * 0.5, 9), m: M4(t.x, y + t.h * 0.25, t.z), c: C('#5a4a3a') });
    for (let k = 0; k < 11; k++) { const a = r() * 6.28, rr = r() * t.r * 0.55; const s = t.r * (0.42 + r() * 0.22);
      parts.push({ g: new THREE.IcosahedronGeometry(s, 1), m: M4(t.x + Math.cos(a) * rr, y + t.h * (0.55 + r() * 0.25), t.z + Math.sin(a) * rr, r() * 6, 1, 0.85, 1), c: C(k % 3 ? '#4d7a30' : '#5c8a3a') }); }
    parts.push({ g: new THREE.IcosahedronGeometry(t.r * 0.5, 1), m: M4(t.x, y + t.h * 0.88, t.z, 0, 1, 0.8, 1), c: C('#557f34') }); }
  // uteserveringar med röda parasoller
  for (const u of DT.uteplatser || []) { const c = Math.cos(u.rot), s = Math.sin(u.rot); const P = (a, b) => [u.x + a * c - b * s, u.z + a * s + b * c];
    for (let a = -u.b / 2 + 1.3; a <= u.b / 2 - 1.0; a += 2.7) for (let b = -u.d / 2 + 1.3; b <= u.d / 2 - 1.0; b += 2.6) { const [x, z] = P(a, b); const y = H(x, z);
      parts.push({ g: new THREE.BoxGeometry(1.5, 0.06, 0.75), m: M4(x, y + 0.74, z, -u.rot), c: C('#7a5a3c') });
      for (const sb of [-0.6, 0.6]) { const q = P(a, b + sb); parts.push({ g: new THREE.BoxGeometry(1.5, 0.05, 0.3), m: M4(q[0], y + 0.45, q[1], -u.rot), c: C('#7a5a3c') }); }
      for (const sa of [-0.6, 0.6]) { const q = P(a + sa, b); parts.push({ g: new THREE.BoxGeometry(0.08, 0.74, 1.5), m: M4(q[0], y + 0.37, q[1], -u.rot), c: C('#5f452d') }); }
      parts.push({ g: new THREE.CylinderGeometry(0.03, 0.03, 2.4, 6), m: M4(x, y + 1.2, z), c: C('#e9e7e0') });
      parts.push({ g: new THREE.ConeGeometry(0.3, 1.8, 10), m: M4(x, y + 2.0, z), c: C(u.parasoll || '#d0262f') }); }
    for (const sb of [-1, 1]) for (let a = -u.b / 2; a <= u.b / 2; a += 1.5) { const [x, z] = P(a, sb * (u.d / 2 + 0.3)); const y = H(x, z);
      parts.push({ g: new THREE.BoxGeometry(1.2, 0.4, 0.45), m: M4(x, y + 0.2, z, -u.rot), c: C('#8a6a4a') });
      for (let k = 0; k < 3; k++) parts.push({ g: new THREE.SphereGeometry(0.18, 7, 5), m: M4(x + (k - 1) * 0.35 * c, y + 0.5, z + (k - 1) * 0.35 * s), c: C(k % 2 ? '#f08a24' : '#f2c414') }); } }
  // flaggstänger, skyltställ, bänkar, papperskorgar och rabatter
  const flaggDukar = [];
  for (const f of DT.flaggstanger || []) { const y = H(f.x, f.z);
    parts.push({ g: new THREE.CylinderGeometry(0.05, 0.08, f.h, 8), m: M4(f.x, y + f.h / 2, f.z), c: C('#f2f2ee') }); parts.push({ g: new THREE.SphereGeometry(0.1, 8, 6), m: M4(f.x, y + f.h + 0.05, f.z), c: C('#d9b23a') });
    if (f.flagga) flaggDukar.push({ x: f.x, y: y + f.h - 0.95, z: f.z, farg: f.flagga }); else parts.push({ g: new THREE.BoxGeometry(0.08, 2.2, 0.08), m: M4(f.x + 0.06, y + f.h - 1.3, f.z), c: C('#eef0f0') }); }
  for (const f of flaggDukar) { const m = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 1.2, 6, 1), new THREE.MeshStandardMaterial({ color: f.farg, roughness: 0.8, side: THREE.DoubleSide }));
    const pos = m.geometry.attributes.position; for (let i = 0; i < pos.count; i++) pos.setZ(i, Math.sin((pos.getX(i) + 0.95) * 2.4) * 0.12 * (pos.getX(i) + 0.95)); m.geometry.computeVertexNormals();
    m.position.set(f.x + 0.95, f.y, f.z); m.rotation.y = 0.4; m.castShadow = true; scene.add(m); }
  for (const s of DT.skyltstall || []) { const y = H(s.x, s.z); const c = Math.cos(s.rot), sn = Math.sin(s.rot);
    for (const o of [-0.95, 0.95]) parts.push({ g: new THREE.BoxGeometry(0.12, 2.3, 0.12), m: M4(s.x + c * o, y + 1.15, s.z - sn * o, s.rot), c: C('#2e6b45') });
    parts.push({ g: new THREE.BoxGeometry(1.8, 1.6, 0.06), m: M4(s.x, y + 1.35, s.z, s.rot), c: C('#f4f4f0') });
    const sk = new THREE.Mesh(new THREE.PlaneGeometry(1.7, 0.7), new THREE.MeshStandardMaterial({ map: kommunSkyltTex(), roughness: 0.6 })); sk.position.set(s.x - sn * 0.04, y + 1.75, s.z - c * 0.04); sk.rotation.y = s.rot + Math.PI; scene.add(sk);
    for (let k = 0; k < 4; k++) parts.push({ g: new THREE.BoxGeometry(1.55, 0.06, 0.07), m: M4(s.x - sn * 0.04, y + 1.25 - k * 0.2, s.z - c * 0.04, s.rot), c: C(k === 3 ? '#e39a2c' : '#c9cbc6') }); }
  for (const b of DT.bankar || []) { const y = H(b.x, b.z); const c = Math.cos(b.rot), sn = Math.sin(b.rot);
    parts.push({ g: new THREE.BoxGeometry(1.8, 0.06, 0.45), m: M4(b.x, y + 0.45, b.z, b.rot), c: C('#6d7276') });
    parts.push({ g: new THREE.BoxGeometry(1.8, 0.4, 0.05), m: M4(b.x + sn * 0.22, y + 0.72, b.z + c * 0.22, b.rot), c: C('#6d7276') });
    for (const o of [-0.8, 0.8]) parts.push({ g: new THREE.BoxGeometry(0.06, 0.45, 0.5), m: M4(b.x + c * o, y + 0.22, b.z - sn * o, b.rot), c: C('#4a4e52') }); }
  for (const d of DT.dorrar || []) { const y = H(d.x, d.z); const sx = Math.sin(d.rot), cz = Math.cos(d.rot); const Q = (o) => [d.x + sx * o, d.z + cz * o];
    { const q = Q(0.05); parts.push({ g: new THREE.BoxGeometry(d.w + 0.3, d.h + 0.2, 0.08), m: M4(q[0], y + 0.45 + (d.h + 0.2) / 2, q[1], d.rot), c: C('#f1f0ec') }); }
    { const q = Q(0.1); parts.push({ g: new THREE.BoxGeometry(d.w, d.h, 0.04), m: M4(q[0], y + 0.45 + d.h / 2, q[1], d.rot), c: C('#3a4a56') }); parts.push({ g: new THREE.BoxGeometry(0.06, d.h, 0.06), m: M4(q[0], y + 0.45 + d.h / 2, q[1], d.rot), c: C('#f1f0ec') }); }
    for (let k = 0; k < 3; k++) { const q = Q(0.5 + k * 0.35); parts.push({ g: new THREE.BoxGeometry(d.w + 1.6, 0.45 - k * 0.15 + 0.4, 0.36 + (2 - k) * 0.0), m: M4(q[0], y + (0.45 - k * 0.15 - 0.4) / 2, q[1], d.rot), c: C(k % 2 ? '#a9a6a0' : '#b3b0aa') }); } }
  for (const p of DT.papperskorgar || []) { const y = H(p.x, p.z); parts.push({ g: new THREE.CylinderGeometry(0.24, 0.22, 0.85, 14), m: M4(p.x, y + 0.42, p.z), c: C('#9aa0a3') }); }
  for (const rb of DT.rabatter || []) { const y = H(rb.x, rb.z); const r = mulberry32(Math.round(rb.x * 3 + rb.z));
    parts.push({ g: new THREE.CylinderGeometry(rb.r, rb.r, 0.2, 18), m: M4(rb.x, y + 0.1, rb.z, 0, 1, 1, 0.6), c: C('#5a4636') });
    for (let k = 0; k < 26; k++) { const a = r() * 6.28, d = Math.sqrt(r()) * rb.r * 0.9; parts.push({ g: new THREE.SphereGeometry(0.17, 6, 5), m: M4(rb.x + Math.cos(a) * d, y + 0.3, rb.z + Math.sin(a) * d * 0.6), c: C(k % 3 ? rb.farg : '#3f7a34') }); } }
  // fristående tegelskorstenar
  for (const sk of DT.skorstenar || []) { const y = H(sk.x, sk.z) - 0.3;
    parts.push({ g: new THREE.CylinderGeometry(sk.r * 1.25, sk.r * 1.3, 1.6, 18), m: M4(sk.x, y + 0.8, sk.z), c: C('#d8d6cf') });
    parts.push({ g: new THREE.CylinderGeometry(sk.r * 0.78, sk.r, sk.h, 18), m: M4(sk.x, y + sk.h / 2, sk.z), c: C('#9c4a33') });
    parts.push({ g: new THREE.CylinderGeometry(sk.r * 0.85, sk.r * 0.82, 1.4, 18), m: M4(sk.x, y + sk.h + 0.6, sk.z), c: C('#b9bec2') }); }
  const skyltar = [], ranor = [];
  for (const o of DT.overgangar || []) {
    const g = gator.find(q => q.osm === o.osm); if (!g || g.sm.length < 2) continue;
    let bi = 0, bd = Infinity; g.sm.forEach((p, i) => { const d = Math.hypot(p.x - o.nara[0], p.z - o.nara[1]); if (d < bd) { bd = d; bi = i; } });
    const p = g.sm[bi]; const nx = -p.tz, nz = p.tx; const half = g.bredd / 2; const ang = Math.atan2(p.tx, p.tz);
    for (let lat = -half + 0.5; lat <= half - 0.45; lat += 1.0) { const Q = []; for (const [dl, ds] of [[-0.25, -1.5], [0.25, -1.5], [0.25, 1.5], [-0.25, 1.5]]) { const x = p.x + nx * (lat + dl) + p.tx * ds, z = p.z + nz * (lat + dl) + p.tz * ds; Q.push([x, roadY(g, x, z, bi, p) + 0.03, z]); } ranor.push([Q[0], Q[1], Q[2], Q[3], [0, 0], [1, 0], [1, 1], [0, 1]]); }
    for (const sg of [-1, 1]) { const lat = sg * (half + (g.trottoar || 1) * 0.6); const x = p.x + nx * lat - p.tx * 1.8, z = p.z + nz * lat - p.tz * 1.8; const y = H(x, z);
      parts.push({ g: new THREE.CylinderGeometry(0.04, 0.04, 2.6, 6), m: M4(x, y + 1.3, z), c: C('#9a9da0') });
      for (const dir of [0, Math.PI]) skyltar.push({ x: x - Math.sin(ang + dir) * 0.04, y: y + 2.3, z: z - Math.cos(ang + dir) * 0.04, ry: ang + dir + Math.PI }); }
  }
  if (parts.length) { const m = new THREE.Mesh(bake(parts), matDetalj); m.castShadow = true; m.receiveShadow = true; scene.add(m); }
  if (ranor.length) { const m = new THREE.Mesh(quadGeo(ranor), matLinje.clone()); m.material.side = THREE.DoubleSide; m.receiveShadow = true; scene.add(m); }
  const sm = new THREE.MeshStandardMaterial({ map: texOvergang, roughness: 0.5 });
  for (const s of skyltar) { const m = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.6), sm); m.position.set(s.x, s.y, s.z); m.rotation.y = s.ry; scene.add(m); }
}

// ---- Stora Hotellet: runt hörntorn, svängd gavel, balkonger, valmat plåttak (efter foto) ----
const HOT_GRON = '#3d5b4b';
function hotFonster(g, X, Y, ppm, u0, u1, y0, y1, bage) {
  g.fillStyle = '#f6f0dc'; g.fillRect(X(u0 - 0.14), Y(y1 + 0.14), (u1 - u0 + 0.28) * ppm, (y1 - y0 + 0.28) * ppm);
  const path = () => { g.beginPath(); if (bage) { const r = (u1 - u0) / 2; g.moveTo(X(u0), Y(y0)); g.lineTo(X(u0), Y(y1 - r)); g.arc(X(u0 + r), Y(y1 - r), r * ppm, Math.PI, 0); g.lineTo(X(u1), Y(y0)); g.closePath(); } else g.rect(X(u0), Y(y1), (u1 - u0) * ppm, (y1 - y0) * ppm); };
  g.fillStyle = HOT_GRON; path(); g.fill(); g.save(); path(); g.clip(); glasYta(g, X(u0 + 0.08), Y(y1 - 0.08), (u1 - u0 - 0.16) * ppm, (y1 - y0 - 0.16) * ppm); g.restore();
  g.fillStyle = HOT_GRON; g.fillRect(X((u0 + u1) / 2 - 0.035), Y(y1), 0.07 * ppm, (y1 - y0) * ppm); g.fillRect(X(u0), Y(y0 + (y1 - y0) * 0.66), (u1 - u0) * ppm, 0.07 * ppm);
}
function hotellTex(len, F) {
  const ppm = 40, top = F.top, yb = -0.8; const Wp = Math.ceil(len * ppm), Hp = Math.ceil((top - yb) * ppm);
  return canvasTex(Wp, Hp, (g) => {
    const X = (u) => u * ppm, Y = (y) => (top - y) * ppm;
    g.fillStyle = '#eee2bd'; g.fillRect(0, 0, Wp, Hp);
    const rr = mulberry32(8); g.fillStyle = 'rgba(120,100,60,0.05)'; for (let k = 0; k < 900; k++) g.fillRect(rr() * Wp, rr() * Hp, 3, 3);
    g.fillStyle = '#6c6e6f'; g.fillRect(0, Y(0.75), Wp, Hp - Y(0.75));
    for (let f = 1; f < F.van; f++) { g.fillStyle = '#e4d6ae'; g.fillRect(0, Y(f * F.fh + 0.12), Wp, 0.2 * ppm); }
    g.fillStyle = '#d9c99c'; g.fillRect(0, 0, Wp, 0.45 * ppm);
    for (let u = 2.0; u < len - 1.0; u += 2.9) {
      if (Math.abs(u - F.ug) < 3.9) continue;
      const bal = F.balk.some(b => Math.abs(u - b) < 1.3);
      hotFonster(g, X, Y, ppm, u - 0.8, u + 0.8, 0.95, 2.95, true);
      if (rr() < 0.6) { g.fillStyle = '#f2c414'; g.fillRect(X(u - 0.7), Y(1.25), 1.4 * ppm, 0.25 * ppm); }
      for (let f = 1; f < F.van; f++) { const y0 = f * F.fh + (bal ? 0.05 : 0.8), y1 = f * F.fh + 2.55; hotFonster(g, X, Y, ppm, u - 0.55, u + 0.55, y0, y1, false); }
    }
    // gavelpartiet: fönsterpar
    for (let f = 0; f < F.van; f++) for (const du of [-1.1, 1.1]) hotFonster(g, X, Y, ppm, F.ug + du - 0.5, F.ug + du + 0.5, f * F.fh + (f ? 0.8 : 0.95), f * F.fh + 2.6, f === 0);
  }, true, false);
}
function hotTornTex(r, F, nv) {
  const omk = 2 * Math.PI * r, ppm = 40, hh = nv * F.fh + 0.8; const Wp = Math.ceil(omk * ppm), Hp = Math.ceil(hh * ppm);
  return canvasTex(Wp, Hp, (g) => {
    const X = (u) => u * ppm, Y = (y) => (hh - 0.8 - y) * ppm;
    g.fillStyle = '#eee2bd'; g.fillRect(0, 0, Wp, Hp); g.fillStyle = '#6c6e6f'; g.fillRect(0, Y(0.75), Wp, Hp - Y(0.75));
    for (let f = 1; f < nv; f++) { g.fillStyle = '#e4d6ae'; g.fillRect(0, Y(f * F.fh + 0.12), Wp, 0.2 * ppm); }
    for (let u = omk / 12; u < omk; u += omk / 6) for (let f = 0; f < nv; f++) hotFonster(g, X, Y, ppm, u - 0.55, u + 0.55, f * F.fh + (f ? 0.8 : 0.95), f * F.fh + 2.6, f === 0);
  }, true, false);
}
function buildHotell(h) {
  const F = h.fasad, bi = h.idx; const A = F.a, B = F.b; const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const dx = (B[0] - A[0]) / L, dz = (B[1] - A[1]) / L; let nx = -dz, nz = dx; if ((F.vag[0] - A[0]) * nx + (F.vag[1] - A[1]) * nz < 0) { nx = -nx; nz = -nz; }
  const P = (u, v) => [A[0] + dx * u + nx * v, A[1] + dz * u + nz * v]; const ry = Math.atan2(nx, nz); const g = h.g0; const top = h.y1;
  const pick = (m, cast = true) => { m.userData.bidx = bi; world.pickables.push(m); m.castShadow = cast; m.receiveShadow = true; scene.add(m); return m; };
  const ug = (F.gavel - A[0]) / dx; const balk = [10.2, 13.4, 24.6, 27.4].filter(u => u < L - 1.5);
  const FF = { top: top - g, van: h.van, fh: h.fh, ug, balk };
  // fasaden mot gatan
  { const t = hotellTex(L, FF); if (nz * dx - nx * dz < 0) { t.repeat.x = -1; t.offset.x = 1; } const c = P(L / 2, 0.07); const m = new THREE.Mesh(new THREE.PlaneGeometry(L, top - g + 0.8), new THREE.MeshStandardMaterial({ map: t, roughness: 0.85 }));
    m.position.set(c[0], (top + g - 0.8) / 2, c[1]); m.rotation.y = ry; pick(m, false); }
  const parts = []; const box = (u, v, y, w, hh, d, col, rx = 0, rz = 0) => { const c = P(u, v); parts.push({ g: new THREE.BoxGeometry(w, hh, d), m: M4(c[0], y, c[1], ry, 1, 1, 1, rx, rz), c: C(col) }); };
  // takfotslist
  box(L / 2, 0.25, top - 0.15, L + 0.2, 0.3, 0.5, '#e1d3a8');
  // balkonger med svarta smidesräcken på våning 2–4
  for (const ub of balk) for (let f = 1; f < h.van; f++) { const y = g + f * h.fh; const w = ub < ug ? 3.2 : 2.2;
    box(ub, 0.65, y - 0.08, w, 0.16, 1.2, '#d6ccb0');
    for (let k = 0; k <= Math.round(w / 0.14); k++) box(ub - w / 2 + k * w / Math.round(w / 0.14), 1.22, y + 0.5, 0.025, 0.95, 0.025, '#1b1b1b');
    for (const s2 of [-1, 1]) for (let k = 0; k <= 7; k++) box(ub + s2 * w / 2, 0.1 + k * 0.16, y + 0.5, 0.025, 0.95, 0.025, '#1b1b1b');
    box(ub, 1.22, y + 0.98, w, 0.05, 0.05, '#1b1b1b'); box(ub, 1.22, y + 0.1, w, 0.04, 0.04, '#1b1b1b');
    for (const s2 of [-1, 1]) box(ub + s2 * w / 2, 0.1 + 0.6, y + 0.98, 0.05, 0.05, 1.2, '#1b1b1b');
    for (const s2 of [-1, 1]) box(ub + s2 * (w / 2 - 0.25), 0.4, y - 0.45, 0.04, 0.04, 1.0, '#1b1b1b', 0.7); }
  // valmat plåttak över huvudkroppen
  { const D = 12.5, o = 0.45, rise = 3.4, ry0 = top, ry1 = top + rise; const r0 = 6.2, r1 = L - 6.2;
    const q = (u, v, y) => { const c = P(u, v); return [c[0], y, c[1]]; };
    const tq = [[q(-o, o, ry0), q(L + o, o, ry0), q(r1, -D / 2, ry1), q(r0, -D / 2, ry1), [0, 0], [1, 0], [1, 1], [0, 1]],
                [q(L + o, -D - o, ry0), q(-o, -D - o, ry0), q(r0, -D / 2, ry1), q(r1, -D / 2, ry1), [0, 0], [1, 0], [1, 1], [0, 1]],
                [q(-o, -D - o, ry0), q(-o, o, ry0), q(r0, -D / 2, ry1), q(r0, -D / 2, ry1), [0, 0], [1, 0], [0.5, 1], [0.5, 1]],
                [q(L + o, o, ry0), q(L + o, -D - o, ry0), q(r1, -D / 2, ry1), q(r1, -D / 2, ry1), [0, 0], [1, 0], [0.5, 1], [0.5, 1]]];
    pick(new THREE.Mesh(quadGeo(tq), new THREE.MeshStandardMaterial({ color: h.takfarg, roughness: 0.55, metalness: 0.25, side: THREE.DoubleSide })));
    for (const u of [7, 18, 26]) box(u, -D / 2 + 1.0, ry1 - 0.2, 0.8, 2.0, 0.8, '#b6a98c'); h.top = ry1 + 1; }
  // svängd gavel med fönster och rödbrun kant
  { const sh = new THREE.Shape(); const hw = 3.6, y0 = -0.6;
    sh.moveTo(-hw, y0); sh.lineTo(hw, y0); sh.lineTo(hw, 0.5); sh.bezierCurveTo(hw - 0.3, 1.9, 1.7, 1.6, 1.6, 3.2); sh.lineTo(1.6, 3.6); sh.quadraticCurveTo(1.0, 4.9, 0, 5.1);
    sh.quadraticCurveTo(-1.0, 4.9, -1.6, 3.6); sh.lineTo(-1.6, 3.2); sh.bezierCurveTo(-1.7, 1.6, -(hw - 0.3), 1.9, -hw, 0.5); sh.closePath();
    const t = canvasTex(256, 256, (gg, W, Hh) => { gg.fillStyle = '#eee2bd'; gg.fillRect(0, 0, W, Hh); }, true, false);
    const geo = new THREE.ExtrudeGeometry(sh, { depth: 0.45, bevelEnabled: false, curveSegments: 10 });
    const m = new THREE.Mesh(geo, [new THREE.MeshStandardMaterial({ color: '#eee2bd', roughness: 0.85 }), new THREE.MeshStandardMaterial({ color: '#a2493a', roughness: 0.7 })]);
    const c = P(ug, -0.1); m.position.set(c[0], top, c[1]); m.rotation.y = ry; pick(m);
    for (const du of [-0.55, 0.55]) { box(ug + du, 0.38, top + 1.6, 0.7, 1.4, 0.06, HOT_GRON); box(ug + du, 0.41, top + 1.6, 0.56, 1.24, 0.03, '#40525e'); }
    parts.push({ g: new THREE.TorusGeometry(0.42, 0.07, 6, 18), m: M4(...(() => { const c2 = P(ug, 0.38); return [c2[0], top + 3.4, c2[1]]; })(), ry), c: C(HOT_GRON) });
    parts.push({ g: new THREE.CircleGeometry(0.4, 18), m: M4(...(() => { const c2 = P(ug, 0.4); return [c2[0], top + 3.4, c2[1]]; })(), ry), c: C('#40525e') });
    box(ug, 0.15, top + 5.3, 0.12, 0.8, 0.12, '#3a3a3a'); }
  // runt hörntorn
  { const [tx, tz, r] = F.torn; const nv = h.van + 1; const hh = nv * h.fh; const t = hotTornTex(r, FF, nv);
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, hh + 0.8, 32, 1, true), new THREE.MeshStandardMaterial({ map: t, roughness: 0.85 }));
    m.position.set(tx, g - 0.8 + (hh + 0.8) / 2, tz); pick(m);
    parts.push({ g: new THREE.CylinderGeometry(r + 0.25, r + 0.25, 0.4, 32), m: M4(tx, g + hh + 0.1, tz), c: C('#e1d3a8') });
    parts.push({ g: new THREE.CylinderGeometry(r, r, 0.3, 32), m: M4(tx, g + hh - 0.05, tz), c: C('#eee2bd') });
    parts.push({ g: new THREE.SphereGeometry(r + 0.1, 24, 10, 0, Math.PI * 2, 0, Math.PI / 2), m: M4(tx, g + hh + 0.3, tz, 0, 1, 0.7, 1), c: C('#58625f') });
    parts.push({ g: new THREE.CylinderGeometry(0.06, 0.1, 1.6, 6), m: M4(tx, g + hh + 0.3 + (r + 0.1) * 0.7 + 0.7, tz), c: C('#3a3a3a') });
    h.top = Math.max(h.top, g + hh + 3.5); }
  const md = new THREE.Mesh(bake(parts), matDetalj); md.castShadow = true; md.receiveShadow = true; md.userData.bidx = bi; world.pickables.push(md); scene.add(md);
}
// ---- gamla mejeriet (Gnesta GYM): lastkaj, grön panel, svarta takkupor ----
function buildMejeri(h) {
  const bi = h.idx; const [x, z, b, d, rot] = h.rekt; const along = b >= d; const L = along ? b : d, D = along ? d : b;
  const yaw = along ? rot : rot + Math.PI / 2; const ux = Math.cos(yaw), uz = Math.sin(yaw), vx = -uz, vz = ux;
  const so = ((h.fasad.kaj[0] - x) * vx + (h.fasad.kaj[1] - z) * vz) > 0 ? 1 : -1;
  const P = (u, v) => [x + ux * u + vx * v * so, z + uz * u + vz * v * so]; const ry = -yaw; const g = h.g0;
  const parts = []; const box = (u, v, y, w, hh, dd, col, rx = 0, rz = 0) => { const c = P(u, v); parts.push({ g: new THREE.BoxGeometry(w, hh, dd), m: M4(c[0], y, c[1], ry, 1, 1, 1, so * rx, rz), c: C(col) }); };
  const kh = 1.1, kd = 2.7;
  // lastkaj längs långsidan
  { const yb = Math.min(...[-L / 2, 0, L / 2].map(u => H(...P(u, D / 2 + kd)))) - 0.4;
    box(0, D / 2 + kd / 2, (g + kh + yb) / 2, L - 1.0, g + kh - yb, kd, '#d9d8d2'); box(0, D / 2 + kd / 2, g + kh + 0.02, L - 1.0, 0.06, kd, '#8f8d88');
    box(0, D / 2 + kd + 0.02, g + kh - 0.1, L - 1.0, 0.22, 0.05, '#3a3a3a');
    for (let k = 0; k < 4; k++) box(-L / 2 + 1.2, D / 2 + kd + 0.3 + k * 0.28, g + kh - 0.2 - k * 0.27, 0.9, 0.06, 0.28, '#5c5c5c'); }
  // grön stående panel under fönstren
  box(0, D / 2 + 0.04, g + kh + 0.7, L - 1.4, 1.4, 0.08, '#4f8a3a');
  for (let u = -L / 2 + 1.0; u < L / 2 - 0.8; u += 0.32) box(u, D / 2 + 0.09, g + kh + 0.7, 0.03, 1.4, 0.02, '#3f7230');
  // svarta takkupor på båda takfallen (generiskt sadeltak, lutning 0.62)
  const y1 = h.y1, pt = 0.62;
  for (const side of [1, -1]) for (const u of [-8.5, -3.5, 1.5, 6.5]) { const vf = side * (D / 2 - 1.4), yf = y1 + 1.4 * pt;
    const dep = 2.6; const vc = vf - side * dep / 2;
    box(u, vc, yf + 0.75, 2.2, 1.9, dep, '#2b2d30'); box(u, vf + side * 0.02, yf + 0.85, 1.2, 1.2, 0.05, '#f2f1ec'); box(u, vf + side * 0.05, yf + 0.85, 1.0, 1.0, 0.03, '#3a4a56');
    box(u, vc + side * 0.15, yf + 1.75, 2.4, 0.1, dep + 0.4, '#2b2d30', side * 0.12); }
  const md = new THREE.Mesh(bake(parts), matDetalj); md.castShadow = true; md.receiveShadow = true; md.userData.bidx = bi; world.pickables.push(md); scene.add(md);
}
// ---- gång- och cykeltunnel under spåret: stödmurar, räcken, betongtak och belysning ----
function gangDjup(c, p) { return c.djup * (1 - smoothstep(c.langd * 0.3, c.langd, Math.abs(p.s - c.s0))); }
function iGangDike(x, z) {
  for (const c of carves) { if (!c.gang || Math.abs(x - c.cx) > c.R || Math.abs(z - c.cz) > c.R) continue;
    const r = nearestOnPolyline(c.pts, x, z); if (!r) continue; const p = c.pts[r.i]; const s = lerp(p.s, c.pts[Math.min(r.i + 1, c.pts.length - 1)].s, r.t);
    if (r.d < c.gang.vagg + 0.45 && gangDjup(c, { s }) > 0.05) return true; }
  return false;
}
function buildGangtunnlar() {
  const matMur = new THREE.MeshStandardMaterial({ color: 0xb3afa6, roughness: 0.9, side: THREE.DoubleSide });
  const matBallastYta = new THREE.MeshStandardMaterial({ color: 0x75695e, roughness: 1, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  const matGrasYta = new THREE.MeshStandardMaterial({ map: texMark, color: 0x7aa84a, roughness: 1, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  for (const c of carves) {
    if (!c.gang) continue; const sm = c.pts, s0 = c.s0, half = c.half, w = c.gang.vagg;
    const dep = (p) => gangDjup(c, p); const inT = (p) => Math.abs(p.s - s0) <= half + 0.01;
    let ceil = -1e9; for (const p of sm) if (inT(p)) { const rb = railBedNear(p.x, p.z, 9); ceil = Math.max(ceil, rb !== null ? rb : heightNC(p.x, p.z) + 0.45); } ceil -= 0.75;
    const murar = [], golv = [], syd = [], nord = [], spar = [], parts = [];
    const ytter = c.bredd / 2 + c.kant + 1.5;
    for (const sg of [1, -1]) {
      murar.push(ribbon(sm, sg * w, sg * w, null, { yA: (x, z, i, p) => inT(p) ? ceil : heightNC(x, z) + 0.22, yB: (x, z) => H(x, z) - 0.4, filter: (i, p) => dep(p) > 0.15, keepNormals: true }));
      murar.push(ribbon(sm, sg * (w + 0.3), sg * (w + 0.3), null, { yA: (x, z) => heightNC(x, z) + 0.22, yB: (x, z) => heightNC(x, z) - 0.1, filter: (i, p) => dep(p) > 0.15 && !inT(p), keepNormals: true }));
      murar.push(ribbon(sm, sg * (w - 0.02), sg * (w + 0.3), (x, z) => heightNC(x, z) + 0.22, { filter: (i, p) => dep(p) > 0.15 && !inT(p) }));
      const yk = (x, z) => heightNC(x, z) + 0.07;
      syd.push(ribbon(sm, sg * (w + 0.3), sg * ytter, yk, { filter: (i, p) => dep(p) > 0.02 && p.s < s0 - half }));
      nord.push(ribbon(sm, sg * (w + 0.3), sg * ytter, yk, { filter: (i, p) => dep(p) > 0.02 && p.s > s0 + half }));
      spar.push(ribbon(sm, sg * (w + 0.3), sg * ytter, yk, { filter: (i, p) => inT(p) }));
    }
    golv.push(ribbon(sm, w, -w, (x, z) => H(x, z) + 0.04, { filter: (i, p) => dep(p) > 0.15 }));
    // betongtak under spåren, lampor i taket
    for (let i = 0; i < sm.length - 1; i++) { const a = sm[i], b = sm[i + 1]; if (!inT(a) || !inT(b)) continue; const L = Math.hypot(b.x - a.x, b.z - a.z);
      parts.push({ g: new THREE.BoxGeometry(2 * w + 1.4, 0.65, L + 0.05), m: M4((a.x + b.x) / 2, ceil + 0.32, (a.z + b.z) / 2, Math.atan2(b.x - a.x, b.z - a.z)), c: C('#a9a59c') });
      if (i % 3 === 0) parts.push({ g: new THREE.BoxGeometry(0.5, 0.08, 1.1), m: M4((a.x + b.x) / 2, ceil - 0.04, (a.z + b.z) / 2, Math.atan2(b.x - a.x, b.z - a.z)), c: C('#fff6d8') }); }
    // räcken på murkrönen längs ramperna
    let last = -1e9;
    for (const p of sm) { if (dep(p) < 0.6 || inT(p) || p.s - last < 1.6) continue; last = p.s;
      for (const sg of [1, -1]) { const x = p.x - p.tz * sg * (w + 0.14), z = p.z + p.tx * sg * (w + 0.14); const y = heightNC(x, z) + 0.22; parts.push({ g: new THREE.BoxGeometry(0.06, 1.0, 0.06), m: M4(x, y + 0.5, z), c: C('#2a2c2e') }); } }
    for (const sg of [1, -1]) for (let i = 0; i < sm.length - 1; i++) { const a = sm[i], b = sm[i + 1]; if (dep(a) < 0.6 || dep(b) < 0.6 || inT(a) || inT(b)) continue;
      const ax = a.x - a.tz * sg * (w + 0.14), az = a.z + a.tx * sg * (w + 0.14), bx = b.x - b.tz * sg * (w + 0.14), bz = b.z + b.tx * sg * (w + 0.14);
      const ya = heightNC(ax, az) + 1.2, yb = heightNC(bx, bz) + 1.2; const L = Math.hypot(bx - ax, bz - az);
      parts.push({ g: new THREE.BoxGeometry(0.05, 0.05, L + 0.02), m: M4((ax + bx) / 2, (ya + yb) / 2, (az + bz) / 2, Math.atan2(bx - ax, bz - az), 1, 1, 1, -Math.atan2(yb - ya, L)), c: C('#2a2c2e') }); }
    const add = (geos, mat, cast = false) => { const g = mergeGeos(geos.filter(Boolean)); if (!g.attributes.position || !g.attributes.position.count) return; const m = new THREE.Mesh(g, mat); m.receiveShadow = true; m.castShadow = cast; scene.add(m); };
    add(murar, matMur, true); add(golv, matGang); add(syd, matSten); add(nord, matGrasYta); add(spar, matBallastYta);
    if (parts.length) { const m = new THREE.Mesh(bake(parts), matDetalj); m.castShadow = true; m.receiveShadow = true; scene.add(m); }
  }
}
// ---- Swedbank/Fastighetsbyrån och bibliotekets glastorn (efter foto) ----
function bankTex(len) {
  const ppm = 40, top = 5.6, yb = -0.9; const Wp = Math.ceil(len * ppm), Hp = Math.ceil((top - yb) * ppm);
  return canvasTex(Wp, Hp, (g) => {
    const X = (u) => u * ppm, Y = (y) => (top - y) * ppm; const r = mulberry32(14);
    g.fillStyle = '#d3cec4'; g.fillRect(0, 0, Wp, Hp);
    for (let y = 0; y < top; y += 1.1) for (let u = 0; u < len; u += 1.2) { const k = 0.94 + r() * 0.08; g.fillStyle = `rgba(${Math.round(211 * k)},${Math.round(206 * k)},${Math.round(196 * k)},1)`; g.fillRect(X(u) + 1, Y(y + 1.1) + 1, 1.2 * ppm - 2, 1.1 * ppm - 2); }
    g.fillStyle = '#55585b'; g.fillRect(0, 0, Wp, 0.4 * ppm);
    g.fillStyle = '#9d9a94'; g.fillRect(0, Y(0.8), Wp, Hp - Y(0.8));
    // glasparti med dörr
    g.fillStyle = '#2c3036'; g.fillRect(X(3.3), Y(4.15), 11.4 * ppm, 3.3 * ppm);
    for (let u = 3.4; u < 14.6; u += 1.4) glasYta(g, X(u), Y(4.05), 1.28 * ppm, 3.1 * ppm);
    g.fillStyle = '#2c3036'; g.fillRect(X(3.3), Y(3.45), 11.4 * ppm, 0.07 * ppm); g.fillRect(X(4.7), Y(3.45), 0.08 * ppm, 2.6 * ppm);
    g.fillStyle = 'rgba(240,130,40,0.65)'; g.beginPath(); g.arc(X(6.9), Y(2.6), 0.45 * ppm, 0, 7); g.fill();
    g.fillStyle = '#3a3d40'; g.fillRect(X(3.1), Y(4.4), 11.8 * ppm, 0.25 * ppm);
    // runt fönster närmast tornet och nisch för bankomaten
    g.fillStyle = '#2c3036'; g.beginPath(); g.ellipse(X(15.6), Y(2.6), 0.42 * ppm, 0.62 * ppm, 0, 0, 7); g.fill();
    g.save(); g.beginPath(); g.ellipse(X(15.6), Y(2.6), 0.32 * ppm, 0.52 * ppm, 0, 0, 7); g.clip(); glasYta(g, X(15.2), Y(3.2), 0.8 * ppm, 1.2 * ppm); g.restore();
    g.fillStyle = '#bdb8ae'; g.fillRect(X(0.8), Y(3.3), 1.7 * ppm, 2.5 * ppm);
  }, true, false);
}
const swedbankLogoTex = canvasTex(256, 256, (g, W, Hh) => {
  g.fillStyle = '#9b3a16'; g.beginPath(); g.arc(128, 128, 126, 0, 7); g.fill(); g.fillStyle = '#ee7a2c'; g.beginPath(); g.arc(128, 128, 112, 0, 7); g.fill();
  g.fillStyle = '#b8471a'; g.fillRect(118, 130, 20, 70); for (const [x, y, r] of [[128, 100, 46], [92, 118, 32], [164, 118, 32], [110, 82, 30], [148, 82, 30]]) { g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); }
}, true, false);
function bankSkylt(text, o) {
  return canvasTex(1024, 220, (g, W, Hh) => {
    g.fillStyle = o.bg; g.fillRect(0, 0, W, Hh); g.fillStyle = o.fg; g.font = o.font; g.textBaseline = 'middle'; g.textAlign = 'left';
    let fs = parseInt(o.font.match(/(\d+)px/)[1]); while (g.measureText(text).width > W - 260 && fs > 40) { fs -= 4; g.font = o.font.replace(/\d+px/, fs + 'px'); }
    g.fillText(text, 40, Hh / 2 + 4); g.fillStyle = '#ee7a2c'; g.beginPath(); g.arc(W - 110, Hh / 2, 72, 0, 7); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.25)'; g.beginPath(); g.arc(W - 130, Hh / 2 - 22, 24, 0, 7); g.fill();
  }, true, false);
}
function buildBank(h) {
  const F = h.fasad, bi = h.idx; const A = F.a, B = F.b; const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const dx = (B[0] - A[0]) / L, dz = (B[1] - A[1]) / L; let nx = -dz, nz = dx; if ((F.vag[0] - A[0]) * nx + (F.vag[1] - A[1]) * nz < 0) { nx = -nx; nz = -nz; }
  const P = (u, v) => [A[0] + dx * u + nx * v, A[1] + dz * u + nz * v]; const ry = Math.atan2(nx, nz); const g = h.g0;
  const pick = (m, cast = true) => { m.userData.bidx = bi; world.pickables.push(m); m.castShadow = cast; m.receiveShadow = true; scene.add(m); return m; };
  const plane = (u, v, y, w, hh, mat) => { const c = P(u, v); const m = new THREE.Mesh(new THREE.PlaneGeometry(w, hh), mat); m.position.set(c[0], y, c[1]); m.rotation.y = ry; return pick(m, false); };
  { const t = bankTex(L); if (nz * dx - nx * dz < 0) { t.repeat.x = -1; t.offset.x = 1; } plane(L / 2, 0.07, g + (5.6 - 0.9) / 2, L, 6.5, new THREE.MeshStandardMaterial({ map: t, roughness: 0.8 })); }
  plane(12.4, 0.12, g + 4.85, 3.4, 0.73, new THREE.MeshStandardMaterial({ map: bankSkylt('Fastighetsbyrån', { bg: '#1c2a44', fg: '#ffffff', font: 'italic 120px Georgia, "Times New Roman", serif' }), roughness: 0.5 }));
  plane(7.4, 0.12, g + 4.85, 4.4, 0.95, new THREE.MeshStandardMaterial({ map: bankSkylt('Swedbank', { bg: '#20345c', fg: '#ee7a2c', font: '150px "Trebuchet MS", Arial, sans-serif' }), roughness: 0.5 }));
  plane(1.65, 0.1, g + 3.65, 1.1, 0.42, new THREE.MeshStandardMaterial({ map: textTex('Bankomat', { bg: '#2a8fd0', fg: '#ffffff', w: 512, h: 196, fit: true }), roughness: 0.5 }));
  const parts = []; const box = (u, v, y, w, hh, d, col, rx = 0) => { const c = P(u, v); parts.push({ g: new THREE.BoxGeometry(w, hh, d), m: M4(c[0], y, c[1], ry, 1, 1, 1, rx), c: C(col) }); };
  // upphöjd entréplan med trappa längs fasaden, räcken, bankomat och bänkar
  const tp = 0.8, ytb = Math.min(...[0, L / 2, L].map(u => H(...P(u, 3.6)))) - 0.4 - g;
  box(7.5, 1.1, g + (tp + ytb) / 2, 15.0, tp - ytb, 2.2, '#a9a6a0');
  for (let k = 1; k <= 4; k++) { const top = tp - k * 0.2; const d = 2.2 + k * 0.34; box(8.3, d / 2, g + (top + ytb) / 2, 12.4, top - ytb, d, k % 2 ? '#9f9c96' : '#a8a59f'); }
  for (const u of [2.0, 14.6]) { box(u, 2.9, g + 0.85, 0.05, 1.0, 0.05, '#1c1c1c'); box(u, 2.25, g + 1.3, 0.05, 0.05, 1.5, '#1c1c1c', 0.55); }
  box(-0.1, 1.1, g + tp + 0.5, 0.05, 1.0, 2.2, '#1c1c1c'); box(-0.1, 1.1, g + tp + 1.0, 0.05, 0.05, 2.2, '#1c1c1c');
  box(1.65, 0.25, g + tp + 0.75, 0.75, 1.5, 0.35, '#1f6fb2'); box(1.65, 0.45, g + tp + 1.05, 0.5, 0.35, 0.05, '#203040');
  box(1.65, 0.7, g + 3.3, 2.0, 0.12, 1.3, '#cfcac0');
  for (const u of [12.8, 14.4]) { const y = H(...P(u, 4.4)); box(u, 4.4, y + 0.45, 1.5, 0.06, 0.45, '#2a2a2a'); box(u, 4.18, y + 0.72, 1.5, 0.45, 0.05, '#2a2a2a'); for (const s2 of [-0.65, 0.65]) box(u + s2, 4.4, y + 0.22, 0.05, 0.45, 0.45, '#2a2a2a'); }
  box(17.2, 4.6, H(...P(17.2, 4.6)) + 0.4, 0.8, 0.8, 0.8, '#5a5d60');
  const md = new THREE.Mesh(bake(parts), matDetalj); md.castShadow = true; md.receiveShadow = true; md.userData.bidx = bi; world.pickables.push(md); scene.add(md);
  // runt Swedbank-märke som sticker ut från hörnet
  { const c = P(0.5, 1.0); const mats = [new THREE.MeshStandardMaterial({ color: '#9b3a16' }), new THREE.MeshStandardMaterial({ map: swedbankLogoTex }), new THREE.MeshStandardMaterial({ map: swedbankLogoTex })];
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.75, 0.18, 32), mats); m.position.set(c[0], g + 5.0, c[1]); m.rotation.set(0, ry, Math.PI / 2, 'YXZ'); pick(m);
    const a2 = P(0.5, 0.35); const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.6), new THREE.MeshStandardMaterial({ color: '#2a2a2a' })); arm.position.set(a2[0], g + 5.0, a2[1]); arm.rotation.y = ry; pick(arm); }
}
function buildGlastorn(h) {
  const T = h.glastorn, bi = h.idx; const y0 = H(T.x, T.z) - 0.5, hh = T.h + 0.5;
  const glas = new THREE.Mesh(new THREE.CylinderGeometry(T.r, T.r, hh, 40, 1, true), new THREE.MeshStandardMaterial({ color: 0x3e4f5c, roughness: 0.12, metalness: 0.65, side: THREE.DoubleSide }));
  glas.position.set(T.x, y0 + hh / 2, T.z); glas.userData.bidx = bi; world.pickables.push(glas); scene.add(glas);
  const parts = [];
  for (let k = 0; k < 24; k++) { const a = k / 24 * Math.PI * 2; parts.push({ g: new THREE.BoxGeometry(0.08, hh, 0.1), m: M4(T.x + Math.sin(a) * (T.r + 0.02), y0 + hh / 2, T.z + Math.cos(a) * (T.r + 0.02), a), c: C('#2a2d30') }); }
  for (const y of [0.9, 3.4, 6.0]) parts.push({ g: new THREE.TorusGeometry(T.r + 0.03, 0.06, 6, 40), m: M4(T.x, y0 + 0.5 + y, T.z, 0, 1, 1, 1, Math.PI / 2), c: C('#2a2d30') });
  parts.push({ g: new THREE.CylinderGeometry(T.r + 0.18, T.r + 0.18, 0.55, 40), m: M4(T.x, y0 + hh + 0.27, T.z), c: C('#3a3d40') });
  const m = new THREE.Mesh(bake(parts), matDetalj); m.castShadow = true; m.userData.bidx = bi; world.pickables.push(m); scene.add(m);
  // BIBLIOTEK i stora bokstäver innanför glaset, vänt mot gatan
  const t = canvasTex(1024, 160, (g, W, Hh) => { g.clearRect(0, 0, W, Hh); g.font = 'bold 120px "Trebuchet MS", Arial, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineWidth = 10; g.strokeStyle = '#2f5fae'; g.strokeText('BIBLIOTEK', W / 2, Hh / 2); g.fillStyle = '#ffffff'; g.fillText('BIBLIOTEK', W / 2, Hh / 2); }, true, false);
  const ang = Math.atan2(T.mot[0] - T.x, T.mot[1] - T.z); const sp = new THREE.Mesh(new THREE.PlaneGeometry(4.6, 0.72), new THREE.MeshStandardMaterial({ map: t, transparent: true, roughness: 0.6 }));
  sp.position.set(T.x + Math.sin(ang) * (T.r - 0.25), y0 + 0.5 + 4.7, T.z + Math.cos(ang) * (T.r - 0.25)); sp.rotation.y = ang; sp.userData.bidx = bi; world.pickables.push(sp); scene.add(sp);
}
// ---- Kulturhuset Elektron: skärmtak med runda lampor, kromskylt och atomskulptur (efter foto) ----
function elektronTex(len) {
  const ppm = 40, top = 6.55, yb = -0.8; const Wp = Math.ceil(len * ppm), Hp = Math.ceil((top - yb) * ppm);
  return canvasTex(Wp, Hp, (g) => {
    const X = (u) => u * ppm, Y = (y) => (top - y) * ppm; const r = mulberry32(19);
    g.fillStyle = '#c6b796'; g.fillRect(0, 0, Wp, Hp);
    for (let y = 0.5; y < 5.3; y += 1.2) for (let u = 0; u < len; u += 1.25) { const k = 0.9 + r() * 0.14; g.fillStyle = `rgb(${Math.round(198 * k)},${Math.round(183 * k)},${Math.round(150 * k)})`; g.fillRect(X(u) + 1, Y(y + 1.2) + 1, 1.25 * ppm - 2, 1.2 * ppm - 2); }
    g.fillStyle = '#262b33'; g.fillRect(0, 0, Wp, Y(5.3)); g.strokeStyle = 'rgba(120,130,150,0.35)'; g.lineWidth = 1;
    for (let u = 0; u < len; u += 0.9) { g.beginPath(); g.moveTo(X(u), 0); g.lineTo(X(u), Y(5.3)); g.stroke(); } g.beginPath(); g.moveTo(0, Y(5.9)); g.lineTo(Wp, Y(5.9)); g.stroke();
    g.fillStyle = '#8f8a80'; g.fillRect(0, Y(0.5), Wp, Hp - Y(0.5));
    const fonster = (u0, u1, y0, y1, n, karm) => { g.fillStyle = karm; g.fillRect(X(u0), Y(y1), (u1 - u0) * ppm, (y1 - y0) * ppm);
      for (let k = 0; k < n; k++) { const a = u0 + 0.08 + k * (u1 - u0 - 0.08) / n; glasYta(g, X(a), Y(y1 - 0.08), ((u1 - u0 - 0.08) / n - 0.08) * ppm, (y1 - y0 - 0.16) * ppm); } };
    fonster(1.4, 3.2, 0.9, 2.95, 1, '#c9c9c4');
    fonster(9.1, 14.1, 1.9, 4.4, 3, '#d9d9d4');
    // glasade pardörrar med vita karmar och överljus
    g.fillStyle = '#f1f0ec'; g.fillRect(X(3.7), Y(3.0), 3.8 * ppm, 3.0 * ppm);
    for (const a of [3.85, 4.75, 5.7, 6.6]) glasYta(g, X(a), Y(2.4), 0.78 * ppm, 2.25 * ppm);
    glasYta(g, X(3.85), Y(2.92), 3.5 * ppm, 0.4 * ppm);
    g.fillStyle = 'rgba(160,60,50,0.35)'; g.fillRect(X(3.85), Y(2.4), 3.5 * ppm, 1.3 * ppm);
    g.fillStyle = '#9aa0a3'; for (const a of [4.6, 6.45]) g.fillRect(X(a), Y(1.25), 0.06 * ppm, 0.3 * ppm);
  }, true, false);
}
function elektronSkyltTex() {
  return canvasTex(1024, 200, (g, W, Hh) => {
    const gr = g.createLinearGradient(0, 0, 0, Hh); gr.addColorStop(0, '#e9ecee'); gr.addColorStop(0.5, '#b9bec2'); gr.addColorStop(1, '#d9dcde'); g.fillStyle = gr; g.fillRect(0, 0, W, Hh);
    g.strokeStyle = '#8b9095'; g.lineWidth = 6; g.strokeRect(3, 3, W - 6, Hh - 6);
    g.font = 'italic bold 150px "Brush Script MT", "Segoe Script", "Lucida Handwriting", Georgia, serif'; g.textBaseline = 'middle'; g.textAlign = 'center';
    g.lineWidth = 10; g.strokeStyle = '#5c6268'; g.strokeText('Elektron', W / 2, Hh / 2 + 6);
    const tg = g.createLinearGradient(0, 30, 0, Hh - 30); tg.addColorStop(0, '#ffffff'); tg.addColorStop(0.45, '#c7ccd1'); tg.addColorStop(0.55, '#8a9096'); tg.addColorStop(1, '#eef0f2'); g.fillStyle = tg; g.fillText('Elektron', W / 2, Hh / 2 + 6);
  }, true, false);
}
function entreSkyltTex(rubrik) {
  return canvasTex(256, 384, (g, W, Hh) => {
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, W, Hh); g.fillStyle = '#1f6b45'; g.fillRect(0, 0, W, 86); g.fillRect(0, Hh - 54, W, 54);
    g.fillStyle = '#ffffff'; g.font = 'bold 30px Arial, sans-serif'; g.textAlign = 'left'; rubrik.split('\n').forEach((t, i) => g.fillText(t, 14, 38 + i * 34));
    g.fillStyle = '#333'; g.font = '22px Arial, sans-serif'; ['Sal A/Bio', 'Sal B', '', 'Gnesta kommun'].forEach((t, i) => g.fillText(t, 14, 130 + i * 34));
  }, true, false);
}
function buildElektron(h) {
  const F = h.fasad, bi = h.idx; const A = F.a, B = F.b; const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const dx = (B[0] - A[0]) / L, dz = (B[1] - A[1]) / L; let nx = -dz, nz = dx; if ((F.vag[0] - A[0]) * nx + (F.vag[1] - A[1]) * nz < 0) { nx = -nx; nz = -nz; }
  const P = (u, v) => [A[0] + dx * u + nx * v, A[1] + dz * u + nz * v]; const ry = Math.atan2(nx, nz); const g = h.g0;
  const pick = (m, cast = true) => { m.userData.bidx = bi; world.pickables.push(m); m.castShadow = cast; m.receiveShadow = true; scene.add(m); return m; };
  const plane = (u, v, y, w, hh, mat) => { const c = P(u, v); const m = new THREE.Mesh(new THREE.PlaneGeometry(w, hh), mat); m.position.set(c[0], y, c[1]); m.rotation.y = ry; return pick(m, false); };
  { const t = elektronTex(L); if (nz * dx - nx * dz < 0) { t.repeat.x = -1; t.offset.x = 1; } plane(L / 2, 0.08, g + (6.55 - 0.8) / 2, L, 7.35, new THREE.MeshStandardMaterial({ map: t, roughness: 0.8 })); }
  const parts = []; const box = (u, v, y, w, hh, d, col, rx = 0, rz = 0) => { const c = P(u, v); parts.push({ g: new THREE.BoxGeometry(w, hh, d), m: M4(c[0], y, c[1], ry, 1, 1, 1, rx, rz), c: C(col) }); };
  // mörkt skärmtak över entrén med runda infällda lampor
  const k0 = 0.6, k1 = 8.1, kd = 2.2, ky0 = 3.45, ky1 = 4.85;
  box((k0 + k1) / 2, kd / 2, (ky0 + ky1) / 2 + g, k1 - k0, ky1 - ky0, kd, '#1f2329');
  for (const v of [0.75, 1.55]) for (let u = k0 + 0.9; u < k1 - 0.5; u += 1.55) { const c = P(u, v); parts.push({ g: new THREE.CylinderGeometry(0.2, 0.2, 0.03, 16), m: M4(c[0], g + ky0 - 0.01, c[1]), c: C('#f4ecd0') }); }
  box(7.2, kd - 0.05, g + ky1 + 0.08, 3.0, 0.1, 0.1, '#c9ccd0');
  // atomskulptur: två korsande banor med färgade kulor
  { const c = P(7.4, kd - 0.35); const cy = g + ky1 + 1.05;
    for (const [rz, ry2] of [[0.35, 0], [-0.55, 0.5]]) parts.push({ g: new THREE.TorusGeometry(1.1, 0.025, 6, 48), m: M4(c[0], cy, c[1], ry + ry2, 1.15, 0.9, 1, 0, rz), c: C('#b9bec2') });
    for (const [a, col] of [[1.45, '#2f9a4a'], [0.55, '#e3b62a'], [-1.6, '#d0362e'], [3.1, '#2f9a4a'], [-0.7, '#c2283a']]) { const lx = Math.cos(a) * 1.25, ly = Math.sin(a) * 1.0;
      const q = [c[0] + Math.cos(ry) * lx, cy + ly, c[1] - Math.sin(ry) * lx]; parts.push({ g: new THREE.SphereGeometry(0.15, 14, 10), m: M4(q[0], q[1], q[2]), c: C(col) }); }
    parts.push({ g: new THREE.CylinderGeometry(0.03, 0.03, 1.1, 6), m: M4(c[0], cy - 0.55, c[1]), c: C('#9aa0a3') }); }
  // räcke vid rampen
  for (const u of [-3.0, -0.6, 1.8]) box(u, 2.6, g + 0.5, 0.05, 1.0, 0.05, '#9aa0a3');
  box(-0.6, 2.6, g + 1.0, 4.8, 0.05, 0.05, '#9aa0a3'); box(-0.6, 2.6, g + 0.55, 4.8, 0.04, 0.04, '#9aa0a3');
  const md = new THREE.Mesh(bake(parts), matDetalj); md.castShadow = true; md.receiveShadow = true; md.userData.bidx = bi; world.pickables.push(md); scene.add(md);
  plane(3.2, kd + 0.02, g + ky1 + 0.5, 5.2, 1.0, new THREE.MeshStandardMaterial({ map: elektronSkyltTex(), roughness: 0.3, metalness: 0.5 }));
  plane(8.45, 0.12, g + 1.95, 0.62, 0.92, new THREE.MeshStandardMaterial({ map: entreSkyltTex('ENTRÉ\nELEKTRON'), roughness: 0.6 }));
  h.top = Math.max(h.top, g + 8.5);
}
function kommunSkyltTex() {
  return canvasTex(384, 288, (g, W, Hh) => {
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, W, Hh); g.fillStyle = '#1f6b45'; g.fillRect(0, Hh - 70, W, 70);
    g.fillStyle = '#2e6b45'; g.font = 'bold 58px Georgia, serif'; g.textAlign = 'left'; g.fillText('GNESTA', 24, 92); g.fillText('KOMMUN', 24, 160);
    g.beginPath(); g.arc(320, 110, 40, 0, 7); g.fill(); g.fillStyle = '#ffffff'; g.fillRect(316, 112, 8, 30); g.beginPath(); g.arc(320, 100, 20, 0, 7); g.fill();
  }, true, false);
}
function buildSpecials() {
  for (const h of world.hus) {
    const bi = h.idx; const g0 = h.g0;
    if (h.typ === 'station' && h.rekt) buildStation(h);
    if (h.typ === 'vattentorn_gammalt') {
      const parts = []; const x = h.x, z = h.z;
      parts.push({ g: new THREE.CylinderGeometry(3.3, 3.8, 20, 20), m: M4(x, g0 + 10, z), c: C('#d9cdb2') });
      parts.push({ g: new THREE.CylinderGeometry(6.4, 5.2, 1.6, 24), m: M4(x, g0 + 20.6, z), c: C('#c8b998') });
      parts.push({ g: new THREE.CylinderGeometry(6.3, 6.3, 5.6, 24), m: M4(x, g0 + 24.2, z), c: C('#e3d8bf') });
      parts.push({ g: new THREE.ConeGeometry(6.9, 3.6, 24), m: M4(x, g0 + 28.8, z), c: C('#4d7a66') });
      parts.push({ g: new THREE.CylinderGeometry(0.9, 0.9, 1.6, 8), m: M4(x, g0 + 31.1, z), c: C('#e3d8bf') });
      parts.push({ g: new THREE.ConeGeometry(1.1, 1.8, 8), m: M4(x, g0 + 32.7, z), c: C('#4d7a66') });
      for (let k = 0; k < 8; k++) { const a = k / 8 * Math.PI * 2; parts.push({ g: new THREE.BoxGeometry(0.9, 1.6, 0.2), m: M4(x + Math.cos(a) * 6.35, g0 + 24.5, z + Math.sin(a) * 6.35, -a + Math.PI / 2), c: C('#2b3440') }); }
      addSpecial(parts, bi); h.top = g0 + 33.6;
    }
    if (h.typ === 'trappa' && K.harspranget) {
      const top = buildSteps(K.harspranget, 2.4, bi); h.top = (top || g0) + 1.5;
      const a = K.harspranget[0], b = K.harspranget[K.harspranget.length - 1]; h.x = (a[0] + b[0]) / 2; h.z = (a[1] + b[1]) / 2;
    }
  }
  for (const h of world.hus) if (h.fasad && h.fasad.typ === 'frejaskolan') buildFrejaskolan(h);
  for (const h of world.hus) if (h.fasad && h.fasad.typ === 'indiska') buildIndiska(h);
  buildDetaljer();
  for (const h of world.hus) if (h.typ === 'tak') buildCanopy(h);
  for (const h of world.hus) for (const k of h.kapell || []) buildKapellPa(h, k);
  for (const h of world.hus) if (h.fasad && h.fasad.typ === 'hotell') buildHotell(h);
  for (const h of world.hus) if (h.fasad && h.fasad.typ === 'mejeri') buildMejeri(h);
  for (const h of world.hus) if (h.fasad && h.fasad.typ === 'bank') buildBank(h);
  for (const h of world.hus) if (h.glastorn) buildGlastorn(h);
  for (const h of world.hus) if (h.fasad && h.fasad.typ === 'elektron') buildElektron(h);
  buildGangtunnlar();
  for (const r of (K.racken || [])) buildRacke(r);
  // skyltar på fasader (från rättningar)
  for (const h of world.hus) {
    if (!h.skyltar) continue;
    const cs = h.corners; const n = cs.length; const ccw = (() => { let a = 0; for (let i = 0; i < n; i++) { const p = cs[i], q = cs[(i + 1) % n]; a += p[0] * q[1] - q[0] * p[1]; } return a > 0; })();
    for (const sk of h.skyltar) {
      let best = null;
      for (let i = 0; i < n; i++) {
        const a = cs[i], b = cs[(i + 1) % n]; const L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 4) continue;
        let nx = (b[1] - a[1]) / L, nz = -(b[0] - a[0]) / L; if (!ccw) { nx = -nx; nz = -nz; }
        const mx = (a[0] + b[0]) / 2, mz = (a[1] + b[1]) / 2; const tx = sk.mot[0] - mx, tz = sk.mot[1] - mz; const tl = Math.hypot(tx, tz) || 1;
        const score = (nx * tx + nz * tz) / tl - tl * 0.002 + Math.min(L, 20) * 0.01;
        if (!best || score > best.score) best = { score, mx, mz, nx, nz, L, tx: (b[0] - a[0]) / L, tz: (b[1] - a[1]) / L };
      }
      if (!best) continue;
      const hgt = sk.hgt || 1.1; const w = sk.bredd || Math.min(best.L * 0.85, 0.42 * sk.text.length + 1.0);
      if (sk.u) { best.mx += best.tx * sk.u; best.mz += best.tz * sk.u; }
      const tex = sk.stil === 'farghus' ? farghusTex(sk.text) : sk.stil === 'kommun' ? kommunSkyltTex() : textTex(sk.text, { bg: sk.bg || '#1d2a3a', fg: sk.fg || '#fff', w: 2048, h: Math.round(2048 * hgt / w), fit: true, italic: sk.kursiv });
      signMesh(tex, w, hgt, best.mx + best.nx * 0.1, h.g0 + sk.hojd, best.mz + best.nz * 0.1, Math.atan2(best.nx, best.nz), h.idx);
      if (sk.utanTak) continue;
      const tak = new THREE.Mesh(new THREE.BoxGeometry(w + 0.4, 0.12, 1.1), new THREE.MeshStandardMaterial({ color: sk.bg || '#333', roughness: 0.6 }));
      tak.position.set(best.mx + best.nx * 0.55, h.g0 + sk.hojd - 0.75, best.mz + best.nz * 0.55); tak.rotation.y = Math.atan2(best.nx, best.nz); tak.castShadow = true; scene.add(tak);
    }
  }
  // övriga trappor
  for (const tr of K.trappor) { if (K.harspranget && tr.pts[0][0] === K.harspranget[0][0] && tr.pts[0][1] === K.harspranget[0][1]) continue; if (!tr.pts.some(p => inRam(p[0], p[1]))) continue; buildSteps(tr.pts, 2.0); }
}

// =====================================================================
// Körbar sträcka, bommar, skyltar, lyktor
// =====================================================================
const drivable = []; const barriers = [];
function buildDrivable() {
  const kb0 = K.korbar; const kb = kb0.rutter[0]; let main = null;
  for (const r of kb0.rutter) {
    const pts = resample(r.pts, 2); if (!main) main = pts;
    drivable.push({ pts, half: r.bredd / 2, capStart: r.capStart, capEnd: r.capEnd, name: r.namn, trott: r.trottoar });
    if (r.capStart) barriers.push({ p: pts[0], dir: -1, half: r.bredd / 2 + r.trottoar, huvud: true });
    if (r.capEnd) barriers.push({ p: pts[pts.length - 1], dir: 1, half: r.bredd / 2 + (r.bredd >= 7 ? r.trottoar : 0.6), huvud: true });
  }
  for (const st of kb0.stumpar) {
    const pts = resample(st.pts, 1.5); if (pts.length < 2) continue;
    drivable.push({ pts, half: st.bredd / 2, capStart: false, capEnd: true, name: st.namn, stub: true });
    barriers.push({ p: pts[pts.length - 1], dir: 1, half: st.bredd / 2 + (st.trottoar || 0) * 0.5 + 0.3, huvud: false, namn: st.namn, typ: st.typ, mouth: pts[0], bredd: st.bredd, trott: st.trottoar || 0 });
  }
  const stripe = canvasTex(256, 64, (gc) => { gc.fillStyle = '#fff'; gc.fillRect(0, 0, 256, 64); gc.fillStyle = '#d4202a'; for (let x = -64; x < 256; x += 48) { gc.beginPath(); gc.moveTo(x, 64); gc.lineTo(x + 24, 64); gc.lineTo(x + 48, 0); gc.lineTo(x + 24, 0); gc.fill(); } }, true, true);
  const matStripe = new THREE.MeshStandardMaterial({ map: stripe, roughness: 0.6 });
  const texVarn = canvasTex(256, 230, (gc) => { gc.clearRect(0, 0, 256, 230); gc.beginPath(); gc.moveTo(128, 8); gc.lineTo(250, 222); gc.lineTo(6, 222); gc.closePath(); gc.fillStyle = '#d0202a'; gc.fill(); gc.beginPath(); gc.moveTo(128, 40); gc.lineTo(222, 205); gc.lineTo(34, 205); gc.closePath(); gc.fillStyle = '#f7d117'; gc.fill(); gc.fillStyle = '#111'; gc.font = 'bold 56px Arial'; gc.textAlign = 'center'; gc.fillText('!', 128, 180); }, true, false);
  const matVarn = new THREE.MeshStandardMaterial({ map: texVarn, transparent: true, alphaTest: 0.5, side: THREE.DoubleSide });
  const matAvst = new THREE.MeshStandardMaterial({ map: textTex('AVSTÄNGT', { bg: '#ffffff', fg: '#c81e28', border: '#c81e28', bw: 14, w: 512, h: 128 }), side: THREE.DoubleSide });
  const matAvst2 = new THREE.MeshStandardMaterial({ map: textTex('KOMMER I NÄSTA VERSION', { bg: '#ffffff', fg: '#333', w: 1024, h: 110, font: 'bold 54px Arial' }), side: THREE.DoubleSide });
  const kon = new THREE.ConeGeometry(0.22, 0.75, 12); const matKon = new THREE.MeshStandardMaterial({ color: 0xff6a13, roughness: 0.6 }); const matPost = new THREE.MeshStandardMaterial({ color: 0x555555 });
  for (const b of barriers) {
    const p = b.p; const tx = p.tx * b.dir, tz = p.tz * b.dir; const ang = Math.atan2(tx, tz);
    const grp = new THREE.Group(); grp.position.set(p.x, H(p.x, p.z) + 0.2, p.z); grp.rotation.y = ang;
    const w = b.half * 2 + 0.6; const small = b.typ === 'service';
    const board = new THREE.Mesh(new THREE.BoxGeometry(w, 0.45, 0.06), matStripe); board.position.y = small ? 0.8 : 1.05; board.castShadow = true; grp.add(board);
    if (!small) { const b2 = board.clone(); b2.position.y = 0.45; grp.add(b2); }
    for (const sx of [-w / 2 + 0.2, w / 2 - 0.2]) { const post = new THREE.Mesh(new THREE.BoxGeometry(0.1, small ? 1.0 : 1.3, 0.1), matPost); post.position.set(sx, small ? 0.5 : 0.65, 0.05); grp.add(post); }
    if (!small) {
      const varn = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.0), matVarn); varn.position.set(-w / 2 + 1.1, 2.0, -0.05); varn.rotation.y = Math.PI; grp.add(varn);
      const avst = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 0.45), matAvst); avst.position.set(0, 1.62, -0.05); avst.rotation.y = Math.PI; grp.add(avst);
      for (let k = 0; k < 4; k++) { const c = new THREE.Mesh(kon, matKon); c.position.set(-w / 2 + 0.6 + k * (w - 1.2) / 3, 0.37, -2.2 - (k % 2) * 0.6); c.castShadow = true; grp.add(c); }
    }
    if (b.huvud) { const a2 = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 0.36), matAvst2); a2.position.set(0, 2.05, -0.05); a2.rotation.y = Math.PI; grp.add(a2); }
    scene.add(grp);
  }
  // gatuskyltar vid namngivna sidogator
  const matPole = new THREE.MeshStandardMaterial({ color: 0x8a8d90, metalness: 0.5, roughness: 0.4 });
  const gjorda = new Set();
  for (const b of barriers) {
    if (b.huvud || !b.namn || b.typ === 'service' || gjorda.has(b.namn + Math.round(b.mouth.x / 30))) continue; gjorda.add(b.namn + Math.round(b.mouth.x / 30));
    const m = b.mouth; const off = b.bredd / 2 + 1.2; const fwd = 4.0 + 2.2 + 1.0;
    const x = m.x - m.tz * off + m.tx * fwd, z = m.z + m.tx * off + m.tz * fwd; const y = H(x, z);
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 2.9, 6), matPole); pole.position.set(x, y + 1.45, z); scene.add(pole);
    const tex = textTex(b.namn, { bg: '#1b4f9c', fg: '#fff', border: '#fff', bw: 8, w: 768, h: 128, font: 'bold 64px "Trebuchet MS", Arial' });
    const sign = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 0.32), new THREE.MeshStandardMaterial({ map: tex, side: THREE.DoubleSide })); sign.position.set(x, y + 2.7, z); sign.rotation.y = Math.atan2(m.tx, m.tz) + Math.PI / 2; scene.add(sign);
  }
  // ortnamnsskylt
  { const p = main[Math.min(main.length - 1, 14)]; const off = kb.bredd / 2 + kb.trottoar + 1.0; const x = p.x - p.tz * off, z = p.z + p.tx * off; const y = H(x, z); const ang = Math.atan2(p.tx, p.tz) + Math.PI;
    const tex = textTex('Gnesta', { bg: '#1b4f9c', fg: '#fff', border: '#fff', bw: 10, w: 512, h: 160, font: 'bold 96px "Trebuchet MS", Arial' });
    const s = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 0.8), new THREE.MeshStandardMaterial({ map: tex, side: THREE.DoubleSide })); s.position.set(x, y + 2.1, z); s.rotation.y = ang; scene.add(s);
    for (const lx of [-1, 1]) { const po = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 2.5, 6), matPole); po.position.set(x + Math.cos(ang) * lx, y + 1.25, z - Math.sin(ang) * lx); scene.add(po); } }
  // gatlyktor längs sträckan
  const lyktor = [];
  for (const dr of drivable) { if (dr.stub) continue; const off = dr.half + dr.trott - 0.35; const lp = dr.pts;
  for (let i = 0; i < lp.length; i += 15) {
    const p = lp[i]; const sg = (Math.floor(i / 15) % 2) ? 1 : -1; const x = p.x - p.tz * off * sg, z = p.z + p.tx * off * sg;
    let blocked = false; roadIndex.near(x, z, 10, (sgm) => { const o = sgm.data.g; if (o.bil && o.typ !== 'secondary' && !(dr.name && o.namn === dr.name) && !['Skolgatan', 'Frejavägen', 'Tingshusgatan'].includes(o.namn) && segDist(x, z, sgm.ax, sgm.az, sgm.bx, sgm.bz)[0] < o.bredd / 2 + 1.5) blocked = true; });
    if (blocked) continue;
    const y = H(x, z); const twx = p.tz * sg, twz = -p.tx * sg; const ang = Math.atan2(twx, twz);
    lyktor.push({ g: new THREE.CylinderGeometry(0.07, 0.11, 7, 6), m: M4(x, y + 3.5, z), c: C('#4b5056') });
    lyktor.push({ g: new THREE.BoxGeometry(0.08, 0.08, 1.8), m: M4(x + twx * 0.9, y + 6.95, z + twz * 0.9, ang), c: C('#4b5056') });
    lyktor.push({ g: new THREE.BoxGeometry(0.3, 0.16, 0.6), m: M4(x + twx * 1.75, y + 6.85, z + twz * 1.75, ang), c: C('#d9d6c8') });
  } }
  const ml = new THREE.Mesh(bake(lyktor), matDetalj); ml.castShadow = true; scene.add(ml);
}

// =====================================================================
// Träd
// =====================================================================
function buildTrees() {
  const R = 2, X0 = RAM[0] - 100, Z0 = RAM[2] - 100, NX = Math.ceil((RAM[1] - RAM[0] + 200) / R), NZ = Math.ceil((RAM[3] - RAM[2] + 200) / R);
  const occ = new Uint8Array(NX * NZ);
  const mark = (x, z, r) => { const i0 = Math.floor((x - r - X0) / R), i1 = Math.floor((x + r - X0) / R), j0 = Math.floor((z - r - Z0) / R), j1 = Math.floor((z + r - Z0) / R); for (let j = Math.max(0, j0); j <= Math.min(NZ - 1, j1); j++) for (let i = Math.max(0, i0); i <= Math.min(NX - 1, i1); i++) occ[j * NX + i] = 1; };
  const markPoly = (poly, pad) => { const bb = bbox(poly); for (let z = bb[1] - pad; z <= bb[3] + pad; z += R) for (let x = bb[0] - pad; x <= bb[2] + pad; x += R) if (pointInPoly(x, z, poly)) mark(x, z, pad); };
  for (const g of gator) { if (g.tunnel) continue; const r = g.bredd / 2 + g.trottoar + (g.bil ? 1.8 : 0.8); for (const p of g.sm) mark(p.x, p.z, r); }
  for (const tr of railTracks) for (const p of tr.sm) mark(p.x, p.z, 5.5);
  for (const h of world.hus) { if (h.typ === 'trappa') { for (const p of resample(K.harspranget, 2)) mark(p.x, p.z, 3); continue; } markPoly(h.corners, 2.2); }
  for (const y of K.ytor) if (y.typ !== 'lekplats') markPoly(y.poly, 1.5);
  for (const pr of K.jarnvag.perronger) markPoly(pr.poly, 1);
  for (const bg of (K.detaljer && K.detaljer.berg) || []) mark(bg.x, bg.z, Math.max(bg.b, bg.d) / 2 + 1.5);
  for (const c of carves) if (c.gang) for (const p of c.pts) if (gangDjup(c, p) > 0.05) mark(p.x, p.z, c.bredd / 2 + c.kant);
  for (const d of drivable) for (const p of d.pts) mark(p.x, p.z, d.half + 3);
  const free = (x, z) => { const i = Math.floor((x - X0) / R), j = Math.floor((z - Z0) / R); if (i < 0 || j < 0 || i >= NX || j >= NZ) return true; return !occ[j * NX + i]; };
  const r = mulberry32(7); const gran = [], lov = [];
  const PROB = { 0: [0.10, 0.35], 1: [0.8, 0.65], 2: [0.05, 0.2], 3: [0.10, 0.3], 4: [0.005, 0.2], 5: [0.18, 0.85], 6: [0.03, 0.3], 7: [0.25, 0.25], 8: [0, 0], 9: [0, 0] };
  const tryTree = (x, z, ute) => {
    if (waterSD(x, z) < 3) return; const y = H(x, z); if (y < VATTEN + 0.6) return;
    let p, pc;
    const lc = ute ? -1 : lcAt(x, z);
    if (lc >= 0) { if (!free(x, z)) return; [p, pc] = PROB[lc] || PROB[0]; }
    else { const sk = skogUte(x, z); p = sk * 0.85; pc = sk > 0.5 ? 0.62 : 0.3; }
    if (r() > p) return;
    (r() < pc ? gran : lov).push([x, y, z, 0.75 + r() * 0.6, r()]);
  };
  for (let z = RAM[2]; z < RAM[3]; z += 7) for (let x = RAM[0]; x < RAM[1]; x += 7) tryTree(x + (r() - 0.5) * 6, z + (r() - 0.5) * 6, false);
  for (let z = -3600; z < 3600; z += 28) for (let x = -3600; x < 3600; x += 28) { if (inRam(x, z, -10)) continue; tryTree(x + (r() - 0.5) * 24, z + (r() - 0.5) * 24, true); }
  const granGeo = bake([{ g: new THREE.ConeGeometry(1, 1, 8), m: M4(0, 0.62, 0, 0, 1, 0.82, 1), c: C('#ffffff') }, { g: new THREE.CylinderGeometry(0.09, 0.12, 0.3, 5), m: M4(0, 0.15, 0), c: C('#6b5a48') }]);
  const granLo = bake([{ g: new THREE.ConeGeometry(1, 1, 5), m: M4(0, 0.6, 0, 0, 1, 0.85, 1), c: C('#ffffff') }]);
  const lovGeo = bake([{ g: new THREE.IcosahedronGeometry(1, 1), m: M4(0, 1.15, 0, 0, 1, 0.85, 1), c: C('#ffffff') }, { g: new THREE.CylinderGeometry(0.1, 0.14, 0.75, 5), m: M4(0, 0.37, 0), c: C('#6b5a48') }]);
  const lovLo = bake([{ g: new THREE.IcosahedronGeometry(1, 0), m: M4(0, 1.15, 0, 0, 1, 0.85, 1), c: C('#ffffff') }, { g: new THREE.CylinderGeometry(0.1, 0.14, 0.75, 3), m: M4(0, 0.37, 0), c: C('#6b5a48') }]);
  const matTree = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 });
  const make = (geo, list, base, sz, cast) => {
    if (!list.length) return;
    const im = new THREE.InstancedMesh(geo, matTree, list.length); const m = new THREE.Matrix4(); const q = new THREE.Quaternion(); const col = new THREE.Color(); const up = new THREE.Vector3(0, 1, 0);
    list.forEach(([x, y, z, s, v], i) => { q.setFromAxisAngle(up, v * 6.28); m.compose(new THREE.Vector3(x, y - 0.2, z), q, new THREE.Vector3(sz[1] * s, sz[0] * s, sz[1] * s)); im.setMatrixAt(i, m); col.set(base).offsetHSL((v - 0.5) * 0.04, (v - 0.5) * 0.1, (v - 0.5) * 0.08); im.setColorAt(i, col); });
    im.castShadow = cast; im.receiveShadow = true; im.frustumCulled = false; scene.add(im);
  };
  const rutt = drivable.filter(d => !d.stub).flatMap(d => d.pts.filter((p, i) => i % 10 === 0));
  const nearRoute = (t) => { for (const p of rutt) if (Math.abs(p.x - t[0]) < 140 && Math.abs(p.z - t[2]) < 140) return true; return false; };
  const G1 = gran.filter(t => inRam(t[0], t[2]) && nearRoute(t)), G2 = gran.filter(t => inRam(t[0], t[2]) && !nearRoute(t)), G3 = gran.filter(t => !inRam(t[0], t[2]));
  const L1 = lov.filter(t => inRam(t[0], t[2]) && nearRoute(t)), L2 = lov.filter(t => inRam(t[0], t[2]) && !nearRoute(t)), L3 = lov.filter(t => !inRam(t[0], t[2]));
  make(granGeo, G1, '#33522f', [15, 3.6], true); make(lovGeo, L1, '#55783a', [9, 3.0], true);
  make(granLo, G2, '#33522f', [15, 3.6], false); make(lovLo, L2, '#55783a', [9, 3.0], false);
  make(granLo, G3, '#2f4a2c', [16, 4.2], false); make(lovLo, L3, '#4f6e36', [9, 4.0], false);
}


// =====================================================================
// EPA-bilen
// =====================================================================
const LACK = [['Vinröd', '#5e1220'], ['Svart', '#141516'], ['Vit', '#e9e7e1'], ['Isblå', '#7fb2cf'], ['Mint', '#91d1b0'], ['Senapsgul', '#d3a62a']];
let lackIdx = 0;
const matLack = new THREE.MeshStandardMaterial({ color: LACK[0][1], metalness: 0.35, roughness: 0.32, envMapIntensity: 1.2 });
const matGlas = new THREE.MeshStandardMaterial({ color: 0x1b2229, metalness: 0.4, roughness: 0.08 });
const matSvart = new THREE.MeshStandardMaterial({ color: 0x151515, roughness: 0.6 });
const matKrom = new THREE.MeshStandardMaterial({ color: 0xd8dade, metalness: 1, roughness: 0.2 });
function buildCar() {
  const car = new THREE.Group(); const body = new THREE.Group(); car.add(body);
  const box = (w, h, d, mat, x, y, z, parent = body) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; parent.add(m); return m; };
  // kaross (fram = +z)
  box(1.74, 0.62, 4.78, matLack, 0, 0.72, 0);
  box(1.70, 0.16, 1.15, matLack, 0, 1.05, 1.75); // motorhuv
  box(1.70, 0.16, 0.95, matLack, 0, 1.05, -1.85); // bagagelucka
  // kupé (trapets)
  const kg = new THREE.BoxGeometry(1.62, 0.62, 2.45); const kp = kg.attributes.position;
  for (let i = 0; i < kp.count; i++) { if (kp.getY(i) > 0) { kp.setX(i, kp.getX(i) * 0.9); kp.setZ(i, kp.getZ(i) * 0.82 - 0.05); } }
  kg.computeVertexNormals(); const kupe = new THREE.Mesh(kg, matGlas); kupe.position.set(0, 1.42, -0.18); kupe.castShadow = true; body.add(kupe);
  box(1.47, 0.07, 1.95, matLack, 0, 1.75, -0.23); // tak
  for (const sx of [-1, 1]) { box(0.07, 0.6, 0.08, matLack, sx * 0.76, 1.42, 0.83); box(0.07, 0.6, 0.08, matLack, sx * 0.76, 1.42, -1.2); }
  // stötfångare, lampor
  box(1.82, 0.22, 0.22, matSvart, 0, 0.5, 2.45); box(1.82, 0.22, 0.22, matSvart, 0, 0.5, -2.45);
  const matLjus = new THREE.MeshStandardMaterial({ color: 0xfff6d8, emissive: 0xfff2c0, emissiveIntensity: 0.6 });
  const matBak = new THREE.MeshStandardMaterial({ color: 0x8a0d10, emissive: 0x500000, emissiveIntensity: 0.5 });
  for (const sx of [-1, 1]) { box(0.42, 0.2, 0.05, matLjus, sx * 0.6, 0.86, 2.4); box(0.5, 0.22, 0.05, matBak, sx * 0.58, 0.86, -2.4); }
  box(0.6, 0.18, 0.05, matKrom, 0, 0.86, 2.4); // grill
  box(0.06, 0.04, 0.5, matKrom, 0, 0.7, 2.25);
  // LGF-skylt (långsamtgående fordon)
  const tri = (r, col) => { const s = new THREE.Shape(); s.moveTo(0, r); s.lineTo(r * 0.866, -r * 0.5); s.lineTo(-r * 0.866, -r * 0.5); s.closePath(); return new THREE.Mesh(new THREE.ShapeGeometry(s), new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.25, side: THREE.DoubleSide })); };
  const lgf = new THREE.Group(); const t1 = tri(0.3, 0xc8101e); const t2 = tri(0.19, 0xff5a1a); t2.position.z = 0.006; lgf.add(t1, t2); lgf.position.set(0, 1.06, -2.455); lgf.rotation.y = Math.PI; body.add(lgf);
  // avgasrör, antenn, stänkskydd
  const ror = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.3, 8), matKrom); ror.rotation.x = Math.PI / 2; ror.position.set(0.55, 0.36, -2.5); body.add(ror);
  const ant = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 1.1, 4), matSvart); ant.position.set(-0.7, 1.6, 1.3); body.add(ant);
  for (const sx of [-1, 1]) box(0.3, 0.32, 0.03, matSvart, sx * 0.72, 0.36, -1.75);
  // hjul
  const wheels = []; const wg = new THREE.CylinderGeometry(0.33, 0.33, 0.24, 18); wg.rotateZ(Math.PI / 2);
  const hg = new THREE.CylinderGeometry(0.2, 0.2, 0.25, 12); hg.rotateZ(Math.PI / 2);
  for (const [x, z, front] of [[-0.78, 1.42, true], [0.78, 1.42, true], [-0.78, -1.38, false], [0.78, -1.38, false]]) {
    const pivot = new THREE.Group(); pivot.position.set(x, 0.33, z); car.add(pivot);
    const w = new THREE.Mesh(wg, matSvart); w.castShadow = true; pivot.add(w);
    const hub = new THREE.Mesh(hg, matKrom); w.add(hub);
    wheels.push({ pivot, w, front });
  }
  car.userData = { body, wheels };
  return car;
}

// =====================================================================
// Tåg
// =====================================================================
function buildTrain(len, bodyCol, bandCol) {
  const grp = new THREE.Group(); const cars = [];
  const side = canvasTex(512, 64, (g) => { g.fillStyle = bodyCol; g.fillRect(0, 0, 512, 64); g.fillStyle = '#1d242b'; for (let x = 10; x < 512; x += 46) g.fillRect(x, 14, 36, 18); g.fillStyle = bandCol; g.fillRect(0, 44, 512, 8); g.fillStyle = '#2b3138'; g.fillRect(150, 12, 26, 44); g.fillRect(340, 12, 26, 44); }, true, true);
  const matSide = new THREE.MeshStandardMaterial({ map: side, roughness: 0.4, metalness: 0.2 });
  const matB = new THREE.MeshStandardMaterial({ color: bodyCol, roughness: 0.4, metalness: 0.2 });
  for (let i = 0; i < len; i++) {
    const c = new THREE.Group();
    const geo = new THREE.BoxGeometry(3.2, 3.6, 25.5);
    const mats = [matSide, matSide, matB, matSvart, matB, matB];
    const b = new THREE.Mesh(geo, mats); b.position.y = 2.25; b.castShadow = true; c.add(b);
    const roof = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.4, 20), new THREE.MeshStandardMaterial({ color: 0x8a9096 })); roof.position.y = 4.25; c.add(roof);
    if (i === 0 || i === len - 1) {
      const nose = new THREE.Mesh(new THREE.BoxGeometry(3.15, 2.2, 2.4), matB); nose.position.set(0, 1.6, (i === 0 ? 1 : -1) * 13.6); c.add(nose);
      const win = new THREE.Mesh(new THREE.BoxGeometry(2.6, 1.0, 1.6), matGlas); win.position.set(0, 3.1, (i === 0 ? 1 : -1) * 13.1); win.rotation.x = (i === 0 ? -1 : 1) * 0.5; c.add(win);
    }
    grp.add(c); cars.push(c);
  }
  scene.add(grp); return { grp, cars, len };
}
function placeTrain(tr, tp, sHead, dir) {
  for (let i = 0; i < tr.len; i++) {
    const s = sHead - dir * (i * 26.5 + 13);
    const a = trackPoint(tp, s - 8), b = trackPoint(tp, s + 8), p = trackPoint(tp, s);
    tr.cars[i].position.set(p.x, p.y + 0.3, p.z);
    tr.cars[i].rotation.set(0, Math.atan2(b.x - a.x, b.z - a.z), 0);
  }
}

// =====================================================================
// Spelvariabler
// =====================================================================
let car, carState, pendel, regional;
const keys = {};
let camMode = 0; // 0 jakt, 1 huv, 2 drönare
let dronAz = 0, dronDist = 160, dronEl = 0.95;
let showLabels = true;
let started = false;
let VMAX = 30 / 3.6; const VREV = 10 / 3.6;
let snabb = /[?&]snabb/.test(location.search);
function setSnabb(on) { snabb = on; VMAX = (on ? 90 : 30) / 3.6; $('btnSnabb').classList.toggle('pa', on); $('sparr').textContent = on ? 'Snabbläge' : 'EPA-spärr'; $('sparr').classList.toggle('snabb', on); }

function initCar() {
  car = buildCar(); scene.add(car);
  const st = K.start;
  carState = { x: st.x, z: st.z, h: st.h, v: 0, steer: 0, y: H(st.x, st.z), pitch: 0, roll: 0, acc: 0, bodyRoll: 0, bodyPitch: 0, wheelRot: 0, rpm: 900, gear: 1, limiter: false, scrape: 0 };
}
function nearestOnPolyline(pts, x, z) {
  let best = null;
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1]; const [d, t, cx, cz] = segDist(x, z, a.x, a.z, b.x, b.z);
    if (!best || d < best.d) best = { d, cx, cz, i, t };
  }
  return best;
}
function constrain(px, pz) {
  let best = null;
  for (const d of drivable) {
    const r = nearestOnPolyline(d.pts, px, pz); if (!r) continue;
    const lim = d.half + 0.3; let cx = px, cz = pz;
    if (r.d > lim) { const k = lim / r.d; cx = r.cx + (px - r.cx) * k; cz = r.cz + (pz - r.cz) * k; }
    let cap = false;
    if (d.capStart) { const p0 = d.pts[0]; const al = (cx - p0.x) * p0.tx + (cz - p0.z) * p0.tz; if (al < 2.6) { cx += p0.tx * (2.6 - al); cz += p0.tz * (2.6 - al); cap = true; } }
    if (d.capEnd) { const p1 = d.pts[d.pts.length - 1]; const al = (cx - p1.x) * p1.tx + (cz - p1.z) * p1.tz; if (al > -2.6) { cx -= p1.tx * (al + 2.6); cz -= p1.tz * (al + 2.6); cap = true; } }
    const corr = Math.hypot(cx - px, cz - pz);
    if (!best || corr < best.corr) best = { cx, cz, corr, d, cap };
  }
  return best;
}
function updateCar(dt) {
  const s = carState;
  const up = keys.up || touch.up, dn = keys.down || touch.down, lf = keys.left || touch.left, rt = keys.right || touch.right, hb = keys.space;
  // drivning
  let a = 0;
  if (up) { if (s.v < -0.2) a = 7; else a = (snabb ? 7 : 2.7) * (1 - Math.pow(Math.max(0, s.v) / VMAX, 2.2)) + 0.25; }
  if (dn) { if (s.v > 0.3) a = -7.5; else a = -1.8 * (1 - Math.pow(Math.max(0, -s.v) / VREV, 2)); }
  if (!up && !dn) a = -Math.sign(s.v) * Math.min(Math.abs(s.v) / dt, 0.9);
  if (hb) a = -Math.sign(s.v) * Math.min(Math.abs(s.v) / dt, 9);
  a -= 9.81 * Math.sin(s.pitch) * 0.55;
  s.v += a * dt;
  s.limiter = false;
  if (s.v > VMAX) { s.v = VMAX; if (up) s.limiter = true; }
  if (s.v < -VREV) s.v = -VREV;
  if (!up && !dn && Math.abs(s.v) < 0.05) s.v = 0;
  s.acc = lerp(s.acc, a, 1 - Math.exp(-dt * 5));
  // styrning
  const maxSteer = 0.6 - 0.22 * Math.abs(s.v) / VMAX;
  const target = (lf ? 1 : 0) - (rt ? 1 : 0);
  s.steer = lerp(s.steer, target * maxSteer, 1 - Math.exp(-dt * 6));
  const yaw = s.v / 2.65 * Math.tan(s.steer);
  s.h += yaw * dt;
  const fx = Math.sin(s.h), fz = Math.cos(s.h);
  let nx = s.x + fx * s.v * dt, nz = s.z + fz * s.v * dt;
  const c = snabb ? constrainFri(nx, nz) : constrain(nx, nz);
  if (c && c.corr > 0.001) {
    nx = c.cx; nz = c.cz;
    if (c.cap) { if (Math.abs(s.v) > 1.5) blip(0.35); s.v *= 0.2; }
    else { s.v *= Math.max(0.6, 1 - c.corr * 2.5); s.scrape = Math.min(1, s.scrape + c.corr * 3); }
  }
  s.scrape *= Math.exp(-dt * 6);
  s.x = nx; s.z = nz;
  // höjd och lutning (hjulen följer vägytan)
  const RO = 0.12;
  const hf = H(s.x + fx * 1.4, s.z + fz * 1.4), hr = H(s.x - fx * 1.4, s.z - fz * 1.4);
  const lx = Math.cos(s.h), lz = -Math.sin(s.h); // vänster (lokal +x)
  const hl = H(s.x + lx * 0.78, s.z + lz * 0.78), hrr = H(s.x - lx * 0.78, s.z - lz * 0.78);
  s.y = (hf + hr + hl + hrr) / 4 + RO;
  s.pitch = Math.atan2(hf - hr, 2.8); s.roll = Math.atan2(hl - hrr, 1.56);
  s.bodyRoll = lerp(s.bodyRoll, clamp(yaw * s.v * 0.03, -0.07, 0.07), 1 - Math.exp(-dt * 4));
  s.bodyPitch = lerp(s.bodyPitch, clamp(-s.acc * 0.006, -0.03, 0.04), 1 - Math.exp(-dt * 4));
  // varvtal
  const kmh = Math.abs(s.v) * 3.6;
  let rpm;
  if (s.v < -0.1) { rpm = 900 + kmh / 10 * 3000; s.gear = 'R'; }
  else if (kmh < 13) { rpm = 900 + kmh / 13 * 3400; s.gear = 1; }
  else if (kmh <= 30.5) { rpm = 2300 + (kmh - 13) / 17 * 2500; s.gear = 2; }
  else { const gi = Math.min(3, Math.floor((kmh - 30) / 20)); rpm = 2600 + ((kmh - 30) - gi * 20) / 20 * 2300; s.gear = 3 + gi; }
  if (up) rpm += 250;
  if (s.limiter) rpm = 4700 + Math.sin(performance.now() / 40) * 220;
  s.rpm = lerp(s.rpm, rpm, 1 - Math.exp(-dt * 8));
  // modell
  car.position.set(s.x, s.y, s.z);
  car.rotation.set(0, 0, 0); car.rotation.order = 'YXZ';
  car.rotation.y = s.h; car.rotation.x = -s.pitch; car.rotation.z = s.roll;
  const { body, wheels } = car.userData;
  const shake = (Math.sin(performance.now() / 23) * 0.004 + Math.sin(performance.now() / 61) * 0.003) * (0.4 + s.rpm / 5000);
  body.rotation.set(s.bodyPitch, 0, s.bodyRoll + shake); body.position.y = shake * 2;
  s.wheelRot += s.v * dt / 0.33;
  for (const w of wheels) { w.w.rotation.x = s.wheelRot; if (w.front) w.pivot.rotation.y = s.steer; }
}
// snabbläge: alla bilvägar öppna, bommar ignoreras
function constrainFri(px, pz) {
  let best = null;
  roadIndex.near(px, pz, 30, (sg) => { const g = sg.data.g; if (!g.bil || g.tunnel) return; const [d, t, cx, cz] = segDist(px, pz, sg.ax, sg.az, sg.bx, sg.bz); const lim = g.bredd / 2 + 0.6; const ex = d - lim; if (!best || ex < best.ex) best = { ex, d, cx, cz, lim }; });
  if (!best || best.ex <= 0) return null;
  const k = best.lim / best.d; const cx = best.cx + (px - best.cx) * k, cz = best.cz + (pz - best.cz) * k;
  return { cx, cz, corr: Math.hypot(cx - px, cz - pz), cap: false };
}
function resetCar() {
  if (snabb) { const nr = nearestRoad(carState.x, carState.z, 400, g => g.bil && !g.tunnel); if (nr) { const a = nr.g.sm[nr.i], b = nr.g.sm[nr.i + 1]; carState.x = lerp(a.x, b.x, nr.t); carState.z = lerp(a.z, b.z, nr.t); carState.v = 0; const f = Math.sin(carState.h) * a.tx + Math.cos(carState.h) * a.tz; carState.h = Math.atan2(a.tx, a.tz) + (f < 0 ? Math.PI : 0); } return; }
  let best = null;
  for (const d of drivable) { const r = nearestOnPolyline(d.pts, carState.x, carState.z); if (r && (!best || r.d < best.r.d)) best = { r, d }; }
  if (!best) return; const p = best.d.pts[best.r.i];
  carState.x = p.x; carState.z = p.z; carState.v = 0;
  const f = Math.sin(carState.h) * p.tx + Math.cos(carState.h) * p.tz;
  carState.h = Math.atan2(p.tx, p.tz) + (f < 0 ? Math.PI : 0);
}

// =====================================================================
// Kamera
// =====================================================================
const camPos = new THREE.Vector3(), camLook = new THREE.Vector3(); const testCam = { pos: new THREE.Vector3(), look: new THREE.Vector3() };
let introT = 0;
function updateCamera(dt) {
  const s = carState; const fx = Math.sin(s.h), fz = Math.cos(s.h);
  if (!started) {
    introT += dt * 0.05;
    const cx = 80 + Math.cos(introT) * 470, cz = 120 + Math.sin(introT) * 360;
    camera.position.set(cx, 150, cz); camera.lookAt(60, 25, 60); return;
  }
  if (camMode === 3) { camera.position.copy(testCam.pos); camera.lookAt(testCam.look); const s2 = carState; setShadowBox(160); sun.position.set(testCam.look.x + SOL.x * 500, testCam.look.y + SOL.y * 500, testCam.look.z + SOL.z * 500); sun.target.position.copy(testCam.look); return; }
  if (camMode === 0) {
    const back = s.v < -0.3 ? -1 : 1;
    const cd = 7.2 + Math.max(0, Math.abs(s.v) - 8.3) * 0.12;
    const want = new THREE.Vector3(s.x - fx * cd, s.y + 2.9, s.z - fz * cd);
    if (back < 0) want.set(s.x + fx * cd, s.y + 2.9, s.z + fz * cd);
    want.y = Math.max(want.y, H(want.x, want.z) + 1.4);
    camPos.lerp(want, 1 - Math.exp(-dt * 4.5));
    camLook.lerp(new THREE.Vector3(s.x + fx * 3, s.y + 1.2, s.z + fz * 3), 1 - Math.exp(-dt * 8));
    camera.position.copy(camPos); camera.lookAt(camLook);
  } else if (camMode === 1) {
    const lx = Math.cos(s.h), lz = -Math.sin(s.h);
    camera.position.set(s.x + fx * 0.05 + lx * 0.36, s.y + 1.42, s.z + fz * 0.05 + lz * 0.36);
    camera.lookAt(s.x + fx * 20, s.y + 1.2 + Math.sin(s.pitch) * 20, s.z + fz * 20);
  } else {
    const az = s.h + Math.PI + dronAz;
    const want = new THREE.Vector3(s.x + Math.sin(az) * Math.cos(dronEl) * dronDist, s.y + Math.sin(dronEl) * dronDist, s.z + Math.cos(az) * Math.cos(dronEl) * dronDist);
    want.y = Math.max(want.y, H(want.x, want.z) + 6); camPos.lerp(want, 1 - Math.exp(-dt * 3)); camera.position.copy(camPos);
    camLook.lerp(new THREE.Vector3(s.x, s.y, s.z), 1 - Math.exp(-dt * 6)); camera.lookAt(camLook);
  }
  // skuggor följer bilen
  const r = camMode === 2 ? Math.min(420, 90 + dronDist * 1.1) : 120; setShadowBox(r);
  sun.position.set(s.x + SOL.x * 500, s.y + SOL.y * 500, s.z + SOL.z * 500); sun.target.position.set(s.x, s.y, s.z);
}

// =====================================================================
// Ljud
// =====================================================================
let audio = null;
function initAudio() {
  const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
  const ctx = new AC(); const master = ctx.createGain(); master.gain.value = 0.8; master.connect(ctx.destination);
  const comp = ctx.createDynamicsCompressor(); comp.connect(master);
  // motor
  const eg = ctx.createGain(); eg.gain.value = 0.0; const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 500; lp.Q.value = 3;
  const o1 = ctx.createOscillator(); o1.type = 'sawtooth'; const o2 = ctx.createOscillator(); o2.type = 'square'; const o3 = ctx.createOscillator(); o3.type = 'triangle';
  const g1 = ctx.createGain(); g1.gain.value = 0.5; const g2 = ctx.createGain(); g2.gain.value = 0.25; const g3 = ctx.createGain(); g3.gain.value = 0.35;
  o1.connect(g1).connect(lp); o2.connect(g2).connect(lp); o3.connect(g3).connect(lp); lp.connect(eg).connect(comp);
  const nb = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate); const nd = nb.getChannelData(0); for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
  const noise = ctx.createBufferSource(); noise.buffer = nb; noise.loop = true; const nbp = ctx.createBiquadFilter(); nbp.type = 'bandpass'; nbp.frequency.value = 180; nbp.Q.value = 0.8; const ng = ctx.createGain(); ng.gain.value = 0.15;
  noise.connect(nbp).connect(ng).connect(eg);
  // skrap
  const sc = ctx.createBufferSource(); sc.buffer = nb; sc.loop = true; const sbp = ctx.createBiquadFilter(); sbp.type = 'bandpass'; sbp.frequency.value = 1400; sbp.Q.value = 1.5; const sg = ctx.createGain(); sg.gain.value = 0; sc.connect(sbp).connect(sg).connect(comp);
  [o1, o2, o3, noise, sc].forEach(o => o.start());
  // radio
  const rg = ctx.createGain(); rg.gain.value = 0.0; const rlp = ctx.createBiquadFilter(); rlp.type = 'lowpass'; rlp.frequency.value = 4200; rg.connect(rlp).connect(comp);
  audio = { ctx, eg, lp, o1, o2, o3, sg, rg, nb, radioOn: true, step: 0, next: ctx.currentTime + 0.1, tutar: false };
  setInterval(radioTick, 25);
  setRadio(true);
}
function setRadio(on) {
  if (!audio) return; audio.radioOn = on; const t = audio.ctx.currentTime;
  audio.rg.gain.cancelScheduledValues(t); audio.rg.gain.linearRampToValueAtTime(on ? 0.42 : 0.0, t + 0.3);
  $('btnRadio').classList.toggle('pa', on);
}
const BAS = [55, 55, 43.65, 43.65, 65.41, 65.41, 49, 49];
const ACK = [[220, 261.6, 329.6], [174.6, 220, 261.6], [261.6, 329.6, 392], [196, 246.9, 293.7]];
function radioTick() {
  if (!audio) return; const { ctx } = audio; const spb = 60 / 128 / 4;
  while (audio.next < ctx.currentTime + 0.15) { if (audio.radioOn) playStep(audio.step, audio.next); audio.next += spb; audio.step = (audio.step + 1) % 128; }
}
function playStep(st, t) {
  const { ctx, rg, nb } = audio; const s16 = st % 16; const bar = Math.floor(st / 16) % 8;
  if (s16 % 4 === 0) { const o = ctx.createOscillator(); const g = ctx.createGain(); o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(42, t + 0.13); g.gain.setValueAtTime(1.0, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.38); o.connect(g).connect(rg); o.start(t); o.stop(t + 0.4); }
  if (s16 === 4 || s16 === 12) { const n = ctx.createBufferSource(); n.buffer = nb; const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = 1900; const g = ctx.createGain(); g.gain.setValueAtTime(0.5, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.16); n.connect(f).connect(g).connect(rg); n.start(t, Math.random()); n.stop(t + 0.2); }
  if (s16 % 2 === 1) { const n = ctx.createBufferSource(); n.buffer = nb; const f = ctx.createBiquadFilter(); f.type = 'highpass'; f.frequency.value = 7500; const g = ctx.createGain(); g.gain.setValueAtTime(0.16, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.05); n.connect(f).connect(g).connect(rg); n.start(t, Math.random()); n.stop(t + 0.06); }
  if (s16 % 4 === 2) { const o = ctx.createOscillator(); o.type = 'sawtooth'; o.frequency.value = BAS[bar]; const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.setValueAtTime(900, t); f.frequency.exponentialRampToValueAtTime(200, t + 0.18); const g = ctx.createGain(); g.gain.setValueAtTime(0.42, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.2); o.connect(f).connect(g).connect(rg); o.start(t); o.stop(t + 0.22); }
  if (bar >= 2 && s16 % 2 === 0) { const ch = ACK[Math.floor(bar / 2) % 4]; const o = ctx.createOscillator(); o.type = 'square'; o.frequency.value = ch[(s16 / 2) % 3] * 2; const g = ctx.createGain(); g.gain.setValueAtTime(0.045, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.11); o.connect(g).connect(rg); o.start(t); o.stop(t + 0.12); }
}
function updateAudio() {
  if (!audio) return; const { ctx, eg, lp, o1, o2, o3, sg } = audio; const t = ctx.currentTime; const s = carState;
  const f = s.rpm / 60 * 2;
  o1.frequency.setTargetAtTime(f, t, 0.03); o2.frequency.setTargetAtTime(f * 0.5, t, 0.03); o3.frequency.setTargetAtTime(f * 1.5, t, 0.03);
  const thr = (keys.up || touch.up) ? 1 : 0.4;
  lp.frequency.setTargetAtTime(220 + s.rpm * 0.18 * thr + (s.limiter ? 300 : 0), t, 0.05);
  let vol = 0.22 + 0.18 * thr + s.rpm / 5000 * 0.12; if (s.limiter && Math.sin(performance.now() / 30) > 0.3) vol *= 0.4;
  if (camMode === 2) vol *= 0.35;
  eg.gain.setTargetAtTime(vol * 0.55, t, 0.04);
  sg.gain.setTargetAtTime(s.scrape * 0.25, t, 0.03);
}
function blip(v) { if (!audio) return; const { ctx, nb } = audio; const t = ctx.currentTime; const n = ctx.createBufferSource(); n.buffer = nb; const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 400; const g = ctx.createGain(); g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.3); n.connect(f).connect(g).connect(ctx.destination); n.start(t); n.stop(t + 0.32); }
function tuta(on) {
  if (!audio) return; const { ctx } = audio;
  if (on && !audio.tutar) { const g = ctx.createGain(); g.gain.value = 0.18; g.connect(ctx.destination); const a = ctx.createOscillator(); a.type = 'square'; a.frequency.value = 370; const b = ctx.createOscillator(); b.type = 'square'; b.frequency.value = 466; a.connect(g); b.connect(g); a.start(); b.start(); audio.tutar = { a, b, g }; }
  if (!on && audio.tutar) { audio.tutar.a.stop(); audio.tutar.b.stop(); audio.tutar.g.disconnect(); audio.tutar = false; }
}

// =====================================================================
// Etiketter, klick, info
// =====================================================================
const labelPool = []; const labelBox = $('etiketter');
function getLabel(i) {
  if (!labelPool[i]) { const d = document.createElement('div'); d.className = 'etikett'; d.addEventListener('pointerdown', (e) => { e.stopPropagation(); }); d.addEventListener('click', (e) => { e.stopPropagation(); const bi = +d.dataset.bi; selectHouse(bi); }); labelBox.appendChild(d); labelPool[i] = d; }
  return labelPool[i];
}
const v3 = new THREE.Vector3();
function updateLabels() {
  let n = 0;
  if (showLabels && started) {
    const cp = camMode === 2 ? { x: carState.x, z: carState.z } : camera.position; const R = camMode === 2 ? clamp(dronDist * 0.7, 50, 260) : 130; const maxN = camMode === 2 ? 55 : 70;
    const cand = [];
    for (const h of world.hus) { const d = Math.hypot(h.x - cp.x, h.z - cp.z); if (d < R || (h.namn && d < Math.max(R * 2.2, 300))) cand.push([d - (h.namn ? 200 : 0), h]); }
    cand.sort((a, b) => a[0] - b[0]);
    const W = window.innerWidth, Hh = window.innerHeight;
    for (const [, h] of cand) {
      if (n >= maxN) break;
      v3.set(h.x, h.top + 1.6, h.z).project(camera);
      if (v3.z > 1 || v3.x < -1.1 || v3.x > 1.1 || v3.y < -1.1 || v3.y > 1.1) continue;
      const el = getLabel(n++);
      const txt = h.namn ? `${h.id} · ${h.namn}` : h.id;
      if (el.textContent !== txt) el.textContent = txt;
      el.dataset.bi = h.idx; el.className = 'etikett' + (h.namn ? ' kand' : '') + (selected === h.idx ? ' vald' : '');
      el.style.transform = `translate(${(v3.x * 0.5 + 0.5) * W}px, ${(-v3.y * 0.5 + 0.5) * Hh}px) translate(-50%, -100%)`;
      el.style.display = '';
    }
  }
  for (let i = n; i < labelPool.length; i++) labelPool[i].style.display = 'none';
}
let selected = -1; let selBox = null;
function selectHouse(bi) {
  selected = bi; const h = world.hus[bi];
  if (selBox) { scene.remove(selBox); selBox.geometry.dispose(); }
  const pts = []; const y0 = h.gmin - 0.2, y1 = h.top + 0.6; const cs = h.corners;
  for (let i = 0; i < cs.length; i++) { const a = cs[i], b = cs[(i + 1) % cs.length]; pts.push(a[0], y0, a[1], b[0], y0, b[1], a[0], y1, a[1], b[0], y1, b[1], a[0], y0, a[1], a[0], y1, a[1]); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  selBox = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xffd400, depthTest: false })); selBox.renderOrder = 999; scene.add(selBox);
  const klass = KLASSNAMN[h.typ] || h.typ; const typ = h.namn || klass;
  const sak = { 'säker': 'Läge och namn belagda', 'osm': 'Läge och form från OpenStreetMap · höjd och färg uppskattade' }[h.sakerhet] || '';
  const van = h.typ === 'trappa' ? '130 steg' : `${h.van} vån. (uppsk.)`;
  const tak = { sadel: 'sadeltak', valm: 'valmat tak', platt: 'platt tak', pulpet: 'pulpettak' }[h.tak] || h.tak;
  $('infoId').textContent = h.id;
  $('infoNamn').textContent = typ;
  $('infoRader').innerHTML = `
    ${h.namn ? `<div><span>Typ</span>${klass}</div>` : ''}
    <div><span>Färg</span><i class="ruta" style="background:${h.vagg}"></i>${h.vagg} · <i class="ruta" style="background:${h.takfarg}"></i>${tak}</div>
    <div><span>Storlek</span>${h.area} m² · ${van}</div>
    <div><span>Läge</span>x ${Math.round(h.x)}, z ${Math.round(h.z)} · mark ${Math.round(h.gmin)} m ö.h.</div>
    <div><span>Status</span>${sak}</div>
    ${h.osm && h.osm.startsWith('w') ? `<div><span>OSM</span>way ${h.osm.slice(1)}</div>` : ''}
    ${h.not ? `<div class="not">${h.not}</div>` : ''}`;
  $('infoKopia').dataset.text = `${h.id} (${typ}): `;
  $('info').classList.add('visa');
}
function showPoint(x, z) {
  const y = H(x, z); const nr = nearestRoad(x, z, 80);
  $('infoId').textContent = 'Punkt';
  $('infoNamn').textContent = `x ${Math.round(x)}, z ${Math.round(z)}`;
  $('infoRader').innerHTML = `<div><span>Höjd</span>${y.toFixed(1)} m ö.h.${y < VATTEN ? ' (Frösjön)' : ''}</div>${nr ? `<div><span>Närmast</span>${nr.g.namn || 'namnlös gata'} (${nr.g.id}), ${nr.d.toFixed(0)} m bort</div>` : ''}<div class="not">Använd koordinaten om något ska flyttas hit.</div>`;
  $('infoKopia').dataset.text = `Punkt x=${Math.round(x)}, z=${Math.round(z)}: `;
  $('info').classList.add('visa');
  if (selBox) { scene.remove(selBox); selBox = null; } selected = -1;
}
const raycaster = new THREE.Raycaster(); const ndc = new THREE.Vector2();
let terrainMeshes = [];
function pick(cx, cy) {
  ndc.set(cx / window.innerWidth * 2 - 1, -(cy / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObjects(world.pickables.concat(terrainMeshes), false);
  for (const h of hits) {
    const o = h.object;
    if (o.userData.owner && h.faceIndex !== undefined) { selectHouse(o.userData.owner[h.faceIndex]); return; }
    if (o.userData.bidx !== undefined) { selectHouse(o.userData.bidx); return; }
    if (o.userData.terrain) { showPoint(h.point.x, h.point.z); return; }
  }
}

// =====================================================================
// HUD
// =====================================================================
const spCan = $('hastighet'); const spCtx = spCan.getContext('2d');
function drawSpeedo() {
  const s = carState; const w = spCan.width, h = spCan.height; const g = spCtx; g.clearRect(0, 0, w, h);
  const cx = w / 2, cy = h * 0.86, r = w * 0.4; const A0 = Math.PI * 0.9, A1 = Math.PI * 2.1; const MAXK = snabb ? 100 : 40;
  g.lineWidth = 10; g.strokeStyle = 'rgba(255,255,255,0.12)'; g.beginPath(); g.arc(cx, cy, r, A0, A1); g.stroke();
  const a30 = A0 + (30 / MAXK) * (A1 - A0);
  if (!snabb) { g.strokeStyle = '#ff3b30'; g.beginPath(); g.arc(cx, cy, r, a30, A1); g.stroke(); }
  g.fillStyle = '#e9e6dc'; g.font = `600 ${w * 0.055}px system-ui, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
  for (let k = 0; k <= MAXK; k += (snabb ? 20 : 10)) { const a = A0 + k / MAXK * (A1 - A0); g.fillText(k, cx + Math.cos(a) * (r - 22), cy + Math.sin(a) * (r - 22)); g.strokeStyle = '#e9e6dc'; g.lineWidth = 2; g.beginPath(); g.moveTo(cx + Math.cos(a) * (r - 8), cy + Math.sin(a) * (r - 8)); g.lineTo(cx + Math.cos(a) * (r + 5), cy + Math.sin(a) * (r + 5)); g.stroke(); }
  const kmh = Math.abs(s.v) * 3.6; const a = A0 + Math.min(kmh, MAXK) / MAXK * (A1 - A0);
  g.strokeStyle = '#ffb000'; g.lineWidth = 4; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(a) * (r - 4), cy + Math.sin(a) * (r - 4)); g.stroke();
  g.fillStyle = '#ffb000'; g.beginPath(); g.arc(cx, cy, 6, 0, 7); g.fill();
  $('kmh').textContent = Math.round(kmh);
  $('vaxel').textContent = s.gear;
  $('sparr').classList.toggle('pa', s.limiter);
  $('hojd').textContent = `${Math.round(s.y)} m ö.h.`;
}
// minikarta
let mmBase = null; const MM = { x0: Math.min(-950, RAM[0] - 50), z0: Math.min(-470, RAM[2] - 30), scale: 0.5 };
function buildMinimap() {
  const w = Math.round((Math.max(1450, RAM[1] + 70) - MM.x0) * MM.scale), h = Math.round((Math.max(1170, RAM[3] + 50) - MM.z0) * MM.scale); const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d');
  const img = g.createImageData(w, h); const tmp = new THREE.Color();
  for (let j = 0; j < h; j += 2) for (let i = 0; i < w; i += 2) {
    const x = MM.x0 + i / MM.scale, z = MM.z0 + j / MM.scale; let r, gg, b;
    if (waterSD(x, z) < 0) { r = 70; gg = 120; b = 160; }
    else {
      const lc = lcAt(x, z); tmp.copy(LCF[lc] || LCF[0]).convertLinearToSRGB(); r = tmp.r * 255; gg = tmp.g * 255; b = tmp.b * 255;
      const y = heightNC(x, z); const hx = heightNC(x + 4, z) - y, hz = heightNC(x, z + 4) - y; const sh = clamp(1 - (hx + hz) * 0.07, 0.6, 1.35); r *= sh; gg *= sh; b *= sh;
    }
    for (let dj = 0; dj < 2; dj++) for (let di = 0; di < 2; di++) { const k = ((j + dj) * w + (i + di)) * 4; img.data[k] = r; img.data[k + 1] = gg; img.data[k + 2] = b; img.data[k + 3] = 255; }
  }
  g.putImageData(img, 0, 0);
  const P = (x, z) => [(x - MM.x0) * MM.scale, (z - MM.z0) * MM.scale];
  const line = (pts, col, lw, dash) => { g.strokeStyle = col; g.lineWidth = lw; g.setLineDash(dash || []); g.beginPath(); pts.forEach((p, i) => { const q = P(p.x ?? p[0], p.z ?? p[1]); i ? g.lineTo(...q) : g.moveTo(...q); }); g.stroke(); g.setLineDash([]); };
  g.lineCap = 'round'; g.lineJoin = 'round';
  for (const gt of gator) { if (gt.tunnel) continue; line(gt.pts, gt.bil ? '#eeeae0' : 'rgba(240,236,224,0.55)', gt.bil ? Math.max(2, gt.bredd * MM.scale) : 1, gt.bil ? null : [2, 2]); }
  for (const tr of railTracks) line(tr.sm, '#2b2b2b', 2, [5, 3]);
  for (const d of drivable) if (!d.stub) line(d.pts, '#ffb000', Math.max(3, d.half * 2 * MM.scale));
  for (const hh of world.hus) { g.fillStyle = hh.namn ? '#c0392b' : '#5c5852'; g.beginPath(); hh.corners.forEach((p, i) => { const q = P(p[0], p[1]); i ? g.lineTo(...q) : g.moveTo(...q); }); g.fill(); }
  mmBase = c;
}
const mmCan = $('minikarta'); const mmCtx = mmCan.getContext('2d');
function drawMinimap() {
  if (!mmBase) return; const g = mmCtx; const w = mmCan.width, h = mmCan.height; const s = carState;
  const zoom = 1.4; g.save(); g.clearRect(0, 0, w, h);
  g.beginPath(); g.arc(w / 2, h / 2, w / 2 - 2, 0, 7); g.clip();
  g.fillStyle = '#3d4a2f'; g.fillRect(0, 0, w, h);
  const cx = (s.x - MM.x0) * MM.scale, cz = (s.z - MM.z0) * MM.scale;
  g.translate(w / 2, h / 2); g.scale(zoom, zoom); g.translate(-cx, -cz); g.drawImage(mmBase, 0, 0); g.restore();
  g.save(); g.translate(w / 2, h / 2); g.rotate(-s.h + Math.PI);
  g.fillStyle = '#fff'; g.strokeStyle = '#000'; g.lineWidth = 1.5; g.beginPath(); g.moveTo(0, -9); g.lineTo(6, 7); g.lineTo(0, 3); g.lineTo(-6, 7); g.closePath(); g.fill(); g.stroke(); g.restore();
  g.fillStyle = '#fff'; g.font = 'bold 12px system-ui'; g.textAlign = 'center'; g.fillText('N', w / 2, 14);
}
let lastGata = ''; let gataTimer = 0;
function updateStreetToast(dt) {
  const nr = nearestRoad(carState.x, carState.z, 20, g => !!g.namn);
  const name = nr && nr.d < 12 ? nr.g.namn : '';
  if (name && name !== lastGata) { lastGata = name; const el = $('gatunamn'); el.textContent = name; el.classList.remove('visa'); void el.offsetWidth; el.classList.add('visa'); }
}

// =====================================================================
// Inmatning
// =====================================================================
const touch = { up: false, down: false, left: false, right: false };
const KEYMAP = { KeyW: 'up', ArrowUp: 'up', KeyS: 'down', ArrowDown: 'down', KeyA: 'left', ArrowLeft: 'left', KeyD: 'right', ArrowRight: 'right', Space: 'space' };
window.addEventListener('keydown', (e) => {
  if (!started) return;
  const k = KEYMAP[e.code]; if (k) { keys[k] = true; e.preventDefault(); }
  if (e.repeat) return;
  if (e.code === 'KeyC') cycleCam();
  if (e.code === 'KeyI') toggleLabels();
  if (e.code === 'KeyR') setRadio(!audio?.radioOn);
  if (e.code === 'KeyP') nextLack();
  if (e.code === 'KeyT') resetCar();
  if (e.code === 'KeyU') setSnabb(!snabb);
  if (e.code === 'KeyH') tuta(true);
  if (e.code === 'Escape') $('info').classList.remove('visa');
});
window.addEventListener('keyup', (e) => { const k = KEYMAP[e.code]; if (k) keys[k] = false; if (e.code === 'KeyH') tuta(false); });
window.addEventListener('blur', () => { for (const k in keys) keys[k] = false; tuta(false); });
function cycleCam() { camMode = (camMode + 1) % 3; $('btnKamera').textContent = ['Kamera: bakom', 'Kamera: förare', 'Kamera: drönare'][camMode]; $('dronTips').style.display = camMode === 2 ? '' : 'none'; }
function toggleLabels() { showLabels = !showLabels; $('btnId').classList.toggle('pa', showLabels); }
function nextLack() { lackIdx = (lackIdx + 1) % LACK.length; matLack.color.set(LACK[lackIdx][1]); $('btnLack').textContent = 'Lack: ' + LACK[lackIdx][0]; }
let down = null;
canvas.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, t: performance.now(), az: dronAz, el: dronEl }; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener('pointermove', (e) => { if (!down || camMode !== 2) return; dronAz = down.az - (e.clientX - down.x) * 0.008; dronEl = clamp(down.el + (e.clientY - down.y) * 0.005, 0.2, 1.45); });
canvas.addEventListener('pointerup', (e) => { if (!down) return; const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y); if (moved < 6 && performance.now() - down.t < 600 && started) pick(e.clientX, e.clientY); down = null; });
canvas.addEventListener('wheel', (e) => { if (camMode === 2) { dronDist = clamp(dronDist * Math.exp(e.deltaY * 0.001), 25, 700); e.preventDefault(); } }, { passive: false });
for (const [id, k] of [['tVanster', 'left'], ['tHoger', 'right'], ['tGas', 'up'], ['tBroms', 'down']]) {
  const el = $(id); el.addEventListener('pointerdown', (e) => { e.preventDefault(); touch[k] = true; el.classList.add('tryckt'); });
  for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) el.addEventListener(ev, () => { touch[k] = false; el.classList.remove('tryckt'); });
}
$('btnKamera').onclick = cycleCam; $('btnId').onclick = toggleLabels; $('btnRadio').onclick = () => setRadio(!audio?.radioOn); $('btnLack').onclick = nextLack; $('btnReset').onclick = resetCar; $('btnSnabb').onclick = () => setSnabb(!snabb);
$('btnHjalp').onclick = () => $('hjalp').classList.toggle('visa');
$('infoStang').onclick = () => { $('info').classList.remove('visa'); if (selBox) { scene.remove(selBox); selBox = null; } selected = -1; };
$('infoKopia').onclick = async () => {
  const t = $('infoKopia').dataset.text || '';
  try { await navigator.clipboard.writeText(t); $('infoKopia').textContent = 'Kopierat!'; } catch (e) { const f = $('kopiaFalt'); f.value = t; f.style.display = 'block'; f.select(); $('infoKopia').textContent = 'Markerat – kopiera'; }
  setTimeout(() => { $('infoKopia').textContent = 'Kopiera ID-rad'; }, 1600);
};
window.addEventListener('resize', () => { camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); });
if (('ontouchstart' in window) || navigator.maxTouchPoints > 0) document.body.classList.add('touch');

// =====================================================================
// Tåg-schema
// =====================================================================
const tagState = { p: { mode: 'borta', t: 6, s: 0, v: 0 }, r: { t: 40, s: -1 } };
let pendelSpar, regSpar, stationS = 0;
function updateTrains(dt) {
  if (!pendelSpar) return;
  const P = tagState.p; const tp = pendelSpar;
  const stopHead = stationS - 53; const farS = Math.min(tp.total - 150, stationS + 1400);
  if (P.mode === 'borta') { P.t -= dt; pendel.grp.visible = false; if (P.t <= 0) { P.mode = 'in'; P.s = farS; P.v = 20; } }
  else if (P.mode === 'in') { const dist = P.s - stopHead; P.v = Math.max(1.0, Math.min(20, Math.sqrt(2 * 0.7 * Math.max(0, dist)))); P.s -= P.v * dt; if (dist < 0.3) { P.mode = 'stannar'; P.t = 35; } }
  else if (P.mode === 'stannar') { P.t -= dt; if (P.t <= 0) { P.mode = 'ut'; P.v = 0; } }
  else if (P.mode === 'ut') { P.v = Math.min(20, P.v + 0.8 * dt); P.s += P.v * dt; if (P.s > farS + 100) { P.mode = 'borta'; P.t = 45; } }
  if (P.mode !== 'borta') { pendel.grp.visible = true; placeTrain(pendel, tp, P.s, -1); }
  const R = tagState.r; const rp = regSpar;
  if (R.s < 0) { R.t -= dt; regional.grp.visible = false; if (R.t <= 0) R.s = Math.max(120, stationS - 1500); }
  else { R.s += 27 * dt; regional.grp.visible = true; placeTrain(regional, rp, R.s, 1); if (R.s > Math.min(rp.total - 50, stationS + 1500)) { R.s = -1; R.t = 140; } }
}

// =====================================================================
// Start
// =====================================================================
let lastT = performance.now();
let fpsAcc = 0, fpsN = 0;
const TESTLAGE = /[?&]test/.test(location.search);
function loop(fixedDt) {
  const now = performance.now(); let dt = Math.min(0.05, (now - lastT) / 1000); lastT = now; if (fixedDt) dt = fixedDt;
  if (started) { if (window.__preUpdate) window.__preUpdate(dt); updateCar(dt); updateStreetToast(dt); updateAudio(); }
  updateCamera(dt);
  updateTrains(dt);
  for (const f of flaggor) { const p = f.geometry.attributes.position; const t = performance.now() / 400; for (let i = 0; i < p.count; i++) { const x = p.getX(i); p.setZ(i, Math.sin(x * 2.5 + t) * 0.12 * (x + 1.1)); } p.needsUpdate = true; }
  water.material.normalMap && (water.material.normalMap.offset.x += dt * 0.004, water.material.normalMap.offset.y += dt * 0.006);
  renderer.render(scene, camera);
  if (started) { drawSpeedo(); drawMinimap(); }
  updateLabels();
  if (!TESTLAGE) requestAnimationFrame(() => loop());
}
function testStep(n, dt = 1 / 30) { const r = renderer.render.bind(renderer); renderer.render = () => {}; for (let i = 0; i < n - 1; i++) loop(dt); renderer.render = r; loop(dt); }
let water;
async function boot() {
  const pause = () => new Promise(r => setTimeout(r, 0));
  status('Formar terrängen…'); await pause();
  prepRail(); prepTrainPaths();
  const tm1 = new THREE.Mesh(buildTerrain(CORE[0], CORE[1], CORE[2], CORE[3], 4, null), matMark); tm1.receiveShadow = true; tm1.userData.terrain = true; scene.add(tm1);
  await pause();
  const tm2 = new THREE.Mesh(buildTerrain(-6000, 6000, -6000, 6000, 40, CORE), matMark); tm2.userData.terrain = true; scene.add(tm2);
  terrainMeshes = [tm1, tm2];
  const wn = canvasTex(256, 256, (g, w, h) => { const id = g.createImageData(w, h); for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const k = (y * w + x) * 4; const nx = vnoise(x / 16, y / 16) * 0.5 + vnoise(x / 6 + 30, y / 6) * 0.25; const nz = vnoise(x / 16 + 7, y / 16 + 3) * 0.5 + vnoise(x / 6, y / 6 + 40) * 0.25; id.data[k] = 128 + nx * 80; id.data[k + 1] = 128 + nz * 80; id.data[k + 2] = 255; id.data[k + 3] = 255; } g.putImageData(id, 0, 0); }, false);
  wn.repeat.set(900, 900);
  const halPaths = []; for (const c of carves) { if (!c.gang) continue; const w = c.gang.vagg + 0.2; const Lp = [], Rp = [];
    for (const p of c.pts) { if (gangDjup(c, p) < 0.02) continue; Lp.push(new THREE.Vector2(p.x - p.tz * w, -(p.z + p.tx * w))); Rp.push(new THREE.Vector2(p.x + p.tz * w, -(p.z - p.tx * w))); }
    if (Lp.length > 2) halPaths.push(new THREE.Path(Lp.concat(Rp.reverse()))); }
  let wgeo = new THREE.PlaneGeometry(12000, 12000);
  if (halPaths.length) { const sh = new THREE.Shape([new THREE.Vector2(-6000, -6000), new THREE.Vector2(6000, -6000), new THREE.Vector2(6000, 6000), new THREE.Vector2(-6000, 6000)]); sh.holes.push(...halPaths); wgeo = new THREE.ShapeGeometry(sh); wn.repeat.set(900 / 12000, 900 / 12000); }
  water = new THREE.Mesh(wgeo, new THREE.MeshStandardMaterial({ color: 0x3e6a78, roughness: 0.12, metalness: 0.05, normalMap: wn, normalScale: new THREE.Vector2(0.35, 0.35), envMapIntensity: 1.1 }));
  water.rotation.x = -Math.PI / 2; water.position.y = VATTEN; water.receiveShadow = true; scene.add(water);
  status('Asfalterar Storgatan…'); await pause();
  prepRoadHeights(); buildRoads(); buildYtor();
  status('Lägger räls…'); await pause();
  buildRailway();
  status('Bygger hus…'); await pause();
  buildHouses();
  status('Ställer ut vägbommar…'); await pause();
  buildDrivable();
  status('Planterar träd…'); await pause();
  buildTrees();
  buildMinimap();
  initCar();
  pendel = buildTrain(4, '#e9ecef', '#5b6670'); regional = buildTrain(4, '#f1f1ee', '#2f5f9e');
  const sp1 = K.jarnvag.perronger.find(p => p.namn === 'Spår 1') || K.jarnvag.perronger[0];
  const pc = sp1.poly.reduce((a, p) => [a[0] + p[0] / sp1.poly.length, a[1] + p[1] / sp1.poly.length], [0, 0]);
  const dA = nearestOnPolyline(tagA.sm, pc[0], pc[1]), dB = nearestOnPolyline(tagB.sm, pc[0], pc[1]);
  pendelSpar = dA.d <= dB.d ? tagA : tagB; regSpar = pendelSpar === tagA ? tagB : tagA;
  const near = pendelSpar === tagA ? dA : dB; stationS = lerp(pendelSpar.sm[near.i].s, pendelSpar.sm[near.i + 1].s, near.t);
  setSnabb(snabb);
  status('Klart');
  $('laddning').classList.add('dold');
  $('start').classList.add('visa');
  loop();
}
$('startKnapp').addEventListener('click', () => {
  started = true; $('start').classList.remove('visa'); $('hud').classList.add('visa');
  try { initAudio(); } catch (e) { console.warn(e); }
  camPos.set(carState.x - Math.sin(carState.h) * 7, carState.y + 3, carState.z - Math.cos(carState.h) * 7);
  camLook.set(carState.x, carState.y + 1, carState.z);
  canvas.focus();
});
// felsökning från testskript
window.__epa = { camAt: (x, y, z, lx, ly, lz) => { testCam.pos.set(x, y, z); testCam.look.set(lx, ly, lz); camMode = 3; }, scene, renderer, testStep, get camMode() { return camMode; }, get car() { return carState; }, keys, setCam: (m) => { camMode = m; }, setDron: (d, az, el) => { dronDist = d; dronAz = az; dronEl = el; }, pick, selectHouse, H, world, drivable, teleport: (x, z, h) => { carState.x = x; carState.z = z; if (h !== undefined) carState.h = h; } };
boot().catch(e => { console.error(e); status('Fel: ' + e.message); });
