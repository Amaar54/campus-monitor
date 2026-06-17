from flask import Flask
import os
import json
import re
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

app = Flask(__name__)

HOME_URL = "https://www.campusgroningen.com"
LOGIN_URL = "https://www.campusgroningen.com/login"
LISTINGS_URL = "https://www.campusgroningen.com/huren-groningen"

EMAIL_TO = ["kakehamar@gmail.com", "liewesjulia@gmail.com"]
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
CAMPUS_EMAIL = os.environ.get("CAMPUS_EMAIL")
CAMPUS_PASSWORD = os.environ.get("CAMPUS_PASSWORD")

DATA_FILE = "bekende_woningen.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ---------- Opslag ----------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("bekende_woningen", [])), set(data.get("deelnemen_gemeld", []))
    return set(), set()


def save_data(bekende, gemeld):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "bekende_woningen": list(bekende),
            "deelnemen_gemeld": list(gemeld)
        }, f)


# ---------- Mail ----------

def send_email(subject, body):
    try:
        requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": "Campus Monitor", "email": "kakehamar@gmail.com"},
                "to": [{"email": e} for e in EMAIL_TO],
                "subject": subject,
                "textContent": body
            },
            timeout=10
        )
    except Exception as e:
        print(f"Email fout: {e}")


# ---------- Login (curl_cffi, want JS-modal accepteert geen plain requests) ----------

def maak_ingelogde_sessie():
    """
    Logt in via curl_cffi (impersonate chrome120) en geeft een sessie terug
    die de open-huis status op woningpaginas kan zien.
    Géén automatische klik op Deelnemen, alleen voor het LEZEN van de status.

    Campus Groningen gebruikt een Yii ActiveForm-widget (form id "form_79")
    in een JS-modal. Velden gevonden via devtools:
      FormWidget[79][ActionLogin][0][0][0][email]
      FormWidget[79][ActionLogin][0][0][0][password]
      full_submit[79] = 1   (geeft aan welk form op de pagina is ingestuurd)
    """
    session = curl_requests.Session(impersonate="chrome120")

    resp = session.get(LOGIN_URL, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_param_meta = soup.find("meta", attrs={"name": "csrf-param"})
    csrf_token = csrf_meta["content"] if csrf_meta else None
    csrf_param = csrf_param_meta["content"] if csrf_param_meta else "_csrf"

    # Form action: probeer het echte form-element te vinden, met fallback naar LOGIN_URL
    login_form = soup.find("form", attrs={"id": re.compile(r"main_form_79|form_79", re.I)}) or soup.find("form")
    action_url = LOGIN_URL
    if login_form and login_form.get("action"):
        a = login_form["action"]
        action_url = HOME_URL + a if a.startswith("/") else a

    payload = {
        "FormWidget[79][ActionLogin][0][0][0][email]": CAMPUS_EMAIL,
        "FormWidget[79][ActionLogin][0][0][0][password]": CAMPUS_PASSWORD,
        "full_submit[79]": "1",
    }
    if csrf_token:
        payload[csrf_param] = csrf_token

    session.post(action_url, data=payload, timeout=20, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": LOGIN_URL,
    })
    return session


def is_ingelogd(session):
    resp = session.get(f"{HOME_URL}/mijn-account", timeout=20)
    return "inloggen" not in resp.text.lower() and "/login" not in resp.url


# ---------- Listings ----------

