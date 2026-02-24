import re
import time
import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event

BASE = "https://www.saishumiraishoujo.com"
SCHEDULE = BASE + "/schedule"

# 例: 2026.02.01 / 2026/2/1 / 2026-02-01 / 2026年2月1日
DATE_ANY_RE = re.compile(
    r"(?P<y>\d{4})\s*(?:[./-]|年)\s*(?P<m>\d{1,2})\s*(?:[./-]|月)\s*(?P<d>\d{1,2})\s*(?:日)?"
)

def fetch(url: str, session: requests.Session) -> str:
    r = session.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def schedule_page_url(page: int) -> str:
    return SCHEDULE if page == 1 else f"{SCHEDULE}?page={page}"

def extract_detail_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        if "/schedule" not in href or href == "/schedule":
            continue
        full = href if href.startswith("http") else BASE + href
        urls.append(full)

    # 重複除去（順序維持）
    seen = set()
    out = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out

def clean(s: str) -> str:
    return " ".join(s.split()).strip()

def bad_location(s: str) -> bool:
    if not s:
        return True
    low = s.lower()
    if low in {"map", "google", "google map", "google maps"}:
        return True
    if low.startswith("http"):
        return True
    return False

def extract_location_from_lines(lines: list[str]) -> str | None:
    """
    ページ全体テキスト(lines)から会場っぽい文字列を拾う。
    ラベルと値が別行でも拾う（次行～数行を探索）。
    """
    labels = ["開催場所・会場", "開催場所", "会場"]

    for label in labels:
        for i, ln in enumerate(lines):
            if label in ln:
                after = clean(ln.split(label, 1)[1])
                if after and not bad_location(after):
                    return after
                # 次行以降に値がある場合（map/URLなどを飛ばす）
                for j in range(1, 5):
                    if i + j < len(lines):
                        cand = clean(lines[i + j])
                        if cand and not bad_location(cand):
                            return cand
    return None

def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # タイトル：最初のh1/h2
    title = None
    h = soup.find(["h1", "h2"])
    if h:
        title = clean(h.get_text(" ", strip=True))
    if not title:
        title = "Schedule"

    # 全文行（LOCATION抽出はここから）
    text = soup.get_text("\n", strip=True)
    raw_lines = [clean(ln) for ln in text.split("\n") if clean(ln)]

    # 日付（複数日対応。見つからなければ空）
    dates = []
    seen = set()
    for ln in raw_lines:
        for m in DATE_ANY_RE.finditer(ln):
            y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
            key = (y, mo, d)
            if key in seen:
                continue
            seen.add(key)
            dates.append(key)

    location = extract_location_from_lines(raw_lines)

    return {"title": title, "dates": dates, "location": location}

def main():
    session = requests.Session()

    # 一覧を全ページ走査して詳細URL収集
    detail_urls: list[str] = []
    seen_urls = set()

    page = 1
    while True:
        html = fetch(schedule_page_url(page), session)
        urls = extract_detail_urls(html)

        new = 0
        for u in urls:
            if u in seen_urls:
                continue
            seen_urls.add(u)
            detail_urls.append(u)
            new += 1

        if new == 0:
            break

        page += 1
        time.sleep(0.5)

    cal = Calendar()

    for url in detail_urls:
        html = fetch(url, session)
        info = parse_detail(html)

        # 日付が無い（後日発表等）はスキップ（必要なら後で「未定」カレンダーを別に作る）
        if not info["dates"]:
            continue

        for (y, m, d) in info["dates"]:
            e = Event()
            e.name = info["title"]
            e.begin = f"{y:04d}-{m:02d}-{d:02d}"
            e.make_all_day()
            e.url = url
            e.description = url  # ★URLだけ
            if info["location"]:
                e.location = info["location"]
            cal.events.add(e)

        time.sleep(0.3)

    with open("docs/calendar.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

if __name__ == "__main__":
    main()
