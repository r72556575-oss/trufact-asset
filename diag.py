import os, json, requests, base64, time
K = os.environ["GEMINI_API_KEY"]; B = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": K, "Content-Type": "application/json"}
def gen(model, body): return requests.post(f"{B}/models/{model}:generateContent", headers=H, json=body, timeout=180)
def show(label, r):
    try:
        j = r.json()
        if r.status_code != 200:
            e = j.get("error", {}); v = ""
            for d in e.get("details", []):
                for x in d.get("violations", []): v += f" [{x.get('quotaId')}|{x.get('quotaDimensions',{}).get('model')}]"
            print(f"{label}: HTTP {r.status_code} {e.get('status')} | {e.get('message','')[:120]}{v[:300]}")
        else:
            parts = j["candidates"][0]["content"]["parts"] if j.get("candidates") else []
            sizes = [len(p.get("inlineData", {}).get("data", "")) for p in parts]
            print(f"{label}: OK parts={[list(p.keys()) for p in parts][:3]} b64sizes={sizes}")
    except Exception as ex:
        print(f"{label}: HTTP {r.status_code} {r.text[:200]}")
img = {"contents": [{"parts": [{"text": "Flat 2D cartoon illustration, thick black outlines: a happy red apple"}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}}}
for m in ["gemini-3.1-flash-image", "gemini-3.1-flash-lite-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image", "nano-banana-pro-preview", "gemini-2.5-flash-image"]:
    show(f"image {m}", gen(m, img))
srch = {"contents": [{"parts": [{"text": "Tallest mountain? One line."}]}], "tools": [{"google_search": {}}]}
for m in ["gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.8-flash"]:
    show(f"search {m}", gen(m, srch))
# free image service from the runner
try:
    r = requests.get("https://image.pollinations.ai/prompt/flat%202D%20cartoon%20red%20apple%20thick%20black%20outline", params={"width": 768, "height": 1344, "nologo": "true", "model": "flux", "seed": 7}, timeout=120)
    print("pollinations:", r.status_code, r.headers.get("content-type"), len(r.content))
except Exception as e: print("pollinations ERR", e)
# wikipedia extract
try:
    r = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "prop": "extracts", "explaintext": 1, "exchars": 3000, "redirects": 1, "titles": "Roman concrete", "format": "json"}, headers={"User-Agent": "TruFactBot/1.0"}, timeout=30)
    pg = list(r.json()["query"]["pages"].values())[0]; print("wikipedia:", r.status_code, pg.get("title"), len(pg.get("extract", "")))
except Exception as e: print("wikipedia ERR", e)
