"""SQLite reads for the API: search, profile, featured pages, shuffle, stats."""
import random

import dataroot  # noqa: F401
import db
import search as datasearch   # reuse embed_query (OpenAI text-embedding-3-large)
import settings
import vectors


def parse_year(year: str):
    """Returns (lo, hi) where either bound may be None for an open range.
    '1990-2005' -> ('1990','2005'); '2005-' -> ('2005', None); '-2008' -> (None,'2008');
    '1998' -> ('1998','1998')."""
    if not year:
        return None
    year = year.strip()
    if not year:
        return None
    if "-" in year:
        lo, hi = year.split("-", 1)
        lo, hi = (lo.strip() or None), (hi.strip() or None)
        return None if (lo is None and hi is None) else (lo, hi)
    return (year, year)


def _interests(row, limit=12):
    raw = (row["interests_agg"] or "").split(";")
    out = [s.strip() for s in raw if s.strip()]
    return out[:limit]


_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v", "vi"}


def split_name(full: str):
    """('Joseph C. Tsai') -> ('Joseph C.', 'Tsai'); keeps a generational suffix on the last name."""
    toks = (full or "").split()
    suffix = ""
    if toks and toks[-1].lower().strip(".") in _SUFFIX:
        suffix = toks.pop()
    if not toks:
        return ("", full or "")
    last = toks[-1] + (f" {suffix}" if suffix else "")
    return (" ".join(toks[:-1]), last)


def featured_pages(conn, ckey):
    rows = conn.execute(
        """SELECT d.title, d.slug, d.url, m.page_num, m.snippet, d.publish_date
           FROM profile_aliases pa
           JOIN people pe ON pe.person_key = pa.person_key
           JOIN mentions m ON m.person_id = pe.id
           JOIN documents d ON d.id = m.document_id
           WHERE pa.canonical_key = ? AND m.page_num IS NOT NULL
           ORDER BY d.publish_date, d.title, m.page_num""",
        (ckey,)).fetchall()
    seen, out = set(), []
    for r in rows:
        key = (r["slug"], r["page_num"])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "document": r["title"], "page": r["page_num"],
            "issuu": f"{r['url']}/{r['page_num']}" if r["url"] else None,
            "thumb": f"/img/{r['slug']}/{r['page_num']}?w=420",
            "full": f"/img/{r['slug']}/{r['page_num']}?full=1",
            "snippet": r["snippet"],
        })
    return out


def _card(conn, ckey, score=None):
    r = conn.execute(
        """SELECT canonical_key, full_name, class_year, role, doc_count, mention_count,
                  interests_agg FROM profiles WHERE canonical_key=?""", (ckey,)).fetchone()
    if not r or _is_junk(r["full_name"]):
        return None
    pages = featured_pages(conn, ckey)
    return {
        "key": r["canonical_key"], "name": r["full_name"], "class_year": r["class_year"],
        "role": r["role"], "doc_count": r["doc_count"], "mention_count": r["mention_count"],
        "interests": _interests(r, 6),
        "thumb": pages[0]["thumb"] if pages else None,
        "score": round(score, 4) if score is not None else None,
    }


