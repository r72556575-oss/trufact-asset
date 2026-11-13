"""2D cartoon scene engine used by generate.py.

Each beat is an animated cartoon scene: colourful gradient + spinning sunburst rays + floating confetti,
a cut-out "sticker" of the beat's subject that pops in and floats, a number badge, and a host character
(a cartoon boy) whose mouth follows the voice, who blinks, bobs, points and cheers.
"""
import math, random, subprocess, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from scipy import ndimage

W, H, FPS = 1080, 1920, 30
INK = (22, 16, 15)
FONT_CANDS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
FONT_PATH = next((p for p in FONT_CANDS if os.path.exists(p)), None)
def font(n): return ImageFont.truetype(FONT_PATH, int(n)) if FONT_PATH else ImageFont.load_default()
def ease(t): t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)
def over(t, k=1.7):
    t = max(0.0, min(1.0, t)); return 1 + (k + 1) * (t - 1) ** 3 + k * (t - 1) ** 2

# ------------------------------------------------------------------ stickers (cut-outs)
def make_sticker(img, maxside=720):
    """RGB subject on a (near) white background -> RGBA sticker with white + ink outline. None if the cut-out looks wrong."""
    img = img.convert("RGB")
    if max(img.size) > 800: img = ImageOps.contain(img, (800, 800), Image.LANCZOS)
    a = np.asarray(img).astype(np.int16)
    near_white = a.min(axis=2) > 232
    lab, n = ndimage.label(near_white)
    if n == 0: return None
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])); border = border[border > 0]
    bg = np.isin(lab, border); fg = ~bg
    frac = fg.mean()
    if frac < 0.04 or frac > 0.80: return None
    lab2, n2 = ndimage.label(fg)
    sizes = ndimage.sum(fg, lab2, range(1, n2 + 1))
    fg = np.isin(lab2, [i + 1 for i, s in enumerate(sizes) if s >= 0.10 * sizes.max()])
    fg = ndimage.binary_fill_holes(ndimage.binary_closing(fg, iterations=2))
    alpha = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.3))
    alpha = alpha.point(lambda v: 255 if v > 150 else (0 if v < 70 else int((v - 70) * 255 / 80)))
    bbox = alpha.getbbox()
    if not bbox: return None
    rgba = img.convert("RGBA"); rgba.putalpha(alpha); rgba = rgba.crop(bbox)
    pad = 34; size = (rgba.width + 2 * pad, rgba.height + 2 * pad)
    base = Image.new("RGBA", size, (0, 0, 0, 0)); base.paste(rgba, (pad, pad), rgba)
    m = base.split()[3]
    white = m.filter(ImageFilter.GaussianBlur(8)).point(lambda v: 255 if v > 14 else 0).filter(ImageFilter.GaussianBlur(1.2))
    ink = m.filter(ImageFilter.GaussianBlur(13)).point(lambda v: 255 if v > 14 else 0).filter(ImageFilter.GaussianBlur(1.2))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", size, INK + (255,)), (0, 0), ink)
    out.paste(Image.new("RGBA", size, (255, 255, 255, 255)), (0, 0), white)
    out.alpha_composite(base)
    s = maxside / max(out.size)
    return out.resize((int(out.width * s), int(out.height * s)), Image.LANCZOS)

def make_card(img, maxside=820):
    """fallback: the picture itself as a framed cartoon card"""
    im = ImageOps.contain(img.convert("RGB"), (maxside, maxside), Image.LANCZOS)
    pad = 22; size = (im.width + 2 * pad, im.height + 2 * pad)
    out = Image.new("RGBA", size, (0, 0, 0, 0)); d = ImageDraw.Draw(out)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], 46, fill=INK + (255,))
    d.rounded_rectangle([8, 8, size[0] - 9, size[1] - 9], 40, fill=(255, 255, 255, 255))
    m = Image.new("L", im.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], 26, fill=255)
    out.paste(im, (pad, pad), m)
    return out

def sticker_or_card(img):
    s = None
    try: s = make_sticker(img)
    except Exception as e: print("  cutout error:", e, flush=True)
    return (s, "sticker") if s is not None else (make_card(img), "card")

