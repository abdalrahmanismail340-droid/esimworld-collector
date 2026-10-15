from flask import Flask, render_template, request, jsonify
import requests
import os
import threading
import time
import random
import re

app = Flask(__name__)

API = "https://api.esimworld.com"
WWW = "https://www.esimworld.com"
TM_NS = "skawx"

# Telegram bot
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_API = f"https://api.telegram.org/bot{TG_TOKEN}" if TG_TOKEN else None

def tg_send(chat_id, text):
    if not TG_API: return
    try:
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except: pass

# Quiz answers
QUIZ_ANSWERS = ["Pumpkin", "Passport", "Mobile connectivity", "Orange", "Boarding pass"]

def safe_json(r, step):
    """Parse JSON safely, raise with step name on failure."""
    try:
        return r.json()
    except Exception as e:
        raise Exception(f"{step}: رد السيرفر مش JSON (HTTP {r.status_code}, أول 50 حرف: {r.text[:50]})")

def collect_flow(chat_id, count=1):
    """Full collection flow: register -> verify -> games. Runs in background."""
    for n in range(count):
        try:
            if count > 1:
                tg_send(chat_id, f"\U0001f4dd الحساب {n+1}/{count}...")
            tag = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
            email = f"{TM_NS}.{tag}@inbox.testmail.app"
            password = "Aboud123!#"

            # Register
            r = requests.post(f"{API}/api/customer/auth/register",
                json={"name": "Collector", "email": email, "password": password},
                headers={"Content-Type": "application/json"}, timeout=15)
            if r.status_code != 200:
                tg_send(chat_id, f"\u274c الحساب {n+1}: التسجيل فشل")
                continue

            # Login
            r = requests.post(f"{API}/api/customer/auth/login",
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"}, timeout=15)
            j = safe_json(r, "تسجيل الدخول")
            token = j.get("access_token") or j.get("token")
            if not token:
                tg_send(chat_id, f"\u274c الحساب {n+1}: الدخول فشل")
                continue
            H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            # Send verification
            requests.post(f"{API}/api/customer/auth/send-verification", json={"email": email}, headers=H, timeout=10)

            # Poll testmail for code
            tm_key = os.environ.get("TESTMAIL_API_KEY", "").strip()
            code = None
            for _ in range(20):
                time.sleep(10)
                try:
                    r = requests.get(f"https://api.testmail.app/api/json?apikey={tm_key}&namespace={TM_NS}&tag={tag}&pretty=true",
                        headers={"Authorization": f"Bearer {tm_key}"}, timeout=15)
                    for em in safe_json(r, "قراءة الإيميل").get("emails", []):
                        if "verif" in em.get("subject", "").lower():
                            m = re.search(r'<div class="code">(\d{6})</div>', em.get("html", ""))
                            if m:
                                code = m.group(1)
                                break
                    if code: break
                except: pass

            if not code:
                tg_send(chat_id, f"\u274c الحساب {n+1}: الكود موصلش\n\U0001f4e7 {email}\n\U0001f511 {password}")
                continue

            # Verify
            requests.post(f"{API}/api/customer/auth/verify-email", json={"email": email, "code": code}, headers=H, timeout=10)

            # Riddle quiz
            r = requests.get(f"{API}/api/customer/games/spooky-riddle", headers=H, timeout=10)
            questions = safe_json(r, "جلب الأسئلة").get("questions", [])
            for i, q in enumerate(questions):
                qid = q["id"]
                options = q.get("options", [])
                answer = QUIZ_ANSWERS[i] if i < len(QUIZ_ANSWERS) else None
                idx = options.index(answer) if answer in options else 0
                requests.post(f"{API}/api/customer/games/spooky-riddle/answer",
                    json={"question_id": qid, "option": idx}, headers=H, timeout=10)
                time.sleep(1)

            # Treat + Trick
            requests.post(f"{API}/api/customer/games/trick-or-treat/treat", json={}, headers=H, timeout=10)
            requests.post(f"{API}/api/customer/games/trick-or-treat/trick", json={"pumpkin": 0}, headers=H, timeout=10)

            tg_send(chat_id, f"\u2705 الحساب {n+1} خلص!\n\U0001f4e7 {email}\n\U0001f511 {password}\n\u23f3 الرصيد هيوصل كمان دقايق.")
            time.sleep(5)  # small delay between accounts
        except Exception as e:
            tg_send(chat_id, f"\u274c الحساب {n+1} خطأ: {str(e)[:80]}")

    tg_send(chat_id, f"\U0001f3c1 خلصت {count} حساب!")


@app.route("/telegram/webhook", methods=["POST"])
def tg_webhook():
    if not TG_API:
        return jsonify({"error": "bot not configured"}), 500
    update = request.get_json(silent=True) or {}
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "").strip()

    if not chat_id: return jsonify({"ok": True})

    if text == "/start":
        tg_send(chat_id, "🎃 أهلاً بيك في بوت تجميع رصيد eSIM World!\n\nالأوامر:\n/collect - حساب واحد ($4)\n/collect <عدد> - كذا حساب (مثال: /collect 5)\n\nالبوت مفتوح للكل!")
    elif text.startswith("/collect"):
        parts = text.split()
        count = 1
        if len(parts) > 1:
            try:
                count = int(parts[1])
            except: pass
        if count < 1: count = 1
        if count > 10:
            tg_send(chat_id, "⚠️ الحد الأقصى 10 حسابات في المرة (عشان الـ quota).")
            count = 10
        tg_send(chat_id, f"⏳ هعمل {count} حساب... هياخد وقت.")
        t = threading.Thread(target=collect_flow, args=(chat_id, count), daemon=True)
        t.start()
    else:
        tg_send(chat_id, "استخدم /collect عشان تبدأ!")

    return jsonify({"ok": True})

