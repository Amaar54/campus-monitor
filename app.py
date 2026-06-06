import subprocess
try:
    subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
except Exception as e:
    print(f"Playwright install fout: {e}")

from flask import Flask
import os

app = Flask(__name__)

@app.route("/debug")
def debug():
    email = os.environ.get("CAMPUS_EMAIL")
    password = os.environ.get("CAMPUS_PASSWORD")
    brevo = os.environ.get("BREVO_API_KEY")
    return f"EMAIL: {email}\nPASSWORD: {'ingesteld' if password else 'LEEG'}\nBREVO: {'ingesteld' if brevo else 'LEEG'}"

@app.route("/")
def home():
    return "Campus monitor actief!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
