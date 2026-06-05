from flask import Flask
import os
import json
import asyncio
from playwright.async_api import async_playwright
import requests
import re

app = Flask(__name__)

LISTINGS_URL = "https://www.campusgroningen.com/huren-groningen"
LOGIN_URL = "https://www.campusgroningen.com/login"
EMAIL_TO = ["kakehamar@gmail.com", "liewesjulia@gmail.com"]
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
CAMPUS_EMAIL = os.environ.get("CAMPUS_EMAIL")
CAMPUS_PASSWORD = os.environ.get("CAMPUS_PASSWORD")
DATA_FILE = "bekende_woningen.json"
MIN_M2 = 35

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
    if match:
        return int(match.group(1))
    return None

async def check_and_act():
    bekende, gemeld = load_data()
    resultaten = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context()
        page = await context.new_page()

        # Inloggen
        await page.goto(LOGIN_URL)
        await page.wait_for_load_state("networkidle")
        await page.fill('input[type="email"], input[name="email"], input[name="username"]', CAMPUS_EMAIL)
        await page.fill('input[type="password"]', CAMPUS_PASSWORD)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle")

        # Listings ophalen
        await page.goto(LISTINGS_URL)
        await page.wait_for_load_state("networkidle")
        content = await page.content()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, "html.parser")
        links = soup.find_all("a", href=True)

        woningen = set()
        for link in links:
            href = link["href"]
            if "/woning/" in href:
                full_url = "https://www.campusgroningen.com" + href if href.startswith("/") else href
                woningen.add(full_url)

        nieuwe = woningen - bekende
        if nieuwe:
            bekende.update(nieuwe)
            resultaten.append(f"{len(nieuwe)} nieuwe woning(en) gevonden.")

        # Elke woning checken op Deelnemen + m2
        for url in woningen:
            if url in gemeld:
                continue

            woning_page = await context.new_page()
            await woning_page.goto(url)
            await woning_page.wait_for_load_state("networkidle")
            tekst = await woning_page.inner_text("body")

            # Check oppervlakte
            m2 = extract_m2(tekst)
            if m2 is not None and m2 < MIN_M2:
                await woning_page.close()
                resultaten.append(f"Overgeslagen ({m2}m²): {url}")
                continue

            # Check op Deelnemen knop
            deelnemen_btn = await woning_page.query_selector("text=Deelnemen")
            if deelnemen_btn:
                try:
                    await deelnemen_btn.click()
                    await woning_page.wait_for_load_state("networkidle")

                    bevestig = await woning_page.query_selector("text=Bevestig, text=Ja, text=Bevestigen")
                    if bevestig:
                        await bevestig.click()
                        await woning_page.wait_for_load_state("networkidle")

                    gemeld.add(url)
                    m2_info = f" ({m2}m²)" if m2 else ""
                    send_email(
                        subject=f"✅ Automatisch deelgenomen!{m2_info}",
                        body=f"De monitor heeft automatisch deelgenomen aan:\n{url}{m2_info}\n\nControleer je account op Campus Groningen."
                    )
                    resultaten.append(f"Deelgenomen: {url}")
                except Exception as e:
                    resultaten.append(f"Fout bij deelnemen {url}: {e}")

            await woning_page.close()

        save_data(bekende, gemeld)
        await browser.close()

    return resultaten

@app.route("/check")
def check():
    try:
        resultaten = asyncio.run(check_and_act())
        return "\n".join(resultaten) if resultaten else "Niets nieuws.", 200
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
