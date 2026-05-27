from flask import Flask
import requests
from bs4 import BeautifulSoup
import os
import json
 
app = Flask(__name__)
 
AANBOD_URL = "https://www.campusgroningen.com/huren-groningen"
EMAIL_TO = ["kakehamar@gmail.com", "liewesjulia@gmail.com"]
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
DATA_FILE = "bekende_woningen.json"
 
def laad_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("bekende", [])), set(data.get("deelnemen", []))
    return set(), set()
 
def sla_op(bekende, deelnemen):
    with open(DATA_FILE, "w") as f:
        json.dump({"bekende": list(bekende), "deelnemen": list(deelnemen)}, f)
 
@app.route("/check")
def check():
    bekende_woningen, deelnemen_gemeld = laad_data()
 
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
 
        response = requests.get(AANBOD_URL, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
 
        woning_links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/woning/" in href:
                if href.startswith("http"):
                    woning_links.add(href)
                else:
                    woning_links.add("https://www.campusgroningen.com" + href)
 
        if not woning_links:
            return "Geen woningen gevonden op aanbodpagina", 200
 
        nieuwe_woningen = []
        deelnemen_woningen = []
 
        for link in woning_links:
            try:
                woning_response = requests.get(link, headers=headers, timeout=10)
                woning_soup = BeautifulSoup(woning_response.text, "html.parser")
                naam = woning_soup.find("h1")
                naam_tekst = naam.get_text(strip=True) if naam else link
                woning_tekst = woning_soup.get_text().lower()
 
                if link not in bekende_woningen:
                    bekende_woningen.add(link)
                    nieuwe_woningen.append({"naam": naam_tekst, "link": link})
 
                if "deelnemen" in woning_tekst and link not in deelnemen_gemeld:
                    deelnemen_gemeld.add(link)
                    deelnemen_woningen.append({"naam": naam_tekst, "link": link})
 
            except Exception:
                continue
 
        sla_op(bekende_woningen, deelnemen_gemeld)
 
        resultaat = []
 
        if nieuwe_woningen:
            send_email(nieuwe_woningen, type="nieuw")
            resultaat.append(f"Nieuwe woningen: {[w['naam'] for w in nieuwe_woningen]}")
 
        if deelnemen_woningen:
            send_email(deelnemen_woningen, type="deelnemen")
            resultaat.append(f"Deelnemen: {[w['naam'] for w in deelnemen_woningen]}")
 
        if not resultaat:
            return f"Niets nieuws ({len(woning_links)} woningen gecheckt)", 200
 
        return " | ".join(resultaat), 200
 
    except Exception as e:
        return f"Error: {e}", 500
 
 
def send_email(woningen, type):
    if type == "nieuw":
        onderwerp = "🏠 Nieuwe woning op Campus Groningen!"
        inhoud = "Er staat een nieuwe woning op het aanbod:\n\n"
    else:
        onderwerp = "⚡ Deelnemen is nu mogelijk - Campus Groningen!"
        inhoud = "De knop Deelnemen is verschenen bij een woning:\n\n"
 
    for w in woningen:
        inhoud += f"- {w['naam']}\n  {w['link']}\n\n"
    inhoud += "Wees er snel bij!"
 
    requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "sender": {"name": "Campus Monitor", "email": "kakehamar@gmail.com"},
            "to": [{"email": e} for e in EMAIL_TO],
            "subject": onderwerp,
            "textContent": inhoud
        }
    )
 
 
@app.route("/")
def home():
    return "Campus monitor actief!", 200
 
 
@app.route("/test")
def test():
    send_email([{"naam": "Testwoning", "link": AANBOD_URL}], type="nieuw")
    return "Testmail verstuurd!", 200
 
 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
 
 
