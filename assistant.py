import json, os, re, shlex, subprocess, urllib.request, urllib.error
from datetime import datetime, timedelta

BASE = os.path.expanduser("~/assistant")
HIST = os.path.join(BASE, "history.json")
MEM = os.path.join(BASE, "memory.md")
KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
VOICE = False

# ---------- helpers ----------
def read_text(path):
    return open(path).read() if os.path.exists(path) else ""

def load_history():
    try:
        return json.load(open(HIST))
    except Exception:
        return []

def save_history(h):
    json.dump(h[-200:], open(HIST, "w"))

def call_gemini(body):
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)

def run(cmd, stdin=None, timeout=60):
    try:
        p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
        return ((p.stdout or "") + (p.stderr or "")).strip()[:6000] or "done"
    except FileNotFoundError:
        return "Termux:API is missing. Run: pkg install termux-api, and install the Termux:API app."
    except subprocess.TimeoutExpired:
        return "timed out"

def confirm(what):
    ans = input(f"\n[ORACLE wants to {what}] Allow? (y/n): ").strip().lower()
    return ans.startswith("y")

def clean(text):
    return re.sub(r"[*#_`>]", "", text)

def speak(text):
    run(["termux-tts-speak"], stdin=clean(text), timeout=300)

def listen():
    print("Listening... speak now")
    out = run(["termux-speech-to-text"], timeout=60)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines[-1] if lines else ""