def cta_sticker(channel):
    im = Image.new("RGBA", (860, 640), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 40, 859, 420], 80, fill=INK + (255,)); d.rounded_rectangle([10, 50, 849, 410], 72, fill=(255, 226, 70, 255))
    d.text((430, 232), channel, font=font(210 if len(channel) <= 8 else 150), fill=(255, 255, 255, 255), anchor="mm", stroke_width=14, stroke_fill=INK)
    d.rounded_rectangle([190, 470, 670, 610], 70, fill=INK + (255,)); d.rounded_rectangle([198, 478, 662, 602], 64, fill=(235, 40, 40, 255))
    d.text((430, 540), "FOLLOW", font=font(86), fill=(255, 255, 255, 255), anchor="mm")
    return im

# ------------------------------------------------------------------ host character
SK, HAIR, SHIRT = (255, 210, 165), (46, 34, 32), (255, 112, 67)

def mascot(t, lt, amp, point=0.0, cheer=0.0, blink=False):
    """returns RGBA 380x470 of the host (drawn at 2x then downsampled)"""
    S = 2; im = Image.new("RGBA", (380 * S, 470 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    def E(cx, cy, rx, ry, fill, w=6, outline=INK): d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill, outline=outline if w else None, width=w * S)
    def L(pts, w, col): d.line([(x * S, y * S) for x, y in pts], fill=col, width=int(w * S), joint="curve")
    bob = 4 * math.sin(t * 5.0); head_y = 200 + bob
    # arms (behind body)
    wave = math.sin(t * 7.5)
    lh = (52 + 6 * wave, 392 - 70 * cheer + 10 * wave - 55 * cheer * abs(wave))
    rp = ease(point)
    rh = (336 + 10 * rp + 14 * cheer, 404 - 150 * rp - 160 * cheer + 10 * wave * cheer)
    for sh, hd in (((122, 340), lh), ((262, 340), rh)):
        L([sh, hd], 30, INK); L([sh, hd], 19, SHIRT)
        E(hd[0], hd[1], 19, 19, SK, 6)
    # body
    d.rounded_rectangle([102 * S, (318 + bob) * S, 282 * S, 462 * S], 46 * S, fill=SHIRT, outline=INK, width=6 * S)
    d.polygon([(165 * S, (322 + bob) * S), (192 * S, (352 + bob) * S), (219 * S, (322 + bob) * S)], fill=(255, 255, 255), outline=INK)
    E(192, 330 + bob, 12, 8, SK, 0)
    # head
    E(86, head_y + 6, 21, 24, SK, 6); E(298, head_y + 6, 21, 24, SK, 6)
    E(192, head_y, 108, 100, SK, 7)
    d.pieslice([84 * S, (head_y - 108) * S, 300 * S, (head_y + 96) * S], 182, 358, fill=HAIR, outline=INK, width=7 * S)
    for k, (x0, x1) in enumerate(((110, 160), (150, 205), (195, 250))):
        d.polygon([(x0 * S, (head_y - 62) * S), ((x0 + x1) / 2 * S, (head_y - 22) * S), (x1 * S, (head_y - 66) * S)], fill=HAIR)
    d.arc([84 * S, (head_y - 108) * S, 300 * S, (head_y + 96) * S], 182, 358, fill=INK, width=7 * S)
    # face
    look = 6 + 2 * math.sin(t * 1.3)
    for ex in (150, 234):
        if blink: L([(ex - 20, head_y + 8), (ex + 20, head_y + 8)], 6, INK)
        else:
            E(ex, head_y + 6, 25, 29, (255, 255, 255), 5)
            E(ex + look, head_y + 10, 12, 15, INK, 0); E(ex + look + 4, head_y + 4, 4, 4, (255, 255, 255), 0)
        L([(ex - 22, head_y - 34 - 8 * amp - 8 * cheer), (ex + 22, head_y - 40 - 8 * amp - 8 * cheer + (4 if ex > 190 else -4))], 6, HAIR)
    E(124, head_y + 48, 17, 10, (255, 150, 150), 0); E(260, head_y + 48, 17, 10, (255, 150, 150), 0)
    my = head_y + 60
    if amp > 0.07 or cheer:
        mh = 6 + 26 * max(amp, 0.45 if cheer else 0)
        E(192, my + mh * 0.35, 27, mh, (120, 28, 38), 5)
        d.pieslice([(192 - 17) * S, (my + mh * 0.35 + mh * 0.2) * S, (192 + 17) * S, (my + mh * 0.35 + mh * 1.05) * S], 0, 180, fill=(235, 96, 110))
    else:
        d.arc([(192 - 28) * S, (my - 18) * S, (192 + 28) * S, (my + 16) * S], 15, 165, fill=INK, width=6 * S)
    return im.resize((380, 470), Image.LANCZOS)

# ------------------------------------------------------------------ backgrounds
PALETTES = [((255, 207, 94), (255, 128, 66)), ((124, 208, 255), (86, 112, 255)), ((255, 150, 176), (186, 86, 204)),
            ((140, 232, 176), (36, 156, 148)), ((255, 192, 96), (232, 84, 96)), ((176, 164, 255), (86, 98, 222)),
            ((255, 226, 122), (118, 200, 122)), ((255, 170, 104), (176, 70, 122))]

def gradient(c1, c2):
    t = np.linspace(0, 1, H)[:, None, None]
    return Image.fromarray((np.array(c1) * (1 - t) + np.array(c2) * t * np.ones((1, W, 1))).astype(np.uint8)).convert("RGBA")

def confetti_items(seed):
    r = random.Random(seed)
    return [dict(x=r.uniform(0, W), y=r.uniform(0, H), vy=r.uniform(-60, -25), sw=r.uniform(15, 40), size=r.uniform(14, 34),
                 kind=r.choice(("c", "s", "p")), col=r.choice(((255, 255, 255), (255, 240, 140), (255, 180, 200), (170, 230, 255))), ph=r.uniform(0, 6.28)) for _ in range(18)]

def draw_confetti(d, items, t):
    for it in items:
        x = (it["x"] + it["sw"] * math.sin(t * 1.4 + it["ph"])) % W; y = (it["y"] + it["vy"] * t) % H; s = it["size"]
        if it["kind"] == "c": d.ellipse([x - s / 2, y - s / 2, x + s / 2, y + s / 2], fill=it["col"] + (150,))
        elif it["kind"] == "s": d.polygon([(x, y - s), (x + s * .3, y - s * .3), (x + s, y), (x + s * .3, y + s * .3), (x, y + s), (x - s * .3, y + s * .3), (x - s, y), (x - s * .3, y - s * .3)], fill=it["col"] + (170,))
        else: d.rectangle([x - s / 2, y - s / 7, x + s / 2, y + s / 7], fill=it["col"] + (150,)); d.rectangle([x - s / 7, y - s / 2, x + s / 7, y + s / 2], fill=it["col"] + (150,))

def rays_overlay(t, cx=580, cy=600, n=18):
    sm = Image.new("RGBA", (W // 2, H // 2), (0, 0, 0, 0)); d = ImageDraw.Draw(sm); R = 2400
    for k in range(n):
        a0 = math.radians(t * 7 + 360 * k / n); a1 = a0 + math.pi / n
        d.polygon([(cx / 2, cy / 2), (cx / 2 + R * math.cos(a0), cy / 2 + R * math.sin(a0)), (cx / 2 + R * math.cos(a1), cy / 2 + R * math.sin(a1))], fill=(255, 255, 255, 48))
    return sm.resize((W, H), Image.BILINEAR)

# ------------------------------------------------------------------ scene compositing
def paste_sticker(im, st, lt, bi):
    pop = over(lt / 0.5, 1.7); kind = bi % 4
    slide = (1 - ease(lt / 0.55)) * 950
    dx = {1: -slide, 2: slide}.get(kind, 0); dy = {3: slide}.get(kind, 0)
    sc = max(pop, 0.001) * (1 + 0.018 * math.sin(lt * 3.1))
    tilt = (-4 if bi % 2 else 4) * (1 - ease(lt / 0.6)) + 3.0 * math.sin(lt * 1.9 + bi)
    w, h = max(2, int(st.width * sc)), max(2, int(st.height * sc))
    s = st.resize((w, h), Image.BILINEAR).rotate(tilt, expand=True, resample=Image.BICUBIC)
    cx, cy = 585 + dx, 520 + dy + 12 * math.sin(lt * 2.4)
    sh = Image.new("RGBA", (s.width, 90), (0, 0, 0, 0)); ImageDraw.Draw(sh).ellipse([s.width * .15, 20, s.width * .85, 70], fill=(0, 0, 0, 70))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), (int(cx - s.width / 2), int(cy + st.height * sc / 2 - 40)))
    im.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2)))

