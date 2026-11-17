
// ---------------- Uniform kit: headgear, armour, weapons and shields for soldiers of any country / era ----------------
const BRONZE = "#c58b3c", GOLD = "#e0b445", IRON = "#3a3f4b";
const SHD = [0.62, 0.64, 0.72];
export const HELM_BACK = {
  kabuto: (c) => {
    const { p, H, cx, hc, light, ow, thick, u, O } = c, col = O.helmCol || "#2b2f3a", y0 = hc + 0.05 * H.b, y1 = hc + 1.2 * H.b;
    const pts = [[cx - 1.08 * H.a, y0], [cx + 1.08 * H.a, y0], [cx + 1.6 * H.a, y1], [cx - 1.6 * H.a, y1]];
    p.shadedFill(pts, col, mul(col, SHD), light, H.a, 0.3);
    p.clip(pts, () => { for (let k = 1; k < 5; k++) { const y = y0 + (y1 - y0) * k / 5; p.stroke([[cx - 1.7 * H.a, y], [cx + 1.7 * H.a, y]], 1.6 * u, O.lace || "#c0392b"); } });
    p.inkRing(pts, ow * 0.85, thick);
  },
  indian: (c) => { // chain-mail aventail hanging from the helmet
    const { p, H, cx, hc, light, ow, thick, u } = c, y0 = hc - 0.1 * H.b, y1 = hc + 1.05 * H.b;
    const pts = [[cx - 1.08 * H.a, y0], [cx + 1.08 * H.a, y0], [cx + 1.3 * H.a, y1], [cx - 1.3 * H.a, y1]];
    p.shadedFill(pts, "#9aa3ad", mul("#9aa3ad", SHD), light, H.a, 0.3);
    p.clip(pts, () => { for (let i = -8; i <= 8; i++) { p.stroke([[cx + i * 8 * u - 40 * u, y0], [cx + i * 8 * u + 40 * u, y1]], 0.9 * u, "#6d757e"); p.stroke([[cx + i * 8 * u + 40 * u, y0], [cx + i * 8 * u - 40 * u, y1]], 0.9 * u, "#6d757e"); } });
    p.inkRing(pts, ow * 0.85, thick);
  },
};
const cone = (c, col, fur, tassel) => {
  const { p, H, cx, hc, light, ow, thick, u } = c, bandY = hc - H.b * 0.34, apexY = hc - 1.95 * H.b;
  const pts = [[cx - 1.04 * H.a, bandY + 0.04 * H.b], [cx + 1.04 * H.a, bandY + 0.04 * H.b], [cx + 0.1 * H.a, apexY], [cx - 0.1 * H.a, apexY]];
  p.shadedFill(pts, col, mul(col, SHD), light, H.a, 0.4);
  p.clip(pts, () => { for (let i = -3; i <= 3; i++) p.stroke([[cx + i * 0.3 * H.a, bandY], [cx + i * 0.04 * H.a, apexY]], 1.2 * u, mul(col, [0.6, 0.55, 0.6])); });
  p.inkRing(pts, ow * 0.9, thick);
  if (fur) {
    p.band([[cx - 1.1 * H.a, bandY], [cx + 1.1 * H.a, bandY]], fur, 0.3 * H.b, 2 * u, "round");
    for (let i = -5; i <= 5; i++) p.dot(cx + i * 0.2 * H.a, bandY + (i % 2 ? 4 : -4) * u, 3 * u, mul(fur, [1.25, 1.2, 1.1]));
    for (const s of [-1, 1]) { p.ell(cx + s * 1.05 * H.a, hc + 0.3 * H.b, 0.22 * H.a, 0.42 * H.b, fur, 2.2 * u); }
  } else p.band([[cx - 1.06 * H.a, bandY], [cx + 1.06 * H.a, bandY]], BRASS, 6 * u, 1.6 * u, "round");
  if (tassel) { p.dot(cx, apexY - 6 * u, 7 * u, tassel); for (let i = -2; i <= 2; i++) p.stroke([[cx, apexY], [cx + i * 7 * u, apexY + 26 * u]], 2 * u, tassel); }
};
export const HELM_FRONT = {
  knight: (c) => {
    const { p, H, cx, hc, light, ow, thick, u, O } = c, bandY = hc - H.b * 0.3, dome = ellPts(cx, bandY, H.a * 1.08, H.b * 0.8, 180, 360, 0, 48);
    const pl = ellPts(cx, bandY - 0.82 * H.b, 0.26 * H.a, 0.48 * H.b, 0, 360, 0, 24), pc = O.plume || "#d2372f";
    p.shadedFill(pl, pc, mul(pc, [0.7, 0.62, 0.7]), light, 0.26 * H.a, 0.3); p.inkRing(pl, ow * 0.7, thick);
    p.shadedFill(dome, STEEL, mul(STEEL, SHD), light, H.a, 0.4);
    p.clip(dome, () => p.stroke(ellPts(cx - 20 * u, bandY - 0.35 * H.b, 0.25 * H.a, 0.18 * H.b, 200, 300, 0, 16), 4 * u, "#ffffff66"));
    p.inkRing(dome, ow * 0.9, thick);
    p.band([[cx - H.a * 1.07, bandY], [cx + H.a * 1.07, bandY]], BRASS, 6 * u, 1.6 * u, "round");
    p.band([[cx, bandY], [cx, hc + 0.1 * H.b]], STEEL, 5 * u, 1.5 * u, "round");
    c.cheeks();
  },
  kabuto: (c) => {
    const { p, H, cx, hc, light, ow, thick, u, O } = c, col = O.helmCol || "#2b2f3a", bandY = hc - H.b * 0.32, dome = ellPts(cx, bandY, H.a * 1.06, H.b * 0.78, 180, 360, 0, 48);
    p.shadedFill(dome, col, mul(col, SHD), light, H.a, 0.4);
    p.clip(dome, () => p.stroke(ellPts(cx - 20 * u, bandY - 0.35 * H.b, 0.25 * H.a, 0.18 * H.b, 200, 300, 0, 16), 4 * u, "#ffffff44"));
    p.inkRing(dome, ow * 0.9, thick);
    p.band([[cx - H.a * 1.05, bandY], [cx + H.a * 1.05, bandY]], GOLD, 6 * u, 1.6 * u, "round");
    for (const s of [-1, 1]) p.stroke(curve([cx + s * 0.1 * H.a, bandY - 0.62 * H.b], [cx + s * 0.55 * H.a, bandY - 1.25 * H.b], [cx + s * 0.9 * H.a, bandY - 1.55 * H.b]), 5 * u, GOLD);
    p.dot(cx, bandY - 0.7 * H.b, 5 * u, GOLD);
  },
  ww2: (c) => {
    const { p, H, cx, hc, light, ow, thick, u, O } = c, col = O.helmCol || "#6f7a4a", bandY = hc - H.b * 0.36, dome = ellPts(cx, bandY, H.a * 1.1, H.b * 0.74, 180, 360, 0, 48);
    for (const s of [-1, 1]) p.stroke([[cx + s * 0.98 * H.a, bandY + 4 * u], [cx + s * 0.8 * H.a, hc + 0.85 * H.b]], 2.2 * u, "#5a4a30");
    p.shadedFill(dome, col, mul(col, SHD), light, H.a, 0.4);
    p.clip(dome, () => { for (let i = -6; i <= 6; i++) p.stroke([[cx + i * 9 * u, bandY], [cx + i * 9 * u + 6 * u, bandY - 0.8 * H.b]], 0.8 * u, mul(col, [0.8, 0.8, 0.8])); p.stroke(ellPts(cx - 20 * u, bandY - 0.3 * H.b, 0.25 * H.a, 0.16 * H.b, 200, 300, 0, 16), 4 * u, "#ffffff44"); });
    p.inkRing(dome, ow * 0.9, thick);
    p.band([[cx - H.a * 1.2, bandY + 2 * u], [cx + H.a * 1.2, bandY + 2 * u]], mul(col, [0.82, 0.82, 0.82]), 7 * u, 1.8 * u, "round");
  },
  indian: (c) => {
    const { p, H, cx, hc, light, ow, thick, u } = c, bandY = hc - H.b * 0.34, dome = ellPts(cx, bandY, H.a * 1.06, H.b * 0.8, 180, 360, 0, 48);
    p.shadedFill(dome, STEEL, mul(STEEL, SHD), light, H.a, 0.4);
    p.clip(dome, () => p.stroke(ellPts(cx - 20 * u, bandY - 0.35 * H.b, 0.25 * H.a, 0.18 * H.b, 200, 300, 0, 16), 4 * u, "#ffffff66"));
    p.inkRing(dome, ow * 0.9, thick);
    p.poly([[cx - 6 * u, bandY - 0.78 * H.b], [cx, bandY - 0.78 * H.b - 36 * u], [cx + 6 * u, bandY - 0.78 * H.b]], "#c9cfd6", 2 * u);
    p.band([[cx - H.a * 1.05, bandY], [cx + H.a * 1.05, bandY]], GOLD, 7 * u, 1.8 * u, "round");
    p.band([[cx, bandY], [cx, hc - 0.02 * H.b]], GOLD, 4 * u, 1.4 * u, "round");
  },
  mongol: (c) => cone(c, c.O.helmCol || "#7a4a2a", "#4a3322", null),
  conical: (c) => cone(c, c.O.helmCol || "#394b6b", null, "#d2372f"),
  peaked: (c) => {
    const { p, H, cx, hc, light, ow, thick, u, O } = c, col = O.helmCol || "#2f3a5a", bandY = hc - H.b * 0.34, dome = ellPts(cx, bandY, H.a * 1.1, H.b * 0.66, 180, 360, 0, 48);
    p.shadedFill(dome, col, mul(col, SHD), light, H.a, 0.4); p.inkRing(dome, ow * 0.9, thick);
    p.band([[cx - H.a * 1.08, bandY], [cx + H.a * 1.08, bandY]], mul(col, [0.5, 0.5, 0.6]), 8 * u, 1.8 * u, "round");
    p.dot(cx, bandY - 0.2 * H.b, 5 * u, GOLD);
    const vz = ellPts(cx, bandY + 3 * u, H.a * 0.95, H.b * 0.22, 0, 180, 0, 24); p.poly(vz, "#1b1b22", 1.6 * u);
  },
};

