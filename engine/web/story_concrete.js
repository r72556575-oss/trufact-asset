// Shot plan: "Roman concrete heals itself" — timed to voice.mp3 (28.66 s, 30 fps).
// Phrases (s): 0.00-4.31 "Roman buildings are still standing after two thousand years." | 4.59-7.91 "Modern concrete can start crumbling..." |
// 8.37-10.17 "So what was the Romans' secret?" | 10.45-12.73 "Scientists found it in 2023." | 13.19-16.39 "quicklime, which heats up" |
// 16.76-20.10 "tiny white chunks" | 20.56-25.36 "When a crack forms... fill the crack." | 25.63-28.20 "The concrete literally repairs itself!"
export const FPS = 30, TOTAL = 860, DECK = 6;
export const SHOTS = [
  { id: 'hook', a: 0, b: 135, light: 'day' },
  { id: 'crumble', a: 136, b: 249, light: 'day' },
  { id: 'secret', a: 250, b: 312, light: 'day' },
  { id: 'sci', a: 313, b: 394, light: 'day' },
  { id: 'mix', a: 395, b: 501, light: 'golden' },
  { id: 'clasts', a: 502, b: 615, light: 'golden' },
  { id: 'heal', a: 616, b: 767, light: 'day' },
  { id: 'end', a: 768, b: 859, light: 'day' },
];
export const shotAt = (f) => SHOTS.find((s) => f >= s.a && f <= s.b) || SHOTS[SHOTS.length - 1];

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const smooth = (t) => { t = clamp(t); return t * t * t * (t * (t * 6 - 15) + 10); };
const lerp = (a, b, t) => a + (b - a) * t;
const lerp3 = (a, b, t) => a.map((v, i) => lerp(v, b[i], t));
const ramp = (f, a, b) => clamp((f - a) / (b - a));

// ---------- lights ----------
export const LIGHTS = {
  day: { az: 140, el: 46, sky: '#c4d6f2', ground: '#8a8262', hemi: 1.15, sun: '#fff1dc', sunI: 2.5, fog: '#cadcf0', fogNear: 70, fogFar: 900,
    skyTop: '#3f80d4', skyHor: '#c3daf2', sat: 1.1, waterDeep: '#2c6c8c', waterShal: '#5aaec4', glint: '#effaff', vig: 0.2, shadowExt: 18 },
  golden: { az: 8, el: 9, sky: '#9a90c8', ground: '#6a4c40', hemi: 1.0, sun: '#ffb46c', sunI: 2.9, fog: '#f0b88c', fogNear: 60, fogFar: 760,
    skyTop: '#6f6eb0', skyHor: '#ffc27e', sunDisc: '#fff0c8', sunSize: 0.0035, sat: 1.12, gain: '#fff2e2', waterDeep: '#3d5a86', waterShal: '#d99a6e',
    glint: '#ffe2a8', vig: 0.26, shadowExt: 18 },
};
export const lightFor = (S, f) => {
  const L = { ...LIGHTS[S.light] };
  if (S.id === 'hook') L.shadowExt = lerp(8, 45, smooth(ramp(f, 14, 70)));
  return L;
};