def badge(im, text, lt):
    e = over((lt - 0.35) / 0.35, 2.2)
    if e <= 0.02: return
    r = int(118 * e); cx, cy = 888, 250 + 8 * math.sin(lt * 4)
    lay = Image.new("RGBA", (300, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.ellipse([150 - r, 150 - r, 150 + r, 150 + r], fill=INK + (255,)); d.ellipse([150 - r + 9, 150 - r + 9, 150 + r - 9, 150 + r - 9], fill=(255, 226, 70, 255))
    size = 96 if len(text) <= 3 else (72 if len(text) <= 5 else 52)
    d.text((150, 154), text, font=font(size * e), fill=(34, 24, 24, 255), anchor="mm")
    lay = lay.rotate(8 * math.sin(lt * 5), resample=Image.BICUBIC)
    im.alpha_composite(lay, (int(cx - 150), int(cy - 150)))

def render(out_path, audio_path, stickers, beats, starts, durs, total_sec, amp, groups, caption_fn, number_of, brand_idx):
    bgs = [gradient(*PALETTES[i % len(PALETTES)]) for i in range(len(beats))]
    conf = [confetti_items(i * 17 + 3) for i in range(len(beats))]
    shade = np.zeros((H, W, 4), np.uint8); ramp = np.clip((np.arange(H) - H * 0.60) / (H * 0.40), 0, 1) ** 1.4 * 150
    shade[..., 3] = ramp[:, None].astype(np.uint8); shade = Image.fromarray(shade, "RGBA")
    cache = {}
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-ar", "44100", "-t", f"{total_sec:.3f}", "-movflags", "+faststart", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(total_sec * FPS)):
        t = f / FPS
        bi = max(i for i in range(len(beats)) if starts[i] <= t + 1e-6); lt = t - starts[bi]
        im = bgs[bi].copy(); im.alpha_composite(rays_overlay(t))
        draw_confetti(ImageDraw.Draw(im), conf[bi], t)
        paste_sticker(im, stickers[bi], lt, bi)
        num = number_of(beats[bi])
        if num: badge(im, num, lt)
        a = float(amp[min(f, len(amp) - 1)])
        cta = (bi == brand_idx)
        mm = mascot(t, lt, a, point=(1.0 if (0.3 < lt < 1.6 and not cta) else 0.0), cheer=(1.0 if cta else 0.0), blink=((f + bi * 7) % 96) in (0, 1, 2))
        sy = 1 - 0.07 * max(0.0, 1 - lt / 0.18)
        mm = mm.resize((475, int(588 * sy)), Image.BILINEAR)
        im.alpha_composite(mm, (6, 1450 - mm.height))
        im.alpha_composite(shade)
        if lt < 0.1: im = Image.blend(im, Image.new("RGBA", (W, H), (255, 255, 255, 255)), 0.30 * (1 - lt / 0.1))
        g = next((x for x in groups if x["t0"] <= t < x["t1"]), None)
        if g:
            act = next((i for i, (x0, x1) in enumerate(g["times"]) if x0 - 0.02 <= t < x1 + 0.02), len(g["words"]) - 1 if t >= g["times"][-1][1] else 0)
            sc = 0.86 + 0.14 * min(1, (t - g["t0"]) * FPS / 5) if (t - g["t0"]) * FPS < 5 else 1.0
            key = (id(g), act, round(sc, 2))
            if key not in cache: cache[key] = caption_fn(g, act, sc)
            im.alpha_composite(cache[key], (0, 1440))
        pr.stdin.write(im.convert("RGB").tobytes())
    pr.stdin.close(); pr.wait()
    if pr.returncode != 0: raise RuntimeError("ffmpeg failed")
