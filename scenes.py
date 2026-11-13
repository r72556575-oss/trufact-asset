"""Automatic 2D cartoon scenes: flat bean-head characters acting in painted settings, with camera moves.

A beat is described by plain data (setting, time of day, camera, cast with role/slot/expression/action, fx, a prop picture).
Everything is drawn with PIL at 2x then downsampled, so it runs anywhere (GitHub runner included).
"""
import math, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import toon
from toon import ease, over, font, INK, W, H, FPS

WW, WH = 1400, 2100            # "world" canvas, the camera crops a 1080x1920 window out of it
GROUND = 1500                  # y of the ground line in world coordinates
SLOTS = {"left": 400, "center": 700, "right": 1000}
SETTINGS = ["village", "city", "mountains", "ocean", "desert", "space", "indoor"]
ROLES = {
    "boy": dict(skin=(255, 210, 165), hair=("short", (46, 34, 32)), shirt=(255, 112, 67), pants=(70, 90, 160)),
    "girl": dict(skin=(240, 190, 150), hair=("long", (40, 28, 30)), shirt=(235, 80, 140), pants=(90, 70, 150)),
    "scientist": dict(skin=(255, 215, 175), hair=("short", (120, 90, 60)), shirt=(250, 250, 250), pants=(60, 70, 90), glasses=True, coat=True),
    "elder": dict(skin=(235, 190, 150), hair=("bald", (235, 235, 235)), shirt=(120, 160, 110), pants=(110, 90, 70), beard=(238, 238, 238)),
    "king": dict(skin=(250, 200, 160), hair=("short", (90, 60, 40)), shirt=(168, 40, 66), pants=(50, 40, 100), crown=True, beard=(90, 60, 40)),
    "worker": dict(skin=(225, 175, 130), hair=("cap", (255, 200, 40)), shirt=(255, 160, 30), pants=(60, 80, 120)),
    "explorer": dict(skin=(245, 205, 165), hair=("hat", (170, 125, 70)), shirt=(110, 150, 80), pants=(120, 90, 60)),
}
EXPRS = ["neutral", "happy", "surprised", "sad", "angry", "think", "laugh"]
ACTIONS = ["idle", "talk", "point", "think", "surprised", "cheer", "wave", "sad", "walk_in"]
CAMERAS = ["push_in", "pull_back", "pan_left", "pan_right", "shake", "static"]
FX = ["none", "sparkles", "exclamation", "question", "sweat", "hearts", "stars"]
TIMES = ["day", "sunset", "night"]

# ------------------------------------------------------------------ settings (painted once per beat)
def _sky(d, S, tm, rnd):
    top, bot = {"day": ((110, 195, 255), (214, 238, 255)), "sunset": ((255, 150, 110), (255, 222, 150)), "night": ((22, 26, 74), (70, 66, 140))}[tm]
    img = np.zeros((WH, WW, 3), np.float32); t = np.linspace(0, 1, WH)[:, None, None]
    img[:] = np.array(top) * (1 - t) + np.array(bot) * t
    return Image.fromarray(img.astype(np.uint8)).convert("RGBA")

