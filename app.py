from flask import Flask
import os
import json
from curl_cffi.requests import Session
from bs4 import BeautifulSoup
import requests
import re

app = Flask(__name__)

LISTINGS_URL = "https://www.campusgroningen.com/huren-groningen"
HOME_URL = "https://www.campusgroningen.com"
EMAIL_TO = ["kakehamar@gmail.com", "liewesjulia@gmail.com"]
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
CAMPUS_EMAIL = os.environ.get("CAMPUS_EMAIL")
CAMPUS_PASSWORD = os.environ.get("CAMPUS_PASSWORD")
DATA_FILE = "bekende_woningen.json"
MIN_M2 = 35
MAX_PRIJS = 1350

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("bekende_woningen", [])), set(data.get("deelnemen_gemeld", []))
    return set(), set()

def save_data(bekende, gemeld):
    with open(DATA_FILE, "w") as f:
        json.dump({"bekende_woningen": list(bekende), "deelnemen_gemeld": list(gemeld)}, f)

def send_email(subject, body):
    requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
        json={
            "sender": {"name": "Campus Monitor", "email": "kakehamar@gmail.com"},
            "to": [{"email": e} for e in EMAIL_TO],
            "subject": subject,
            "textContent": body
        }
    )

def extract_m2(text):
    match = re.search(r'(\d+)\s*m[²2]', text, re.IGNORECASE)
    return int(match.group(1)) if match else None

def extract_prijs(text):
    match = re.search(r'€\s*(\d[\d\.]*)', text)
    return float(match.group(1).replace('.', '')) if match else None

def vind_deelnemen_form(soup):
    """Zoekt naar een echte Deelnemen knop in een formulier."""
    for form in soup.find_all("form"):
        knoppen = form.find_all(["button", "input"])
        for knop in knoppen:
            tekst = knop.get_text(strip=True).lower() or knop.get("value", "").lower()
            if "deelnemen" in tekst:
                return form
    return None

def maak_sessie():
    session = Session(impersonate="chrome120")
    resp = session.get(HOME_URL, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    csrf = None
    for inp in soup.find_all('input'):
        if inp.get('name') in ['_token', 'csrf_token', 'csrfmiddlewaretoken']:
            csrf = inp.get('value')
            break
    login_data = {"email": CAMPUS_EMAIL, "password": CAMPUS_PASSWORD}
    if csrf:
        login_data["_token"] = csrf
    session.post(f"{HOME_URL}/login", data=login_data, timeout=15)
    return session

@app.route("/check")
def check():
    try:
        bekende, gemeld = load_data()
        resultaten = []
        session = maak_sessie()

        resp = session.get(LISTINGS_URL, timeout=15)
        resultaten.append(f"Listings status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, "html.parser")

        woningen = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/woning/" in href:
                full_url = HOME_URL + href if href.startswith("/") else href
                woningen.add(full_url)

        resultaten.append(f"Woningen gevonden: {len(woningen)}")
        nieuwe = woningen - bekende
        if nieuwe:
            bekende.update(nieuwe)
            resultaten.append(f"{len(nieuwe)} nieuwe woning(en).")

        for url in woningen:
            if url in gemeld:
                continue
            woning_resp = session.get(url, timeout=15)
            soup_w = BeautifulSoup(woning_resp.text, "html.parser")
            body_tekst = soup_w.get_text()

            m2 = extract_m2(body_tekst)
            if m2 is not None and m2 < MIN_M2:
                resultaten.append(f"Te klein ({m2}m2): {url}")
                continue

            prijs = extract_prijs(body_tekst)
            if prijs is not None and prijs > MAX_PRIJS:
                resultaten.append(f"Te duur (E{int(prijs)}): {url}")
                continue

            # Zoek naar echte Deelnemen knop in formulier
            deelnemen_form = vind_deelnemen_form(soup_w)
            if deelnemen_form:
                action = deelnemen_form.get("action", url)
                form_data = {
                    inp.get("name"): inp.get("value", "")
                    for inp in deelnemen_form.find_all("input")
                    if inp.get("name")
                }
                full_action = action if action.startswith("http") else f"{HOME_URL}{action}"
                session.post(full_action, data=form_data, timeout=15)
                gemeld.add(url)
                m2_info = f" ({m2}m2)" if m2 else ""
                prijs_info = f" E{int(prijs)}" if prijs else ""
                send_email(
                    subject=f"Deelgenomen!{m2_info}{prijs_info}",
                    body=f"Deelgenomen aan:\n{url}\n{m2_info}{prijs_info}\n\nControleer je account."
                )
                resultaten.append(f"Deelgenomen: {url}")

        save_data(bekende, gemeld)
        return "\n".join(resultaten) if resultaten else "Niets nieuws.", 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/")
def home():
    return "Campus monitor actief!", 200

@app.route("/test")
def test():
    send_email("Testmail Campus Monitor", "De monitor werkt nog steeds!")
    return "Testmail verstuurd!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
