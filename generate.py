#!/usr/bin/env python3
"""TruFact daily Short generator.

Hindi boy voice (Gemini TTS) + English captions + 2D cartoon pictures (Gemini image) with motion,
synthesized background music and sound effects, ~45 s vertical video, scheduled on YouTube for 07:00 IST.
Runs on GitHub Actions (see .github/workflows/daily.yml). Nothing needs to be typed by a human.
"""
import os, sys, json, math, base64, time, random, wave, subprocess, datetime, re, asyncio
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import toon, scenes

# ----------------------------------------------------------------------------- config
SR = 24000
W, H, FPS = 1080, 1920, 30
OFFLINE = os.environ.get("OFFLINE_TEST") == "1"          # local test mode: no network
OUT = os.environ.get("OUT_DIR", "out")
HIST = "history.json"
GKEY = os.environ.get("GEMINI_API_KEY", "")
TEXT_MODELS = [os.environ.get("GEMINI_TEXT_MODEL", "gemini-flash-latest"), "gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-2.5-flash"]
TTS_MODELS = [os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"), "gemini-2.5-flash-preview-tts"]
IMG_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
VOICE = os.environ.get("GEMINI_VOICE", "Puck")           # boy voice
TARGET_SEC = float(os.environ.get("TARGET_SEC", "45"))
PUBLISH_HOUR_IST, PUBLISH_MIN_IST = 7, 0
CHANNEL = "TruFact"
CATEGORIES = ["Space", "History", "Human body", "Animals", "Chemistry and everyday science", "Technology",
              "Earth and nature", "Psychology and the brain", "Ancient engineering", "Oceans"]
FONT_CANDS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
FONT_PATH = next((p for p in FONT_CANDS if os.path.exists(p)), None)
INK = (22, 16, 15)

def log(*a): print(*a, flush=True)
def font(n): return ImageFont.truetype(FONT_PATH, int(n)) if FONT_PATH else ImageFont.load_default()
def ease(t): t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)

# ----------------------------------------------------------------------------- Gemini REST helpers
def gemini(model, body, tries=5):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    wait = 15
    for k in range(tries):
        try:
            r = requests.post(url, headers={"x-goog-api-key": GKEY, "Content-Type": "application/json"}, json=body, timeout=120)
        except requests.RequestException as e:
            log(f"  [{model}] network error: {e}"); r = None
        if r is not None and r.status_code == 200:
            return r.json()
        if r is not None:
            log(f"  [{model}] HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code in (400, 401, 403, 404): break          # not retryable
            if r.status_code == 429 and 'PerDay' in r.text: break    # daily quota is gone: retrying is pointless
        time.sleep(wait); wait = min(wait * 2, 120)
    raise RuntimeError(f"Gemini call failed: {model}")

def gemini_text(body):
    """try several text models in turn (503 'high demand' on one model is common)"""
    last = None
    for m in TEXT_MODELS:
        try: return gemini(m, body, tries=3)
        except Exception as e: last = e; log(f"  text model {m} unavailable, trying next")
    raise RuntimeError(f"all text models failed: {last}")

def parts_of(resp):
    try: return resp["candidates"][0]["content"]["parts"]
    except Exception: return []

def text_of(resp): return "".join(p.get("text", "") for p in parts_of(resp))

def inline_of(resp):
    for p in parts_of(resp):
        d = p.get("inlineData") or p.get("inline_data")
        if d and d.get("data"): return base64.b64decode(d["data"]), (d.get("mimeType") or d.get("mime_type") or "")
    return None, ""

# ----------------------------------------------------------------------------- 1. topic + script
def load_history():
    try: return json.load(open(HIST))
    except Exception: return {"topics": []}

def wiki_extract(title):
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
                         "redirects": 1, "titles": title, "format": "json"}, headers={"User-Agent": "TruFactBot/1.0 (educational shorts)"}, timeout=30)
        pg = list(r.json()["query"]["pages"].values())[0]; ex = pg.get("extract", "") or ""
        if "may refer to" in ex[:400]: return None, None
        return pg.get("title", title), ex
    except Exception as e:
        log("  wiki error:", e); return None, None