def keyword_search(conn, q, role, yrange, n):
    out = []
    if db.has_fts(conn) and conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='profiles_fts'").fetchone():
        try:
            rows = conn.execute(
                """SELECT p.canonical_key, bm25(profiles_fts) AS rank
                   FROM profiles_fts JOIN profiles p ON p.canonical_key=profiles_fts.canonical_key
                   WHERE profiles_fts MATCH ? ORDER BY rank LIMIT ?""",
                (q, n * 5)).fetchall()
            for r in rows:
                out.append((r["canonical_key"], -r["rank"]))
        except Exception:  # noqa: BLE001
            out = []
    if not out:
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT canonical_key, mention_count FROM profiles
               WHERE profile_text LIKE ? OR full_name LIKE ?
               ORDER BY mention_count DESC LIMIT ?""", (like, like, n * 5)).fetchall()
        out = [(r["canonical_key"], float(r["mention_count"])) for r in rows]
    # apply role/year filters via the profiles row
    filtered = []
    for ckey, sc in out:
        pr = conn.execute("SELECT role, class_year, full_name FROM profiles WHERE canonical_key=?",
                          (ckey,)).fetchone()
        if not pr or _is_junk(pr["full_name"]):
            continue
        if role and (pr["role"] or "") != role:
            continue
        if yrange:
            y = pr["class_year"]
            lo, hi = yrange
            if not y or (lo and y < lo) or (hi and y > hi):
                continue
        filtered.append((ckey, sc))
        if len(filtered) >= n:
            break
    return filtered


def run_search(conn, q, mode, role, yrange, n):
    q = (q or "").strip()
    if not q:
        return []
    cards, seen = [], set()
    if mode in ("semantic", "hybrid"):
        try:
            qv = datasearch.embed_query(q)
            for ckey, score in vectors.search(qv, role, yrange, n):
                if ckey not in seen:
                    seen.add(ckey)
                    c = _card(conn, ckey, score)
                    if c:
                        cards.append(c)
        except Exception as e:  # noqa: BLE001
            print("semantic search error:", e)
    if mode in ("keyword", "hybrid"):
        for ckey, sc in keyword_search(conn, q, role, yrange, n):
            if ckey not in seen:
                seen.add(ckey)
                c = _card(conn, ckey, None)
                if c:
                    cards.append(c)
    return cards[:n]


def shuffle(conn, theme_key, q, n):
    theme = settings.THEME_BY_KEY.get(theme_key)
    query = (theme["query"] if theme else "") or (q or "")
    if not query:
        return []
    try:
        qv = datasearch.embed_query(query)
    except Exception as e:  # noqa: BLE001
        print("shuffle embed error:", e)
        return []
    hits = vectors.search(qv, None, None, max(n * 2, 40))
    random.shuffle(hits)
    cards = []
    for ckey, score in hits[:n]:
        c = _card(conn, ckey, score)
        if c:
            cards.append(c)
    return cards


def discover(conn, n=12):
    rows = conn.execute(
        "SELECT canonical_key FROM profiles WHERE doc_count >= 2 AND interests_agg != '' "
        "AND " + NOT_JUNK + " ORDER BY RANDOM() LIMIT ?",
        (n,)).fetchall()
    return [c for c in (_card(conn, r["canonical_key"]) for r in rows) if c]


SORTS = {
    "mentions": "mention_count DESC, full_name COLLATE NOCASE",
    "name": "full_name COLLATE NOCASE",
    "year": "class_year DESC, full_name COLLATE NOCASE",
    "docs": "doc_count DESC, full_name COLLATE NOCASE",
}


NOT_JUNK = ("full_name NOT LIKE '[%' AND full_name NOT GLOB '[0-9]*' "
            "AND full_name NOT LIKE 'and %' AND full_name NOT LIKE 'the %' "
            "AND full_name NOT LIKE '& %'")


def _is_junk(name: str) -> bool:
    n = (name or "").strip()
    if not n or n[0] in "[(" or n[0].isdigit() or len(n) < 3:
        return True
    return n.lower().startswith(("and ", "the ", "& "))


def _filter_sql(role, yrange):
    clauses, params = [NOT_JUNK], []
    if role:
        clauses.append("role = ?")
        params.append(role)
    if yrange:
        lo, hi = yrange
        if lo:
            clauses.append("class_year >= ?")
            params.append(lo)
        if hi:
            clauses.append("class_year <= ?")
            params.append(hi)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _sources_for_keys(conn, keys):
    """One representative source page per canonical_key (thumbnail + Issuu deep link), one query."""
    if not keys:
        return {}
    ph = ",".join("?" * len(keys))
    rows = conn.execute(
        f"""SELECT ck, slug, page_num, url, title FROM (
              SELECT pa.canonical_key AS ck, d.slug AS slug, m.page_num AS page_num,
                d.url AS url, d.title AS title,
                ROW_NUMBER() OVER (PARTITION BY pa.canonical_key
                                   ORDER BY d.publish_date, m.page_num) AS rn
              FROM profile_aliases pa
              JOIN people pe ON pe.person_key = pa.person_key
              JOIN mentions m ON m.person_id = pe.id
              JOIN documents d ON d.id = m.document_id
              WHERE pa.canonical_key IN ({ph}) AND m.page_num IS NOT NULL
            ) WHERE rn = 1""", keys).fetchall()
    return {r["ck"]: {
        "thumb": f"/img/{r['slug']}/{r['page_num']}?w=300",
        "image": f"/img/{r['slug']}/{r['page_num']}?full=1",
        "image_path": str(settings.RAW / r["slug"] / f"page_{r['page_num']:03d}.jpg"),
        "issuu": f"{r['url']}/{r['page_num']}" if r["url"] else None,
        "doc": r["title"], "page": r["page_num"],
    } for r in rows}


def _cards_for_keys(conn, keys):
    """Build cards for many keys with just two queries (profiles + one thumb each)."""
    if not keys:
        return []
    ph = ",".join("?" * len(keys))
    prof = {r["canonical_key"]: r for r in conn.execute(
        f"""SELECT canonical_key, full_name, class_year, role, doc_count, mention_count,
                   interests_agg FROM profiles WHERE canonical_key IN ({ph})""", keys)}
    src = _sources_for_keys(conn, keys)
    out = []
    for k in keys:                       # preserve incoming order
        r = prof.get(k)
        if not r or _is_junk(r["full_name"]):
            continue
        fn, ln = split_name(r["full_name"])
        s = src.get(k) or {}
        out.append({
            "key": k, "name": r["full_name"], "first_name": fn, "last_name": ln,
            "class_year": r["class_year"], "role": r["role"], "doc_count": r["doc_count"],
            "mention_count": r["mention_count"], "interests": _interests(r, 6),
            "thumb": s.get("thumb"), "source_url": s.get("issuu"),
            "source_image": s.get("image"), "source_doc": s.get("doc"),
            "source_page": s.get("page"), "score": None,
        })
    return out


def export_rows(conn, q, mode, role, yrange, sort, cap=20000):
    """All matching profiles (respecting the current filters/search) as flat rows for CSV."""
    q = (q or "").strip()
    if q:
        if mode == "semantic":
            try:
                qv = datasearch.embed_query(q)
            except Exception:  # noqa: BLE001
                return []
            keys = [k for k, _ in vectors.search(qv, role, yrange, min(cap, 1000))]
        else:
            keys = [k for k, _ in keyword_search(conn, q, role, yrange, min(cap, 5000))]
    else:
        where, params = _filter_sql(role, yrange)
        order = SORTS.get(sort, SORTS["mentions"])
        keys = [r["canonical_key"] for r in conn.execute(
            f"SELECT canonical_key FROM profiles{where} ORDER BY {order} LIMIT ?",
            params + [cap]).fetchall()]
    if not keys:
        return []
    ph = ",".join("?" * len(keys))
    prof = {r["canonical_key"]: r for r in conn.execute(
        f"""SELECT canonical_key, full_name, class_year, class_year_tags, role, doc_count,
                   mention_count, interests_agg FROM profiles WHERE canonical_key IN ({ph})""",
        keys)}
    src = _sources_for_keys(conn, keys)
    rows = []
    for k in keys:
        r = prof.get(k)
        if not r or _is_junk(r["full_name"]):
            continue
        fn, ln = split_name(r["full_name"])
        s = src.get(k) or {}
        rows.append({
            "first_name": fn, "last_name": ln, "class_year": r["class_year"] or "",
            "role": r["role"] or "", "mentions": r["mention_count"],
            "publications": r["doc_count"], "class_year_tags": r["class_year_tags"] or "",
            "interests": r["interests_agg"] or "", "full_name": r["full_name"],
            "source_document": s.get("doc") or "", "source_url": s.get("issuu") or "",
            "source_image_url": s.get("image") or "", "source_image_path": s.get("image_path") or "",
            "profile_path": f"/p/{k}",
        })
    return rows


def browse(conn, q, mode, role, yrange, sort, offset, limit):
    """Paginated directory. No query -> all profiles (filtered/sorted). Query -> search hits."""
    limit = min(max(int(limit), 1), 120)
    offset = max(int(offset), 0)
    q = (q or "").strip()
    if q:
        if mode == "semantic":
            try:
                qv = datasearch.embed_query(q)
            except Exception as e:  # noqa: BLE001
                print("browse semantic error:", e)
                return {"results": [], "total": None, "has_more": False}
            hits = vectors.search(qv, role, yrange, offset + limit + 1)
            page = hits[offset:offset + limit]
            cards = _cards_for_keys(conn, [k for k, _ in page])
            sc = dict(page)
            for c in cards:
                c["score"] = round(sc.get(c["key"], 0.0), 4)
            return {"results": cards, "total": None, "has_more": len(hits) > offset + limit}
        hits = keyword_search(conn, q, role, yrange, offset + limit + 1)
        page = hits[offset:offset + limit]
        return {"results": _cards_for_keys(conn, [k for k, _ in page]),
                "total": None, "has_more": len(hits) > offset + limit}

    where, params = _filter_sql(role, yrange)
    total = conn.execute(f"SELECT COUNT(*) FROM profiles{where}", params).fetchone()[0]
    order = SORTS.get(sort, SORTS["mentions"])
    rows = conn.execute(
        f"SELECT canonical_key FROM profiles{where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [limit, offset]).fetchall()
    cards = _cards_for_keys(conn, [r["canonical_key"] for r in rows])
    return {"results": cards, "total": total, "has_more": offset + limit < total}


def get_person(conn, ckey, user=None):
    r = conn.execute(
        """SELECT canonical_key, full_name, class_year, class_year_tags, role,
                  interests_agg, source_docs, doc_count, mention_count, profile_text
           FROM profiles WHERE canonical_key=?""", (ckey,)).fetchone()
    if not r:
        return None
    out = {
        "key": r["canonical_key"], "name": r["full_name"], "class_year": r["class_year"],
        "class_year_tags": r["class_year_tags"], "role": r["role"],
        "interests": _interests(r, 40), "doc_count": r["doc_count"],
        "mention_count": r["mention_count"],
        "featured_pages": featured_pages(conn, ckey),
        "is_favorite": False, "note": "",
    }
    if user:
        ensure_favorites(conn)
        fav = conn.execute(
            "SELECT note FROM favorites WHERE user_phone=? AND canonical_key=?",
            (user, ckey)).fetchone()
        if fav:
            out["is_favorite"] = True
            out["note"] = fav["note"] or ""
    return out


# ---------------- per-user favorites ----------------

def ensure_favorites(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS favorites (
            user_phone    TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            note          TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_phone, canonical_key))""")
    conn.commit()