// ---- torso variants (drawn inside the clipped torso) ----
export const ARMOR_BODY = {
  lamellar: (c) => {
    const { p, tcx, T, chin, torsoBot, HH, u, O } = c, top = chin - 0.1 * HH, bot = torsoBot - 0.25 * HH, rows = 7, cols = O.plateCols || ["#8b1e1e", "#d9a845"];
    for (let r = 0; r < rows; r++) { const y0 = top + (bot - top) * r / rows, y1 = top + (bot - top) * (r + 1) / rows;
      for (let i = -5; i <= 5; i++) p.poly(rrect(tcx + i * 0.3 * T.a - 0.15 * T.a, y0, tcx + i * 0.3 * T.a + 0.15 * T.a, y1, 2 * u), cols[(r + i + 20) % 2], 1.1 * u); }
    p.band([[tcx - 1.4 * T.a, torsoBot - 0.2 * HH], [tcx + 1.4 * T.a, torsoBot - 0.2 * HH]], O.beltCol || "#2b2f3a", 0.08 * HH, 1.5 * u);
  },
  mail: (c) => {
    const { p, tcx, T, chin, torsoBot, HH, u, O } = c, top = chin - 0.1 * HH, bot = torsoBot - 0.1 * HH;
    p.poly([[tcx - 1.5 * T.a, top], [tcx + 1.5 * T.a, top], [tcx + 1.5 * T.a, bot], [tcx - 1.5 * T.a, bot]], "#a9b1bb", 0);
    for (let i = -14; i <= 14; i++) { p.stroke([[tcx + i * 0.11 * T.a - 0.5 * T.a, top], [tcx + i * 0.11 * T.a + 0.5 * T.a, bot]], 0.9 * u, "#6d757e"); p.stroke([[tcx + i * 0.11 * T.a + 0.5 * T.a, top], [tcx + i * 0.11 * T.a - 0.5 * T.a, bot]], 0.9 * u, "#6d757e"); }
    p.poly([[tcx - 0.85 * T.a, top + 0.12 * HH], [tcx + 0.85 * T.a, top + 0.12 * HH], [tcx + 0.9 * T.a, bot], [tcx - 0.9 * T.a, bot]], O.tunic, 1.6 * u);   // surcoat
    if (O.emblem === "cross") { p.band([[tcx, top + 0.18 * HH], [tcx, bot - 0.06 * HH]], "#f4f1ea", 8 * u, 1 * u); p.band([[tcx - 0.55 * T.a, top + 0.42 * HH], [tcx + 0.55 * T.a, top + 0.42 * HH]], "#f4f1ea", 8 * u, 1 * u); }
    p.band([[tcx - 1.4 * T.a, torsoBot - 0.2 * HH], [tcx + 1.4 * T.a, torsoBot - 0.2 * HH]], LEATHER, 0.07 * HH, 1.5 * u);
  },
  plate: (c) => {
    const { p, tcx, T, chin, torsoBot, HH, u, light } = c, top = chin - 0.1 * HH, bot = torsoBot - 0.15 * HH;
    p.poly([[tcx - 1.5 * T.a, top], [tcx + 1.5 * T.a, top], [tcx + 1.5 * T.a, bot], [tcx - 1.5 * T.a, bot]], BRONZE, 0);
    for (const s of [-1, 1]) { p.stroke(ellPts(tcx + s * 0.35 * T.a, top + 0.28 * HH, 0.3 * T.a, 0.14 * HH, 0, 180, 0, 16), 2.2 * u, "#8a5d22"); }
    p.stroke([[tcx, top + 0.1 * HH], [tcx, bot - 0.2 * HH]], 2 * u, "#8a5d22");
    p.stroke(ellPts(tcx, bot - 0.45 * HH, 0.5 * T.a, 0.12 * HH, 0, 180, 0, 16), 2 * u, "#8a5d22");
    p.band([[tcx - 1.4 * T.a, torsoBot - 0.2 * HH], [tcx + 1.4 * T.a, torsoBot - 0.2 * HH]], "#7a1f1f", 0.08 * HH, 1.5 * u);
  },
  uniform: (c) => {
    const { p, tcx, T, chin, torsoBot, HH, u, O } = c, top = chin - 0.1 * HH, bot = torsoBot - 0.25 * HH;
    for (const s of [-1, 1]) { p.poly(rrect(tcx + s * 0.5 * T.a - 0.18 * T.a, top + 0.28 * HH, tcx + s * 0.5 * T.a + 0.18 * T.a, top + 0.5 * HH, 1.5 * u), mul(O.tunic, [0.86, 0.86, 0.86]), 1.3 * u); p.dot(tcx + s * 0.5 * T.a, top + 0.34 * HH, 1.6 * u, BRASS); }
    p.band([[tcx - 0.9 * T.a, top + 0.02 * HH], [tcx + 0.6 * T.a, torsoBot - 0.15 * HH]], O.strapCol || LEATHER, 0.06 * HH, 1.2 * u);
    p.band([[tcx - 1.4 * T.a, torsoBot - 0.24 * HH], [tcx + 1.4 * T.a, torsoBot - 0.24 * HH]], O.beltCol || LEATHER, 0.07 * HH, 1.4 * u);
    p.rect ? 0 : 0; p.dot(tcx, torsoBot - 0.24 * HH, 4 * u, BRASS);
  },
};

