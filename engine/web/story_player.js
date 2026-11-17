// Generic story player: turns a storyboard (JSON written by Gemini / the generator) into shots, cameras, actors and fx.
// The storyboard is injected by render.mjs as window.__STORYBOARD__.
const DEFAULT_SB = { fps: 30, beats: [{ a: 0, b: 89, light: "day", camera: "medium", actors: [{ uniform: "roman", team: "A", slot: "center", expr: "smile", pose: "idle" }] }] };
const SB = (typeof window !== "undefined" && window.__STORYBOARD__) || DEFAULT_SB;
export const FPS = SB.fps || 30, DECK = 6;
const EXPR_OK = ["neutral", "stern", "stubborn", "nervous", "shock", "snore", "squint", "grin", "smile", "laugh"];
const EXPR_MAP = { worry: "nervous", worried: "nervous", scared: "nervous", sad: "nervous", angry: "stern", mad: "stern", happy: "smile", glad: "smile", joy: "laugh", surprised: "shock", surprise: "shock", shocked: "shock", think: "squint", thinking: "squint", confident: "grin", proud: "grin", smirk: "grin", serious: "stern", determined: "stubborn", calm: "neutral" };
const POSE_OK = ["idle", "ready", "point", "cheer", "think", "worry", "command", "cross", "wave", "thumb", "talk"];
const POSE_MAP = { shout: "point", attack: "point", salute: "wave", celebrate: "cheer", plan: "think", scared: "worry", fear: "worry", stand: "idle", explain: "talk", order: "command" };
const SLOT_OK = ["far_left", "left", "center", "right", "far_right"], CAM_OK = ["medium", "close", "two", "wide", "pull", "low", "pan_l", "pan_r", "push"], LIGHT_OK = ["day", "golden", "night", "fog"];
const UNI_OK = ["roman", "knight", "samurai", "indian", "mongol", "chinese", "us_ww2", "jp_ww2", "uk_ww2", "officer", "villager", "villager2", "elder"];
const pick = (v, ok, map = {}, dflt) => { v = String(v || "").toLowerCase(); return ok.includes(v) ? v : (map[v] && ok.includes(map[v]) ? map[v] : dflt); };
const BEATS = SB.beats.map((b) => ({ ...b, camera: pick(b.camera, CAM_OK, { dolly: "push", closeup: "close", medium_trio: "medium", two_shot: "two", line_wide: "wide", pan_left: "pan_l", pan_right: "pan_r" }, "medium"), light: pick(b.light, LIGHT_OK, { dusk: "golden", sunset: "golden", dark: "night", misty: "fog" }, "day"),
  actors: (b.actors || []).slice(0, 5).map((a) => ({ ...a, uniform: pick(a.uniform, UNI_OK, { india: "indian", japan: "samurai", japanese: "jp_ww2", american: "us_ww2", usa: "us_ww2", british: "uk_ww2", greek: "roman", viking: "knight", mughal: "mongol", persian: "mongol", ottoman: "mongol", chinese_ancient: "chinese", soldier: "roman", general: "officer", king: "officer", commander: "officer" }, "roman"),
    team: ["A", "B", "C"].includes(a.team) ? a.team : "A", slot: pick(a.slot, SLOT_OK, {}, "center"), expr: pick(a.expr, EXPR_OK, EXPR_MAP, "smile"), pose: pick(a.pose, POSE_OK, POSE_MAP, "idle") })) }));
export const TOTAL = SB.total || BEATS[BEATS.length - 1].b + 1;
export const SHOTS = BEATS.map((b, i) => ({ id: "b" + i, a: b.a, b: b.b, light: b.light || "day", beat: b, i }));
export const shotAt = (f) => SHOTS.find((s) => f >= s.a && f <= s.b) || (f < SHOTS[0].a ? SHOTS[0] : SHOTS[SHOTS.length - 1]);
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const smooth = (t) => { t = clamp(t); return t * t * t * (t * (t * 6 - 15) + 10); };
const lerp = (a, b, t) => a + (b - a) * t;
const lerp3 = (a, b, t) => a.map((v, i) => lerp(v, b[i], t));
const SOL = [-21.5, DECK, 0];