def make_script(hist):
    today = datetime.date.today()
    cat = CATEGORIES[today.toordinal() % len(CATEGORIES)]
    used = [t["title"] for t in hist["topics"][-80:]]
    if OFFLINE: return offline_script()
    # step A: pick a topic that has a real Wikipedia article, then ground the script on that article only
    title, extract = None, None
    cj = text_of(gemini_text({"contents": [{"parts": [{"text":
        f"Suggest 8 different English Wikipedia article titles about surprising, well-documented, TRUE facts in the category '{cat}', "
        f"each good for an amazing 45-second story. Prefer topics about concrete, VISUAL things that are easy to draw as cartoons "
        f"(animals, plants, places, buildings, machines, space objects, inventions, food, historical objects). Avoid abstract topics "
        f"(medical syndromes, psychology effects, economics, laws) and avoid grim topics (deaths, disasters, crime). Do not use these used topics: {used}. "
        "Return a JSON list of exact Wikipedia article titles (strings) only."}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}}))
    log("candidate reply:", cj[:300].replace("\n", " "))
    try: cands = json.loads(re.sub(r"^```json|```$", "", cj.strip(), flags=re.M).strip())
    except Exception as e: log("  candidate JSON error:", e); cands = []
    if isinstance(cands, dict): cands = next((v for v in cands.values() if isinstance(v, list)), [])
    for t in cands:
        t = t if isinstance(t, str) else (t.get("title") if isinstance(t, dict) else str(t))
        title, extract = wiki_extract(str(t))
        log(f"  candidate {t!r} -> {title!r}, {len(extract or '')} chars")
        if extract and len(extract) >= 1500: break
        title, extract = None, None
    if not extract: raise RuntimeError("no usable Wikipedia topic found")
    research = f"Wikipedia article '{title}':\n{extract[:7500]}"
    log("topic:", title, "| extract chars:", len(extract))
    prompt = f"""You write a 45-second YouTube Short for the channel {CHANNEL}.
Use ONLY facts that are stated in this source text (do not add outside facts):
{research}

Return JSON with this exact shape:
{{"title": "<English title, max 60 chars, curiosity-driven, no clickbait lies>",
  "description": "<2-3 English sentences + 5 hashtags>",
  "tags": ["<8 short English tags>"],
  "beats": [ {{"hindi": "...", "english": "...", "image_prompt": "...", "sfx": "whoosh|pop|none",
               "setting": "village|city|mountains|ocean|desert|space|indoor", "time": "day|sunset|night",
               "camera": "push_in|pull_back|pan_left|pan_right|shake|static",
               "cast": [ {{"role": "boy|girl|scientist|elder|king|worker|explorer", "slot": "left|center|right", "expr": "neutral|happy|surprised|sad|angry|think|laugh", "action": "idle|talk|point|think|surprised|cheer|wave|sad|walk_in"}} ],
               "fx": "none|sparkles|exclamation|question|sweat|hearts|stars"}} ]}}

Rules:
- Exactly 7 beats = 7 short sentences, told as a story: hook, tension, reveal, explanation, closing punch. 
- "hindi": natural spoken Hindi in Devanagari for a young storyteller. Write ALL numbers and years as Hindi words (दो हज़ार, तेईस...). 
  English technical words must be written in Devanagari (क्विकलाइम). 8-17 words per beat; total 110-125 Hindi words. No emojis.
- "english": a faithful, natural English translation of that beat for captions, max 14 words, numbers as digits.
- "image_prompt": the ONE main SUBJECT to draw for that beat, as a short noun phrase of 4-12 English words (e.g. "a happy cartoon octopus with three hearts", "an ancient stone bridge", "a glowing full moon"). A single physical thing, no scene, no background, no abstract ideas, no text, no real people, no violence. Use a different subject for each beat.
- Scene fields: each beat is a tiny cartoon scene. Pick the "setting" that fits the story place (use the SAME setting for neighbouring beats of the same place), the "time" of day, a "camera" move, and 1-3 "cast" characters who ACT OUT / REACT to what the narrator says (surprised for a shock, think for a puzzle, cheer for success, point when something is shown, sad for a failure). Vary slots, roles, expressions and actions between beats; at most one "walk_in" per beat. "fx": exclamation for a surprise, question for a mystery, sparkles/stars for a wonder, hearts for love, sweat for worry, otherwise none.
- "sfx": "pop" if the beat has a key number, otherwise "whoosh" (use "none" at most once).
- Be accurate. Never invent facts that are not in the source text."""
    last = None
    for attempt in range(3):
        resp = gemini_text({"contents": [{"parts": [{"text": prompt}]}],
                                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}})
        try:
            s = json.loads(re.sub(r"^```json|```$", "", text_of(resp).strip(), flags=re.M).strip())
            assert len(s["beats"]) == 7 and all(b["hindi"] and b["english"] and b["image_prompt"] for b in s["beats"])
            assert re.search(r"[\u0900-\u097F]", s["beats"][0]["hindi"])
            return s
        except Exception as e:
            last = e; log("  script invalid, retrying:", e)
    raise RuntimeError(f"script generation failed: {last}")

def offline_script():
    H7 = ["रोमन इमारतें दो हज़ार साल बाद भी खड़ी हैं।", "जबकि आज का कंक्रीट, कुछ ही दशकों में टूटने लगता है।",
          "तो रोमनों का राज़ क्या था? वैज्ञानिकों ने दो हज़ार तेईस में इसका पता लगाया।",
          "रोमन लोग कंक्रीट में क्विकलाइम मिलाते थे, जो मिलाते समय गरम हो जाता है।",
          "इससे कंक्रीट के अंदर, छोटे छोटे सफ़ेद टुकड़े बन गए।",
          "जब दरार पड़ती है, तो पानी उन टुकड़ों तक पहुँचता है, वे घुलते हैं, और दरार को भर देते हैं।",
          "यानी कंक्रीट अपनी मरम्मत ख़ुद कर लेता है!"]
    E7 = ["Roman buildings are still standing after 2,000 years.", "Modern concrete can start crumbling in just decades.",
          "So what was the Romans' secret? Scientists found it in 2023.", "They mixed in quicklime, which heats up as it's mixed.",
          "That left tiny white chunks hidden inside.", "When a crack forms, water reaches those chunks, and they dissolve and fill the crack.",
          "The concrete literally repairs itself!"]
    SC = [dict(setting="village", time="day", camera="push_in", fx="sparkles", cast=[dict(role="elder", slot="left", expr="happy", action="talk"), dict(role="boy", slot="right", expr="surprised", action="point")]),
          dict(setting="city", time="sunset", camera="pan_left", fx="sweat", cast=[dict(role="worker", slot="center", expr="sad", action="sad")]),
          dict(setting="indoor", time="day", camera="pull_back", fx="question", cast=[dict(role="scientist", slot="left", expr="think", action="think"), dict(role="girl", slot="right", expr="neutral", action="idle")]),
          dict(setting="indoor", time="day", camera="push_in", fx="exclamation", cast=[dict(role="king", slot="center", expr="surprised", action="surprised")]),
          dict(setting="mountains", time="day", camera="pan_right", fx="none", cast=[dict(role="explorer", slot="left", expr="happy", action="walk_in"), dict(role="girl", slot="center", expr="happy", action="wave")]),
          dict(setting="ocean", time="sunset", camera="shake", fx="hearts", cast=[dict(role="boy", slot="center", expr="laugh", action="cheer")]),
          dict(setting="space", time="night", camera="pull_back", fx="stars", cast=[dict(role="scientist", slot="left", expr="laugh", action="cheer"), dict(role="worker", slot="right", expr="happy", action="cheer")])]
    return {"title": "Romans' Concrete HEALS ITSELF", "description": "Test.", "tags": ["test"],
            "beats": [dict(hindi=h, english=e, image_prompt=e, sfx="pop" if i in (2, 3) else "whoosh", **SC[i]) for i, (h, e) in enumerate(zip(H7, E7))]}

# ----------------------------------------------------------------------------- 2. voice
def read_wav(path):
    with wave.open(path) as w:
        sr = w.getframerate(); assert w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32), sr