def favorite_keys(conn, user):
    ensure_favorites(conn)
    return [r[0] for r in conn.execute(
        "SELECT canonical_key FROM favorites WHERE user_phone=?", (user,)).fetchall()]


def list_favorites(conn, user):
    ensure_favorites(conn)
    rows = conn.execute(
        """SELECT canonical_key, note, created_at FROM favorites
           WHERE user_phone=? ORDER BY created_at DESC""", (user,)).fetchall()
    cards = {c["key"]: c for c in _cards_for_keys(conn, [r["canonical_key"] for r in rows])}
    out = []
    for r in rows:
        c = cards.get(r["canonical_key"])
        if not c:
            continue
        c = dict(c)
        c["note"] = r["note"] or ""
        c["created_at"] = r["created_at"]
        out.append(c)
    return out


def add_favorite(conn, user, key, note=""):
    ensure_favorites(conn)
    conn.execute("INSERT OR IGNORE INTO favorites (user_phone, canonical_key, note) "
                 "VALUES (?,?,?)", (user, key, note or ""))
    if note:
        conn.execute("UPDATE favorites SET note=? WHERE user_phone=? AND canonical_key=?",
                     (note, user, key))
    conn.commit()


def update_note(conn, user, key, note):
    ensure_favorites(conn)
    conn.execute("UPDATE favorites SET note=? WHERE user_phone=? AND canonical_key=?",
                 (note or "", user, key))
    conn.commit()


def remove_favorite(conn, user, key):
    ensure_favorites(conn)
    conn.execute("DELETE FROM favorites WHERE user_phone=? AND canonical_key=?", (user, key))
    conn.commit()


def stats(conn):
    by_role = {r["role"]: r["n"] for r in conn.execute(
        "SELECT role, COUNT(*) n FROM profiles GROUP BY role")}
    return {
        "people": conn.execute(
            "SELECT COUNT(*) FROM profiles WHERE " + NOT_JUNK).fetchone()[0],
        "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "mentions": conn.execute("SELECT COUNT(*) FROM mentions").fetchone()[0],
        "with_year": conn.execute(
            "SELECT COUNT(*) FROM profiles WHERE class_year IS NOT NULL").fetchone()[0],
        "by_role": by_role,
    }
