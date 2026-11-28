"""TruFact daily Short: retry-safe wrapper + channel-growth rules around generate.py.

Runs instead of generate.py (see kit-daily.yml). Everything here is patched onto generate.py at start-up.

Retry safety (same job): the story, the Hindi voice, the render and the hosted URL are remembered, so a failed upload
never spends the Gemini quota twice; the upload itself is retried with long waits (Zapier says "throttled").

Channel rules (from the owner's audit, 2026-11-26):
  * title fully in Hindi + one emoji + a question; hook in the first 2 s is a question/shock, never "आज हम..."
  * every story differs from the last ones (hooks of recent videos are passed in, openings rotate)
  * every story is fact-checked against its Wikipedia source (editor pass); legend wording "कहा जाता है"; source in the description
  * like/stats are NOT hidden; every video goes into a playlist
  * community step: a question comment on each new public video and short Hindi replies to unanswered comments
    (the YouTube API cannot pin a comment: pin it by hand in Studio)
"""
import os, json, time, asyncio, re, datetime
import numpy as np
import generate, atlas

OUT = generate.OUT
log = generate.log
os.makedirs(OUT, exist_ok=True)
YT = "https://www.googleapis.com/youtube/v3"
DEV = re.compile(r"[\u0900-\u097F]")
PLAYLIST_TITLE = "TruFact: जंग और जुगाड़ की कहानियाँ"
PLAYLIST_DESC = "इतिहास की सबसे चालाक जंगें, सफ़र और जुगाड़ की कहानियाँ। हर रोज़ एक नई कहानी। #TruFact"
QUESTIONS = ["आपको इस कहानी की सबसे हैरान करने वाली बात क्या लगी? कमेंट में बताइए 👇",
             "अगली कहानी किस जंग या सफ़र की चाहिए? नाम कमेंट में लिखिए 👇",
             "अगर आप इस जगह होते, तो क्या करते? अपनी राय कमेंट में बताइए 👇",
             "क्या आप ये कहानी पहले से जानते थे? हाँ या ना, कमेंट में बताइए 👇"]

def _p(name):
    return os.path.join(OUT, name)

def _json_of(txt):
    return json.loads(re.sub(r"^```json|```$", "", txt.strip(), flags=re.M).strip())

# ------------------------------------------------------------------ Zapier / YouTube helpers
def _client():
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    tr = StreamableHttpTransport("https://mcp.zapier.com/api/v1/connect", headers={"Authorization": "Bearer " + os.environ["ZAPIER_MCP_TOKEN"]})
    return Client(tr)

def _txt(res):
    return " ".join(getattr(x, "text", "") or "" for x in res.content)

async def _yt(c, method, url, qs=None, body=None):
    params = {"fail_on_errors": "true", "method": method, "querystring": qs or {}, "url": url}
    if body is not None:
        params["body"] = json.dumps(body)
    tool = "execute_zapier_read_action" if method == "GET" else "execute_zapier_write_action"
    r = await c.call_tool(tool, {"action": "_zap_raw_request", "selected_api": "YouTubeV4CLIAPI", "params": params})
    t = _txt(r)
    if getattr(r, "is_error", False):
        raise RuntimeError("YouTube request failed: " + t[:300])
    o = generate._first_json(t)
    if o and "results" in o:
        return o["results"][0].get("body", {})
    raise RuntimeError("no body from YouTube request: " + t[:200])

# ------------------------------------------------------------------ 1. story: variety rules in the writing prompt
_orig_gemini_text = generate.gemini_text
def gemini_text(body):
    try:
        if body["contents"][0]["parts"][0]["text"].startswith("You write a 45-second"):
            hooks = [t.get("hook") for t in generate.load_history().get("topics", [])[-8:] if t.get("hook")]
            extra = ("\n\nEXTRA CHANNEL RULES (mandatory, they override anything above):\n"
                     "- TITLE: fully in Devanagari Hindi (names of people and places written in Devanagari), exactly ONE emoji, a direct question that ends with '?', max 60 characters.\n"
                     "- HOOK (beat 1): a direct question or a shocking fact in the first two seconds. NEVER begin with a greeting or with 'आज हम', 'आज मैं', 'दोस्तों', 'नमस्कार', 'क्या आप जानते हैं'.\n"
                     "- VARIETY: these were the English hooks of the latest videos: " + json.dumps(hooks, ensure_ascii=False) + ". Use a clearly different opening pattern this time "
                     "(rotate between a direct question, a shocking number, a bold claim, a 'what if', a mystery) and a different story shape in beats 2-7 "
                     "(for example start in the middle of the action, or tell it from the enemy's side). Never reuse the same sentence frames as the earlier videos.\n"
                     "- FACTS: anything that is only a legend or uncertain must be worded with 'कहा जाता है' in that beat.")
            body = json.loads(json.dumps(body))
            body["contents"][0]["parts"][0]["text"] += extra
    except Exception as e:
        log("  variety rules not added:", e)
    return _orig_gemini_text(body)
