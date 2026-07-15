"""SQLite schema + helpers for the alumni database.

Tables
------
documents : one row per Issuu publication
pages     : one row per page image (tracks OCR text + extraction status)
mentions  : one row per (person occurrence) found on a page
people    : deduped person, aggregated across all mentions

All writes are idempotent so the pipeline is fully resumable.
"""
import re
import sqlite3
import unicodedata
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL DEFAULT 'issuu',
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT,
    url           TEXT,
    publish_date  TEXT,
    num_pages     INTEGER,
    folder        TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL REFERENCES documents(id),
    page_num      INTEGER NOT NULL,
    image_path    TEXT,
    ocr_text      TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | done | error
    error         TEXT,
    processed_at  TEXT,
    UNIQUE(document_id, page_num)
);

CREATE TABLE IF NOT EXISTS people (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_key      TEXT,                 -- stable id: normalized_name|class_year
    full_name       TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    class_year      TEXT,                 -- normalized 4-digit when parseable, else raw
    class_year_tags TEXT,                 -- all year-ish tags seen (e.g. "P'12; GP'18")
    role            TEXT,                 -- alumnus | student | faculty | parent | unknown
    roles_all       TEXT,                 -- all roles seen across mentions
    interests_agg   TEXT,                 -- '; '-joined distinct interests
    snippets_agg    TEXT,                 -- newline-joined distinct snippets (with source)
    source_docs     TEXT,                 -- distinct document titles person appears in
    doc_count       INTEGER DEFAULT 0,
    mention_count   INTEGER DEFAULT 0,
    profile_text    TEXT,                 -- full text blob used for search/embedding
    summary         TEXT,                 -- optional LLM-written bio
    UNIQUE(normalized_name, class_year)
);

-- one embedding row per person (keyed by stable person_key so it survives people rebuilds)
CREATE TABLE IF NOT EXISTS embeddings (
    person_key    TEXT PRIMARY KEY,
    model         TEXT,
    dim           INTEGER,
    norm_vector   BLOB,                   -- L2-normalized float32 vector
    profile_hash  TEXT                    -- hash of profile_text the vector was built from
);

CREATE TABLE IF NOT EXISTS mentions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     INTEGER REFERENCES people(id),
    document_id   INTEGER NOT NULL REFERENCES documents(id),
    page_id       INTEGER REFERENCES pages(id),
    page_num      INTEGER,
    name          TEXT NOT NULL,
    class_year    TEXT,
    role          TEXT,
    interests     TEXT,                   -- '; '-joined interests for this mention
    snippet       TEXT,
    confidence    REAL
);

CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages(document_id);
CREATE INDEX IF NOT EXISTS idx_mentions_person ON mentions(person_id);
CREATE INDEX IF NOT EXISTS idx_mentions_doc ON mentions(document_id);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


_PEOPLE_COLS = {
    "person_key": "TEXT", "class_year_tags": "TEXT", "roles_all": "TEXT",
    "snippets_agg": "TEXT", "source_docs": "TEXT", "doc_count": "INTEGER DEFAULT 0",
    "profile_text": "TEXT", "summary": "TEXT",
}


def init(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.commit()


def migrate(conn: sqlite3.Connection):
    """Add columns/tables that may be missing on a DB created by an earlier schema."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(people)").fetchall()}
    for col, decl in _PEOPLE_COLS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE people ADD COLUMN {col} {decl}")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS embeddings (
            person_key TEXT PRIMARY KEY, model TEXT, dim INTEGER,
            norm_vector BLOB, profile_hash TEXT)""")
    # full-text index for keyword search (best-effort; skipped if FTS5 unavailable)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS people_fts USING fts5("
            "person_key UNINDEXED, full_name, class_year, role, profile_text)")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def has_fts(conn) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='people_fts'").fetchone())


# ---------- normalization helpers ----------