// ---- weapons held in the right hand (drawn behind the body, like the spear) ----
export const drawWeapon = (p, kind, hx, hy, u, O) => {
  const blade = "#d7dde3";
  if (kind === "sword") { p.band([[hx, hy + 8 * u], [hx + 3 * u, hy - 64 * u]], blade, 5 * u, 1.4 * u, "round"); p.stroke([[hx - 10 * u, hy + 2 * u], [hx + 10 * u, hy + 2 * u]], 3.4 * u, BRASS); p.dot(hx, hy + 14 * u, 3.4 * u, BRASS); }
  else if (kind === "katana") { p.stroke(curve([hx, hy + 10 * u], [hx + 14 * u, hy - 38 * u], [hx + 8 * u, hy - 84 * u]), 4.4 * u, INK); p.stroke(curve([hx, hy + 10 * u], [hx + 14 * u, hy - 38 * u], [hx + 8 * u, hy - 84 * u]), 2.6 * u, blade); p.ell(hx, hy + 2 * u, 7 * u, 3 * u, GOLD, 1.6 * u); p.stroke([[hx, hy + 6 * u], [hx, hy + 20 * u]], 4 * u, "#2b2f3a"); }
  else if (kind === "talwar") { p.stroke(curve([hx, hy + 8 * u], [hx + 20 * u, hy - 36 * u], [hx + 4 * u, hy - 72 * u]), 6 * u, INK); p.stroke(curve([hx, hy + 8 * u], [hx + 20 * u, hy - 36 * u], [hx + 4 * u, hy - 72 * u]), 3.8 * u, blade); p.stroke(curve([hx - 8 * u, hy + 4 * u], [hx - 12 * u, hy + 14 * u], [hx - 2 * u, hy + 18 * u]), 2.2 * u, GOLD); p.ell(hx, hy + 2 * u, 9 * u, 3 * u, GOLD, 1.6 * u); }
  else if (kind === "rifle") { p.band([[hx - 16 * u, hy + 20 * u], [hx + 22 * u, hy - 70 * u]], "#5a4326", 5.4 * u, 1.5 * u, "round"); p.band([[hx + 2 * u, hy - 14 * u], [hx + 24 * u, hy - 68 * u]], "#2f3238", 3 * u, 1.2 * u, "round"); }
  else if (kind === "bow") { const arc = ellPts(hx + 6 * u, hy - 28 * u, 16 * u, 50 * u, -75, 75, 0, 24); p.stroke(arc, 4.6 * u, INK); p.stroke(arc, 2.8 * u, "#8a5a34"); p.stroke([arc[0], arc[arc.length - 1]], 1 * u, "#f4f1ea"); }
  else if (kind === "flag") { const top = hy - 92 * u, fc = O.flag || "#d2372f"; p.band([[hx, hy + 70 * u], [hx - 2 * u, top]], "#8a5a34", 3.6 * u, 1.2 * u, "round");
    const cl = [[hx - 2 * u, top + 2 * u], [hx + 30 * u, top - 4 * u], [hx + 60 * u, top + 4 * u], [hx + 58 * u, top + 40 * u], [hx + 30 * u, top + 34 * u], [hx - 2 * u, top + 42 * u]];
    p.poly(cl, fc, 2 * u); p.dot(hx + 30 * u, top + 20 * u, 9 * u, "#f4f1ea"); }
};

