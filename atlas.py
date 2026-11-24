"""Low-Poly Atlas video engine for TruFact.
Story (places with lat/lon, dates, counter, English captions) + Hindi voice timing  ->  one HTML page (template_atlas.html)
-> headless Chrome renders every frame (window.seek) and the sound score (SFX.render) -> ffmpeg mux with the Hindi voice."""
import os, re, json, math, subprocess, glob, time, base64, shutil
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template_atlas.html")
FPS = 30

# ------------------------------------------------------------------ geography -> stylised map
def project(route, extra):
    """lat/lon -> scene x,z. The map is rotated so the march runs away from the camera (up the phone screen); never a traced map."""
    pts = [(p["lat"], p["lon"]) for p in route] + [(p["lat"], p["lon"]) for r in extra for p in r["points"]]
    lat0 = sum(p[0] for p in pts) / len(pts); lon0 = sum(p[1] for p in pts) / len(pts); kx = math.cos(math.radians(lat0))
    def xy(lat, lon): return ((lon - lon0) * kx, -(lat - lat0))               # x = east, z = -north (north up)
    a, b = xy(route[0]["lat"], route[0]["lon"]), xy(route[-1]["lat"], route[-1]["lon"])
    far = max(route, key=lambda p: math.hypot(xy(p["lat"], p["lon"])[0] - a[0], xy(p["lat"], p["lon"])[1] - a[1]))
    b = xy(far["lat"], far["lon"]); d = (b[0] - a[0], b[1] - a[1])
    ang = math.atan2(-1, 0) - math.atan2(d[1], d[0]); ca, sa = math.cos(ang), math.sin(ang)
    def rot(p): return (p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca)
    allr = [rot(xy(la, lo)) for la, lo in pts]
    xs = [p[0] for p in allr]; zs = [p[1] for p in allr]
    wx = max(max(xs) - min(xs), 1e-6); wz = max(max(zs) - min(zs), 1e-6)
    s = min(12.5 / wz, 8.0 / wx); cx = (max(xs) + min(xs)) / 2; cz = (max(zs) + min(zs)) / 2
    def sc(la, lo):
        x, z = rot(xy(la, lo)); return round((x - cx) * s, 3), round((z - cz) * s, 3)
    for p in route: p["x"], p["z"] = sc(p["lat"], p["lon"])
    for r in extra:
        for p in r["points"]: p["x"], p["z"] = sc(p["lat"], p["lon"])
    return route, extra

# ------------------------------------------------------------------ captions
def caption_groups(text, t0, t1, maxc=26):
    words = text.split(); groups, cur = [], []
    for w in words:
        if cur and (len(" ".join(cur + [w])) > maxc or len(cur) >= 4): groups.append(cur); cur = []
        cur.append(w)
    if cur: groups.append(cur)
    tot = sum(len(" ".join(g)) + 3 for g in groups); out, t = [], t0
    for g in groups:
        d = (t1 - t0) * (len(" ".join(g)) + 3) / tot; out.append([round(t, 3), round(t + d, 3), " ".join(g)]); t += d
    return out