def write_wav(path, x, sr=SR):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(np.clip(x, -32768, 32767).astype(np.int16).tobytes())

def tts(text):
    """returns float32 mono @24 kHz"""
    if OFFLINE: return offline_tts(text)
    prompt = ("Read the following Hindi text exactly as written, nothing added. Young male voice, energetic, curious, "
              "punchy storyteller for a YouTube Short, brisk pace, a short natural pause between sentences:\n\n" + text)
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    for model in TTS_MODELS:
        try:
            raw, mime = inline_of(gemini(model, body))
            if raw:
                m = re.search(r"rate=(\d+)", mime); sr = int(m.group(1)) if m else 24000
                x = np.frombuffer(raw, np.int16).astype(np.float32)
                if sr != SR: x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * SR / sr)), np.arange(len(x)), x)
                return x
        except Exception as e:
            log(f"  TTS model {model} failed: {e}")
    raise RuntimeError("TTS failed on all models")

def offline_tts(text):
    from piper import PiperVoice
    d = "/home/claude/tts/vits-piper-hi_IN-pratham-medium"
    v = PiperVoice.load(f"{d}/hi_IN-pratham-medium.onnx", config_path=f"{d}/hi_IN-pratham-medium.onnx.json")
    tmp = os.path.join(OUT, "_tts.wav")
    with wave.open(tmp, "wb") as w: v.synthesize_wav(text, w)
    x, sr = read_wav(tmp)
    return np.interp(np.linspace(0, len(x) - 1, int(len(x) * SR / sr)), np.arange(len(x)), x)