// ---- shields held in front (left hand) ----
export const drawShield = (p, kind, sx, sy, sw, sh, u, ow, thick, light, O) => {
  const col = O.shieldCol || "#c0302c";
  if (kind === "round") {
    const r = sw * 0.95, pts = ellPts(sx, sy - 0.1 * sh, r, r, 0, 360, 0, 40);
    p.gradFill(pts, col, mul(col, [0.55, 0.55, 0.6]), light);
    p.clip(pts, () => { for (const k of [0.82, 0.58]) p.stroke(ellPts(sx, sy - 0.1 * sh, r * k, r * k, 0, 360, 0, 40), 2.4 * u, k > 0.7 ? GOLD : "#f4f1ea"); });
    p.ell(sx, sy - 0.1 * sh, 0.2 * r, 0.2 * r, "#e6c068", 2.2 * u); p.inkRing(pts, ow, thick);
  } else if (kind === "heater") {
    const pts = [[sx - sw, sy - sh], [sx + sw, sy - sh], [sx + sw, sy + 0.05 * sh], [sx, sy + sh * 1.05], [sx - sw, sy + 0.05 * sh]];
    p.gradFill(pts, col, mul(col, [0.55, 0.55, 0.6]), light);
    p.clip(pts, () => { p.band([[sx, sy - sh], [sx, sy + sh]], "#f4f1ea", 9 * u, 1.2 * u); p.band([[sx - sw, sy - 0.35 * sh], [sx + sw, sy - 0.35 * sh]], "#f4f1ea", 9 * u, 1.2 * u); });
    p.inkRing(pts, ow, thick);
  }
};

