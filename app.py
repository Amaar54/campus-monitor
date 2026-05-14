from flask import Flask
import requests
from bs4 import BeautifulSoup
import os
import httpx

app = Flask(__name__)

URL = "https://www.campusgroningen.com/woning/friesestraatweg-groningen-2168"
EMAIL_TO = ["amarkakehking@gmail.com"]
EMAIL_FROM = "onboarding@resend.dev"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

email_sent = False

@app.route("/check")
def check():
    global email_sent
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(URL, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text().lower()
        if "deelnemen" in page_text and not email_sent:
            send_email()
            email_sent = True
            return "FOUND - email sent!", 200
        elif email_sent:
            return "Already notified", 200
        else:
            return "Not available yet", 200
    except Exception as e:
        return f"Error: {e}", 500

def send_email():
    httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": EMAIL_FROM,
            "to": EMAIL_TO,
            "subject": "Campus Groningen - Bezichtiging beschikbaar!",
            "text": f"De knop Deelnemen is verschenen! Ga naar: {URL}"
        }
    )

@app.route("/")
def home():
    return "Campus monitor actief!", 200

@app.route("/test")
def test():
    send_email()
    return "Testmail verstuurd!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