def trim(x, lead=0.03, tail=0.08):
    idx = np.where(np.abs(x) > 0.02 * 32768)[0]
    if len(idx) == 0: return x
    return x[max(idx[0] - int(lead * SR), 0): idx[-1] + int(tail * SR)]

def split_two(x):
    """split a 2-sentence recording at its longest silence (middle 30-70%). None if no clear gap."""
    win = int(0.01 * SR); n = len(x) // win
    rms = np.sqrt(np.mean(x[:n * win].reshape(n, win) ** 2, axis=1)); quiet = rms < 0.018 * 32768
    best, cur = (0, None), None
    for i in range(int(0.25 * n), int(0.75 * n)):
        if quiet[i]:
            cur = (cur[0], i) if cur else (i, i)
            if cur[1] - cur[0] + 1 > best[0]: best = (cur[1] - cur[0] + 1, cur)
        else: cur = None
    if best[0] < 12 or best[1] is None: return None            # < 120 ms gap
    mid = (best[1][0] + best[1][1]) // 2 * win
    return x[:mid], x[mid:]

def build_voice(beats):
    """beats: list of 8 dicts (7 story + CTA). TTS 2 beats per call (4 calls/day) and split at the pause."""
    segs = []
    for i in range(0, len(beats), 2):
        a, b = beats[i], beats[i + 1]
        x = trim(tts(a["hindi"] + " " + b["hindi"]))
        parts = split_two(x)
        if parts is None:
            log(f"  no clean split for beats {i+1}-{i+2}; speaking them separately")
            parts = (trim(tts(a["hindi"])), trim(tts(b["hindi"])))
        segs += [trim(parts[0]), trim(parts[1])]
    return segs

