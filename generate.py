#!/usr/bin/env python3
"""TruFact daily Short generator.

Hindi boy voice (Gemini TTS) + English captions + the "Low-Poly Atlas" 3D style (Three.js map, routes that draw themselves,
synthesized sound score), ~45 s vertical video, scheduled on YouTube for 07:00 IST.
Runs on GitHub Actions (see .github/workflows/daily.yml). Nothing needs to be typed by a human.
"""
import os, sys, json, math, base64, time, random, wave, subprocess, datetime, re, asyncio
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import atlas

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
STORY_BRIEF = ("true stories from old history (before 1950) that are built around a ROUTE: a march, journey, voyage, escape, expedition, trade route or campaign across real geography, "
               "the kind a history atlas explains with a line drawn across a map: a clear start place, 3-6 named places along the way, a destination, real dates, approximate distances, "
               "and one number that adds up (km, days, soldiers, ships). A clever trick or jugaad on the way is welcome but not required. Examples of the kind of story: "
               "Shivaji Maharaj's escape from Agra to Raigad, Gandhi's Dandi Salt March (about 390 km), Alexander's march to the Hydaspes, Chandragupta's campaign, Rajendra Chola's march to the Ganga, "
               "Vasco da Gama's voyage to Calicut, Zheng He's voyages, Hannibal crossing the Alps, Napoleon's march to Moscow, Genghis Khan's campaign west, Marco Polo's journey, the Silk Road, "
               "Magellan's circumnavigation, Lewis and Clark, Operation Mincemeat")
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
    used = [t["title"] for t in hist["topics"][-80:]] + [t["wiki"] for t in hist["topics"][-80:] if t.get("wiki")]
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
           "Suggest 10 English Wikipedia article titles (a march, journey, expedition, voyage, escape, campaign or trade-route article) for stories of this type. Each must: "
           "be a clear, well-sourced event whose route, places, dates and distances are documented in the article; be NEW (not in this used list: " + str(used) + "); "
           "be well known or at least exciting for Hindi-speaking youth; contain no graphic gore; avoid anything about religion-versus-religion conflict, "
           "modern politics or events after 1950. "
           "NEVER pick a battle whose story is already uploaded, even under a different name: compare against ALL UPLOADED TITLES above (for example 'Mud Wall' = Battle of Saraighat, 'Sacred Cats' = Battle of Pelusium, "
           "'Local Divers' = Battle of Colachel, 'Impossible Sea Battle' = Battle of Myeongnyang, 'Taj Mahal' = Taj Mahal). "
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
    prompt = f"""You write a 45-second YouTube Short for the channel {CHANNEL}: a gripping true history story built around a ROUTE (a march, journey, voyage, escape or campaign across real places), told the way a history atlas would: where it started, the named places along the way with dates, the key obstacle, the clever move or turning point, and where it ended. It will be shown as a 3D low-poly MAP: a line draws itself from place to place, a red arrow marches along it, name tags and dates pop up, and a counter adds up one number. Use real dates, place names and distances (say 'about' for estimates); never invent numbers.
Use ONLY facts that are stated in this source text (do not add outside facts). The only exception: the approximate latitude and longitude of the named real places, which you give from general geographic knowledge:
{research}

LEARNINGS FROM THIS CHANNEL'S REAL VIEW NUMBERS (apply them):
{LEARN or 'none yet'}

Return JSON with this exact shape:
{{"title": "<Hindi (Devanagari) or Hinglish title, max 60 chars, exactly ONE emoji, built like the best titles of this channel: a direct question or a shock plus a number or the impossible odds; do not reveal the trick; no clickbait lies>",
  "description": "<2-3 Hindi sentences that tease the story and END WITH A QUESTION asking viewers to comment, then 5 hashtags including #Shorts>",
  "tags": ["<10 short tags, mix of Hindi and English>"],
  "title_lines": ["<English headline line 1, max 14 characters, e.g. Hannibal's>", "<English headline line 2, max 14 characters, e.g. Alps March>"],
  "date_chip": "<UPPER CASE English, max 30 chars: the year and the route, e.g. 218 BC · SPAIN TO ITALY>",
  "route": [ {{"name": "<real place, English, max 14 chars>", "lat": 0.0, "lon": 0.0, "date": "<real date or year of arriving there, max 14 chars, or empty>"}} ],
  "extra": [ ],
  "arrow_label": "<UPPER CASE, max 22 chars, who or what marches, with a number if the source gives one, e.g. 37 ELEPHANTS>",
  "counter": {{"value": 0, "unit": "<km|days|soldiers|ships|miles>", "label": "<UPPER CASE English, max 26 chars, what the number counts, e.g. MARCH TO ITALY>", "about": true}},
  "take_lines": ["<English takeaway line 1, max 16 chars>", "<English takeaway line 2, max 16 chars, last word is the punch>"],
  "beats": [ {{"hindi": "...", "english": "..."}} ]}}

Rules:
- "route": 4 to 6 real places IN TRAVEL ORDER (start place first, destination last), at least 80 km apart from each other, each named in the source. lat and lon are decimal degrees (south and west negative). "extra": optional, at most 2 side routes that the source mentions (for example a second army or the return), each {{"points": [{{"lat":..,"lon":..}}, ...]}} with 2-4 points; otherwise [].
- "counter": ONE number that the source states (distance, days, soldiers or ships) as a plain number, with "about" true if the source says about or approximately.
- HOOK (beat 1, the first two seconds): open with the most shocking fact, the impossible odds, or a direct question, in at most 12 Hindi words. Never a greeting, never background first. Style example: तेरह नावें... और सामने एक सौ तैंतीस! फिर भी जीत किसकी हुई?
- SUSPENSE BUILD-UP: beats 2 and 3 raise the stakes and the question "how can they possibly win?" and beat 3 ends on a mini-cliffhanger; hold the trick back until beat 4; beat 5 shows it working step by step; beat 6 is the payoff and says the counter number out loud; beat 7 calls back to the hook. Every beat should end on something that makes the viewer need the next sentence.
- MAP TIMING: the route starts drawing in beat 2 and reaches the destination at the end of beat 5, so beats 2 to 5 must name the places of the route in the same order as "route". Beat 6 must say the counter number. Beat 7 is the lesson and matches take_lines.
- Exactly 7 beats = 7 short sentences, told as a gripping story: 1 hook with the impossible odds, 2 who/where/when, 3 the danger or problem, 4 the clever move or turning point (the key reveal), 5 how the trick worked, 6 the result with the number, 7 a punchy closing line about the lesson. Name the people and the place. If a detail is only legend, say 'कहा जाता है'. Be neutral and respectful to every community, no hatred, no gore.
- "hindi": natural spoken Hindi in Devanagari for a young storyteller. Write ALL numbers and years as Hindi words (दो हज़ार, तेईस...). English technical words must be written in Devanagari (क्विकलाइम). 8-17 words per beat; total 110-125 Hindi words. No emojis.
- "english": a faithful, natural English translation of that beat for captions, max 14 words, numbers as digits.
- Be accurate. Never invent facts that are not in the source text."""
    last = None
    for attempt in range(3):
        resp = gemini_text({"contents": [{"parts": [{"text": prompt}]}],
                                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}})
        try:
            s = json.loads(re.sub(r"^```json|```$", "", text_of(resp).strip(), flags=re.M).strip())
            assert len(s["beats"]) == 7 and all(b["hindi"] and b["english"] for b in s["beats"])
            r = s["route"]; assert 3 <= len(r) <= 6 and all(isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float)) and p.get("name") for p in r)
            assert all(-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180 for p in r)
            assert max(abs(p["lat"] - r[0]["lat"]) + abs(p["lon"] - r[0]["lon"]) for p in r) > 0.8, "route too short on the map"
            s.setdefault("extra", []); s["extra"] = [e for e in s["extra"] if isinstance(e, dict) and len(e.get("points", [])) >= 2 and all(isinstance(q.get("lat"), (int, float)) and isinstance(q.get("lon"), (int, float)) for q in e["points"])][:2]
            c = s["counter"]; assert float(c["value"]) > 0 and c.get("unit") and c.get("label")
            assert len(s["title_lines"]) == 2 and len(s["take_lines"]) == 2 and s.get("date_chip")
            s.setdefault("arrow_label", ""); s["seed"] = today.toordinal() % 1000
            assert re.search(r"[\u0900-\u097F]", s["beats"][0]["hindi"])
            s["wiki"] = title
            return s
        except Exception as e:
            last = e; log("  script invalid, retrying:", e)
    raise RuntimeError(f"script generation failed: {last}")

