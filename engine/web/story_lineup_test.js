// uniform lineup test
export const FPS = 30, TOTAL = 6, DECK = 6;
export const SHOTS = [0, 1, 2, 3, 4, 5].map((i) => ({ id: "s" + i, a: i, b: i, light: "day" }));
export const shotAt = (f) => SHOTS[Math.min(f, 5)];
export const smooth = (t) => t;
export const LIGHTS = { day: { az: 140, el: 46, sky: "#c4d6f2", ground: "#8a8262", hemi: 1.15, sun: "#fff1dc", sunI: 2.5, fog: "#cadcf0", fogNear: 70, fogFar: 900, skyTop: "#3f80d4", skyHor: "#c3daf2", sat: 1.1, waterDeep: "#2c6c8c", waterShal: "#5aaec4", glint: "#effaff", vig: 0.2, shadowExt: 18 } };
export const lightFor = (S, f) => ({ ...LIGHTS.day });
export const camAt = (f) => ({ pos: [-8.4, 7.5, 0.2], look: [-21.5, 6.9, 0.0], fov: 22, roll: 0, flash: 0 });
export const dofAt = (f) => ({ focus: 13.1, cinf: 5 });
export const worldAt = (f) => ({ collapse: 0, banner: "wave", bannerFall: 0, old: false, braceFall: 0, helmet: null });
const IDS = ["samurai", "indian", "chinese", "jp_ww2", "uk_ww2", "officer"];
export const actorsAt = (f, T) => { const id = IDS[Math.min(f, 5)], O = T.UNIFORMS[id], L = O.shield ? "shield" : "hang", R = (O.weapon && O.weapon !== "spear") ? "hold" : (O.spear ? "spear" : "hang");
  return [{ key: id, draw: (p) => T.romanFront(p, O, { expr: "smile", seed: 3, L, R, blink: 0 }), x: -21.5, y: 6, z: 0, order: 3, tint: "#ffffff" }]; };
export const fxAt = (f, T) => [];