const DAY = { az: 140, el: 46, sky: "#c4d6f2", ground: "#8a8262", hemi: 1.15, sun: "#fff1dc", sunI: 2.5, fog: "#cadcf0", fogNear: 70, fogFar: 900, skyTop: "#3f80d4", skyHor: "#c3daf2", sat: 1.1, waterDeep: "#2c6c8c", waterShal: "#5aaec4", glint: "#effaff", vig: 0.2, shadowExt: 18 };
export const LIGHTS = {
  day: DAY,
  golden: { az: 8, el: 9, sky: "#9a90c8", ground: "#6a4c40", hemi: 1.0, sun: "#ffb46c", sunI: 2.9, fog: "#f0b88c", fogNear: 60, fogFar: 760, skyTop: "#6f6eb0", skyHor: "#ffc27e", sunDisc: "#fff0c8", sunSize: 0.0035, sat: 1.12, gain: "#fff2e2", waterDeep: "#3d5a86", waterShal: "#d99a6e", glint: "#ffe2a8", vig: 0.26, shadowExt: 18 },
  night: { az: 200, el: 28, sky: "#2a3470", ground: "#262a44", hemi: 0.62, sun: "#9fb4ff", sunI: 1.3, fog: "#1d2350", fogNear: 40, fogFar: 520, skyTop: "#0e1442", skyHor: "#3a3f86", sunDisc: "#e8f0ff", sunSize: 0.003, sat: 1.0, waterDeep: "#10224a", waterShal: "#2f4c8a", glint: "#cfe0ff", vig: 0.34, shadowExt: 18 },
  fog: { az: 140, el: 40, sky: "#b9bfc6", ground: "#7a7c78", hemi: 1.05, sun: "#eef0f2", sunI: 1.1, fog: "#c8ccd0", fogNear: 14, fogFar: 150, skyTop: "#aab0b8", skyHor: "#d0d4d8", sat: 0.85, waterDeep: "#4b5560", waterShal: "#8d99a3", glint: "#f2f4f6", vig: 0.24, shadowExt: 18 },
};
export const lightFor = (S, f) => ({ ...(LIGHTS[S.light] || DAY) });

const CAMS = {
  medium: [{ pos: [-14.0, 7.8, 1.6], look: [-21.5, 8.35, 0], fov: 33 }, { pos: [-14.9, 7.8, 1.2], look: [-21.5, 8.35, 0], fov: 32 }],
  close: [{ pos: [-16.9, 7.4, 0.3], look: [-21.0, 7.35, -0.3], fov: 38 }, { pos: [-17.4, 7.4, 0.25], look: [-21.0, 7.35, -0.3], fov: 35 }],
  two: [{ pos: [-12.2, 7.6, -0.6], look: [-21.5, 7.9, 0], fov: 27 }, { pos: [-13.0, 7.6, -0.3], look: [-21.5, 7.9, 0], fov: 26.5 }],
  wide: [{ pos: [-9.5, 8.4, 0.2], look: [-21.5, 7.1, 0], fov: 42 }, { pos: [-10.2, 8.2, 0.2], look: [-21.5, 7.1, 0], fov: 40 }],
  pull: [{ pos: [-19.35, 7.42, 1.55], look: [-21.5, 7.32, 0], fov: 34 }, { pos: [-30.0, 10.6, 11.6], look: [-15.5, 5.4, -3.5], fov: 45 }],
  low: [{ pos: [-16.5, 6.2, 0.6], look: [-21.5, 7.8, 0], fov: 36 }, { pos: [-15.6, 6.4, 0.4], look: [-21.5, 7.8, 0], fov: 34 }],
  pan_l: [{ pos: [-13.5, 7.6, 2.8], look: [-21.5, 7.9, 0], fov: 30 }, { pos: [-13.5, 7.6, -2.8], look: [-21.5, 7.9, 0], fov: 30 }],
  pan_r: [{ pos: [-13.5, 7.6, -2.8], look: [-21.5, 7.9, 0], fov: 30 }, { pos: [-13.5, 7.6, 2.8], look: [-21.5, 7.9, 0], fov: 30 }],
  push: [{ pos: [-13.0, 7.8, 0.4], look: [-21.5, 8.0, 0], fov: 36 }, { pos: [-17.0, 7.6, 0.3], look: [-21.5, 7.9, 0], fov: 30 }],
};
const widthAt = (pos, look, fov) => 2 * Math.hypot(pos[0] - look[0], pos[1] - look[1], pos[2] - look[2]) * Math.tan(Math.atan(Math.tan(fov * Math.PI / 360) * 0.5625));
export const camAt = (f) => {
  const S = shotAt(f), b = S.beat, K = CAMS[b.camera] || CAMS.medium, p = smooth((f - S.a) / Math.max(1, S.b - S.a));
  let c = { pos: lerp3(K[0].pos, K[1].pos, p), look: lerp3(K[0].look, K[1].look, p), fov: lerp(K[0].fov, K[1].fov, p), roll: 0 };
  const zs = (b.actors || []).map((a) => SLOT_Z[a.slot] ?? 0);
  if (zs.length && b.camera !== "pull" && b.camera !== "pan_l" && b.camera !== "pan_r") {      // pull the camera back until everybody fits
    const zc = (Math.min(...zs) + Math.max(...zs)) / 2, need = (Math.max(...zs) - Math.min(...zs)) + 1.5, k = Math.max(1, need / widthAt(c.pos, c.look, c.fov));
    c.pos = [c.look[0] + (c.pos[0] - c.look[0]) * k, c.pos[1] + (k - 1) * 0.5, c.pos[2] * (b.camera === "wide" ? 1 : k) + zc]; c.look = [c.look[0], c.look[1], c.look[2] + zc];
  }
  const d = f - S.a;
  if (b.shake && d >= 0 && d < 9) { const s = (d % 2 ? -1 : 1) * 0.04 * (1 - d / 9); c.look = [c.look[0], c.look[1] + s * 3, c.look[2] + s * 2]; c.roll = s * 22; }
  c.flash = b.flash && d >= 0 && d < 5 ? (1 - d / 5) * 0.5 : 0;
  return c;
};
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
export const dofAt = (f) => { const S = shotAt(f), C = camAt(f); return { focus: dist(C.pos, [SOL[0], 7.2, C.look[2]]), cinf: ({ wide: 2, pull: 2, pan_l: 4, pan_r: 4, close: 9, two: 5 })[S.beat.camera] ?? 6 }; };
export const worldAt = (f) => ({ collapse: 0, banner: "wave", bannerFall: 0, old: false, braceFall: 0, helmet: null });

