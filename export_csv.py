"""Export the database tables to CSV under data/exports/."""
import csv
import sys

import config
import db


def dump(conn, table, path, order):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = conn.execute(f"SELECT {','.join(cols)} FROM {table} ORDER BY {order}").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    print(f"  {table}: {len(rows)} rows -> {path}")
    return len(rows)


def main():
    config.ensure_dirs()
    conn = db.connect()
    db.init(conn)
    print("Exporting CSVs...")
    dump(conn, "documents", config.EXPORT_DIR / "documents.csv", "publish_date, slug")
    dump(conn, "people", config.EXPORT_DIR / "people.csv",
         "class_year, normalized_name")
    dump(conn, "mentions", config.EXPORT_DIR / "mentions.csv", "document_id, page_num")
    # convenience: people with interests only
    rows = conn.execute(
        "SELECT full_name, class_year, role, mention_count, interests_agg "
        "FROM people WHERE interests_agg != '' ORDER BY class_year, normalized_name"
    ).fetchall()
    with open(config.EXPORT_DIR / "people_with_interests.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["full_name", "class_year", "role", "mention_count", "interests"])
        for r in rows:
            w.writerow([r["full_name"], r["class_year"], r["role"],
                        r["mention_count"], r["interests_agg"]])
    print(f"  people_with_interests: {len(rows)} rows")

    # located mentions: every appearance with doc, page, issuu page link, and local image
    loc = conn.execute(
        """SELECT p.full_name, p.class_year, p.role, d.title AS document, m.page_num,
                  d.url || '/' || m.page_num AS issuu_page_link, pg.image_path,
                  m.interests, m.snippet
           FROM mentions m
           JOIN documents d ON d.id=m.document_id
           LEFT JOIN people p ON p.id=m.person_id
           LEFT JOIN pages pg ON pg.id=m.page_id
           ORDER BY p.full_name, d.publish_date, m.page_num""").fetchall()
    cols = ["full_name", "class_year", "role", "document", "page_num",
            "issuu_page_link", "image_path", "interests", "snippet"]
    with open(config.EXPORT_DIR / "mentions_located.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in loc:
            w.writerow([r[c] for c in cols])
    print(f"  mentions_located: {len(loc)} rows")
    print(f"\nExports in {config.EXPORT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