@app.route("/telegram/setwebhook")
def tg_setwebhook():
    """Helper to set webhook URL. Call once after deploy."""
    if not TG_API:
        return "Bot token not set!", 500
    host = request.host
    url = f"https://{host}/telegram/webhook"
    r = requests.post(f"{TG_API}/setWebhook", json={"url": url}, timeout=10)
    return r.text

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/proxy/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy(subpath):
    """Proxy API calls to avoid CORS."""
    if subpath.startswith("www/"):
        target = WWW + "/" + subpath[4:]
    elif subpath.startswith("bulkmail/"):
        target = "https://bulkmail.shop/" + subpath[9:]
    elif subpath.startswith("mailtm/"):
        target = "https://api.mail.tm/" + subpath[7:]
    elif subpath.startswith("testmail/"):
        tm_key = os.environ.get("TESTMAIL_API_KEY", "").strip()
        parts = subpath[9:].split("/")
        ns = parts[0] if len(parts) > 0 else ""
        tag = parts[1] if len(parts) > 1 else ""
        target = f"https://api.testmail.app/api/json?apikey={tm_key}&namespace={ns}&tag={tag}&pretty=true"
        try:
            r = requests.get(target, headers={"Authorization": f"Bearer {tm_key}"}, timeout=30)
            return (r.text, r.status_code, {"Content-Type": "application/json"})
        except Exception as e:
            return jsonify({"error": str(e)}), 502
    else:
        target = API + "/" + subpath

    headers = {"Content-Type": "application/json", "User-Agent": "Dart/3.10 (dart:io)"}
    auth = request.headers.get("Authorization")
    if auth:
        headers["Authorization"] = auth

    try:
        r = requests.request(
            request.method, target,
            headers=headers,
            json=request.get_json(silent=True),
            params=request.args,
            timeout=30
        )
        ct = r.headers.get("Content-Type", "application/json")
        return (r.text, r.status_code, {"Content-Type": ct})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