def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower()
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_class_year(raw) -> str | None:
    """Turn things like "'85", "’85", "P'12", "1985", "Class of 2007" into a 4-digit year."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.search(r"(19|20)\d{2}", s)          # explicit 4-digit
    if m:
        return m.group(0)
    m = re.search(r"[’'`](\d{2})", s)          # apostrophe + 2 digits
    if not m:
        m = re.search(r"\b(\d{2})\b", s)
    if m:
        yy = int(m.group(1))
        # Lawrenceville issues span ~1930s-2030s; <=30 -> 2000s, else 1900s
        return str(2000 + yy) if yy <= 30 else str(1900 + yy)
    return None


# ---------- writes ----------

def upsert_document(conn, slug, title, url, publish_date, num_pages, folder) -> int:
    conn.execute(
        """INSERT INTO documents (slug, title, url, publish_date, num_pages, folder)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(slug) DO UPDATE SET
             title=excluded.title, url=excluded.url,
             publish_date=excluded.publish_date, num_pages=excluded.num_pages,
             folder=excluded.folder""",
        (slug, title, url, publish_date, num_pages, str(folder)),
    )
    conn.commit()
    return conn.execute("SELECT id FROM documents WHERE slug=?", (slug,)).fetchone()[0]


def ensure_page(conn, document_id, page_num, image_path) -> int:
    conn.execute(
        """INSERT INTO pages (document_id, page_num, image_path)
           VALUES (?,?,?)
           ON CONFLICT(document_id, page_num) DO UPDATE SET image_path=excluded.image_path""",
        (document_id, page_num, str(image_path)),
    )
    return conn.execute(
        "SELECT id FROM pages WHERE document_id=? AND page_num=?",
        (document_id, page_num),
    ).fetchone()[0]


def page_status(conn, page_id) -> str:
    row = conn.execute("SELECT status FROM pages WHERE id=?", (page_id,)).fetchone()
    return row[0] if row else "pending"


def record_page_result(conn, page_id, ocr_text, status, error=None):
    conn.execute(
        """UPDATE pages SET ocr_text=?, status=?, error=?, processed_at=datetime('now')
           WHERE id=?""",
        (ocr_text, status, error, page_id),
    )


def insert_mention(conn, document_id, page_id, page_num, m: dict):
    interests = "; ".join(m.get("interests") or [])
    conn.execute(
        """INSERT INTO mentions
           (document_id, page_id, page_num, name, class_year, role, interests, snippet, confidence)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (document_id, page_id, page_num, m.get("name"),
         normalize_class_year(m.get("class_year")), m.get("role"),
         interests, m.get("snippet"), m.get("confidence")),
    )


def _strong_year(norm, name_year_counts, name_total):
    """The single class year a name is reliably associated with, or None.

    A year qualifies only if at least 2 mentions support it AND it accounts for >= 1/3 of all
    mentions of that name. This folds genuine alumni (whose year recurs) into one profile while
    refusing a stray year on a frequently-mentioned staff name (e.g. an editor tagged '65 in
    2 of 50 mentions). Ambiguous (two qualifying years) -> None."""
    counts = name_year_counts.get(norm)
    if not counts:
        return None
    total = name_total.get(norm, 0)
    strong = [y for y, n in counts.items() if n >= 2 and n * 3 >= total]
    return strong[0] if len(strong) == 1 else None


def _assign_year(norm, year, name_year_counts, name_total):
    """Mentions with no class year are folded into the name's reliably-associated year."""
    if year:
        return year
    return _strong_year(norm, name_year_counts, name_total)


def build_profile_text(g) -> str:
    parts = [g["display"]]
    meta = []
    if g["year"]:
        meta.append(f"Class of {g['year']}")
    if g["role"]:
        meta.append(g["role"])
    if meta:
        parts.append(" — " + ", ".join(meta))
    if g["tags"]:
        parts.append(f"\nYear tags: {'; '.join(sorted(g['tags']))}")
    if g["interests"]:
        parts.append("\nInterests / activities: " + "; ".join(sorted(g["interests"])))
    if g["docs"]:
        parts.append("\nAppears in: " + "; ".join(sorted(g["docs"])))
    if g["snippets"]:
        parts.append("\nMentions:\n" + "\n".join(f"- {s}" for s in g["snippets"]))
    return "".join(parts)