def paint_setting(setting, tm, seed):
    rnd = random.Random(seed); S = 2
    base = _sky(None, S, tm, rnd).resize((WW * S, WH * S), Image.BILINEAR); d = ImageDraw.Draw(base)
    P = lambda pts: [(x * S, y * S) for x, y in pts]
    def poly(pts, fill, w=6): d.polygon(P(pts), fill=fill); d.line(P(pts + [pts[0]]), fill=INK, width=w * S, joint="curve")
    def ell(cx, cy, rx, ry, fill, w=6): d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill, outline=INK if w else None, width=w * S)
    def rect(x0, y0, x1, y1, fill, w=6, r=0): d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], r * S, fill=fill, outline=INK if w else None, width=w * S)
    night = tm == "night"
    if night:
        for _ in range(70): ell(rnd.uniform(0, WW), rnd.uniform(0, 1300), rnd.uniform(2, 5), rnd.uniform(2, 5), (255, 255, 230), 0)
    ell(1050 if setting != "space" else 330, 330, 80, 80, (255, 245, 200) if night else (255, 226, 90) if tm == "day" else (255, 120, 60), 7)
    if not night and setting not in ("indoor", "space"):
        for cx, cy in ((260, 420), (760, 300), (1180, 560)):
            for dx, dy, r in ((-60, 10, 50), (0, -20, 64), (62, 10, 50)): ell(cx + dx, cy + dy, r, r * 0.8, (255, 255, 255), 0)
            rect(cx - 112, cy + 12, cx + 112, cy + 40, (255, 255, 255), 0)
    g1, g2 = {"day": ((120, 205, 105), (90, 170, 85)), "sunset": ((200, 160, 90), (170, 120, 70)), "night": ((50, 100, 90), (35, 75, 70))}[tm]
    if setting == "village":
        poly([(0, 1180), (260, 1040), (560, 1160), (860, 1010), (1150, 1150), (1400, 1060), (1400, 1500), (0, 1500)], g2)
        for hx, hy, hc in ((140, 1260, (240, 120, 100)), (620, 1230, (250, 200, 90)), (1130, 1270, (110, 170, 230))):
            rect(hx - 110, hy - 150, hx + 110, hy + 60, (255, 245, 225)); poly([(hx - 140, hy - 150), (hx, hy - 270), (hx + 140, hy - 150)], hc)
            rect(hx - 28, hy - 40, hx + 28, hy + 60, (140, 90, 60)); rect(hx + 50, hy - 110, hx + 90, hy - 62, (190, 230, 255), 5)
        for tx in (400, 900, 1300): rect(tx - 14, 1290, tx + 14, 1400, (130, 90, 60)); ell(tx, 1250, 70, 80, (70, 170, 90))
    elif setting == "city":
        for i in range(9):
            bx = i * 170 - 30; bh = rnd.randint(380, 760); col = rnd.choice([(150, 170, 230), (240, 170, 190), (170, 220, 200), (250, 210, 140), (190, 180, 240)])
            rect(bx, 1500 - bh, bx + 150, 1500, col)
            for wy in range(1500 - bh + 40, 1440, 64):
                for wx in (bx + 22, bx + 74): rect(wx, wy, wx + 38, wy + 34, (255, 240, 170) if (wx + wy) % 3 else (130, 160, 210), 4)
    elif setting == "mountains":
        poly([(-100, 1500), (300, 760), (760, 1500)], (140, 150, 190)); poly([(480, 1500), (940, 640), (1500, 1500)], (120, 130, 175))
        poly([(940, 640), (860, 790), (920, 760), (960, 820), (1010, 760), (1070, 800)], (255, 255, 255)); poly([(300, 760), (230, 880), (290, 850), (340, 900), (380, 840)], (255, 255, 255))
        poly([(0, 1280), (400, 1210), (900, 1290), (1400, 1230), (1400, 1500), (0, 1500)], g2)
        for tx in (160, 520, 880, 1260): poly([(tx - 50, 1400), (tx, 1240), (tx + 50, 1400)], (50, 130, 80)); rect(tx - 8, 1400, tx + 8, 1440, (120, 80, 50), 4)
    elif setting == "ocean":
        rect(-20, 1000, WW + 20, 1520, (60, 160, 220), 0)
        for wy in (1080, 1180, 1290, 1400):
            for wx in range(-40, WW + 80, 140): d.arc([wx * S, wy * S, (wx + 100) * S, (wy + 40) * S], 200, 340, fill=(255, 255, 255), width=6 * S)
        poly([(180, 1060), (420, 1060), (350, 1130), (250, 1130)], (240, 90, 70)); rect(296, 840, 304, 1060, INK, 0); poly([(304, 860), (304, 1040), (420, 1040)], (255, 255, 255))
        g1, g2 = (240, 215, 150), (225, 190, 120)
    elif setting == "desert":
        poly([(-50, 1300), (350, 1130), (800, 1280), (1100, 1150), (1500, 1300), (1500, 1500), (-50, 1500)], (245, 205, 120))
        poly([(820, 1250), (1010, 900), (1200, 1250)], (230, 180, 100)); poly([(1010, 900), (1100, 1070), (920, 1070)], (240, 195, 110))
        for cx in (180, 560): rect(cx - 16, 1230, cx + 16, 1400, (80, 170, 90)); rect(cx - 60, 1290, cx - 36, 1340, (80, 170, 90)); rect(cx + 36, 1270, cx + 60, 1320, (80, 170, 90)); rect(cx - 60, 1330, cx, 1346, (80, 170, 90), 5)
        g1, g2 = (240, 205, 130), (225, 185, 110)
    elif setting == "space":
        for _ in range(90): ell(rnd.uniform(0, WW), rnd.uniform(0, 1450), rnd.uniform(2, 6), rnd.uniform(2, 6), (255, 255, 235), 0)
        ell(300, 700, 190, 190, (235, 120, 90)); ell(300, 700, 190, 60, None, 0); d.arc([100 * S, 640 * S, 500 * S, 760 * S], 0, 360, fill=INK, width=8 * S)
        ell(1060, 940, 120, 120, (110, 170, 240)); ell(1020, 910, 40, 28, (90, 210, 130), 0)
        g1, g2 = (170, 170, 190), (140, 140, 165)
        for cx, cy in ((200, 1440), (700, 1470), (1180, 1430)): ell(cx, cy, 70, 18, (125, 125, 150), 5)
    else:  # indoor
        rect(-20, 0, WW + 20, GROUND, (255, 232, 190), 0); rect(-20, 260, WW + 20, 300, (230, 190, 140), 0)
        rect(480, 340, 920, 880, (190, 230, 255), 10)
        d.line(P([(700, 340), (700, 880)]), fill=INK, width=8 * S); d.line(P([(480, 610), (920, 610)]), fill=INK, width=8 * S)
        rect(60, 900, 340, 1500, (170, 120, 80), 8)
        for sy, col in ((960, (240, 120, 120)), (1100, (120, 200, 140)), (1240, (120, 160, 240))): rect(80, sy + 90, 320, sy + 100, (110, 70, 40), 0); ell(130, sy + 40, 26, 40, col, 5); ell(220, sy + 52, 30, 30, col, 5); ell(280, sy + 44, 22, 44, col, 5)
        g1, g2 = (205, 150, 100), (185, 130, 85)
    # ground
    rect(-20, GROUND, WW + 20, WH + 20, g1, 0)
    d.line(P([(-20, GROUND), (WW + 20, GROUND)]), fill=INK, width=8 * S)
    for k in range(0, WW + 200, 200): d.line(P([(k, GROUND + 90), (k + 110, GROUND + 90)]), fill=g2, width=14 * S)
    for k in range(60, WW, 260): d.line(P([(k, GROUND + 230), (k + 130, GROUND + 230)]), fill=g2, width=14 * S)
    return base.resize((WW, WH), Image.LANCZOS)

