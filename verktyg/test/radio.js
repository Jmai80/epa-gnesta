// radiotest: startar spelet, kollar att mera_bas.mp3 laddas och spelas, pausas och återupptas med R: node radio.js [port]
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--autoplay-policy=user-gesture-required'] });
  const p = await b.newPage(); const logs = [];
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') logs.push(m.text()); }); p.on('pageerror', e => logs.push('pageerror ' + e.message));
  p.on('response', r => { if (r.url().includes('.mp3')) logs.push('mp3 ' + r.status() + ' ' + (r.headers()['content-type'] || '')); });
  await p.goto(`http://localhost:${process.argv[2] || 8772}/index.html?test`); await p.waitForSelector('#start.visa', { timeout: 120000 });
  await p.click('#startKnapp'); await p.waitForTimeout(4000);
  const a = await p.evaluate(() => { const A = __epa.audio; return { synt: A.synt, paused: A.lat && A.lat.paused, t: A.lat && A.lat.currentTime, ready: A.lat && A.lat.readyState, dur: A.lat && A.lat.duration, ctx: A.ctx.state, gain: A.rg.gain.value }; });
  console.log('efter start', JSON.stringify(a));
  await p.keyboard.press('KeyR'); await p.waitForTimeout(1000);
  console.log('radio av', JSON.stringify(await p.evaluate(() => { const A = __epa.audio; return { on: A.radioOn, paused: A.lat.paused, t: A.lat.currentTime, gain: A.rg.gain.value }; })));
  await p.keyboard.press('KeyR'); await p.waitForTimeout(1500);
  console.log('radio på', JSON.stringify(await p.evaluate(() => { const A = __epa.audio; return { on: A.radioOn, paused: A.lat.paused, t: A.lat.currentTime, gain: A.rg.gain.value }; })));
  console.log(logs.join('\n') || 'inga fel'); await b.close();
})();
