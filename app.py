from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

API = "https://api.esimworld.com"
WWW = "https://www.esimworld.com"

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
        # testmail.app proxy - API key from env
        import os
        tm_key = os.environ.get("TESTMAIL_API_KEY", "").strip()
        # subpath is testmail/<namespace>/<tag> -> query API
        parts = subpath[9:].split("/")
        ns = parts[0] if len(parts) > 0 else ""
        tag = parts[1] if len(parts) > 1 else ""
        target = f"https://api.testmail.app/api/json?apikey={tm_key}&namespace={ns}&tag={tag}&pretty=true"
        # GET request to testmail with Bearer header too
        try:
            r = requests.get(target, headers={"Authorization": f"Bearer {tm_key}"}, timeout=30)
            return (r.text, r.status_code, {"Content-Type": "application/json"})
        except Exception as e:
            return jsonify({"error": str(e)}), 502
    else:
        target = API + "/" + subpath

    headers = {"Content-Type": "application/json", "User-Agent": "Dart/3.10 (dart:io)"}
    # Forward Authorization if present
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
        # Pass through actual content type
        ct = r.headers.get("Content-Type", "application/json")
        return (r.text, r.status_code, {"Content-Type": ct})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