# ----------------------------------------------------------------------------- 3. pictures
def card(title, sub="", seed=0):
    rnd = random.Random(seed)
    c1 = rnd.choice([(255, 190, 70), (120, 200, 255), (255, 130, 120), (150, 225, 160)])
    c2 = (30, 30, 70)
    im = Image.new("RGB", (W, H)); px = np.zeros((H, W, 3), np.float32)
    t = np.linspace(0, 1, H)[:, None, None]
    px[:] = np.array(c1) * (1 - t) + np.array(c2) * t
    im = Image.fromarray(px.astype(np.uint8)); d = ImageDraw.Draw(im)
    for _ in range(14):
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(60, 220)
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255), width=6)
    if title: d.text((W // 2, H // 2 - 200), title, font=font(190), fill=(255, 255, 255), anchor="mm", stroke_width=12, stroke_fill=INK)
    return im

STYLE_TAIL = ("flat 2D cartoon sticker illustration of this single subject, bold black outlines, bright cheerful colors, cute friendly style, "
              "centered, isolated on a plain pure white background, no scenery, no ground, no shadow, no text, no letters, no watermark")
def style_prompt(prompt): return f"{prompt.strip()}. {STYLE_TAIL}"

IMG_PROVIDERS = os.environ.get("IMG_PROVIDERS", "gemini,pollinations").split(",")
_gemini_img_ok = True

_last_poll = [0.0]

def pollinations(prompt):
    """Free anonymous service: it answers HTTP 402/429 if called too often, so keep >=35 s between requests."""
    import io, urllib.parse
    q = urllib.parse.quote(style_prompt(prompt)[:700])
    for k in range(6):
        wait = 36 - (time.time() - _last_poll[0])
        if wait > 0: time.sleep(wait)
        _last_poll[0] = time.time()
        try:
            r = requests.get(f"https://image.pollinations.ai/prompt/{q}", params={"width": 768, "height": 768, "nologo": "true", "model": "flux",
                             "seed": random.randint(1, 10 ** 6)}, timeout=150)
            _last_poll[0] = time.time()
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") and len(r.content) > 8000:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
            log(f"  pollinations HTTP {r.status_code}, {len(r.content)} bytes (try {k+1})")
        except Exception as e:
            log("  pollinations error:", e)
    return None

def stub_subject(i):
    """plain cartoon blob on white (offline tests and last-resort fallback)"""
    im = Image.new("RGB", (768, 768), (255, 255, 255)); d = ImageDraw.Draw(im)
    col = [(255, 120, 100), (100, 180, 255), (120, 210, 120), (255, 200, 70)][i % 4]
    for k in range(5): d.line([(250 + k * 66, 470), (225 + k * 80, 690)], fill=INK, width=52); d.line([(250 + k * 66, 470), (225 + k * 80, 690)], fill=col, width=40)
    d.ellipse([150, 110, 620, 540], fill=col, outline=INK, width=12)
    for ex in (290, 480): d.ellipse([ex - 48, 250 - 52, ex + 48, 250 + 52], fill=(255, 255, 255), outline=INK, width=8); d.ellipse([ex - 18, 250 - 20, ex + 18, 250 + 20], fill=INK)
    d.arc([300, 330, 470, 440], 15, 165, fill=INK, width=10)
    return im

def get_image(prompt, i):
    global _gemini_img_ok
    if OFFLINE or not GKEY: return stub_subject(i)
    for prov in IMG_PROVIDERS:
        if prov == "gemini" and _gemini_img_ok:
            try:
                resp = gemini(IMG_MODEL, {"contents": [{"parts": [{"text": style_prompt(prompt)}]}],
                              "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}}}, tries=1)
                raw, _ = inline_of(resp)
                if raw:
                    import io
                    log(f"  image {i+1}: gemini"); return Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception as e:
                log(f"  gemini image unavailable ({e}); not trying it again this run"); _gemini_img_ok = False
        elif prov == "pollinations":
            im = pollinations(prompt)
            if im is not None:
                log(f"  image {i+1}: pollinations"); return im
    log(f"  image {i+1}: no picture available, using a plain star")
    return stub_subject(i)

# ----------------------------------------------------------------------------- 4. music + sfx (synthesized, no copyright)
def synth_music(dur, seed):
    rnd = random.Random(seed); n = int(dur * SR); t = np.arange(n) / SR
    bpm = rnd.choice([100, 104, 108, 112]); beat = 60 / bpm; root = rnd.randint(0, 5)
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)
    prog = [(57, [0, 3, 7]), (53, [0, 4, 7]), (60, [0, 4, 7]), (55, [0, 4, 7])]   # Am F C G
    out = np.zeros(n, np.float32)
    def add(sig, start):
        s = int(start * SR); e = min(n, s + len(sig))
        if s < n: out[s:e] += sig[:e - s]
    # drums
    k_t = np.arange(int(0.18 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 * k_t + (90 / 28) * (1 - np.exp(-k_t * 28)))) * np.exp(-k_t * 18) * 0.55
    hat = (np.random.RandomState(seed).randn(int(0.05 * SR))); hat = np.diff(hat, prepend=0) * np.exp(-np.arange(len(hat)) / SR * 90) * 0.12
    bars = int(dur / (4 * beat)) + 2
    for bar in range(bars):
        base, tones = prog[bar % 4]; base += root
        t0 = bar * 4 * beat
        for b in range(4):
            tb = t0 + b * beat
            if bar >= 1 or b >= 2: add(kick, tb)
            add(hat, tb + beat / 2)
        # pad
        pt = np.arange(int(4 * beat * SR)) / SR
        env = np.minimum(1, pt / 0.4) * np.minimum(1, (4 * beat - pt) / 0.3)
        pad = sum(np.sin(2 * np.pi * midi(base - 12 + q) * pt) + 0.5 * np.sin(2 * np.pi * midi(base - 12 + q) * 2 * pt) for q in tones) * env * 0.045
        add(pad, t0)
        # bass
        bt = np.arange(int(beat * SR)) / SR
        for b in (0, 2):
            add(np.sin(2 * np.pi * midi(base - 24) * bt) * np.exp(-bt * 3.2) * 0.32, t0 + b * beat)
        # arpeggio (8th notes)
        for s8 in range(8):
            q = tones[(s8 * 2 + (bar % 2)) % 3] + (12 if s8 % 4 >= 2 else 0)
            nt = np.arange(int(beat * 0.5 * SR)) / SR; f = midi(base + 12 + q)
            tri = (2 / np.pi) * np.arcsin(np.sin(2 * np.pi * f * nt))
            add(tri * np.exp(-nt * 9) * 0.11, t0 + s8 * beat / 2)
    out *= np.minimum(1, t / 0.8) * np.minimum(1, (dur - t) / 2.0)
    return out / max(np.abs(out).max(), 1e-6)

def sfx(kind):
    if kind == "whoosh":
        n = int(0.6 * SR); noise = np.random.RandomState(3).randn(n); y = np.zeros(n); a_prev = 0.0
        for i in range(n):
            p = i / n; alpha = 0.02 + 0.55 * math.sin(math.pi * p) ** 2
            a_prev += alpha * (noise[i] - a_prev); y[i] = a_prev
        env = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
        return (y * env / max(np.abs(y * env).max(), 1e-6) * 0.9).astype(np.float32)
    if kind == "pop":
        t = np.arange(int(0.16 * SR)) / SR
        return (np.sin(2 * np.pi * (700 * np.exp(-t * 14) + 180) * t) * np.exp(-t * 22)).astype(np.float32)
    if kind == "ding":
        t = np.arange(int(1.2 * SR)) / SR
        return ((np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 1976 * t) + 0.25 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 3.2) * 0.5).astype(np.float32)
    return np.zeros(10, np.float32)

def mix_audio(durs, starts, speech, total_sec, sfx_plan, seed):
    n = int(total_sec * SR)
    voice = np.zeros(n, np.float32)
    for st, sp in zip(starts, speech): voice[int(st * SR): int(st * SR) + len(sp)] += sp / 32768
    # duck the music under the voice
    win = int(0.05 * SR); env = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, mode="same"))
    env = np.convolve(np.minimum(1, env / 0.08), np.ones(int(0.25 * SR)) / int(0.25 * SR), mode="same")
    music = synth_music(total_sec, seed)[:n] * (0.30 - 0.20 * env)
    fx = np.zeros(n, np.float32)
    for kind, tt in sfx_plan:
        s = sfx(kind); st = int(max(tt, 0) * SR)
        if st < n: e = min(n, st + len(s)); fx[st:e] += s[:e - st] * 0.55
    mix = voice * 1.0 + music + fx
    mix = np.tanh(mix * 1.15) * 0.92
    return mix.astype(np.float32)

