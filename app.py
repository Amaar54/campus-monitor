from flask import Flask
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

app = Flask(__name__)

URL = "https://www.campusgroningen.com/woning/friesestraatweg-groningen-2168"
EMAIL_TO = "kakehamar@gmail.com"
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

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
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = "🏠 Campus Groningen - Bezichtiging beschikbaar!"
    body = f"""De knop 'Deelnemen' is verschenen op de woningpagina!

Ga nu direct naar:
{URL}

Wees er snel bij!"""
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)

@app.route("/")
def home():
    return "Campus monitor actief!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