export const UNIFORMS = {
  roman: OUTFITS.legion,
  knight: { tunic: "#2c4a8a", skin: SKIN, helmet: true, helm: "knight", armor: false, armorKind: "mail", emblem: "cross", shield: true, shieldKind: "heater", shieldCol: "#2c4a8a", weapon: "sword", plume: "#d2372f" },
  samurai: { tunic: "#7a1f1f", skin: SKIN, helmet: true, helm: "kabuto", helmCol: "#2b2f3a", armor: true, armorKind: "lamellar", plateCols: ["#8b1e1e", "#d9a845"], weapon: "katana", moustache: "#222222" },
  indian: { tunic: "#c0662a", skin: "#d9a679", helmet: true, helm: "indian", armor: false, armorKind: "mail", shield: true, shieldKind: "round", shieldCol: "#c0662a", weapon: "talwar", moustache: "#1e1714" },
  mongol: { tunic: "#2f6f6b", skin: "#e0b98f", helmet: true, helm: "mongol", helmCol: "#7a4a2a", armor: false, armorKind: "lamellar", plateCols: ["#6b4a2a", "#8a6a3a"], weapon: "bow", moustache: "#1e1714" },
  chinese: { tunic: "#8a2a2a", skin: SKIN, helmet: true, helm: "conical", helmCol: "#394b6b", armor: false, armorKind: "lamellar", plateCols: ["#394b6b", "#8a2a2a"], spear: true },
  us_ww2: { tunic: "#6b7a3a", skin: "#f3d6bb", helmet: true, helm: "ww2", helmCol: "#6f7a4a", armor: false, armorKind: "uniform", weapon: "rifle" },
  jp_ww2: { tunic: "#8a7a3a", skin: SKIN, helmet: true, helm: "ww2", helmCol: "#7a7340", armor: false, armorKind: "uniform", weapon: "rifle" },
  uk_ww2: { tunic: "#7b6f4a", skin: "#f3d6bb", helmet: true, helm: "ww2", helmCol: "#6c7358", armor: false, armorKind: "uniform", weapon: "rifle" },
  officer: { tunic: "#2f3a5a", skin: "#f3d6bb", helmet: true, helm: "peaked", helmCol: "#2f3a5a", armor: false, armorKind: "uniform", weapon: "sword", strapCol: "#7a4a2a" },
};