// ---- actors ----
const SLOT_Z = { far_left: -1.7, left: -0.85, center: 0, right: 0.85, far_right: 1.7 };
const blinkAt = (f, seed) => { const per = 38 + (seed * 17) % 31, ph = (f + seed * 13) % per; return ph < 2 ? 0.5 : ph < 4 ? 1 : 0; };
const q = (x, n = 2) => Math.round(x * 10 ** n) / 10 ** n;
export const actorsAt = (f, T) => {
  const S = shotAt(f), b = S.beat, out = [], d = f - S.a;
  (b.actors || []).forEach((a, i) => {
    const O = T.teamed(a.uniform || "roman", a.team || "A"), seed = 3 + i * 7 + S.i;
    const hasShield = !!O.shield, hasW = !!(O.weapon && O.weapon !== "spear"), hasSpear = !!O.spear;
    const ready = { L: hasShield ? "shield" : "hang", R: hasW ? "hold" : (hasSpear ? "spear" : "hang") };
    const pose = a.pose || "idle", tt = f * 0.2 + i;
    const P = {
      idle: ready, ready, point: { L: ready.L, R: "point" }, cheer: { L: "up", R: "up" }, think: { L: "hang", R: "temple" }, worry: { L: "cheek", R: "cheek" },
      command: { L: "hip", R: "point" }, cross: { L: "cross", R: "cross" }, wave: { L: ready.L, R: "wave" }, thumb: { L: "hang", R: "thumb" },
      talk: { L: "belly", R: (Math.floor(f / 24) % 2 ? "point" : "lift") },
    }[pose] || ready;
    let z = (SLOT_Z[a.slot] ?? 0), step = 0;
    if (a.enter && a.enter.startsWith("walk")) { const e = smooth(d / 40); z += (1 - e) * (a.enter === "walk_left" ? 3.4 : -3.4); step = (1 - e) > 0.001 ? q((d % 14) / 14) : 0; }
    const look = clamp(-z * 0.3, -0.7, 0.7);
    const o = { expr: a.expr || "smile", seed, L: P.L, R: P.R, blink: blinkAt(f, seed), look, bob: q(Math.abs(Math.sin((f + seed) * 0.45)) * 0.02, 3), step, facing: z > 0 ? -1 : 1 };
    out.push({ key: (a.uniform || "roman") + (a.team || "A") + JSON.stringify(o), draw: (p) => T.romanFront(p, O, o), x: SOL[0] + (a.row === "back" ? -1.1 : a.row === "front" ? 0.9 : 0), y: SOL[1], z, order: 3, tint: b.light === "golden" ? "#ffe2c8" : "#ffffff" });
  });
  return out;
};

// ---- fx ----
const FX = (key, draw, pos, s, extra = {}) => ({ key, draw, x: pos[0], y: pos[1], z: pos[2], s, blob: false, shadow: false, order: 5, ...extra });
export const fxAt = (f, T) => {
  const S = shotAt(f), b = S.beat, d = f - S.a, out = [], first = (b.actors || [])[0], z0 = first ? -(SLOT_Z[first.slot] ?? 0) : 0;      // fx cards use the mirrored z axis
  for (const k of (b.fx || [])) {
    if (k === "exclaim" || k === "question") { if (d > 6 && d < 70) { const t = q(Math.min(1, (d - 6) / 12)); out.push(FX(k + t, (p) => T.fxMark(p, k === "exclaim" ? "!" : "?", t), [SOL[0], DECK + (b.fxy ?? 2.0), z0], b.fxs ?? 0.5)); } }
    else if (k === "stars") { const t = q(((d % 40) / 40)); out.push(FX("st" + t, (p) => T.fxStars(p, t), [SOL[0], DECK + 1.25, z0], 0.6)); }
    else if (k === "dust") { const t = q(((d % 34) / 34)); out.push(FX("du" + t, (p) => T.fxDust(p, t), [SOL[0] + 0.3, DECK + 0.3, z0], 0.6)); }
    else if (k === "sweat") out.push(FX("sw", (p) => T.fxDrip(p), [SOL[0] + 0.15, DECK + 2.1 - ((d % 30) * 0.012), z0 + 0.35], 0.18));
  }
  return out;
};
