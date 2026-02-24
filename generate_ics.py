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

def normalize_text_block(s: str) -> str:
    # 余計な空行を潰しつつ、内容はなるべく保持
    lines = [ln.strip() for ln in s.splitlines()]
    # 連続空行を1つに
    out = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank:
                out.append("")
            blank = True
            continue
        blank = False
        out.append(ln)
    return "\n".join(out).strip()

def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # タイトル：最初のh1/h2を優先
    title = None
    h = soup.find(["h1", "h2"])
    if h:
        title = " ".join(h.get_text(" ", strip=True).split())
    if not title:
        title = "Schedule"

    # ページ全体テキスト（ナビ等も混ざるが、「全部入れる」方針なので許容）
    # ただし極端に長い場合に備えて整形する
    page_text = soup.get_text("\n", strip=True)
    page_text = normalize_text_block(page_text)

    # 行単位
    lines = [ln for ln in page_text.split("\n") if ln.strip()]

    # 日付：ページ内に出てくる日付を“全部”拾う（複数日イベント対策）
    dates = []
    seen = set()
    for ln in lines:
        for m in DATE_ANY_RE.finditer(ln):
            y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
            key = (y, mo, d)
            if key in seen:
                continue
            seen.add(key)
            dates.append(key)

    # 会場：よくあるラベルから抽出（無ければNone）
    location = None
    for ln in lines:
        if ln.startswith("開催場所・会場"):
            location = ln.replace("開催場所・会場", "", 1).strip()
            if location:
                break
        if ln.startswith("会場"):
            cand = re.sub(r"^会場[:：]?\s*", "", ln).strip()
            if cand:
                location = cand
                break

    return {
        "title": title,
        "dates": dates,          # [(y,m,d), ...]
        "location": location,
        "page_text": page_text,  # 説明欄に全部入れる
    }

def main():
    session = requests.Session()

    # 1) 一覧を全ページ走査して詳細URLを集める
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

    # 2) 詳細ページを読んで終日イベント化
    cal = Calendar()

    for url in detail_urls:
        html = fetch(url, session)
        info = parse_detail(html)

        # 日付が取れない（完全に後日発表等）なら、いったんスキップ
        if not info["dates"]:
            continue

        # 説明欄：URL + 全文
        description = f"{url}\n\n{info['page_text']}"

        # 複数日があれば日付ごとに1件作る（終日）
        for (y, m, d) in info["dates"]:
            e = Event()
            e.name = info["title"]
            e.begin = f"{y:04d}-{m:02d}-{d:02d}"
            e.make_all_day()
            e.url = url
            if info["location"]:
                e.location = info["location"]
            e.description = description
            cal.events.add(e)

        time.sleep(0.3)

    with open("docs/calendar.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

if __name__ == "__main__":
    main()