generate.gemini_text = gemini_text

# remember the Wikipedia text the story is based on (needed for the fact check)
_SRC = {}
_orig_wiki = generate.wiki_extract
def wiki_extract(title):
    t, ex = _orig_wiki(title)
    if ex:
        _SRC["title"], _SRC["text"] = t, ex
    return t, ex
generate.wiki_extract = wiki_extract

BANNED_OPENERS = ("आज हम", "आज मैं", "दोस्तों", "नमस्कार", "क्या आप जानते हैं")

def _edit(s):
    """strict editor: Hindi question title, real hook, fact check against the source. Never raises; changes as little as possible."""
    src = _SRC.get("text")
    if not src or generate.OFFLINE:
        return s
    beats = [{"n": i + 1, "hindi": b["hindi"], "english": b["english"]} for i, b in enumerate(s["beats"])]
    prompt = ("You are the strict editor of the Hindi history Shorts channel TruFact.\nSOURCE TEXT (the only allowed facts):\n" + src[:7000] +
              "\n\nSCRIPT:\ntitle: " + s["title"] + "\ndescription: " + s["description"] + "\nbeats: " + json.dumps(beats, ensure_ascii=False) +
              "\n\nDo these checks and return JSON {\"title\": \"...\", \"description\": \"...\", \"beats\": [{\"n\": 1, \"hindi\": \"...\", \"english\": \"...\"}], \"issues\": [\"...\"]}. "
              "\"beats\" lists ONLY the beats you changed (empty list if none).\n"
              "1. TITLE: fully in Devanagari Hindi (names transliterated into Devanagari), exactly ONE emoji, a direct question ending with '?', max 60 characters, does not reveal the trick. Return the old title unchanged if it already complies.\n"
              "2. HOOK (beat 1): a direct question or a shocking fact, max 12 Hindi words; it must NEVER start with a greeting or with 'आज हम', 'आज मैं', 'दोस्तों', 'नमस्कार', 'क्या आप जानते हैं'. Change it only if it breaks this.\n"
              "3. FACT CHECK: compare every claim (names, dates, numbers, places, who did what) of every beat with the source text. If a claim is NOT in the source, is contradicted by it, or the source calls it a legend/tradition/uncertain, "
              "rewrite that beat so it is correct, or hedge it with 'कहा जाता है'. A rewritten beat has 8-17 Hindi words (all numbers and years written as Hindi words) and a faithful English translation (max 14 words, digits allowed).\n"
              "4. DESCRIPTION: 2-3 Hindi sentences that tease the story and end with a question asking viewers to comment, then 5 hashtags including #Shorts; no claim that is not in the source. Return it unchanged if it complies.\n"
              "Be conservative: change as little as possible.")
    try:
        ed = _json_of(generate.text_of(generate.gemini_text({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}})))
    except Exception as e:
        log("  editor pass unavailable:", e)
        return s
    changed = []
    t = ed.get("title")
    if isinstance(t, str) and DEV.search(t) and ("?" in t or "？" in t) and 0 < len(t) <= 80 and t != s["title"]:
        changed.append("title"); s["title"] = t.strip()
    d = ed.get("description")
    if isinstance(d, str) and DEV.search(d) and 20 <= len(d) <= 900 and d != s["description"]:
        changed.append("description"); s["description"] = d.strip()
    for b in ed.get("beats") or []:
        try:
            n = int(b["n"]); h = b["hindi"].strip(); e = b["english"].strip()
            if 1 <= n <= len(s["beats"]) and DEV.search(h) and 4 <= len(h.split()) <= 22 and e and len(e.split()) <= 20 and not (n == 1 and h.startswith(BANNED_OPENERS)):
                s["beats"][n - 1] = {"hindi": h, "english": e}; changed.append("beat%d" % n)
        except Exception:
            continue
    if s["beats"][0]["hindi"].strip().startswith(BANNED_OPENERS):
        log("  WARNING: the hook still starts with a banned opener")
    log("EDITOR CHANGED:", changed or "nothing", "| ISSUES:", json.dumps(ed.get("issues"), ensure_ascii=False)[:700])
    return s