// ---------- cameras ----------
const SOL = [-21.5, DECK, 0];
const CAMS = {
  hook: [
    { f: 0, pos: [-19.35, 7.42, 1.55], look: [-21.5, 7.32, 0], fov: 34 },
    { f: 22, pos: [-19.5, 7.42, 1.45], look: [-21.5, 7.32, 0], fov: 33 },
    { f: 95, pos: [-30.5, 10.8, 12.0], look: [-15.5, 5.4, -3.5], fov: 46 },
    { f: 135, pos: [-30.0, 10.6, 11.6], look: [-15.5, 5.4, -3.5], fov: 44.5 },
  ],
  // medium shots: characters sit in the lower half, the top ~40% is left for the 2D insert panel
  crumble: [
    { f: 136, pos: [-14.0, 7.8, 1.6], look: [-21.5, 8.35, 0], fov: 33 },
    { f: 249, pos: [-14.9, 7.8, 1.2], look: [-21.5, 8.35, 0], fov: 32 },
  ],
  secret: [
    { f: 250, pos: [-16.9, 7.4, 0.3], look: [-21.0, 7.35, -0.3], fov: 38 },
    { f: 312, pos: [-17.4, 7.4, 0.25], look: [-21.0, 7.35, -0.3], fov: 35 },
  ],
  sci: [
    { f: 313, pos: [-14.2, 7.8, -1.8], look: [-21.5, 8.35, 0], fov: 33 },
    { f: 394, pos: [-15.0, 7.8, -1.2], look: [-21.5, 8.35, 0], fov: 32 },
  ],
  mix: [
    { f: 395, pos: [-13.6, 7.8, 0.4], look: [-21.5, 8.3, 0], fov: 34 },
    { f: 501, pos: [-15.2, 7.8, 0.2], look: [-21.5, 8.3, 0], fov: 31 },
  ],
  clasts: [
    { f: 502, pos: [-14.4, 7.8, 1.9], look: [-21.5, 8.35, 0], fov: 33 },
    { f: 615, pos: [-15.4, 7.8, 1.4], look: [-21.5, 8.35, 0], fov: 32 },
  ],
  heal: [
    { f: 616, pos: [-14.0, 7.8, -0.6], look: [-21.5, 8.35, 0], fov: 34 },
    { f: 700, pos: [-14.8, 7.8, -0.2], look: [-21.5, 8.35, 0], fov: 32.5 },
    { f: 767, pos: [-15.6, 7.8, 0.1], look: [-21.5, 8.35, 0], fov: 31.5 },
  ],
  end: [
    { f: 768, pos: [-14.4, 7.8, 0.5], look: [-21.5, 8.35, 0], fov: 34 },
    { f: 859, pos: [-15.8, 7.8, 0.2], look: [-21.5, 8.35, 0], fov: 31 },
  ],
};
const KICKS = [{ f: 748, a: 0.035 }, { f: 773, a: 0.03 }];
export const camAt = (f) => {
  const S = shotAt(f), K = CAMS[S.id];
  let c;
  if (f <= K[0].f) c = { ...K[0] };
  else if (f >= K[K.length - 1].f) c = { ...K[K.length - 1] };
  else for (let i = 0; i < K.length - 1; i++) if (f >= K[i].f && f <= K[i + 1].f) {
    const t = smooth((f - K[i].f) / (K[i + 1].f - K[i].f)), a = K[i], b = K[i + 1];
    c = { pos: lerp3(a.pos, b.pos, t), look: lerp3(a.look, b.look, t), fov: lerp(a.fov, b.fov, t), roll: lerp(a.roll || 0, b.roll || 0, t) };
  }
  for (const k of KICKS) { const d = f - k.f; if (d >= 0 && d < 7) { const s = (d % 2 ? -1 : 1) * k.a * (1 - d / 7); c.look = [c.look[0], c.look[1] + s * 3, c.look[2] + s * 2]; c.roll = (c.roll || 0) + s * 20; } }
  c.flash = (f >= 313 && f < 317) ? (1 - (f - 313) / 4) * 0.55 : (f >= 748 && f < 752) ? (1 - (f - 748) / 4) * 0.4 : 0;
  if (S.id === 'hook') c.shadowAt = [-21.5, 6, 0];
  return c;
};

// ---------- lens ----------
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
export const dofAt = (f) => {
  const S = shotAt(f), C = camAt(f), eye = [SOL[0], 7.32, 0];
  switch (S.id) {
    case 'hook': return { focus: dist(C.pos, eye), cinf: lerp(13, 0, smooth(ramp(f, 22, 60))) };
    case 'secret': case 'end': return { focus: dist(C.pos, [-20.9, 7.3, -0.2]), cinf: 11 };
    default: return { focus: dist(C.pos, eye), cinf: 7 };
  }
};

// ---------- world state (nothing collapses in this story) ----------
export const worldAt = (f) => ({ collapse: 0, banner: 'wave', bannerFall: 0, old: false, braceFall: 0, helmet: null });

// ---------- actors (2D cards) ----------
const blinkAt = (f, seed) => { const per = 38 + (seed * 17) % 31, ph = (f + seed * 13) % per; return ph < 2 ? 0.5 : ph < 4 ? 1 : 0; };
const R = (T, who, o, pos, extra = {}) => ({ key: who + JSON.stringify(o), draw: (p) => T.romanFront(p, who, o), x: pos[0], y: pos[1], z: pos[2], ...extra });
const q = (x, n = 2) => Math.round(x * 10 ** n) / 10 ** n;

