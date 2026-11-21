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
import toon, scenes, kitpost

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
# The owner's chosen story type: how the weaker side won a war with a clever trick ("jugaad") in olden times.
STORY_BRIEF = ("true stories from old history (before 1950) where soldiers, kings or commanders who were OUTNUMBERED or weaker won a battle or war "
               "through a clever trick, deception, local jugaad, smart use of terrain/animals/weather/tools. Examples of the kind of story: "
               "Chanakya and Chandragupta's strategies, Shivaji Maharaj's guerrilla tactics, Lachit Borphukan at Saraighat, Maharana Pratap's Chetak and hill tactics, "
               "Rani Durgavati, Porus vs Alexander, Raja Suhaldev, the Trojan Horse, Hannibal's fire-oxen trick, the Battle of Red Cliffs, Mongol feigned retreat, "
               "Operation Mincemeat, the Ghost Army, Thermopylae and Marathon tactics, Zheng He, Admiral Yi Sun-sin's turtle ships")
CATEGORIES = ["Indian history"] * 7 + ["world history"] * 3             # 70 percent Indian stories, 30 percent world stories
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


# ----------------------------------------------------------------------------- 0. channel analysis (through the owner's Zapier/YouTube connection)
def _first_json(txt):
    i = txt.find("{")
    if i < 0: return None
    try: return json.JSONDecoder().raw_decode(txt[i:])[0]
    except Exception: return None

async def _yt_get(c, url, qs):
    r = await c.call_tool("execute_zapier_read_action", {"action": "_zap_raw_request", "selected_api": "YouTubeV4CLIAPI",
        "params": {"fail_on_errors": "true", "method": "GET", "querystring": qs, "url": url}})
    for x in r.content:
        o = _first_json(getattr(x, "text", "") or "")
        if o and "results" in o: return o["results"][0].get("body", {})
    raise RuntimeError("no body from YouTube request")