def haal_listings_op():
    """Lichte requests-call, geen login nodig voor het overzicht."""
    resp = requests.get(LISTINGS_URL, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    woningen = []
    for link in soup.select("a[href*='/woning/']"):
        href = link.get("href", "")
        if not href.startswith("http"):
            href = HOME_URL + href
        titel = link.get_text(strip=True)
        if href not in [w["url"] for w in woningen] and "/woning/" in href:
            woningen.append({"url": href, "titel": titel or href})
    return woningen


# ---------- Open-huis status check (ingelogde sessie nodig) ----------

def check_open_huis_status(session, woning_url):
    """
    Kijkt op de woningpagina (ingelogd) of er een open-huis blok staat
    en wat de knoptekst per tijdslot is: 'Deelnemen' (echt beschikbaar)
    of 'Volgeboekt' (vol, NIET melden).

    Returnt een lijst van dicts: [{"datum": "...", "status": "deelnemen"/"volgeboekt"}]
    """
    resp = session.get(woning_url, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    resultaten = []

    # Het open-huis blok bevat losse rijen met een datum/tijd en een knop ernaast.
    # We zoeken breed naar elk element dat een datum-achtig patroon bevat
    # (dd-mm-jjjj of dd-mm-jj, gevolgd door tijd) en kijken naar de knoptekst
    # die in dezelfde rij/container staat.
    datum_patroon = re.compile(r"\d{2}-\d{2}-(\d{4}|\d{2})\s+\d{2}:\d{2}u?", re.IGNORECASE)

    for el in soup.find_all(string=datum_patroon):
        datum_tekst = el.strip()
        # Loop omhoog naar de gemeenschappelijke rij-container
        rij = el.find_parent()
        knop_tekst = ""
        # Doorzoek een paar niveaus omhoog voor de knoptekst naast de datum
        huidige = rij
        for _ in range(4):
            if huidige is None:
                break
            tekst = huidige.get_text(" ", strip=True).lower()
            if "deelnemen" in tekst or "volgeboekt" in tekst:
                if "volgeboekt" in tekst:
                    knop_tekst = "volgeboekt"
                elif "deelnemen" in tekst:
                    knop_tekst = "deelnemen"
                break
            huidige = huidige.find_parent()

        if knop_tekst:
            resultaten.append({"datum": datum_tekst, "status": knop_tekst})

    return resultaten


# ---------- Hoofd-check ----------

@app.route("/check")
def check():
    try:
        bekende, gemeld = load_data()

        woningen = haal_listings_op()
        nieuwe_woningen = [w for w in woningen if w["url"] not in bekende]

        if nieuwe_woningen:
            tekst = "\n".join(f"- {w['titel']}\n  {w['url']}" for w in nieuwe_woningen)
            send_email(
                f"{len(nieuwe_woningen)} nieuwe woning(en) op Campus Groningen",
                f"Nieuwe woningen gevonden:\n\n{tekst}"
            )
            for w in nieuwe_woningen:
                bekende.add(w["url"])

        # Alleen inloggen en open-huis status checken als er woningen zijn om te checken
        if woningen:
            session = maak_ingelogde_sessie()
            if not is_ingelogd(session):
                send_email("Campus Monitor: login mislukt", "Kon niet inloggen, check credentials.")
                save_data(bekende, gemeld)
                return "Login mislukt", 200

            for w in woningen:
                sloten = check_open_huis_status(session, w["url"])
                for slot in sloten:
                    key = f"{w['url']}|{slot['datum']}"
                    if slot["status"] == "deelnemen" and key not in gemeld:
                        send_email(
                            f"Deelnemen mogelijk: {w['titel']}",
                            f"Open huis op {slot['datum']} staat open voor deelname.\n\n"
                            f"{w['titel']}\n{w['url']}\n\n"
                            f"Log zelf in en klik op Deelnemen om je aan te melden."
                        )
                        gemeld.add(key)

        save_data(bekende, gemeld)
        return f"Check voltooid: {len(woningen)} woningen, {len(nieuwe_woningen)} nieuw", 200

    except Exception as e:
        send_email("Campus Monitor: check gefaald", f"Check gefaald: {str(e)}")
        return f"Error: {e}", 500


@app.route("/")
def home():
    return "Campus monitor actief!", 200


@app.route("/test")
def test():
    send_email("Testmail Campus Monitor", "De monitor werkt nog steeds!")
    return "Testmail verstuurd!", 200


@app.route("/testlogin")
def testlogin():
    session = maak_ingelogde_sessie()
    if is_ingelogd(session):
        return "Login GELUKT", 200
    return "Login MISLUKT - niet ingelogd", 200


@app.route("/debuglogin")
def debuglogin():
    """Tijdelijke route om te zien wat er echt gebeurt tijdens de login-poging."""
    session = curl_requests.Session(impersonate="chrome120")

    resp_get = session.get(LOGIN_URL, timeout=20)
    soup = BeautifulSoup(resp_get.text, "html.parser")

    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_param_meta = soup.find("meta", attrs={"name": "csrf-param"})
    csrf_token = csrf_meta["content"] if csrf_meta else None
    csrf_param = csrf_param_meta["content"] if csrf_param_meta else "_csrf"

    login_form = soup.find("form", attrs={"id": re.compile(r"main_form_79|form_79", re.I)}) or soup.find("form")
    action_url = LOGIN_URL
    if login_form and login_form.get("action"):
        a = login_form["action"]
        action_url = HOME_URL + a if a.startswith("/") else a

    payload = {
        "FormWidget[79][ActionLogin][0][0][0][email]": CAMPUS_EMAIL,
        "FormWidget[79][ActionLogin][0][0][0][password]": CAMPUS_PASSWORD,
        "full_submit[79]": "1",
    }
    if csrf_token:
        payload[csrf_param] = csrf_token

    resp_post = session.post(action_url, data=payload, timeout=20, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": LOGIN_URL,
    })

    account_resp = session.get(f"{HOME_URL}/mijn-account", timeout=20)

    info = (
        f"GET login statuscode: {resp_get.status_code}\n"
        f"Gevonden form-id: {login_form.get('id') if login_form else 'GEEN FORM GEVONDEN'}\n"
        f"Action URL gebruikt: {action_url}\n"
        f"CSRF param: {csrf_param}\n"
        f"CSRF token gevonden: {'JA' if csrf_token else 'NEE'}\n"
        f"\n--- POST login ---\n"
        f"POST statuscode: {resp_post.status_code}\n"
        f"POST eindURL: {resp_post.url}\n"
        f"POST response (eerste 500 tekens):\n{resp_post.text[:500]}\n"
        f"\n--- GET /mijn-account na login ---\n"
        f"Statuscode: {account_resp.status_code}\n"
        f"EindURL: {account_resp.url}\n"
        f"Bevat 'inloggen': {'inloggen' in account_resp.text.lower()}\n"
    )
    return f"<pre>{info}</pre>", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