// ---- teams: the two sides of a battle get clearly different colours ----
export const TEAMCOL = { A: "#2f6fb0", B: "#c2432f", C: "#4c9a4a" };
export const UNIFORMS_EXTRA = { villager: OUTFITS.civA, villager2: OUTFITS.civB, elder: OUTFITS.toga };
export const teamed = (id, team) => {
  const base = UNIFORMS[id] || UNIFORMS_EXTRA[id] || UNIFORMS.roman, o = { ...base }, col = TEAMCOL[team];
  if (col && UNIFORMS[id] && id !== "roman") { o.tunic = col; if (o.shieldCol) o.shieldCol = col; o.plume = col; o.flag = col; if (o.armorKind === "uniform" || o.helm === "peaked") o.helmCol = mul(col, [0.7, 0.7, 0.7]); }
  else if (col && id === "roman") { o.tunic = col; }
  return o;
};

// ---- attention marks drawn as cards ----
const rr = (x0, y0, x1, y1, r) => rrect(x0, y0, x1, y1, r);
export const fxMark = (p, kind, t) => {
  const e = Math.min(1, t * 3), s = 0.4 + 0.6 * (1 - Math.pow(1 - e, 3)) + 0.06 * Math.sin(t * 20);
  p.g.save(); p.g.translate(300, 520); p.g.scale(s, s); p.g.translate(-300, -520);
  if (kind === "!") { p.poly(rr(262, 260, 338, 560, 24), "#e0302a", 14); p.ell(300, 650, 44, 44, "#e0302a", 14); }
  else { const arc = ellPts(300, 390, 88, 84, 150, 420, 0, 30); const pts = [...arc, [300, 520], [300, 556]]; p.stroke(pts, 66, INK); p.stroke(pts, 40, "#ffd94a"); p.ell(300, 650, 40, 40, "#ffd94a", 14); }
  p.g.restore();
};