async def _channel_data():
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    tr = StreamableHttpTransport("https://mcp.zapier.com/api/v1/connect", headers={"Authorization": f"Bearer {os.environ['ZAPIER_MCP_TOKEN']}"})
    base = "https://www.googleapis.com/youtube/v3"
    async with Client(tr) as c:
        ch = await _yt_get(c, f"{base}/channels", {"mine": "true", "part": "snippet,statistics,contentDetails,brandingSettings"})
        item = ch["items"][0]; up = item["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = await _yt_get(c, f"{base}/playlistItems", {"playlistId": up, "part": "contentDetails", "maxResults": "50"})
        ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        vids = []
        if ids: vids = (await _yt_get(c, f"{base}/videos", {"id": ",".join(ids), "part": "snippet,statistics,status,contentDetails"})).get("items", [])
        skill = ""
        try:
            sr = await c.call_tool("get_zapier_skill", {"name": "upload to youtube"})
            skill = " ".join(getattr(x, "text", "") for x in sr.content)[:3500]
        except Exception as e: log("  owner notes (skill) not read:", e)
    return item, vids, skill

def _secs(iso):
    m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 0

def channel_profile():
    """what the channel is about and which videos worked -> (text, rows) or None"""
    if OFFLINE or not os.environ.get("ZAPIER_MCP_TOKEN"): return None
    try: item, vids, skill = asyncio.run(_channel_data())
    except Exception as e:
        log("  channel analysis unavailable:", e); return None
    sn, st = item.get("snippet", {}), item.get("statistics", {}); bd = item.get("brandingSettings", {}).get("channel", {})
    now = datetime.datetime.now(datetime.timezone.utc); rows = []
    for v in vids:
        s_, t_ = v["snippet"], v.get("statistics", {})
        pub = datetime.datetime.fromisoformat(s_["publishedAt"].replace("Z", "+00:00")); age = max(0.3, (now - pub).total_seconds() / 86400)
        views, likes = int(t_.get("viewCount", 0)), int(t_.get("likeCount", 0))
        rows.append(dict(id=v["id"], title=s_["title"], published=s_["publishedAt"][:10], hour_ist=(pub + datetime.timedelta(hours=5, minutes=30)).hour, age_days=round(age, 1),
                         views=views, views_per_day=round(views / age, 1), likes=likes, like_pct=round(100 * likes / views, 1) if views else 0, comments=int(t_.get("commentCount", 0)),
                         seconds=_secs(v.get("contentDetails", {}).get("duration")), privacy=v.get("status", {}).get("privacyStatus"),
                         title_language="hindi" if re.search(r"[\u0900-\u097F]", s_["title"]) else "english", has_emoji=bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", s_["title"])),
                         has_custom_thumbnail=bool(v.get("contentDetails", {}).get("hasCustomThumbnail")), description_chars=len(s_.get("description", "")), tags=len(s_.get("tags") or [])))
    public = sorted([r for r in rows if r["privacy"] == "public" and r["age_days"] >= 1.0], key=lambda r: -r["views"])
    text = (f"CHANNEL: {sn.get('title')} | {sn.get('description', '')[:400]} | keywords: {bd.get('keywords', '')} | subscribers: {st.get('subscriberCount')} "
            f"| total views: {st.get('viewCount')} | video count: {st.get('videoCount')}\nPUBLIC VIDEOS (older than 1 day), BEST FIRST: {json.dumps(public[:40], ensure_ascii=False)}\n"
            f"ALL UPLOADED TITLES (never repeat): {json.dumps([r['title'] for r in rows], ensure_ascii=False)}")
    if skill: text += f"\nOWNER NOTES ABOUT THE CHANNEL IDEA:\n{skill}"
    log("CHANNEL PROFILE:", text[:2500].replace("\n", " | "))
    return text, public

COACH_FILE = "playbook.json"
LEARN = ""

def performance_coach(rows, hist):
    """Reads every public video's numbers (and our own past scripts) and writes a playbook of concrete fixes for the next video."""
    if not rows: return ""
    ours = {t.get("video_id"): t for t in hist.get("topics", []) if t.get("video_id")}
    data = []
    for r in rows:
        d = dict(r)
        if r["id"] in ours: d["our_script"] = {"hook": ours[r["id"]].get("hook"), "beats": ours[r["id"]].get("beats"), "uniforms": ours[r["id"]].get("uniforms")}
        data.append(d)
    med = sorted(r["views"] for r in rows)[len(rows) // 2]
    ask = (f"You are a YouTube Shorts growth coach for the Hindi channel {CHANNEL}. Below is the real data of every public video (views, views_per_day, likes, like_pct, duration in seconds, "
           f"title language, emoji in title, custom thumbnail, hour published in IST). The channel median is {med} views. The owner wants to know which videos did NOT perform (for example under 50-100 views), "
           "WHY, and what to improve in the next video: a stronger HOOK, a better suspense/story BUILD-UP, better VISUALS, better title and topic.\n"
           f"DATA: {json.dumps(data, ensure_ascii=False)}\n\n"
           "Compare the best and the worst videos honestly. Only state a pattern if the numbers support it; say when the data is too small. Note that retention (drop-off) data is NOT available, so judge the hook only from titles, topics, likes and length. "
           "Return JSON: {\"weak_videos\": [{\"title\": \"\", \"views\": 0, \"likely_reasons\": [\"\"]}], \"what_works\": [\"\"], \"diagnosis\": {\"hook\": \"\", \"buildup\": \"\", \"visuals\": \"\", \"titles_topics\": \"\", \"other\": \"\"}, "
           "\"playbook\": {\"hook_rules\": [\"5 concrete rules\"], \"buildup_rules\": [\"4 concrete rules\"], \"visual_rules\": [\"4 concrete rules\"], \"title_rules\": [\"4 concrete rules\"], \"topic_rules\": [\"3 concrete rules\"], \"avoid\": [\"\"]}}")
    try:
        txt = text_of(gemini_text({"contents": [{"parts": [{"text": ask}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}}))
        pb = json.loads(re.sub(r"^```json|```$", "", txt.strip(), flags=re.M).strip())
    except Exception as e:
        log("  coach analysis unavailable:", e); return ""
    try: json.dump({"date": str(datetime.date.today()), **pb}, open(COACH_FILE, "w"), indent=1, ensure_ascii=False)
    except Exception: pass
    log("COACH DIAGNOSIS:", json.dumps(pb.get("diagnosis"), ensure_ascii=False)[:1500]); log("COACH WEAK:", json.dumps(pb.get("weak_videos"), ensure_ascii=False)[:900])
    p = pb.get("playbook") or {}
    lines = [f"{k.replace('_', ' ').upper()}: " + " | ".join(map(str, v)) for k, v in p.items() if isinstance(v, list) and v]
    return "\n".join(lines)

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
    global LEARN
    prof = channel_profile(); profile, rows = (prof if prof else (None, []))
    learn = performance_coach(rows, hist) if rows else ""
    LEARN = learn
    region = "Indian history (India's kings, commanders and soldiers)" if cat == "Indian history" else "world history (any country)"
    ctx = (f"CHANNEL DATA (for tone and audience only):\n{profile}\n\n") if profile else ""
    ask = (f"You choose the next 45-second YouTube Shorts story for a Hindi channel.\n{ctx}"
           f"MANDATORY STORY TYPE: {STORY_BRIEF}.\n"
           f"Today's region: {region}.\n"
           + (f"LEARNINGS FROM THE CHANNEL'S REAL NUMBERS (follow them when choosing): {learn}\n" if learn else "")
           + "Strongly prefer FAMOUS, relatable stories that many Indians already know or search for (Indian rulers and battles, Chanakya, Shivaji, Rani Lakshmibai, the Trojan Horse, Napoleon, Hannibal), because obscure foreign battles got very few views on this channel.\n"
           "Suggest 10 English Wikipedia article titles (a battle, siege, campaign, operation or ruler/commander article) for stories of this type. Each must: "
           "be a clear, well-sourced event where the clever trick or jugaad is documented in the article; be NEW (not in this used list: " + str(used) + "); "
           "be well known or at least exciting for Hindi-speaking youth; contain no graphic gore; avoid anything about religion-versus-religion conflict, "
           "modern politics or events after 1950. "
           "Return JSON: {\"niche\": \"...\", \"audience\": \"...\", \"why\": \"...\", \"wikipedia_titles\": [\"exact Wikipedia article title\", ...]} with the best story first.")
    cj = text_of(gemini_text({"contents": [{"parts": [{"text": ask}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}}))
    log("candidate reply:", cj[:300].replace("\n", " "))
    try: cands = json.loads(re.sub(r"^```json|```$", "", cj.strip(), flags=re.M).strip())
    except Exception as e: log("  candidate JSON error:", e); cands = []
    if isinstance(cands, dict):
        log("  strategist says: niche=", cands.get("niche"), "| audience=", cands.get("audience"), "| why=", cands.get("why"))
        cands = cands.get("wikipedia_titles") or next((v for v in cands.values() if isinstance(v, list)), [])
    for t in cands:
        t = t if isinstance(t, str) else (t.get("title") if isinstance(t, dict) else str(t))
        title, extract = wiki_extract(str(t))
        log(f"  candidate {t!r} -> {title!r}, {len(extract or '')} chars")
        if extract and len(extract) >= 2500: break
        title, extract = None, None
    if not extract: raise RuntimeError("no usable Wikipedia topic found")
    research = f"Wikipedia article '{title}':\n{extract[:7500]}"
    log("topic:", title, "| extract chars:", len(extract))
    prompt = f"""You write a 45-second YouTube Short for the channel {CHANNEL}: a dramatic true war story about how the weaker side won with a clever trick (jugaad).
Use ONLY facts that are stated in this source text (do not add outside facts):
{research}

LEARNINGS FROM THIS CHANNEL'S REAL VIEW NUMBERS (apply them):
{LEARN or 'none yet'}

Return JSON with this exact shape:
{{"title": "<Hindi (Devanagari) or Hinglish title, max 60 chars, exactly ONE emoji, built like the best titles of this channel: a direct question or a shock plus a number or the impossible odds; do not reveal the trick; no clickbait lies>",
  "description": "<2-3 Hindi sentences that tease the story and END WITH A QUESTION asking viewers to comment, then 5 hashtags including #Shorts>",
  "tags": ["<10 short tags, mix of Hindi and English>"],
  "beats": [ {{"hindi": "...", "english": "...", "sfx": "whoosh|pop|none", "light": "day|golden|night|fog",
               "camera": "medium|close|two|wide|pull|low|pan_l|pan_r|push",
               "actors": [ {{"uniform": "roman|knight|samurai|indian|mongol|chinese|us_ww2|jp_ww2|uk_ww2|officer|villager|elder", "team": "A|B",
                             "slot": "far_left|left|center|right|far_right", "expr": "neutral|stern|stubborn|nervous|shock|squint|grin|smile|laugh",
                             "pose": "idle|point|cheer|think|worry|command|cross|wave|thumb|talk", "enter": "none|walk_left|walk_right"}} ],
               "fx": ["exclaim|question|stars|dust|sweat"], "shake": false, "flash": false,
               "panel": null }} ]}}

Rules:
- HOOK (beat 1, the first two seconds): open with the most shocking fact, the impossible odds, or a direct question, in at most 12 Hindi words. Never a greeting, never background first. Style example: तेरह नावें... और सामने एक सौ तैंतीस! फिर भी जीत किसकी हुई?
- SUSPENSE BUILD-UP: beats 2 and 3 raise the stakes and the question "how can they possibly win?" and beat 3 ends on a mini-cliffhanger; hold the trick back until beat 4; beat 5 shows it working step by step; beat 6 is the payoff; beat 7 calls back to the hook. Every beat should end on something that makes the viewer need the next sentence.
- VISUALS: every beat must look clearly different from the previous one (change camera, poses, expressions, fx); show the trick in a panel; use shock + exclaim at the reveal.
- Exactly 7 beats = 7 short sentences, told as a gripping story: 1 hook with the impossible odds, 2 who/where/when, 3 the danger or problem, 4 the clever trick (the key reveal), 5 how the trick worked, 6 the result, 7 a punchy closing line about the lesson. Name the people and the place. If a detail is only legend, say 'कहा जाता है'. Be neutral and respectful to every community, no hatred, no gore. 
- "hindi": natural spoken Hindi in Devanagari for a young storyteller. Write ALL numbers and years as Hindi words (दो हज़ार, तेईस...). 
  English technical words must be written in Devanagari (क्विकलाइम). 8-17 words per beat; total 110-125 Hindi words. No emojis.
- "english": a faithful, natural English translation of that beat for captions, max 14 words, numbers as digits.
- "image_prompt": the ONE main SUBJECT to draw for that beat, as a short noun phrase of 4-12 English words (e.g. "a big wooden horse on wheels", "a bull with a burning torch tied to its horns", "a mountain fort", "a war elephant", "a rolled treasure map"). Kid-friendly cartoon, no blood, no wounded people, no real people. A single physical thing, no scene, no background, no abstract ideas, no text, no real people, no violence. Use a different subject for each beat.
- Each beat is a short cartoon SCENE in which soldiers ACT OUT what the narrator says, like a silent-film reenactment. Team A = the clever, weaker side (the heroes); team B = their opponents. Choose each uniform by the real nationality and era of that side: roman (ancient Rome/Greece/Mediterranean), knight (medieval Europe, crusaders), samurai (feudal Japan), indian (Indian kingdoms: Rajput, Maratha, Ahom, Sikh, Maurya...), mongol (Mongols, Mughals, Turks, Persians, Central Asia), chinese (ancient China, Korea, Vietnam), us_ww2 / jp_ww2 / uk_ww2 (World War II), officer (generals and officers of the 1700s-1900s, or any commander), villager / elder (civilians and advisers such as Chanakya). 1-4 actors per beat; show the heroes in most beats and the opponents when they matter; put the two sides on opposite slots (heroes left, opponents right). Reactions: shock/nervous for the surprised enemy when the trick works, laugh/grin with pose cheer for the heroes' win, squint with think or command while planning. At most one actor per beat uses "enter". Camera: wide for armies, close for one thinker, two for a face-off, pull for the opening beat, low for heroic moments, medium otherwise. Lighting: night for an ambush, fog for a surprise, golden for victory, day otherwise. fx: exclaim when the trick is revealed, question for a puzzle, stars for the win, dust for a charge, sweat for fear. Set "shake" true on the beat where the trick bursts into action and "flash" true on the final victory beat.
- "panel": on at most 3 beats (the plan, the trick, the result) give {{"picture": "one clear drawable thing, 6-14 English words, kid-friendly cartoon, no blood", "tag": "THE TRICK"}} (tag = 2-3 words, upper case); those beats must use camera medium, two or wide. All other beats: null.
- "sfx": "pop" if the beat has a key number, otherwise "whoosh" (use "none" at most once).
- Be accurate. Never invent facts that are not in the source text."""
    last = None
    for attempt in range(3):
        resp = gemini_text({"contents": [{"parts": [{"text": prompt}]}],
                                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}})
        try:
            s = json.loads(re.sub(r"^```json|```$", "", text_of(resp).strip(), flags=re.M).strip())
            assert len(s["beats"]) == 7 and all(b["hindi"] and b["english"] and b.get("actors") for b in s["beats"])
            assert re.search(r"[\u0900-\u097F]", s["beats"][0]["hindi"])
            return s
        except Exception as e:
            last = e; log("  script invalid, retrying:", e)
    raise RuntimeError(f"script generation failed: {last}")

def offline_script():
    H7 = ["सन् सोलह सौ इकहत्तर में, मुग़लों की विशाल सेना असम पर चढ़ आई।", "लाचित बरफूकन के पास सैनिक कम थे।", "उन्होंने नदी के किनारे रातों-रात मिट्टी की दीवार खड़ी करवाई।",
          "दुश्मन को लगा कि यहाँ से रास्ता खुला है।", "उनका बेड़ा तंग नदी में फँस गया।", "तब असम की नावों ने चारों ओर से हमला कर दिया।", "इस तरह चालाकी ने बड़ी सेना को हरा दिया!"]
    E7 = ["In 1671 a huge Mughal army marched on Assam.", "Lachit Borphukan had far fewer soldiers.", "So he built a mud wall by the river overnight.",
          "The enemy thought the way was open.", "Their fleet got trapped in the narrow river.", "Then Assam's boats attacked from every side.", "Cleverness beat a giant army!"]
    A = lambda u, slot, expr="smile", pose="idle", **k: dict(uniform=u, team="A", slot=slot, expr=expr, pose=pose, **k)
    B = lambda u, slot, expr="stern", pose="idle", **k: dict(uniform=u, team="B", slot=slot, expr=expr, pose=pose, **k)
    SC = [dict(camera="pull", light="day", actors=[B("mongol", "right", "stern", "ready"), B("mongol", "far_right", "grin", "ready")], fx=["dust"], panel=None),
          dict(camera="two", light="day", actors=[A("indian", "left", "nervous", "worry"), B("mongol", "right", "grin", "cross")], fx=["sweat"], panel=None),
          dict(camera="medium", light="night", actors=[A("indian", "center", "squint", "command")], fx=["exclaim"], panel={"picture": "a long mud wall beside a river", "tag": "THE TRICK"}),
          dict(camera="wide", light="fog", actors=[A("indian", "far_left", "grin", "ready"), A("indian", "left", "grin", "ready"), B("mongol", "right", "shock", "worry"), B("mongol", "far_right", "shock", "worry")], fx=["question"], panel=None),
          dict(camera="two", light="fog", actors=[A("officer", "left", "smile", "point"), B("mongol", "right", "shock", "worry")], fx=["sweat"], panel=None),
          dict(camera="wide", light="golden", actors=[A("indian", "left", "laugh", "cheer"), A("indian", "center", "laugh", "cheer"), B("mongol", "right", "nervous", "worry")], fx=["dust"], shake=True, panel=None),
          dict(camera="low", light="golden", actors=[A("indian", "center", "laugh", "cheer")], fx=["stars"], flash=True, panel={"picture": "a happy cartoon warrior holding a flag on a boat", "tag": "VICTORY"})]
    return {"title": "How a Mud Wall Stopped an Empire", "description": "Test.", "tags": ["test"], "beats": [dict(hindi=h, english=e, sfx="pop" if i == 0 else "whoosh", **SC[i]) for i, (h, e) in enumerate(zip(H7, E7))]}

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
_poll_deadline = [None]      # set when the picture phase starts: at most 12 minutes of waiting for the free service

def pollinations(prompt):
    """Free anonymous service: it answers HTTP 402/429 if called too often, so keep >=35 s between requests."""
    import io, urllib.parse
    q = urllib.parse.quote(style_prompt(prompt)[:700])
    for k in range(5):
        if _poll_deadline[0] is None: _poll_deadline[0] = time.time() + 720
        if time.time() > _poll_deadline[0]: log('  pollinations time budget used up'); return None
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

def check_picture(im, want):
    """Ask Gemini to look at the picture: is the subject recognisable and is it clean? True when unsure."""
    if OFFLINE or not GKEY: return True
    try:
        import io
        buf = io.BytesIO(); im.convert("RGB").resize((512, 512)).save(buf, "JPEG", quality=80)
        body = {"contents": [{"parts": [{"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
                {"text": "This picture is meant to be a kid-friendly cartoon of: '" + want + "'. Reply as JSON {\"shows_subject\": true or false, \"clean\": true or false}. shows_subject = the main subject is clearly recognisable; clean = no deformed or garbled shapes, no letters or text, no gore."}]}],
                "generationConfig": {"responseMimeType": "application/json"}}
        r = json.loads(text_of(gemini_text(body))); ok = bool(r.get("shows_subject")) and bool(r.get("clean")); log("  picture check for", repr(want[:40]), r); return ok
    except Exception as e:
        log("  picture check skipped:", e); return True

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
    log(f"  image {i+1}: no picture available, this scene runs without a prop")
    return None

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
    ov = os.environ.get("PUBLISH_AT_IST", "").strip()           # e.g. 2026-11-15T09:00 (catch-up run)
    if ov:
        try:
            tgt = datetime.datetime.fromisoformat(ov).replace(tzinfo=ist)
            if tgt < now + datetime.timedelta(minutes=12): tgt = now + datetime.timedelta(minutes=12)
            return tgt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception as e: log("  bad PUBLISH_AT_IST:", e)
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
    if os.environ.get("ANALYZE_ONLY") == "1":
        log("BEATS:", json.dumps([b["english"] for b in script["beats"]], ensure_ascii=False)); log("analysis only: stopping before the video"); return
    hero = next((x for bb in script["beats"] for x in bb.get("actors", []) if x.get("team", "A") == "A" and x.get("uniform") not in ("villager", "elder")), {"uniform": "roman"})["uniform"]
    cta = {"hindi": "ऐसे ही हैरान करने वाली कहानियों के लिए, ट्रू फैक्ट को फ़ॉलो करें।", "english": f"Follow {CHANNEL} for a new story every day!",
           "sfx": "ding", "brand": True, "light": "golden", "camera": "medium", "fx": ["stars"], "flash": True,
           "actors": [{"uniform": hero, "team": "A", "slot": "left", "expr": "laugh", "pose": "cheer"}, {"uniform": hero, "team": "A", "slot": "center", "expr": "laugh", "pose": "cheer"}, {"uniform": hero, "team": "A", "slot": "right", "expr": "laugh", "pose": "cheer"}], "panel": None}
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
    # ---- storyboard for the kit engine (frames are exact: voice timing -> frame ranges)
    FPSK = 30; ntot = int(round(total * FPSK)); sb = []
    for i, b in enumerate(beats):
        a_ = int(round(starts[i] * FPSK)); e_ = ntot - 1 if i == len(beats) - 1 else int(round((starts[i] + durs[i]) * FPSK)) - 1
        sb.append({"a": a_, "b": max(a_, e_), "light": b.get("light", "day"), "camera": b.get("camera", "medium"), "actors": b.get("actors", []), "fx": b.get("fx") or [],
                   "shake": bool(b.get("shake")), "flash": bool(b.get("flash"))})
    sbp = os.path.join(OUT, "storyboard.json"); json.dump({"fps": FPSK, "total": ntot, "beats": sb}, open(sbp, "w"), ensure_ascii=False)
    # ---- panels: the picture of the trick, shown in a frame at the top
    panels = {}
    for i, b in enumerate(beats):
        pn = b.get("panel")
        if isinstance(pn, dict) and pn.get("picture"):
            im = get_image(pn["picture"], i)
            if im is not None and not check_picture(im, pn["picture"]):
                log(f"  panel beat {i+1}: picture not good enough, trying once more")
                im2 = get_image(pn["picture"] + ", very simple, one clear object, centered, plain background", i)
                im = im2 if (im2 is not None and check_picture(im2, pn["picture"])) else None
            if im is not None: panels[i] = kitpost.make_panel(im, str(pn.get("tag") or "")[:18].upper()); log(f"  panel beat {i+1}: picture ok")
            else: log(f"  panel beat {i+1}: no picture, scene runs without the panel")
    groups = []
    for i, b in enumerate(beats): groups += [dict(g, beat=i) for g in make_groups(i, b["english"], starts[i] + 0.02, starts[i] + b["speech"])]
    engine = os.environ.get("ENGINE_DIR", "engine"); fdir = os.path.join(OUT, "frames"); kstep = int(os.environ.get("KIT_STEP", "2"))
    kitpost.render_frames(engine, sbp, fdir, ntot, procs=int(os.environ.get("KIT_PROCS", "4")), step=kstep)
    kitpost.compose(fdir, os.path.join(OUT, "short.mp4"), os.path.join(OUT, "audio.wav"), ntot, kstep, sb, panels, groups, caption_img, len(beats) - 1, CHANNEL)
    log("rendered", os.path.join(OUT, "short.mp4"))
    if OFFLINE or os.environ.get("SKIP_UPLOAD") == "1": log("upload skipped"); return
    res = publish(os.path.join(OUT, "short.mp4"), script)
    mv = re.search(r'"(?:id|videoId)"\s*:\s*"([A-Za-z0-9_-]{11})"', res or "")
    hist["topics"].append({"date": str(datetime.date.today()), "title": script["title"], "video_id": mv.group(1) if mv else None, "hook": beats[0]["english"],
                           "beats": [b["english"] for b in script["beats"]], "uniforms": sorted({a.get("uniform") for b in script["beats"] for a in b.get("actors", []) if a.get("uniform")}),
                           "panels": [b["panel"]["picture"] for b in script["beats"] if isinstance(b.get("panel"), dict)]}); hist["topics"] = hist["topics"][-300:]
    json.dump(hist, open(HIST, "w"), indent=1, ensure_ascii=False)
    log("done")

if __name__ == "__main__":
    main()
