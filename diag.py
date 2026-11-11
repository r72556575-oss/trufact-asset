import os, json, requests, base64
K = os.environ["GEMINI_API_KEY"]; B = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": K, "Content-Type": "application/json"}
def show(label, r):
    t = r.text
    try:
        j = r.json()
        if r.status_code != 200:
            e = j.get("error", {}); det = json.dumps(e.get("details", ""))[:700]
            print(f"{label}: HTTP {r.status_code} {e.get('status')} | {e.get('message','')[:250]} | {det}")
        else:
            parts = j["candidates"][0]["content"]["parts"] if j.get("candidates") else []
            print(f"{label}: OK  parts={[list(p.keys()) for p in parts][:3]}")
    except Exception as ex:
        print(f"{label}: HTTP {r.status_code} {t[:200]}")
def gen(model, body): return requests.post(f"{B}/models/{model}:generateContent", headers=H, json=body, timeout=180)
r = requests.get(f"{B}/models?pageSize=200", headers=H, timeout=60); print("list models:", r.status_code)
if r.status_code == 200:
    names = [m["name"].replace("models/", "") for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    print("MODELS:", [n for n in names if any(x in n for x in ("flash", "pro", "tts", "image", "lite"))])
txt = {"contents": [{"parts": [{"text": "Say hello in 3 words."}]}]}
for m in ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-3-flash-preview", "gemini-flash-lite-latest"]:
    show(f"text   {m}", gen(m, txt))
srch = {"contents": [{"parts": [{"text": "What is the tallest mountain on Earth? One line."}]}], "tools": [{"google_search": {}}]}
for m in ["gemini-2.5-flash", "gemini-flash-latest"]:
    show(f"search {m}", gen(m, srch))
tts = {"contents": [{"parts": [{"text": "Say cheerfully: hello"}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}}}}
for m in ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]:
    show(f"tts    {m}", gen(m, tts))
img = {"contents": [{"parts": [{"text": "A red apple, flat cartoon"}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}}}
for m in ["gemini-2.5-flash-image"]:
    show(f"image  {m}", gen(m, img))