# ------------------------------------------------------------------ story
def make_story(script, starts, speech, total, brand="TruFact"):
    """script: the model's JSON (beats with english, geo fields). starts/speech: per beat (7 story beats + 1 follow card)."""
    route = [dict(p) for p in script["route"]]; extra = [dict(r, points=[dict(q) for q in r["points"]]) for r in (script.get("extra") or [])][:2]
    route, extra = project(route, extra)
    n = len(starts); s = starts; sp = speech
    cnt = script["counter"]; val = float(cnt["value"])
    step = 1 if val < 60 else 5 if val < 600 else 50 if val < 6000 else 500 if val < 60000 else 5000
    tick = max(step, int(val / 14 // step * step) or step)
    tl = {"D": round(total, 3), "title": [0.3, 0.55], "date": 1.0,
          "route": [round(s[1] + 0.4, 3), round(s[5] - 0.2, 3)],
          "extra": [[round(s[5] + 0.2 + 1.6 * i, 3), round(s[5] + 1.9 + 1.6 * i, 3)] for i in range(len(extra))],
          "count": [round(s[5] + 0.3, 3), round(s[5] + max(1.4, min(2.4, sp[5] - 0.5)), 3)],
          "take": [round(s[6] + 0.1, 3), round(s[6] + 0.7, 3)], "brand": round(s[7], 3)}
    caps = []
    for i, b in enumerate(script["beats"]): caps += caption_groups(b["english"], s[i] + 0.02, s[i] + sp[i] - 0.02)
    caps += caption_groups(f"Follow {brand} for a new story every day", s[7] + 0.02, s[7] + sp[7] - 0.02)
    clean = lambda t, m: str(t).strip()[:m]
    story = {"seed": int(script.get("seed", 7)), "title": [clean(script["title_lines"][0], 16), clean(script["title_lines"][1], 16)],
             "date_chip": clean(script["date_chip"], 32).upper(), "arrow_label": clean(script.get("arrow_label", ""), 26).upper(), "brand": brand,
             "route": [{"name": clean(p["name"], 16).upper(), "date": clean(p.get("date", ""), 16).upper(), "x": p["x"], "z": p["z"]} for p in route],
             "extra": [{"points": [{"x": q["x"], "z": q["z"]} for q in r["points"]]} for r in extra],
             "counter": {"value": val, "unit": clean(cnt["unit"], 10), "label": clean(cnt["label"], 30).upper(), "about": bool(cnt.get("about", True)), "step": step, "tickEvery": tick},
             "take": [clean(script["take_lines"][0], 20), clean(script["take_lines"][1], 20)], "tl": tl, "caps": caps,
             "cam": {"z": -1.0, "r": 17.5, "h": 13.0, "back": 1.5}}
    return story

def write_page(story, outdir):
    os.makedirs(outdir, exist_ok=True)
    html = open(TEMPLATE, encoding="utf-8").read().replace("/*__STORY__*/null", json.dumps(story, ensure_ascii=False))
    p = os.path.join(outdir, "index.html"); open(p, "w", encoding="utf-8").write(html); return p

# ------------------------------------------------------------------ render
def run_node(args, cwd, env=None, check=True):
    return subprocess.run(["node", "atlas_render.mjs"] + args, cwd=cwd, env=dict(os.environ, **(env or {})), check=check)

def render_video(story, web_dir, work, voice_wav, out_mp4, procs=3, quality="0.92", log=print):
    """web_dir holds lib/three.min.js and fonts/ (see workflow step). work = scratch dir."""
    os.makedirs(work, exist_ok=True); page = write_page(story, web_dir)
    sj = os.path.join(work, "story.json"); json.dump(story, open(sj, "w"), ensure_ascii=False)
    total = int(round(story["tl"]["D"] * FPS)); frames = os.path.join(work, "frames"); os.makedirs(frames, exist_ok=True)
    node_dir = os.path.dirname(os.path.abspath(web_dir)); env = {"WEB": os.path.abspath(web_dir)}
    t0 = time.time()
    for attempt in range(2):
        ps = [subprocess.Popen(["node", "atlas_render.mjs", "frames", os.path.abspath(frames), f"{k}-{total - 1}", str(procs), quality], cwd=node_dir, env=dict(os.environ, **env, RESUME="1")) for k in range(procs)]
        codes = [p.wait() for p in ps]; have = len(glob.glob(os.path.join(frames, "f*.jpg")))
        log(f"  atlas frames pass {attempt + 1}: exit {codes}, {have}/{total}, {time.time() - t0:.0f}s")
        if have >= total: break
    else: raise RuntimeError(f"atlas render incomplete: {have}/{total}")
    fx = os.path.join(work, "fx.raw"); subprocess.run(["node", "atlas_render.mjs", "fx", fx], cwd=node_dir, env=dict(os.environ, **env), check=True)
    raw = np.fromfile(fx, dtype="<i2").astype(np.float32) / 32768.0; fxw = os.path.join(work, "fx.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", fx, fxw], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "f%04d.jpg"), "-i", voice_wav, "-i", fxw,
                    "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.0[v];[2:a]volume=0.9[f];[v][f]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", "-r", str(FPS), "-t", f"{story['tl']['D']:.3f}", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_mp4], check=True)
    return out_mp4
