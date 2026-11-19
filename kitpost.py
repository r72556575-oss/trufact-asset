"""Kit engine glue: render the 3D/2D cartoon frames (several parallel processes), then add the picture panel,
captions and the Follow card, and encode with the mixed audio."""
import os, math, subprocess, time, glob, json
from PIL import Image, ImageDraw, ImageFilter, ImageOps
import toon
from toon import ease, over, font, INK, W, H, FPS

def render_frames(engine_dir, storyboard, frames_dir, total, procs=4, step=2, quality="0.9"):
    os.makedirs(frames_dir, exist_ok=True)
    env = dict(os.environ, STORYBOARD=os.path.abspath(storyboard), RESUME="1")
    stride = step * procs
    t0 = time.time()
    for attempt in range(2):                                   # second pass fills in anything a crashed process missed (RESUME skips done frames)
        ps = [subprocess.Popen(["node", "render.mjs", os.path.abspath(frames_dir), f"{step * k}-{total - 1}", str(stride), quality], cwd=engine_dir, env=env) for k in range(procs)]
        codes = [p.wait() for p in ps]
        have = len(glob.glob(os.path.join(frames_dir, "f*.jpg"))); want = len(range(0, total, step))
        print(f"  render pass {attempt + 1}: exit codes {codes}, frames {have}/{want}, {time.time() - t0:.0f}s", flush=True)
        if have >= want: return
    raise RuntimeError(f"kit render incomplete: {have}/{want} frames")

def frame_file(frames_dir, f, step):
    g = f - (f % step)
    while g > 0 and not os.path.exists(os.path.join(frames_dir, f"f{g:04d}.jpg")): g -= step
    return os.path.join(frames_dir, f"f{g:04d}.jpg")

def make_panel(img, tag):
    """framed picture card for the top of the screen (like the comic panel in the Roman video)"""
    pw, ph = 800, 540
    pic = ImageOps.fit(img.convert("RGB"), (pw, ph), Image.LANCZOS)
    pad = 20; card = Image.new("RGBA", (pw + 2 * pad + 20, ph + 2 * pad + 20), (0, 0, 0, 0)); d = ImageDraw.Draw(card)
    d.rounded_rectangle([10, 10, card.width - 11, card.height - 11], 40, fill=INK + (255,))
    d.rounded_rectangle([20, 20, card.width - 21, card.height - 21], 32, fill=(255, 255, 255, 255))
    m = Image.new("L", pic.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, pw - 1, ph - 1], 22, fill=255)
    card.paste(pic, (10 + pad, 10 + pad), m)
    if tag:
        f = font(46); w = f.getlength(tag) + 70
        d.polygon([(40, 0), (40 + w, 0), (40 + w - 24, 40), (40 + w, 80), (40, 80)], fill=(255, 213, 72, 255), outline=INK)
        d.line([(40, 0), (40 + w, 0), (40 + w - 24, 40), (40 + w, 80), (40, 80), (40, 0)], fill=INK, width=7)
        d.text((40 + w / 2 - 6, 41), tag, font=f, fill=INK, anchor="mm")
    sh = Image.new("RGBA", (card.width + 60, card.height + 60), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle([30, 44, card.width + 28, card.height + 40], 44, fill=(0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(12)); sh.alpha_composite(card, (30, 20)); return sh

def paste_panel(im, panel, lt, dur, idx):
    e = over(lt / 0.45, 1.7); out = max(0.0, min(1.0, (dur - lt) / 0.3))
    sc = max(0.02, e * (0.55 + 0.45 * ease(out)))
    if sc < 0.03: return
    ang = (-2.0 if idx % 2 else 2.0) * (1 - ease(lt / 0.6)) + 1.2 * math.sin(lt * 1.6)
    p = panel.resize((max(2, int(panel.width * sc)), max(2, int(panel.height * sc))), Image.BILINEAR).rotate(ang, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(p, (int((W - p.width) / 2), int(110 + (panel.height - p.height) / 2 * 0.6)))

def compose(frames_dir, out_path, audio_path, total, step, beats, panels, groups, caption_fn, brand_idx, channel):
    cta = toon.cta_sticker(channel); cache = {}
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-ar", "44100", "-t", f"{total / FPS:.3f}", "-movflags", "+faststart", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last_path, last_im = None, None
    for f in range(total):
        t = f / FPS
        bi = max(i for i in range(len(beats)) if beats[i]["a"] <= f); b = beats[bi]; lt = (f - b["a"]) / FPS; dur = (b["b"] - b["a"] + 1) / FPS
        path = frame_file(frames_dir, f, step)
        if path != last_path: last_im = Image.open(path).convert("RGBA"); last_path = path
        im = last_im.copy()
        pn = panels.get(bi)
        if pn is not None: paste_panel(im, pn, lt, dur, bi)
        if bi == brand_idx:
            try: toon.paste_sticker(im, cta, lt, 0)
            except Exception: pass
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
