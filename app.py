@app.route("/test")
def test():
    import requests as req
    try:
        r = req.get("https://www.campusgroningen.com/huren-groningen", 
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        woningen = [l["href"] for l in soup.find_all("a", href=True) if "/woning/" in l["href"]]
        return f"Status: {r.status_code} | Woningen gevonden: {len(woningen)}", 200
    except Exception as e:
        return f"Fout: {e}", 500
