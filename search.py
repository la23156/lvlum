"""Search the Lawrenceville community database — keyword, semantic, or hybrid.

Examples:
    python search.py "climate policy"                 # hybrid (semantic + keyword)
    python search.py --semantic "founded a startup in biotech"
    python search.py --keyword "crew rowing OR sailing"
    python search.py "documentary filmmaker" --role alumnus --year 1990-2005 -n 15
    python search.py --person "Getz"                  # show one person's full profile

Semantic search needs embeddings (run embed_people.py first).
"""
import argparse
import struct
import sys

import config
import db
import httputil


def unpack(blob):
    n = len(blob) // 4
    return struct.unpack(f"{n}f", blob)


def embed_query(text):
    key = config.openai_key()
    status, body = httputil.post_json(
        f"{config.OPENAI_BASE}/embeddings",
        {"model": config.EMBED_MODEL, "input": [text]},
        headers={"Authorization": f"Bearer {key}"})
    if status != 200:
        raise RuntimeError(f"embeddings {status}: {str(body)[:200]}")
    v = body["data"][0]["embedding"]
    s = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / s for x in v]


def year_filter(year_arg):
    if not year_arg:
        return None
    if "-" in year_arg:
        lo, hi = year_arg.split("-", 1)
        return (lo.strip(), hi.strip())
    return (year_arg.strip(), year_arg.strip())


def passes(row, role, yrange):
    if role and (row["role"] or "") != role:
        return False
    if yrange:
        y = row["class_year"]
        if not y or not (yrange[0] <= y <= yrange[1]):
            return False
    return True


def semantic(conn, query, role, yrange, n):
    qv = embed_query(query)
    rows = conn.execute(
        """SELECT e.person_key, e.norm_vector, p.full_name, p.class_year, p.role,
                  p.doc_count, p.mention_count, p.interests_agg
           FROM embeddings e JOIN people p ON p.person_key=e.person_key""").fetchall()
    scored = []
    for r in rows:
        if not passes(r, role, yrange):
            continue
        v = unpack(r["norm_vector"])
        score = sum(a * b for a, b in zip(qv, v))   # cosine (both normalized)
        scored.append((score, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:n]


def keyword(conn, query, role, yrange, n):
    results = []
    if db.has_fts(conn):
        try:
            rows = conn.execute(
                """SELECT p.full_name, p.class_year, p.role, p.doc_count, p.mention_count,
                          p.interests_agg, bm25(people_fts) AS rank
                   FROM people_fts JOIN people p ON p.person_key=people_fts.person_key
                   WHERE people_fts MATCH ? ORDER BY rank LIMIT ?""",
                (query, n * 4)).fetchall()
            for r in rows:
                if passes(r, role, yrange):
                    results.append((-r["rank"], r))
            return results[:n]
        except Exception:  # noqa: BLE001  (fall through to LIKE on bad FTS syntax)
            pass
    like = f"%{query}%"
    rows = conn.execute(
        """SELECT full_name, class_year, role, doc_count, mention_count, interests_agg
           FROM people WHERE profile_text LIKE ? OR full_name LIKE ?
           ORDER BY mention_count DESC LIMIT ?""", (like, like, n * 4)).fetchall()
    for r in rows:
        if passes(r, role, yrange):
            results.append((float(r["mention_count"]), r))
    return results[:n]


def fmt(score, r):
    yr = f" '{r['class_year'][2:]}" if r["class_year"] else ""
    head = f"  [{score:.3f}] {r['full_name']}{yr}  ({r['role']}, {r['doc_count']} docs, " \
           f"{r['mention_count']} mentions)"
    interests = (r["interests_agg"] or "")[:200]
    return head + (f"\n        {interests}" if interests else "")


def person_locations(conn, person_id):
    """Every page the person is featured on: (doc title, issuu page link, page#, image)."""
    rows = conn.execute(
        """SELECT d.title, d.url, m.page_num, pg.image_path, m.snippet
           FROM mentions m JOIN documents d ON d.id=m.document_id
           LEFT JOIN pages pg ON pg.id=m.page_id
           WHERE m.person_id=? ORDER BY d.publish_date, d.title, m.page_num""",
        (person_id,)).fetchall()
    out = []
    for r in rows:
        page = r["page_num"]
        link = f"{r['url']}/{page}" if (r["url"] and page) else r["url"]
        out.append((r["title"], page, link, r["image_path"], r["snippet"]))
    return out


def show_person(conn, q):
    rows = conn.execute(
        """SELECT id, full_name, class_year, class_year_tags, role, doc_count,
                  mention_count, interests_agg, summary
           FROM people WHERE full_name LIKE ? ORDER BY mention_count DESC LIMIT 5""",
        (f"%{q}%",)).fetchall()
    if not rows:
        print("No match.")
        return
    for r in rows:
        print("=" * 72)
        print(f"{r['full_name']}   ({r['role']}; class {r['class_year'] or '?'}"
              f"{'; tags ' + r['class_year_tags'] if r['class_year_tags'] else ''})")
        print(f"appears in {r['doc_count']} documents, {r['mention_count']} mentions")
        if r["summary"]:
            print(f"\nSummary: {r['summary']}")
        if r["interests_agg"]:
            print(f"\nInterests/activities:\n  {r['interests_agg']}")
        locs = person_locations(conn, r["id"])
        if locs:
            print("\nFeatured on:")
            for title, page, link, img, snippet in locs:
                print(f"  • {title} — p.{page}")
                print(f"      issuu: {link}")
                print(f"      image: {img}")
                if snippet:
                    print(f"      “{snippet[:160]}”")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", help="search text (hybrid by default)")
    ap.add_argument("--semantic", metavar="Q")
    ap.add_argument("--keyword", metavar="Q")
    ap.add_argument("--person", metavar="NAME", help="print one person's full profile")
    ap.add_argument("--role", help="filter: student|alumnus|faculty|parent|unknown")
    ap.add_argument("--year", help="filter: single year or range like 1990-2005")
    ap.add_argument("-n", type=int, default=10)
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn)
    yrange = year_filter(args.year)

    if args.person:
        show_person(conn, args.person)
        return

    if args.semantic:
        print(f"# semantic: {args.semantic}")
        for s, r in semantic(conn, args.semantic, args.role, yrange, args.n):
            print(fmt(s, r))
        return
    if args.keyword:
        print(f"# keyword: {args.keyword}")
        for s, r in keyword(conn, args.keyword, args.role, yrange, args.n):
            print(fmt(s, r))
        return

    q = args.query
    if not q:
        ap.error("provide a query, or use --semantic/--keyword/--person")

    n_emb = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    print(f"# hybrid: {q}\n")
    if n_emb:
        print("Semantic matches:")
        for s, r in semantic(conn, q, args.role, yrange, args.n):
            print(fmt(s, r))
    else:
        print("(no embeddings yet — run embed_people.py for semantic search)")
    print("\nKeyword matches:")
    for s, r in keyword(conn, q, args.role, yrange, args.n):
        print(fmt(s, r))


if __name__ == "__main__":
    sys.exit(main())
