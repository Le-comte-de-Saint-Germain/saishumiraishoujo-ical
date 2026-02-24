def extract_detail_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []

    # /schedule/<uuid> だけ拾う（一覧 /schedule や他リンクは捨てる）
    uuid_re = re.compile(r"^/schedule/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue

        # 相対パスのみ判定（絶対URLの場合も /schedule/ を含んでいれば相対に寄せる）
        if href.startswith(BASE):
            href = href[len(BASE):]

        if not uuid_re.match(href):
            continue

        urls.append(BASE + href)

    # 重複除去（順序維持）
    seen = set()
    out = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out
