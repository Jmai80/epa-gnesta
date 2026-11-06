// testar Hitta: vägnät, sökning och rutt på minikartan (utkast 48)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 640 } }); const logs = []; p.on('pageerror', e => logs.push(e.message)); p.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  await p.goto('http://localhost:8772/index.html?test'); await p.waitForSelector('#start.visa', { timeout: 120000 }); await p.click('#startKnapp'); await p.waitForTimeout(1500);
  const info = await p.evaluate(() => { const e = __epa; const N = e.NAT; const oppna = N.kanter.filter(k => k.oppen).length;
    const sok = (q) => e.hittaSok(q).slice(0, 4).map(t => `${t.titel} (${t.under})`);
    return { noder: N.x.length, kanter: N.kanter.length, oppna, index: e.hitta.index.length,
      samuel: sok('Samuel'), mormor: sok('mormor'), gran: sok('granbackavägen 108'), nyg: sok('Nygatan 28'), hem: sok('hemköp'), sto: sok('stopp'), kadr: sok('kadriljvagen 1') }; });
  console.log(JSON.stringify(info, null, 1));
  for (const [q, snabb, namn] of [['Mormor', false, 'mormor_epa'], ['Samuel', false, 'samuel_epa'], ['Samuel', true, 'samuel_snabb'], ['Stopp', false, 'stopp_epa']]) {
    const r = await p.evaluate(([q, snabb]) => { const e = __epa; e.setSnabb(snabb); const t = e.hittaSok(q)[0]; e.valjMal(t); e.testStep(2);
      const r = e.hitta.rutt; return r ? { titel: t.titel, L: Math.round(r.L), fri: Math.round(r.fri), avst: r.avst, n: r.pts.length, chip: document.getElementById('mal').innerText } : { titel: t.titel, ingen: true }; }, [q, snabb]);
    console.log(q, snabb ? 'snabb' : 'EPA', JSON.stringify(r));
    await p.waitForTimeout(300); await p.screenshot({ path: `/tmp/epa-bilder/hitta_${namn}.png`, clip: { x: 0, y: 330, width: 420, height: 310 }, timeout: 120000 });
  }
  // sökrutan
  await p.evaluate(() => __epa.setSnabb(false)); await p.keyboard.press('f'); await p.waitForTimeout(300); await p.screenshot({ path: '/tmp/epa-bilder/hitta_ruta_tom.png', timeout: 120000 });
  await p.keyboard.type('gran'); await p.waitForTimeout(300); await p.screenshot({ path: '/tmp/epa-bilder/hitta_ruta_gran.png', timeout: 120000 });
  const fv = await p.evaluate(() => document.getElementById('hittaFalt').value); console.log('fältet:', JSON.stringify(fv), 'bilens fart', await p.evaluate(() => __epa.car.v));
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);
  console.log('ruta öppen efter Esc:', await p.evaluate(() => document.getElementById('hitta').classList.contains('visa')));
  const framme = await p.evaluate(() => { const e = __epa; e.setSnabb(true); e.valjMal(e.hittaSok('Samuel')[0]); e.testStep(2); const r = e.hitta.rutt; const q = r.pts[r.pts.length - 2] || r.slut;
    e.teleport(r.slut[0] + (q[0] - r.slut[0]) * 0.1, r.slut[1] + (q[1] - r.slut[1]) * 0.1); e.testStep(20); return { mal: e.hitta.mal, toast: document.getElementById('gatunamn').textContent }; });
  console.log('framme:', JSON.stringify(framme));
  console.log(logs.join(' | ') || 'inga fel'); await b.close();
})();
