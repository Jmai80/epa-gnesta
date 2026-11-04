// markhöjder i spelet: node hojd.js '[["namn", x, z], ...]'  (PORT, standard 8772)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage(); await p.goto(`http://localhost:${process.env.PORT || 8772}/index.html?test`); await p.waitForSelector('#start.visa', { timeout: 120000 });
  const pts = JSON.parse(process.argv[2]);
  const r = await p.evaluate((pts) => pts.map(([n, x, z]) => [n, x, z, Math.round(__epa.H(x, z) * 100) / 100]), pts);
  for (const q of r) console.log(q.join('\t')); await b.close();
})();