# ----------------------------------------------------------------------------- 5. video
def make_groups(beat_idx, text, t0, t1):
    words = text.split(); wts = [len(w) + 2 for w in words]; tot = sum(wts); acc = 0; times = []
    for w, k in zip(words, wts):
        times.append((t0 + (t1 - t0) * acc / tot, t0 + (t1 - t0) * (acc + k) / tot)); acc += k
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if len(cur) >= 3 or w.endswith((",", ".", "?", "!")) or i == len(words) - 1:
            groups.append(cur); cur = []
    if len(groups) > 1 and len(groups[-1]) == 1 and len(groups[-2]) <= 3: groups[-2] += groups.pop()
    out = []
    for gi, g in enumerate(groups):
        nxt = times[groups[gi + 1][0]][0] if gi + 1 < len(groups) else t1 + 0.25
        out.append({"words": [words[j].upper() for j in g], "times": [times[j] for j in g], "t0": times[g[0]][0] - 0.03, "t1": nxt})
    return out

def caption_img(g, active, scale=1.0):
    words = g["words"]; size = 100
    while True:
        f = font(size); sp = f.getlength(" "); ws = [f.getlength(w) for w in words]
        if sum(ws) + sp * (len(words) - 1) <= 940 or size <= 52: break
        size -= 4
    total = sum(ws) + sp * (len(words) - 1)
    lay = Image.new("RGBA", (W, 240), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); x = (W - total) / 2
    for i, (w, ww) in enumerate(zip(words, ws)):
        d.text((x, 120), w, font=f, fill=(255, 226, 70) if i == active else (255, 255, 255), anchor="lm", stroke_width=11, stroke_fill=INK)
        x += ww + sp
    if abs(scale - 1) > 0.01:
        lay = lay.resize((int(W * scale), int(240 * scale)), Image.LANCZOS)
        full = Image.new("RGBA", (W, 240), (0, 0, 0, 0)); full.alpha_composite(lay, ((W - lay.width) // 2, (240 - lay.height) // 2)); lay = full
    return lay

def number_of(beat):
    m = re.search(r"\d[\d,\.]*%?", beat.get("english", ""))
    return m.group(0).rstrip(".,")[:6] if m else ""

def lip_amplitude(starts, segs, total):
    n = int(total * SR); voice = np.zeros(n, np.float32)
    for st, sp in zip(starts, segs): voice[int(st * SR): int(st * SR) + len(sp)] += np.abs(sp) / 32768
    hop = SR // FPS; nfr = int(total * FPS) + 2
    a = np.array([voice[i * hop:(i + 1) * hop].mean() if len(voice[i * hop:(i + 1) * hop]) else 0 for i in range(nfr)])
    a = np.clip(a / (np.percentile(a[a > 0.002], 90) + 1e-6), 0, 1) if (a > 0.002).any() else a
    a = np.convolve(a, np.ones(3) / 3, mode="same"); a[a < 0.12] = 0
    return a

# ----------------------------------------------------------------------------- 6. publish via Zapier MCP (verified YouTube client)
def next_publish_utc():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(ist)
    tgt = now.replace(hour=PUBLISH_HOUR_IST, minute=PUBLISH_MIN_IST, second=0, microsecond=0)
    if tgt <= now + datetime.timedelta(minutes=45): tgt += datetime.timedelta(days=1)
    return tgt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def host_video(path):
    """Publish the mp4 as a GitHub release asset (public URL, no repo bloat). Falls back to committing it."""
    repo = os.environ["GITHUB_REPOSITORY"]; tag = "daily-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")
    subprocess.run(["gh", "release", "create", tag, path, "--title", tag, "--notes", "auto-generated short"], check=True)
    # delete releases older than 3 days
    try:
        out = subprocess.run(["gh", "release", "list", "--limit", "50", "--json", "tagName,createdAt"], capture_output=True, text=True, check=True).stdout
        for r in json.loads(out):
            if r["tagName"].startswith("daily-") and r["tagName"] != tag:
                age = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
                if age > datetime.timedelta(days=3):
                    subprocess.run(["gh", "release", "delete", r["tagName"], "--cleanup-tag", "-y"], check=False)
    except Exception as e: log("  release cleanup skipped:", e)
    return f"https://github.com/{repo}/releases/download/{tag}/{os.path.basename(path)}"

async def zapier_upload(args, pub=None):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    tok = os.environ["ZAPIER_MCP_TOKEN"]
    tr = StreamableHttpTransport("https://mcp.zapier.com/api/v1/connect", headers={"Authorization": f"Bearer {tok}"})
    async with Client(tr) as c:
        tools = [t.name for t in await c.list_tools()]; log("  zapier tools:", tools[:6], "...")
        res = await c.call_tool("execute_zapier_write_action", {"action": "upload_video", "params": args, "selected_api": "YouTubeV4CLIAPI"})
        txt = " ".join(getattr(x, "text", "") for x in res.content); log("  zapier result:", txt[:1800])
        if getattr(res, "is_error", False) or "isError\":true" in txt: raise RuntimeError("Zapier upload failed: " + txt[:300])
        # Extra settings the upload action does not offer: hide extended public statistics (the like-count toggle itself is not in the API)
        m = re.search(r'"(?:id|videoId)"\s*:\s*"([A-Za-z0-9_-]{11})"', txt)
        if m:
            vid = m.group(1); log("  video id:", vid, "| https://www.youtube.com/watch?v=" + vid)
            try:
                status = {"privacyStatus": "private", "license": "youtube", "embeddable": True, "publicStatsViewable": False, "selfDeclaredMadeForKids": False}
                if pub: status["publishAt"] = pub
                r2 = await c.call_tool("execute_zapier_write_action", {"action": "_zap_raw_request", "selected_api": "YouTubeV4CLIAPI", "params": {
                    "fail_on_errors": "true", "method": "PUT", "querystring": {"part": "status"},
                    "url": "https://www.googleapis.com/youtube/v3/videos", "body": json.dumps({"id": vid, "status": status})}})
                log("  hide-stats update:", " ".join(getattr(x, "text", "") for x in r2.content)[:400])
            except Exception as e: log("  hide-stats update failed (video is still uploaded):", e)
        else: log("  could not read the video id from the answer")
        return txt

def publish(path, script):
    url = host_video(path); pub = next_publish_utc(); log("video url:", url, "| publishAt", pub)
    args = {"title": script["title"][:95], "description": script["description"] + f"\n\nHindi narration, English captions.\n#Shorts",
            "tags": script.get("tags", [])[:12] + ["Shorts"], "privacy_status": "private", "publish_at": pub,
            "made_for_kids": False, "notify_subscribers": True, "default_audio_language": "hi", "video": url}
    if os.environ.get("PRIVATE_ONLY") == "1":                  # test mode: stay private, never auto-publish, no notification
        args.pop("publish_at", None); args["notify_subscribers"] = False
    for attempt in range(3):
        try: return asyncio.run(zapier_upload(args, args.get('publish_at')))
        except Exception as e:
            log(f"  upload attempt {attempt+1} failed: {e}"); time.sleep(30)
    raise RuntimeError("YouTube upload failed after 3 tries")

# ----------------------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    hist = load_history(); script = make_script(hist)
    log("TITLE:", script["title"])
    cta = {"hindi": "ऐसे ही हैरान करने वाले फैक्ट्स के लिए, ट्रू फैक्ट को फ़ॉलो करें।", "english": f"Follow {CHANNEL} for a new fact every day!",
           "image_prompt": "", "sfx": "ding", "brand": True, "setting": "indoor", "time": "day", "camera": "push_in", "fx": "sparkles",
           "cast": [{"role": "boy", "slot": "left", "expr": "laugh", "action": "cheer"}, {"role": "girl", "slot": "right", "expr": "laugh", "action": "cheer"}]}
    beats = script["beats"] + [cta]
    segs = build_voice(beats)
    speech_sec = [len(s) / SR for s in segs]
    pad = 0.30
    total_speech = sum(speech_sec) + pad * len(segs)
    if total_speech > TARGET_SEC + 3:                          # too long -> speed up the voice a little (pitch preserved)
        f = min(1.18, total_speech / (TARGET_SEC + 0.5)); log(f"  voice too long ({total_speech:.1f}s) -> atempo {f:.2f}")
        for i, s in enumerate(segs):
            write_wav(os.path.join(OUT, "_a.wav"), s)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(OUT, "_a.wav"), "-filter:a", f"atempo={f:.3f}", "-ar", str(SR), os.path.join(OUT, "_b.wav")], check=True)
            segs[i], _ = read_wav(os.path.join(OUT, "_b.wav"))
        speech_sec = [len(s) / SR for s in segs]; total_speech = sum(speech_sec) + pad * len(segs)
    tail = max(0.8, min(3.5, TARGET_SEC - total_speech))        # hold the brand card so the video lands near 45 s
    starts, durs, t = [], [], 0.0
    for i, sp in enumerate(speech_sec):
        d = sp + pad + (tail if i == len(segs) - 1 else 0.0); starts.append(t); durs.append(d); t += d
        beats[i]["speech"] = sp
    total = t
    log(f"  speech {sum(speech_sec):.1f}s, total video {total:.1f}s")
    sfx_plan = [("whoosh", starts[i] - 0.15) for i in range(1, len(beats) - 1)] + \
               [("pop", starts[i] + 0.05) for i in range(len(beats) - 1) if beats[i].get("sfx") == "pop"] + [("ding", starts[-1] + 0.05)]
    audio = mix_audio(durs, starts, segs, total, sfx_plan, seed=datetime.date.today().toordinal())
    write_wav(os.path.join(OUT, "audio.wav"), audio * 32767)
    images = [get_image(b["image_prompt"], i) for i, b in enumerate(script["beats"])]
    stickers = []
    for i, im in enumerate(images):
        st, kind = toon.sticker_or_card(im); stickers.append(st); log(f"  picture {i+1}: {kind}")
    stickers.append(toon.cta_sticker(CHANNEL))
    groups = []
    for i, b in enumerate(beats): groups += [dict(g, beat=i) for g in make_groups(i, b["english"], starts[i] + 0.02, starts[i] + b["speech"])]
    scenes.render(os.path.join(OUT, "short.mp4"), os.path.join(OUT, "audio.wav"), stickers, beats, starts, durs, total, groups, caption_img, number_of, brand_idx=len(beats) - 1)
    log("rendered", os.path.join(OUT, "short.mp4"))
    if OFFLINE or os.environ.get("SKIP_UPLOAD") == "1": log("upload skipped"); return
    res = publish(os.path.join(OUT, "short.mp4"), script)
    hist["topics"].append({"date": str(datetime.date.today()), "title": script["title"]}); hist["topics"] = hist["topics"][-300:]
    json.dump(hist, open(HIST, "w"), indent=1, ensure_ascii=False)
    log("done")

if __name__ == "__main__":
    main()