export const actorsAt = (f, T) => {
  const S = shotAt(f), out = [];
  const tint = S.light === 'golden' ? '#ffe2c8' : '#ffffff';
  const hero = (o, pos = SOL, extra = {}) => out.push(R(T, 'legion', { L: 'shield', expr: 'stern', seed: 3, blink: blinkAt(f, 3), ...o }, pos, { tint, ...extra }));
  const wk = (eA, eB, A = {}, B = {}) => {
    out.push(R(T, 'workA', { seed: 41, expr: eA, L: 'hang', R: 'hang', facing: 1, blink: blinkAt(f, 41), look: 0.5, ...A }, [SOL[0] - 0.05, DECK, 0.74], { order: 3, tint }));
    out.push(R(T, 'workB', { seed: 42, expr: eB, L: 'hang', R: 'hang', facing: -1, blink: blinkAt(f, 42), look: -0.5, ...B }, [SOL[0] - 0.05, DECK, -0.74], { order: 3, tint }));
  };
  const bob = (s) => q(Math.abs(Math.sin((f + s) * 0.45)) * 0.02, 3);
  switch (S.id) {
    case 'hook': {
      hero({ look: f < 30 ? 0 : 0.3 });
      const w = ((f % 20) / 20);
      out.push(R(T, 'civA', { seed: 11, step: q(w), facing: 1, blink: blinkAt(f, 11) }, [-4 + f * 0.035, DECK, 0.9], { tint }));
      out.push(R(T, 'civB', { seed: 12, facing: 1, blink: blinkAt(f, 12) }, [2.5 + f * 0.03, DECK, -1.0], { tint }));
      break;
    }
    case 'crumble': {
      const shake = q(2.5 * Math.sin(f * 0.6), 1);
      hero({ expr: 'nervous', look: 0.3, headTilt: shake });
      wk('shock', 'shock', { L: 'cheek', R: 'cheek', bob: bob(0), look: 0.6 }, { L: 'cheek', R: 'cheek', bob: bob(7), look: -0.6 });
      break;
    }
    case 'secret': {
      hero({ expr: 'squint', look: 0.6, headTilt: q(5 * Math.sin((f - 250) * 0.12), 1) });
      break;
    }
    case 'sci': {
      hero({ expr: 'smile', look: 0.4 });
      wk('grin', 'grin', { L: 'point', bob: bob(0) }, { R: 'point', bob: bob(5) });
      break;
    }
    case 'mix': {
      hero({ expr: 'squint', look: 0.3 });
      const st = q(Math.sin(f * 0.5), 1);
      wk('nervous', 'nervous', { L: 'reach', R: 'reach', headTilt: st, bob: bob(0) }, { L: 'reach', R: 'reach', headTilt: q(-st, 1), bob: bob(4) });
      break;
    }
    case 'clasts': {
      hero({ expr: 'smile', look: 0.3 });
      wk('grin', 'smile', { L: 'point', bob: bob(2) }, { L: 'belly', R: 'belly', bob: bob(6) });
      break;
    }
    case 'heal': {
      const done = f >= 748;
      hero({ expr: done ? 'grin' : 'squint', look: 0.4 });
      wk(done ? 'laugh' : 'shock', done ? 'grin' : 'shock', done ? { L: 'belly', R: 'belly', bob: bob(1) } : { L: 'cheek', R: 'cheek' }, done ? { L: 'point', bob: bob(6) } : { L: 'cheek', R: 'cheek' });
      break;
    }
    case 'end': {
      hero({ expr: 'grin', look: 0.2, bob: bob(0) });
      wk('laugh', 'grin', { L: 'belly', R: 'belly', bob: bob(1) }, { L: 'point', bob: bob(6) });
      break;
    }
  }
  return out;
};

// ---------- 2D effects ----------
const FX = (key, draw, pos, s, extra = {}) => ({ key, draw, x: pos[0], y: pos[1], z: pos[2], s, blob: false, shadow: false, order: 5, ...extra });
export const fxAt = (f, T) => {
  const S = shotAt(f), out = [];
  if (S.id === 'hook' && f > 60) {
    for (let i = 0; i < 9; i++) {
      const t = ((f - 60) * 0.012 + i / 9) % 1, cols = ['#d9822b', '#c4452c', '#e6b13a'];
      const x = -24 + t * 7 + Math.sin(i * 3.1) * 0.6, y = DECK + 3.2 - t * 3.4 + Math.sin(t * 9 + i) * 0.25, z = -1.5 + i * 0.45;
      out.push(FX('leaf' + i % 3, (p) => T.fxLeaf(p, cols[i % 3]), [x, y, z], 0.12, { roll: q(t * 8 + i, 1) }));
    }
  }
  if (S.id === 'mix') { // steam / heat
    for (const [z, s] of [[0.74, 1], [-0.74, -1]]) out.push(FX('dripm', (p) => T.fxDrip(p), [SOL[0] + 0.15, DECK + 1.62 - ((f - 395) % 30) * 0.012, z + s * 0.33], 0.18));
  }
  return out;
};