# ------------------------------------------------------------------ characters
def _arms(action, t):
    w = math.sin(t * 7.0)
    return {"idle": ((-80, -168), (80, -168)), "talk": ((-86, -222 + 8 * w), (92, -262 - 16 * w)), "point": ((-80, -168), (190, -350 + 6 * w)),
            "think": ((-80, -168), (36, -376)), "surprised": ((-76, -396), (76, -396)), "cheer": ((-122, -505 - 22 * abs(w)), (122, -505 - 22 * abs(math.sin(t * 7 + 1)))),
            "wave": ((-80, -168), (118, -480 + 34 * w)), "sad": ((-70, -150), (70, -150)), "walk_in": ((-84 + 14 * w, -190), (84 - 14 * w, -190))}.get(action, ((-80, -168), (80, -168)))

def character(role, t, expr, action, blink=False, walk=0.0, look=0.5):
    R = ROLES[role]; S = 2; ox, oy = 210, 600
    im = Image.new("RGBA", (420 * S, 640 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    X = lambda x: (ox + x) * S; Y = lambda y: (oy + y) * S
    def E(cx, cy, rx, ry, fill, w=6): d.ellipse([X(cx - rx), Y(cy - ry), X(cx + rx), Y(cy + ry)], fill=fill, outline=INK if w else None, width=w * S)
    def L(pts, w, col): d.line([(X(x), Y(y)) for x, y in pts], fill=col, width=int(w * S), joint="curve")
    def Pg(pts, fill, w=5): d.polygon([(X(x), Y(y)) for x, y in pts], fill=fill); d.line([(X(x), Y(y)) for x, y in pts + [pts[0]]], fill=INK, width=w * S, joint="curve")
    bob = 4 * math.sin(t * 5.0) if action != "walk_in" else 8 * abs(math.sin(walk * 2))
    jump = -34 * abs(math.sin(t * 6.5)) if action == "cheer" else 0
    by = bob + jump
    # legs
    sw = 26 * math.sin(walk) if action == "walk_in" else 0
    for lx, off in ((-30, sw), (30, -sw)):
        L([(lx, -170 + by), (lx + off, -22 + jump)], 36, INK); L([(lx, -170 + by), (lx + off, -22 + jump)], 24, R["pants"]); E(lx + off + 6, -14 + jump, 30, 16, (60, 50, 60), 5)
    # back arm + body + front arm
    ls, rs = (-64, -318 + by), (64, -318 + by); lh, rh = _arms(action, t)
    lh, rh = (lh[0], lh[1] + by), (rh[0], rh[1] + by)
    sleeve = R["shirt"]
    for sh, hd in ((ls, lh), (rs, rh)):
        L([sh, hd], 34, INK); L([sh, hd], 22, sleeve); E(hd[0], hd[1], 19, 19, R["skin"], 6)
    d.rounded_rectangle([X(-70), Y(-340 + by), X(70), Y(-130 + by)], 44 * S, fill=R["shirt"], outline=INK, width=6 * S)
    if R.get("coat"): d.line([(X(0), Y(-336 + by)), (X(0), Y(-132 + by))], fill=INK, width=5 * S); Pg([(-22, -336 + by), (0, -292 + by), (22, -336 + by)], (200, 220, 255))
    else: E(0, -336 + by, 26, 12, R["skin"], 0)
    # head
    hy = -418 + by
    E(-86, hy + 8, 20, 24, R["skin"], 6); E(86, hy + 8, 20, 24, R["skin"], 6); E(0, hy, 92, 86, R["skin"], 7)
    kind, hc = R["hair"]
    if kind == "short": d.pieslice([X(-92), Y(hy - 86), X(92), Y(hy + 86)], 182, 358, fill=hc, outline=INK, width=7 * S)
    elif kind == "long":
        d.pieslice([X(-96), Y(hy - 92), X(96), Y(hy + 86)], 178, 362, fill=hc, outline=INK, width=7 * S); E(-90, hy + 50, 22, 62, hc, 6); E(90, hy + 50, 22, 62, hc, 6); E(0, hy, 92, 86, R["skin"], 7)
        d.pieslice([X(-96), Y(hy - 92), X(96), Y(hy + 86)], 192, 348, fill=hc, outline=INK, width=7 * S)
    elif kind == "cap": d.pieslice([X(-92), Y(hy - 86), X(92), Y(hy + 86)], 182, 358, fill=hc, outline=INK, width=7 * S); d.rounded_rectangle([X(-110), Y(hy - 20), X(70), Y(hy - 2)], 8 * S, fill=hc, outline=INK, width=6 * S)
    elif kind == "hat":
        E(0, hy - 62, 128, 26, hc, 7); d.pieslice([X(-76), Y(hy - 150), X(76), Y(hy - 20)], 180, 360, fill=hc, outline=INK, width=7 * S)
    if R.get("crown"): Pg([(-60, hy - 78), (-60, hy - 130), (-30, hy - 100), (0, hy - 140), (30, hy - 100), (60, hy - 130), (60, hy - 78)], (255, 206, 60))
    # face
    ex_, mo = expr, ("open" if expr in ("laugh", "surprised") else "frown" if expr in ("sad", "angry") else "smile")
    for ex in (-36, 36):
        if blink or expr in ("laugh",):
            d.arc([X(ex - 20), Y(hy - 6), X(ex + 20), Y(hy + 24)], 200, 340, fill=INK, width=6 * S)
        else:
            big = 1.25 if expr == "surprised" else 1.0
            E(ex, hy + 4, 22 * big, 26 * big, (255, 255, 255), 5); E(ex + look * 7, hy + 8, (11 if expr != "surprised" else 6), (14 if expr != "surprised" else 7), INK, 0)
        brow = {"angry": (-6, 6), "sad": (7, -7), "surprised": (-12, -12), "think": (0, -10)}.get(expr, (0, 0)); sgn = 1 if ex < 0 else -1
        L([(ex - 22, hy - 38 + (brow[0] if ex < 0 else brow[1])), (ex + 22, hy - 38 + (brow[1] if ex < 0 else brow[0]))], 6, R["hair"][1] if R["hair"][0] != "bald" else (150, 150, 150))
    if R.get("glasses"):
        for ex in (-36, 36): d.ellipse([X(ex - 28), Y(hy - 24), X(ex + 28), Y(hy + 34)], outline=INK, width=5 * S)
        L([(-8, hy + 4), (8, hy + 4)], 5, INK)
    E(-62, hy + 40, 14, 9, (255, 150, 150), 0); E(62, hy + 40, 14, 9, (255, 150, 150), 0)
    my = hy + 52
    if R.get("beard"):
        d.pieslice([X(-70), Y(hy + 6), X(70), Y(hy + 120)], 10, 170, fill=R["beard"], outline=INK, width=6 * S)
    if mo == "open": E(0, my + 8, 22 if expr == "laugh" else 14, 22 if expr == "laugh" else 20, (120, 28, 38), 5)
    elif mo == "frown": d.arc([X(-24), Y(my - 2), X(24), Y(my + 30)], 200, 340, fill=INK, width=6 * S)
    else: d.arc([X(-26), Y(my - 22), X(26), Y(my + 10)], 20, 160, fill=INK, width=6 * S)
    return im.resize((420, 640), Image.LANCZOS)

# ------------------------------------------------------------------ fx
def draw_fx(im, kind, lt, cx, cy):
    d = ImageDraw.Draw(im)
    if kind == "exclamation":
        e = over((lt - 0.1) / 0.3, 2.4); s = 1.0 * max(e, 0.01); y = cy - 30 * ease(lt / 0.4)
        d.rounded_rectangle([cx - 22 * s, y - 120 * s, cx + 22 * s, y + 10 * s], 14 * s, fill=(235, 40, 40), outline=INK, width=int(6 * s)); d.ellipse([cx - 20 * s, y + 28 * s, cx + 20 * s, y + 68 * s], fill=(235, 40, 40), outline=INK, width=int(6 * s))
    elif kind == "question":
        e = over((lt - 0.1) / 0.3, 2.4); d.text((cx, cy - 30), "?", font=font(180 * max(e, 0.05)), fill=(255, 226, 70), anchor="mm", stroke_width=12, stroke_fill=INK)
    elif kind == "sweat":
        y = cy + 30 * ((lt * 1.6) % 1); d.polygon([(cx, y - 46), (cx + 20, y), (cx, y + 18), (cx - 20, y)], fill=(130, 200, 255), outline=INK)
    elif kind in ("sparkles", "stars", "hearts"):
        for k in range(5):
            a = lt * 2 + k * 1.26; r = 150 + 40 * math.sin(lt * 3 + k); x = cx + r * math.cos(a) * 1.3; y = cy + r * math.sin(a) * 0.8; s = 22 + 10 * math.sin(lt * 5 + k)
            if kind == "hearts": d.ellipse([x - s, y - s, x, y], fill=(255, 90, 130)); d.ellipse([x, y - s, x + s, y], fill=(255, 90, 130)); d.polygon([(x - s, y - s * .35), (x + s, y - s * .35), (x, y + s * 1.1)], fill=(255, 90, 130))
            else: d.polygon([(x, y - s * 1.4), (x + s * .4, y - s * .4), (x + s * 1.4, y), (x + s * .4, y + s * .4), (x, y + s * 1.4), (x - s * .4, y + s * .4), (x - s * 1.4, y), (x - s * .4, y - s * .4)], fill=(255, 240, 130), outline=INK)

# ------------------------------------------------------------------ rendering
def norm_scene(b, i):
    c = dict(b)
    c["setting"] = c.get("setting") if c.get("setting") in SETTINGS else SETTINGS[i % len(SETTINGS)]
    c["time"] = c.get("time") if c.get("time") in TIMES else "day"
    c["camera"] = c.get("camera") if c.get("camera") in CAMERAS else CAMERAS[i % 4]
    c["fx"] = c.get("fx") if c.get("fx") in FX else "none"
    cast = []
    for k, m in enumerate((b.get("cast") or [])[:3]):
        role = m.get("role") if m.get("role") in ROLES else list(ROLES)[(i + k) % len(ROLES)]
        slot = m.get("slot") if m.get("slot") in SLOTS else ("left", "center", "right")[k]
        cast.append(dict(role=role, slot=slot, expr=m.get("expr") if m.get("expr") in EXPRS else "happy", action=m.get("action") if m.get("action") in ACTIONS else "talk"))
    if not cast: cast = [dict(role="boy", slot="center", expr="happy", action="talk")]
    c["cast"] = cast
    return c

def camera_window(kind, p, lt):
    z, px = {"push_in": (1.0 + 0.13 * ease(p), 0), "pull_back": (1.16 - 0.14 * ease(p), 0), "pan_left": (1.08, 70 * (1 - 2 * ease(p))),
             "pan_right": (1.08, -70 * (1 - 2 * ease(p))), "shake": (1.04, 0), "static": (1.0, 0)}[kind]
    cx, cy = 700 + px, 1060
    if kind == "shake": cx += 6 * math.sin(lt * 40); cy += 5 * math.cos(lt * 33)
    cw, ch = W / z, H / z
    return (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)

def render(out_path, audio_path, stickers, beats, starts, durs, total_sec, groups, caption_fn, number_of, brand_idx):
    scenes = [norm_scene(b, i) for i, b in enumerate(beats)]
    worlds = [paint_setting(s["setting"], s["time"], i * 11 + 5) for i, s in enumerate(scenes)]
    shade = np.zeros((H, W, 4), np.uint8); ramp = np.clip((np.arange(H) - H * 0.66) / (H * 0.34), 0, 1) ** 1.4 * 140
    shade[..., 3] = ramp[:, None].astype(np.uint8); shade = Image.fromarray(shade, "RGBA")
    cache = {}
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-ar", "44100", "-t", f"{total_sec:.3f}", "-movflags", "+faststart", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(total_sec * FPS)):
        t = f / FPS
        bi = max(i for i in range(len(beats)) if starts[i] <= t + 1e-6); lt = t - starts[bi]; p = lt / max(durs[bi], 0.1)
        sc = scenes[bi]; world = worlds[bi].copy(); wd = ImageDraw.Draw(world)
        cta = bi == brand_idx
        for k, m in enumerate(sc["cast"]):
            x = SLOTS[m["slot"]]; facing = -1 if m["slot"] == "right" else 1
            action = "cheer" if cta else m["action"]; walk = 0.0; xo = 0.0; sy = 1.0
            if action == "walk_in":
                e = ease(lt / 1.1); xo = (1 - e) * (-720 if m["slot"] != "right" else 720); walk = lt * 11
                if e >= 1: action = "idle"
            else:
                pe = over((lt - 0.08 * k) / 0.4, 1.8); sy = 0.55 + 0.45 * max(pe, 0.0) if pe < 1 else 1.0
            blink = ((f + 13 * k + bi * 5) % 90) in (0, 1, 2)
            spr = character(m["role"], t + k * 0.7, m["expr"], action, blink, walk, look=0.5 * facing * -1)
            if facing == -1: spr = spr.transpose(Image.FLIP_LEFT_RIGHT)
            if sy != 1.0: spr = spr.resize((spr.width, max(2, int(spr.height * sy))), Image.BILINEAR)
            gx, gy = x + xo, GROUND + 70
            wd.ellipse([gx - 80, gy - 12, gx + 80, gy + 16], fill=(0, 0, 0, 60))
            world.alpha_composite(spr, (int(gx - 210), int(gy - (600 * (spr.height / 640)))))
            if sc["fx"] != "none" and k == 0: draw_fx(world, sc["fx"], lt, gx + 20 * facing, gy - 560)
        box = camera_window({"push_in": "push_in"}.get(sc["camera"], sc["camera"]), p, lt)
        im = world.crop(tuple(int(v) for v in box)).resize((W, H), Image.BILINEAR)
        im.alpha_composite(shade)
        st = stickers[bi]
        if st is not None and not cta: toon.paste_sticker(im, st, lt, bi)
        if cta: toon.paste_sticker(im, st, lt, 0)
        num = number_of(beats[bi])
        if num: toon.badge(im, num, lt)
        if lt < 0.1: im = Image.blend(im, Image.new("RGBA", (W, H), (255, 255, 255, 255)), 0.30 * (1 - lt / 0.1))
        g = next((x for x in groups if x["t0"] <= t < x["t1"]), None)
        if g:
            act = next((i for i, (x0, x1) in enumerate(g["times"]) if x0 - 0.02 <= t < x1 + 0.02), len(g["words"]) - 1 if t >= g["times"][-1][1] else 0)
            scl = 0.86 + 0.14 * min(1, (t - g["t0"]) * FPS / 5) if (t - g["t0"]) * FPS < 5 else 1.0
            key = (id(g), act, round(scl, 2))
            if key not in cache: cache[key] = caption_fn(g, act, scl)
            im.alpha_composite(cache[key], (0, 1440))
        pr.stdin.write(im.convert("RGB").tobytes())
    pr.stdin.close(); pr.wait()
    if pr.returncode != 0: raise RuntimeError("ffmpeg failed")
