import re
import time
import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event

BASE = "https://www.saishumiraishoujo.com"
SCHEDULE = BASE + "/schedule"

DATE_RE = re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})")

def fetch_page(page: int) -> str:
    # 1ページ目は /schedule、2ページ目以降は /schedule?page=2
    url = SCHEDULE if page == 1 else f"{SCHEDULE}?page={page}"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def extract_event_links(html: str) -> list[tuple[str, str]]:
    """(text, url) のリストを返す。ページ内の /schedule/<uuid> だけ拾う。"""
    soup = BeautifulSoup(html, "html.parser")
    items: list[tuple[str, str]] = []

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue

        # /schedule そのものは除外し、詳細ページらしきものだけ
        if "/schedule" not in href or href == "/schedule":
            continue

        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            continue

        full = href if href.startswith("http") else BASE + href
        items.append((text, full))

    return items

def main():
    cal = Calendar()

    seen_urls: set[str] = set()      # 既に拾ったイベントURL（全ページ共通）
    added_keys: set[tuple[str, str]] = set()  # (text,url)の重複も念のため

    page = 1
    while True:
        html = fetch_page(page)
        candidates = extract_event_links(html)

        # このページで「新規URL」が1つも増えなければ終端とみなす
        new_count = 0
        for text, url in candidates:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            new_count += 1

            # 日付がテキスト内にあるものだけ（現状仕様）
            m = DATE_RE.search(text)
            if not m:
                continue

            y, mo, d = map(int, m.groups())
            key = (text, url)
            if key in added_keys:
                continue
            added_keys.add(key)

            e = Event()
            e.name = text
            e.url = url
            e.begin = f"{y:04d}-{mo:02d}-{d:02d}"
            e.make_all_day()
            cal.events.add(e)

        if new_count == 0:
            break

        page += 1
        # 礼儀として少し待つ（サイト負荷軽減）
        time.sleep(0.5)

    with open("docs/calendar.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

if __name__ == "__main__":
    main()
