"""Retry-safe wrapper around generate.py (TruFact daily Short).

Why: when the YouTube upload (Zapier) fails, the old workflow ran generate.py again from the start,
which spent the Gemini quota a second time (topic, script, 4 voice calls) and often failed on a 429.
Here every expensive step is remembered inside the same job, so a retry only repeats what really failed,
and the upload is retried with long waits (Zapier says "throttled").
"""
import os, json, time, asyncio
import numpy as np
import generate, atlas

OUT = generate.OUT
log = generate.log
os.makedirs(OUT, exist_ok=True)

def _p(name):
    return os.path.join(OUT, name)

# 1. script (topic + story): choose it once
_orig_make_script = generate.make_script
def make_script(hist):
    if os.path.exists(_p("script.json")):
        log("resume: using the script from the earlier attempt")
        return json.load(open(_p("script.json")))
    s = _orig_make_script(hist)
    json.dump(s, open(_p("script.json"), "w"), ensure_ascii=False)
    return s
generate.make_script = make_script

# 2. Hindi voice (Gemini TTS): record it once
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

# 3. rendering: render once
_orig_render = atlas.render_video
def render_video(story, web, work, voice, out_mp4, **kw):
    if os.path.exists(out_mp4) and os.path.exists(_p("render.ok")):
        log("resume: video already rendered")
        return
    _orig_render(story, web, work, voice, out_mp4, **kw)
    open(_p("render.ok"), "w").write("ok")
atlas.render_video = render_video

# 4. hosting: one GitHub release per run
_orig_host = generate.host_video
def host_video(path):
    fn = _p("video_url.txt")
    if os.path.exists(fn):
        return open(fn).read().strip()
    url = _orig_host(path)
    open(fn, "w").write(url)
    return url
generate.host_video = host_video

# 5. upload: patient retries (Zapier throttling clears after a while)
WAITS = [0, 180, 420, 900, 1500]
def publish(path, script):
    url = generate.host_video(path)
    pub = generate.next_publish_utc()
    log("video url:", url, "| publishAt", pub)
    args = {"title": script["title"][:95], "description": script["description"] + "\n\nHindi narration, English captions.\n#Shorts",
            "tags": script.get("tags", [])[:12] + ["Shorts"], "privacy_status": "private", "publish_at": pub,
            "made_for_kids": False, "notify_subscribers": True, "default_audio_language": "hi", "video": url}
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

if __name__ == "__main__":
    generate.main()
