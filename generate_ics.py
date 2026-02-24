def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # タイトル：最初のh1/h2を優先
    title = None
    h = soup.find(["h1", "h2"])
    if h:
        title = " ".join(h.get_text(" ", strip=True).split())
    if not title:
        title = "Schedule"

    # 行として取り出す（全体）
    text = soup.get_text("\n", strip=True)
    raw_lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # 本文開始：最初の「日程」行
    start_idx = 0
    for i, ln in enumerate(raw_lines):
        if ln.startswith("日程"):
            start_idx = i
            break

    # 本文終了：「share」直前（無ければ末尾）
    end_idx = len(raw_lines)
    for i, ln in enumerate(raw_lines):
        if ln.strip().lower() == "share":
            end_idx = i
            break

    # 重要：start/end は「同じ配列(raw_lines)のインデックス」で切る（相対計算しない）
    lines = raw_lines[start_idx:end_idx]

    # ノイズ除去（保守的に）
    def is_noise(ln: str) -> bool:
        lower = ln.lower()
        if lower.startswith("image:"):
            return True
        if ln in {"PREV", "NEXT", "BACK TO LIST"}:
            return True
        # メニュー画像名など（必要に応じて追加）
        if ln in {"ライブスケジュール", "ニューリリース", "チェキレギュレーション", "ファンクラブの楽しみ方", "ショップ"}:
            return True
        return False

    lines = [ln for ln in lines if not is_noise(ln)]

    # 会場抽出：同一行/次行の両方に対応
    location = None
    for i, ln in enumerate(lines):
        if "開催場所・会場" in ln:
            after = ln.split("開催場所・会場", 1)[1].strip()
            if after:
                location = after
            else:
                # 次行が会場名のことがある
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if nxt and nxt.lower() != "map":
                        location = nxt
            break

    # 「会場」だけで書かれているパターンも拾う（念のため）
    if not location:
        for i, ln in enumerate(lines):
            if ln.startswith("会場"):
                after = re.sub(r"^会場[:：]?\s*", "", ln).strip()
                if after:
                    location = after
                else:
                    if i + 1 < len(lines):
                        location = lines[i + 1].strip()
                break

    # 日付：本文部分だけから拾う（複数日対応）
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

    page_text = "\n".join(lines).strip()

    return {
        "title": title,
        "dates": dates,
        "location": location,
        "page_text": page_text,
    }