# ---------- tools ----------
def web_search(query):
    body = {
        "contents": [{"role": "user", "parts": [{"text": query}]}],
        "tools": [{"google_search": {}}],
    }
    d = call_gemini(body)
    cand = d["candidates"][0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
    srcs = [c["web"].get("title", "") for c in chunks if "web" in c]
    return text + ("\nSources: " + ", ".join(srcs[:5]) if srcs else "")

def remember(fact):
    with open(MEM, "a") as f:
        f.write("- " + fact.strip() + "\n")
    return "saved"

def set_reminder(message, minutes):
    secs = max(0, int(float(minutes) * 60))
    when = (datetime.now() + timedelta(seconds=secs)).strftime("%a %H:%M")
    script = (
        f"sleep {secs}; "
        f"termux-notification --title 'ORACLE reminder' --content {shlex.quote(message)} --sound --vibrate 500; "
        f"termux-tts-speak {shlex.quote(message)}"
    )
    subprocess.Popen(["sh", "-c", script], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run(["termux-wake-lock"], timeout=10)
    return f"Reminder set for {when}. Keep Termux running in the background."

def read_sms(count=5):
    return run(["termux-sms-list", "-l", str(int(count)), "-t", "inbox"])

def send_sms(number, message):
    if not confirm(f"text {number}: \"{message}\""):
        return "User declined. Message not sent."
    return run(["termux-sms-send", "-n", str(number), message])

def find_contact(name):
    try:
        contacts = json.loads(run(["termux-contact-list"]))
    except Exception as e:
        return f"Could not read contacts: {e}"
    hits = [c for c in contacts if name.lower() in c.get("name", "").lower()]
    return json.dumps(hits[:10]) if hits else "No match."

def battery_status():
    return run(["termux-battery-status"])

def get_clipboard():
    return run(["termux-clipboard-get"])

def set_clipboard(text):
    run(["termux-clipboard-set"], stdin=text)
    return "copied"

def read_notifications():
    return run(["termux-notification-list"])

def run_shell(command):
    if not confirm(f"run: {command}"):
        return "User declined."
    return run(["sh", "-c", command], timeout=120)

TOOLS = {f.__name__: f for f in [web_search, remember, set_reminder, read_sms, send_sms,
                                  find_contact, battery_status, get_clipboard, set_clipboard,
                                  read_notifications, run_shell]}

def decl(fname, desc, **props):
    d = {"name": fname, "description": desc}
    if props:
        d["parameters"] = {
            "type": "object",
            "properties": {k: {"type": t, "description": ds} for k, (t, ds) in props.items()},
            "required": list(props.keys()),
        }
    return d

DECLS = [
    decl("web_search", "Search Google for current info: news, prices, weather, facts, anything recent.",
         query=("string", "what to search")),
    decl("remember", "Save a lasting fact or preference about the user.", fact=("string", "the fact")),
    decl("set_reminder", "Set a phone reminder that notifies and speaks after some minutes.",
         message=("string", "reminder text"), minutes=("number", "minutes from now")),
    decl("read_sms", "Read the newest text messages in the inbox.", count=("integer", "how many")),
    decl("send_sms", "Send a text message. The user confirms first.",
         number=("string", "phone number"), message=("string", "text to send")),
    decl("find_contact", "Look up a contact's phone number by name.", name=("string", "name")),
    decl("battery_status", "Get the phone's battery level and charging state."),
    decl("get_clipboard", "Read the phone's clipboard."),
    decl("set_clipboard", "Copy text to the phone's clipboard.", text=("string", "text")),
    decl("read_notifications", "Read the phone's current notifications."),
    decl("run_shell", "Run a Termux shell command. The user confirms first.", command=("string", "command")),
]

# ---------- chat ----------
def trim(history):
    h = history[-40:]
    while h and h[0]["role"] != "user":
        h = h[1:]
    return h

def chat(history, user_text):
    memory = read_text(MEM).strip() or "Nothing yet."
    system = (
        "You are ORACLE, a warm, sharp personal assistant living in Termux on the user's Android phone. "
        f"Now: {datetime.now():%A %Y-%m-%d %H:%M}. Answer first, keep it short and specific. "
        "Use web_search for anything current. Use the phone tools when they help. "
        + ("Voice mode is on: reply in plain spoken sentences, no markdown or lists. " if VOICE else "")
        + f"\nWhat you remember about the user:\n{memory}"
    )
    convo = trim(history) + [{"role": "user", "parts": [{"text": user_text}]}]
    for _ in range(8):
        d = call_gemini({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": convo,
            "tools": [{"function_declarations": DECLS}],
        })
        content = d["candidates"][0].get("content", {"parts": []})
        content["role"] = "model"
        parts = content.get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
            return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip() or "(no reply)"
        convo.append(content)
        responses = []
        for c in calls:
            name, args = c["name"], c.get("args", {})
            print(f"  ... {name}")
            try:
                result = TOOLS[name](**args)
            except Exception as e:
                result = f"error: {e}"
            fr = {"name": name, "response": {"result": result}}
            if "id" in c:
                fr["id"] = c["id"]
            responses.append({"functionResponse": fr})
        convo.append({"role": "user", "parts": responses})
    return "I got stuck using my tools. Try asking another way."

HELP = ("Commands: /voice (talk on/off), /remember <fact>, /memory, /clear, /help, /quit\n"
        "In voice mode, press Enter on an empty line to talk.")

def main():
    global VOICE
    if not KEY:
        print("No GEMINI_API_KEY found. Run: source ~/.bashrc")
        return
    history = load_history()
    print("ORACLE ready. " + HELP)
    while True:
        try:
            msg = input("\nYou" + (" (Enter = talk)" if VOICE else "") + ": ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if VOICE and not msg:
            msg = listen()
            if not msg:
                print("Didn't catch that.")
                continue
            print("You said:", msg)
        if not msg:
            continue
        if msg == "/quit":
            break
        if msg == "/help":
            print(HELP); continue
        if msg == "/voice":
            VOICE = not VOICE
            print("Voice mode " + ("on." if VOICE else "off."))
            continue
        if msg == "/clear":
            history = []; save_history(history)
            print("Chat history cleared (memory kept)."); continue
        if msg == "/memory":
            print(read_text(MEM) or "Memory is empty."); continue
        if msg.startswith("/remember "):
            remember(msg[10:]); print("Saved."); continue
        try:
            reply = chat(history, msg)
        except urllib.error.HTTPError as e:
            print("Error:", e.code, e.read().decode()[:300]); continue
        except Exception as e:
            print("Error:", e); continue
        history.append({"role": "user", "parts": [{"text": msg}]})
        history.append({"role": "model", "parts": [{"text": reply}]})
        save_history(history)
        print("\nORACLE:", reply)
        if VOICE:
            speak(reply)

if __name__ == "__main__":
    main()
