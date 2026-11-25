// usage: node atlas_render.mjs frames <outdir> <start-end> <stride> [quality]   |   node atlas_render.mjs fx <out.raw>
import { chromium } from 'playwright'; import http from 'http'; import fs from 'fs'; import path from 'path';
const [,, mode, a1, a2, a3, a4] = process.argv;
const root = process.env.WEB || path.resolve('web');
const srv = http.createServer((q, s) => { const p = path.join(root, decodeURIComponent(q.url.split('?')[0])); if (!fs.existsSync(p) || fs.statSync(p).isDirectory()) { s.writeHead(404); return s.end(); }
  const ext = path.extname(p); s.writeHead(200, { 'Content-Type': ext === '.js' ? 'text/javascript' : ext === '.css' ? 'text/css' : ext === '.woff2' ? 'font/woff2' : 'text/html' }); fs.createReadStream(p).pipe(s); }).listen(0);
await new Promise(r => srv.on('listening', r));
const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'] });
const pg = await b.newPage({ viewport: { width: 900, height: 1500 } });
pg.on('console', m => { const t = m.text(); if (/error|fail/i.test(t)) console.log('PAGE', t); }); pg.on('pageerror', e => console.log('ERR', e.message));
await pg.goto(`http://localhost:${srv.address().port}/index.html`);
await pg.waitForFunction(() => window.__ready, null, { timeout: 120000 });
if (mode === 'frames') {
  const outdir = a1, [from, to] = a2.split('-').map(Number), stride = +a3, q = +(a4 || 0.92); fs.mkdirSync(outdir, { recursive: true }); let n = 0; const t0 = Date.now();
  for (let f = from; f <= to; f += stride) {
    const file = path.join(outdir, `f${String(f + 1).padStart(4, '0')}.jpg`);
    if (process.env.RESUME && fs.existsSync(file)) continue;
    const d = await pg.evaluate(([f, q]) => { window.seek(f / 30); return document.getElementById('stage').toDataURL('image/jpeg', q); }, [f, q]);
    fs.writeFileSync(file, Buffer.from(d.split(',')[1], 'base64')); n++;
  }
  console.log(`done ${n} frames, ${((Date.now() - t0) / Math.max(1, n) / 1000).toFixed(2)} s/frame`);
} else if (mode === 'fx') {
  const b64 = await pg.evaluate(async () => { const r = await window.SFX.render(window.scoreSound, window.DURATION, 48000, { voiceover: true }); const out = new Int16Array(r.inter.length); const g = r.peak > 0.98 ? 0.98 / r.peak : 1; for (let i = 0; i < out.length; i++) out[i] = Math.max(-1, Math.min(1, r.inter[i] * g)) * 32767;
    let s = ''; const u = new Uint8Array(out.buffer); for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); });
  fs.writeFileSync(a1, Buffer.from(b64, 'base64')); console.log('fx written');
}
await b.close(); srv.close();
