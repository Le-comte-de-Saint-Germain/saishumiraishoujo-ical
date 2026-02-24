import re
import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event

BASE = "https://www.saishumiraishoujo.com"
URL  = BASE + "/schedule"

def main():
    html = requests.get(URL, timeout=30, headers={"User-Agent":"Mozilla/5.0"}).text
    soup = BeautifulSoup(html, "html.parser")

    cal = Calendar()
    seen = set()

    for a in soup.select("a[href]"):
        href = a.get("href","")
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            continue
        if "/schedule" not in href or href == "/schedule":
            continue

        full = href if href.startswith("http") else BASE + href
        key = (text, full)
        if key in seen:
            continue
        seen.add(key)

        # テキスト内に YYYY/MM/DD があるものだけ拾う（最小版）
        m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if not m:
            continue
        y, mo, d = map(int, m.groups())

        e = Event()
        e.name = text
        e.url = full
        e.begin = f"{y:04d}-{mo:02d}-{d:02d}"
        e.make_all_day()
        cal.events.add(e)

    with open("docs/calendar.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

if __name__ == "__main__":
    main()