# 2. script (topic + story + editor pass): choose it once
_orig_make_script = generate.make_script
def make_script(hist):
    fn = _p("script.json")
    if os.path.exists(fn):
        log("resume: using the script from the earlier attempt")
        return json.load(open(fn))
    s = _edit(_orig_make_script(hist))
    json.dump(s, open(fn, "w"), ensure_ascii=False)
    return s
generate.make_script = make_script

# 3. Hindi voice (Gemini TTS): record it once
_orig_build_voice = generate.build_voice
def build_voice(beats):
    fn = _p("voice_segs.npz")
    if os.path.exists(fn):
        d = np.load(fn)
        log("resume: using the voice from the earlier attempt")
        return [d["a%d" % i] for i in range(len(d.files))]
    segs = _orig_build_voice(beats)
    np.savez(fn, **{"a%d" % i: s for i, s in enumerate(segs)})
    return segs
generate.build_voice = build_voice

# 4. rendering: render once
_orig_render = atlas.render_video
def render_video(story, web, work, voice, out_mp4, **kw):
    if os.path.exists(out_mp4) and os.path.exists(_p("render.ok")):
        log("resume: video already rendered")
        return
    _orig_render(story, web, work, voice, out_mp4, **kw)
    open(_p("render.ok"), "w").write("ok")
atlas.render_video = render_video

# 5. hosting: one GitHub release per run
_orig_host = generate.host_video
def host_video(path):
    fn = _p("video_url.txt")
    if os.path.exists(fn):
        return open(fn).read().strip()
    url = _orig_host(path)
    open(fn, "w").write(url)
    return url
generate.host_video = host_video