def rebuild_people(conn):
    """Collapse mentions into one consolidated profile per person.

    Keyed by normalized name + class year, with same-name/no-year mentions folded into a
    uniquely-yeared person. Builds the searchable profile_text and refreshes the FTS index.
    Idempotent full rebuild. Embeddings are keyed by the stable person_key and survive.
    """
    conn.execute("UPDATE mentions SET person_id=NULL")
    conn.execute("DELETE FROM people")
    rows = conn.execute(
        """SELECT m.id, m.name, m.class_year, m.role, m.interests, m.snippet,
                  m.confidence, d.title AS doc_title
           FROM mentions m LEFT JOIN documents d ON d.id=m.document_id"""
    ).fetchall()

    # first pass: total mentions per name, and how many support each (name, year)?
    name_year_counts = {}
    name_total = {}
    for r in rows:
        norm = normalize_name(r["name"])
        if not norm:
            continue
        name_total[norm] = name_total.get(norm, 0) + 1
        if r["class_year"]:
            name_year_counts.setdefault(norm, {})
            name_year_counts[norm][r["class_year"]] = \
                name_year_counts[norm].get(r["class_year"], 0) + 1

    groups = {}
    for r in rows:
        norm = normalize_name(r["name"])
        if not norm:
            continue
        year = _assign_year(norm, r["class_year"], name_year_counts, name_total)
        key = (norm, year)
        g = groups.setdefault(key, {
            "display": r["name"], "year": year, "roles": {}, "tags": set(),
            "interests": set(), "snippets": [], "docs": set(),
            "mention_ids": [], "count": 0,
        })
        g["count"] += 1
        g["mention_ids"].append(r["id"])
        if r["role"]:
            g["roles"][r["role"]] = g["roles"].get(r["role"], 0) + 1
        if r["class_year"]:
            g["tags"].add(r["class_year"])
        for it in (r["interests"] or "").split(";"):
            it = it.strip()
            if it:
                g["interests"].add(it)
        snip = (r["snippet"] or "").strip()
        if snip:
            tag = f'"{snip}"' + (f" ({r['doc_title']})" if r["doc_title"] else "")
            if tag not in g["snippets"]:
                g["snippets"].append(tag)
        if r["doc_title"]:
            g["docs"].add(r["doc_title"])
        if len(r["name"] or "") > len(g["display"] or ""):
            g["display"] = r["name"]

    if has_fts(conn):
        conn.execute("DELETE FROM people_fts")

    for (norm, year), g in groups.items():
        g["role"] = max(g["roles"], key=g["roles"].get) if g["roles"] else "unknown"
        person_key = f"{norm}|{year or ''}"
        interests = "; ".join(sorted(g["interests"]))
        snippets = "\n".join(g["snippets"][:25])
        roles_all = "; ".join(sorted(g["roles"]))
        tags = "; ".join(sorted(g["tags"]))
        docs = "; ".join(sorted(g["docs"]))
        profile_text = build_profile_text(g)
        cur = conn.execute(
            """INSERT INTO people
               (person_key, full_name, normalized_name, class_year, class_year_tags,
                role, roles_all, interests_agg, snippets_agg, source_docs, doc_count,
                mention_count, profile_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (person_key, g["display"], norm, year, tags, g["role"], roles_all,
             interests, snippets, docs, len(g["docs"]), g["count"], profile_text),
        )
        pid = cur.lastrowid
        conn.executemany("UPDATE mentions SET person_id=? WHERE id=?",
                         [(pid, mid) for mid in g["mention_ids"]])
        if has_fts(conn):
            conn.execute(
                "INSERT INTO people_fts (person_key, full_name, class_year, role, profile_text)"
                " VALUES (?,?,?,?,?)",
                (person_key, g["display"], year or "", g["role"], profile_text))
    conn.commit()


if __name__ == "__main__":
    c = connect()
    init(c)
    print(f"Initialized {config.DB_PATH}")
