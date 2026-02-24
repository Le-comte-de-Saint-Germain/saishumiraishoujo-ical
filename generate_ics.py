import os
import re
import time
import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event

BASE = "https://www.saishumiraishoujo.com"
SCHEDULE = BASE + "/schedule"

# 一覧に出る日付（例: 2026.02.01 / 2026/02/01 / 2026-02-01）
LIST_DATE_RE = re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})")

# /schedule/<uuid> だけを許可（一覧 /schedule は除外）
UUID_PATH_RE = re.compile(
    r"^/schedule/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# タイトル先頭の余計な部分を落とす
TITLE_PREFIX_RE = re.compile(
    r"^\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})\s*(\[[A-Za-z]{3}\])?\s*",
    re.IGNORECASE
)

# 先頭1語だけ落とす対象（ALL以外のタブ）
LABELS_TO_STRIP = {
    "LIVE", "EVENT", "TV", "RADIO", "MAGAZINE", "OTHER",
}


def clean(s: str) -> str:
    return " ".join(s.split()).strip()


def normalize_event_name(list_text: str) -> str:
    """
    例: '2026.02.01 [SUN] EVENT 〜タイトル〜' -> '〜タイトル〜'
        '2026.02.01 [SUN] LIVE 〜タイトル〜'  -> '〜タイトル〜'
    ※先頭のラベルは「1語だけ」除去。2語目以降のLIVE等は残る。
    """
    s = clean(list_text)

    # 先頭の日付 + [SUN] を落とす
    s = TITLE_PREFIX_RE.sub("", s).strip()

    # 先頭のラベル（EVENT/LIVE/TV...）を1つだけ落とす
    parts = s.split(maxsplit=1)
    if parts and parts[0].upper() in LABELS_TO_STRIP:
        s = parts[1] if len(parts) == 2 else ""

    # 記号が残ることがあるので整える
    s = s.lstrip(":-｜|–—・").strip()

    # 何も残らない事故の保険
    return s or clean(list_text)


def fetch(url: str, session: requests.Session) -> str:
    r = session.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text


def schedule_page_url(page: int) -> str:
    return SCHEDULE if page == 1 else f"{SCHEDULE}?page={page}"


def parse_list_page(html: str) -> list[dict]:
    """
    一覧ページから「日付・表示名・詳細URL」を抽出する。
    ここで確定した日付/名前は後段で絶対に変えない（ただし名前は一覧文字列を整形したもの）。
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        # 絶対URLなら相対化
        if href.startswith(BASE):
            href = href[len(BASE):]

        if not UUID_PATH_RE.match(href):
            continue

        text = clean(a.get_text(" ", strip=True))
        if not text:
            continue

        # 日付は「一覧テキスト」からだけ拾う（詳細ページの投稿日等を拾わない）
        m = LIST_DATE_RE.search(text)
        if not m:
            continue
        y, mo, d = map(int, m.groups())

        items.append({
            "y": y, "m": mo, "d": d,
            "name": normalize_event_name(text),  # ★ここで整形
            "url": BASE + href,                  # 詳細URL
        })

    # 同一ページ内重複除去（順序維持）
    seen = set()
    out: list[dict] = []
    for it in items:
        key = (it["y"], it["m"], it["d"], it["name"], it["url"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def bad_location(s: str) -> bool:
    if not s:
        return True
    low = s.lower()
    if low in {"map", "google", "google map", "google maps"}:
        return True
    if low.startswith("http"):
        return True
    return False


def extract_location_from_detail(html: str) -> str | None:
    """
    詳細ページからLOCATIONだけ取る。
    日付やタイトルは一切取らない。
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [clean(ln) for ln in text.split("\n") if clean(ln)]

    labels = ["開催場所・会場", "開催場所", "会場"]

    for label in labels:
        for i, ln in enumerate(lines):
            if label in ln:
                after = clean(ln.split(label, 1)[1])
                if after and not bad_location(after):
                    return after
                # 次行以降に値が来る場合（map/URL等を飛ばす）
                for j in range(1, 6):
                    if i + j < len(lines):
                        cand = clean(lines[i + j])
                        if cand and not bad_location(cand):
                            return cand
    return None


def main() -> None:
    os.makedirs("docs", exist_ok=True)

    session = requests.Session()

    # 1) 一覧を全ページ走査して「日付・名前・詳細URL」を確定収集
    collected: list[dict] = []
    seen_keys = set()

    page = 1
    while True:
        html = fetch(schedule_page_url(page), session)
        items = parse_list_page(html)

        new = 0
        for it in items:
            key = (it["y"], it["m"], it["d"], it["name"], it["url"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            collected.append(it)
            new += 1

        if new == 0:
            break

        page += 1
        time.sleep(0.5)

    # 2) 詳細ページは LOCATION 取得だけに使う（名前・日付は変更しない）
    location_cache: dict[str, str | None] = {}

    cal = Calendar()

    for it in collected:
        url = it["url"]
        if url not in location_cache:
            detail_html = fetch(url, session)
            location_cache[url] = extract_location_from_detail(detail_html)
            time.sleep(0.3)

        e = Event()
        e.name = it["name"]
        e.begin = f"{it['y']:04d}-{it['m']:02d}-{it['d']:02d}"
        e.make_all_day()
        e.url = url
        e.description = ""  # メモ欄は空（URL欄だけ使う）

        loc = location_cache[url]
        if loc:
            e.location = loc

        e.uid = f"{it['y']:04d}{it['m']:02d}{it['d']:02d}:{url}"
        cal.events.add(e)

    ics_text = "".join(cal.serialize_iter())

    with open("docs/sms-schedule.ics", "w", encoding="utf-8") as f:
        f.write(ics_text)


if __name__ == "__main__":
    main()