# ------------------------------------------------------------------ 6. upload + playlist (+ stats stay visible)
async def _add_to_playlist(c, vid):
    pl = await _yt(c, "GET", YT + "/playlists", {"part": "snippet", "mine": "true", "maxResults": "50"})
    pid = next((i["id"] for i in pl.get("items", []) if i["snippet"]["title"] == PLAYLIST_TITLE), None)
    if not pid:
        made = await _yt(c, "POST", YT + "/playlists", {"part": "snippet,status"},
                         {"snippet": {"title": PLAYLIST_TITLE, "description": PLAYLIST_DESC, "defaultLanguage": "hi"}, "status": {"privacyStatus": "public"}})
        pid = made["id"]; log("  created playlist", pid)
    await _yt(c, "POST", YT + "/playlistItems", {"part": "snippet"}, {"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}})
    log("  added to playlist", pid)

async def my_upload(args, pub=None):
    async with _client() as c:
        res = await c.call_tool("execute_zapier_write_action", {"action": "upload_video", "params": args, "selected_api": "YouTubeV4CLIAPI"})
        txt = _txt(res)
        log("  zapier result:", txt[:1500])
        if getattr(res, "is_error", False) or 'isError":true' in txt:
            raise RuntimeError("Zapier upload failed: " + txt[:300])
        m = re.search(r'"(?:id|videoId)"\s*:\s*"([A-Za-z0-9_-]{11})"', txt)
        if not m:
            log("  could not read the video id from the answer")
            return txt
        vid = m.group(1)
        log("  video id:", vid, "| https://www.youtube.com/watch?v=" + vid)
        try:      # keep the schedule and make sure statistics are visible (nothing is hidden any more)
            status = {"privacyStatus": "private", "license": "youtube", "embeddable": True, "publicStatsViewable": True, "selfDeclaredMadeForKids": False}
            if pub:
                status["publishAt"] = pub
            await _yt(c, "PUT", YT + "/videos", {"part": "status"}, {"id": vid, "status": status})
            log("  status set")
        except Exception as e:
            log("  status update failed (video is uploaded):", e)
        try:
            await _add_to_playlist(c, vid)
        except Exception as e:
            log("  playlist step failed (video is uploaded):", e)
        return txt
generate.zapier_upload = my_upload

WAITS = [0, 180, 420, 900, 1500]
def publish(path, script):
    url = generate.host_video(path)
    pub = generate.next_publish_utc()
    log("video url:", url, "| publishAt", pub)
    src = ("\n\nस्रोत (Source): Wikipedia, " + script["wiki"]) if script.get("wiki") else ""
    args = {"title": script["title"][:95], "description": script["description"] + src + "\n\nHindi narration, English captions.\n#Shorts",
            "tags": script.get("tags", [])[:12] + ["Shorts"], "privacy_status": "private", "publish_at": pub,
            "made_for_kids": False, "notify_subscribers": True, "default_audio_language": "hi", "public_stats_viewable": True, "video": url}
    if os.environ.get("PRIVATE_ONLY") == "1":
        args.pop("publish_at", None)
        args["notify_subscribers"] = False
    last = None
    for i, w in enumerate(WAITS):
        if w:
            log("  waiting %d s before upload try %d" % (w, i + 1))
            time.sleep(w)
        try:
            return asyncio.run(generate.zapier_upload(args, args.get("publish_at")))
        except Exception as e:
            last = e
            log("  upload try %d failed: %s" % (i + 1, e))
    raise RuntimeError("YouTube upload failed after %d tries: %s" % (len(WAITS), last))
generate.publish = publish

# ------------------------------------------------------------------ 7. community: question comment + replies
def _gen_replies(items):
    prompt = ("You run the Hindi history Shorts channel TruFact. For each viewer comment below write a short, warm reply in Hindi (Devanagari), 1-2 sentences, max 200 characters: "
              "thank them, or answer using only safe general knowledge (say so if you are not sure). Reply \"SKIP\" for spam, abuse, promotion, links, politics, religion fights, or anything the owner must answer himself. "
              "No hashtags, at most one emoji.\nCOMMENTS: " + json.dumps(items, ensure_ascii=False) +
              "\nReturn JSON: [{\"id\": \"...\", \"reply\": \"...\"}]")
    try:
        data = _json_of(generate.text_of(generate.gemini_text({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.5}})))
    except Exception as e:
        log("  reply writer unavailable:", e)
        return []
    ids = {i["id"] for i in items}
    out = []
    for d in data if isinstance(data, list) else []:
        r = (d.get("reply") or "").strip()
        if d.get("id") in ids and r and r.upper() != "SKIP" and DEV.search(r) and len(r) <= 300 and "http" not in r.lower():
            out.append((d["id"], r))
    return out

async def _community(c):
    ch = await _yt(c, "GET", YT + "/channels", {"mine": "true", "part": "id,contentDetails"})
    item = ch["items"][0]
    me = item["id"]
    up = item["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = await _yt(c, "GET", YT + "/playlistItems", {"playlistId": up, "part": "contentDetails", "maxResults": "10"})
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = []
    for i in pl.get("items", []):
        cd = i["contentDetails"]
        ts = cd.get("videoPublishedAt")
        if ts:
            age = now - datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if datetime.timedelta(0) < age < datetime.timedelta(days=4):
                recent.append(cd["videoId"])
    todo = []
    for vid in recent:
        try:
            th = await _yt(c, "GET", YT + "/commentThreads", {"part": "snippet", "videoId": vid, "maxResults": "30", "order": "time", "textFormat": "plainText"})
        except Exception as e:
            log("  comments not readable for", vid, ":", e)
            continue
        items = th.get("items", [])
        def author(t):
            return (t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId") or {}).get("value")
        if not any(author(t) == me for t in items):
            q = QUESTIONS[(now.toordinal() + len(todo)) % len(QUESTIONS)]
            try:
                await _yt(c, "POST", YT + "/commentThreads", {"part": "snippet"}, {"snippet": {"videoId": vid, "topLevelComment": {"snippet": {"textOriginal": q}}}})
                log("  posted the question comment on", vid)
            except Exception as e:
                log("  could not post the question comment on", vid, ":", e)
        for t in items:
            top = t["snippet"]["topLevelComment"]["snippet"]
            txt = (top.get("textDisplay") or top.get("textOriginal") or "").strip()
            if author(t) == me or t["snippet"].get("totalReplyCount", 0) > 0 or not txt or "http" in txt.lower():
                continue
            todo.append({"id": t["id"], "text": txt[:300], "author": top.get("authorDisplayName", "")})
    replies = _gen_replies(todo[:8]) if todo else []
    for cid, r in replies:
        try:
            await _yt(c, "POST", YT + "/comments", {"part": "snippet"}, {"snippet": {"parentId": cid, "textOriginal": r}})
            log("  replied to", cid, ":", r[:60])
            await asyncio.sleep(2)
        except Exception as e:
            log("  reply failed:", e)
    log("community: %d recent videos, %d unanswered comments, %d replies" % (len(recent), len(todo), len(replies)))

def run_community():
    if generate.OFFLINE or not os.environ.get("ZAPIER_MCP_TOKEN"):
        return
    if any(os.environ.get(k) == "1" for k in ("SKIP_UPLOAD", "ANALYZE_ONLY", "PRIVATE_ONLY")):
        return
    async def go():
        async with _client() as c:
            await _community(c)
    try:
        asyncio.run(go())
    except Exception as e:
        log("community step failed (ignored):", e)

if __name__ == "__main__":
    generate.main()
    run_community()