def offline_script():
    H7 = ["तीस हज़ार सैनिक और सैंतीस हाथी, और सामने आल्प्स के बर्फ़ीले पहाड़!", "दो सौ अठारह ईसा पूर्व में हैनिबल स्पेन से इटली की ओर निकला।", "रास्ते में नदियाँ थीं, कड़ाके की ठंड थी और दुश्मन भी।",
          "फिर उसने वह किया जो कोई सोच भी नहीं सकता था: पहाड़ पार करना।", "सिरका और आग से उसने चट्टानें तोड़ीं, कहा जाता है।", "लगभग पंद्रह सौ किलोमीटर चलकर वह इटली पहुँच गया।", "हिम्मत हो तो पहाड़ भी रास्ता दे देते हैं।"]
    E7 = ["Thirty thousand soldiers, 37 elephants, and the snowy Alps ahead!", "In 218 BC, Hannibal set out from Spain toward Italy.", "Rivers, bitter cold and enemies waited on the way.",
          "Then he did what nobody thought possible: he crossed the mountains.", "Legend says fire and vinegar cracked the rocks.", "After about 1,500 km he reached Italy.", "With courage, even mountains make a road."]
    return {"title": "हैनिबल ने आल्प्स कैसे पार किए? 🐘", "description": "हैनिबल की अनोखी यात्रा। आपको क्या लगता है, कैसे किया उसने? कमेंट करें। #Shorts #History #Hannibal #TruFact #Story", "tags": ["hannibal", "alps", "history"],
            "title_lines": ["Hannibal's", "Alps March"], "date_chip": "218 BC · SPAIN TO ITALY", "seed": 3, "arrow_label": "37 ELEPHANTS",
            "route": [{"name": "CARTHAGO NOVA", "lat": 37.6, "lon": -0.98, "date": "218 BC"}, {"name": "EBRO", "lat": 41.0, "lon": 0.85, "date": "218 BC"}, {"name": "RHONE", "lat": 43.9, "lon": 4.7, "date": "AUTUMN 218 BC"},
                      {"name": "ALPS", "lat": 45.1, "lon": 6.9, "date": "OCT 218 BC"}, {"name": "ITALY", "lat": 45.07, "lon": 7.69, "date": "NOV 218 BC"}], "extra": [],
            "counter": {"value": 1500, "unit": "km", "label": "MARCH TO ITALY", "about": True}, "take_lines": ["Courage beats", "the odds."],
            "beats": [{"hindi": h, "english": e} for h, e in zip(H7, E7)], "wiki": "Hannibal's crossing of the Alps"}

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
    cta = {"hindi": "ऐसे ही हैरान करने वाली कहानियों के लिए, ट्रू फैक्ट को फ़ॉलो करें।", "english": f"Follow {CHANNEL} for a new story every day!"}
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
    # voice-only track: the Low-Poly Atlas sound score (drums, pad, quill, steps, ticks, horn) is rendered in the browser and mixed under it
    nvo = int(total * SR); voice = np.zeros(nvo, np.float32)
    for st, sp in zip(starts, segs):
        i0 = int(st * SR); seg = sp[: max(0, nvo - i0)]; voice[i0: i0 + len(seg)] += seg / 32768
    write_wav(os.path.join(OUT, "voice.wav"), np.clip(voice, -1, 1) * 32767)
    story = atlas.make_story(script, starts, speech_sec, total, brand=CHANNEL)
    json.dump(story, open(os.path.join(OUT, "story.json"), "w"), ensure_ascii=False)
    atlas.render_video(story, os.environ.get("ATLAS_WEB", "atlas_node/web"), os.path.join(OUT, "work"), os.path.join(OUT, "voice.wav"), os.path.join(OUT, "short.mp4"),
                       procs=int(os.environ.get("KIT_PROCS", "4")), log=log)
    log("rendered", os.path.join(OUT, "short.mp4"))
    if OFFLINE or os.environ.get("SKIP_UPLOAD") == "1": log("upload skipped"); return
    res = publish(os.path.join(OUT, "short.mp4"), script)
    mv = re.search(r'"(?:id|videoId)"\s*:\s*"([A-Za-z0-9_-]{11})"', res or "")
    hist["topics"].append({"date": str(datetime.date.today()), "title": script["title"], "wiki": script.get("wiki"), "video_id": mv.group(1) if mv else None, "hook": beats[0]["english"],
                           "beats": [b["english"] for b in script["beats"]], "places": [p["name"] for p in script["route"]]}); hist["topics"] = hist["topics"][-300:]
    json.dump(hist, open(HIST, "w"), indent=1, ensure_ascii=False)
    log("done")

if __name__ == "__main__":
    main()
