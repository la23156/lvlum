"""Entity resolution: merge name-variant duplicates into canonical profiles.

The raw `people` table keys by (normalized_name, class_year), so the same person under different
name forms ("Joe Tsai" vs "Joseph Tsai '82", or a surname-only mention "Frezza") becomes several
rows. This pass clusters those into one canonical profile and writes a parallel set of tables the
website reads — leaving the raw `people`/`mentions`/`embeddings` tables untouched.

Outputs (in the same SQLite DB):
  profiles            one canonical profile per person
  profile_aliases     person_key -> canonical_key (every raw person maps to a canonical)
  profiles_fts        FTS5 over canonical name + profile_text (keyword search)
  profile_embeddings  one re-embedded vector per canonical profile (semantic search)

Strategy (conservative — a wrong merge is worse than a duplicate):
  * Within a class-year bucket, merge two people when their names are compatible (token-subset,
    or first-name nickname/initial with the same surname) AND their embeddings agree above a
    name-confidence-dependent cosine threshold.
  * Separately, fold a surname-only, year-less record into a uniquely-matching full name that
    has a year (e.g. "Frezza" -> "Brian Frezza '01").

Usage:
    python resolve_people.py [--report] [--no-embed]
"""
import argparse
import struct
import sys

import numpy as np

import config
import db
import embed_people as ep

# --- nickname groups (each set is mutually interchangeable as a first name) ---
NICK_GROUPS = [
    {"joe", "joey", "joseph"}, {"tom", "tommy", "thomas"}, {"mike", "michael", "mikey"},
    {"bob", "bobby", "rob", "robbie", "robert"}, {"will", "bill", "billy", "willy", "william"},
    {"jim", "jimmy", "james"}, {"dave", "davey", "david"}, {"dan", "danny", "daniel"},
    {"chris", "christopher"}, {"matt", "matthew"}, {"nick", "nicky", "nicholas"},
    {"tony", "anthony"}, {"andy", "drew", "andrew"}, {"ben", "benji", "benjamin"},
    {"sam", "sammy", "samuel"}, {"alex", "alexander", "alexandra"}, {"ed", "eddie", "edward"},
    {"ted", "teddy", "theodore"}, {"rick", "ricky", "dick", "richard"},
    {"steve", "stephen", "steven"}, {"greg", "gregory"}, {"jeff", "jeffrey", "geoff", "geoffrey"},
    {"ken", "kenny", "kenneth"}, {"kathy", "kate", "katie", "kit", "katherine", "catherine"},
    {"liz", "lizzie", "beth", "betsy", "betty", "elizabeth"},
    {"peggy", "meg", "maggie", "margaret"}, {"sue", "susie", "susan"}, {"cindy", "cynthia"},
    {"jen", "jenny", "jennifer"}, {"becky", "rebecca"}, {"abby", "abigail"},
    {"tim", "timmy", "timothy"}, {"pat", "patty", "patrick", "patricia"}, {"ron", "ronnie", "ronald"},
    {"don", "donnie", "donald"}, {"charlie", "chuck", "charles"}, {"frank", "frankie", "francis"},
    {"hank", "henry"}, {"jack", "john", "johnny", "jonathan"}, {"gabe", "gabriel"},
    {"nate", "nathan", "nathaniel"}, {"vinny", "vincent"}, {"zach", "zack", "zachary"},
]
_NICK = {}
for _i, _g in enumerate(NICK_GROUPS):
    for _t in _g:
        _NICK.setdefault(_t, set()).add(_i)


HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "rev", "prof", "hon", "sir", "fr", "mx",
              "headmaster", "head", "master", "coach", "dean", "capt", "col", "lt", "gen"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "vi", "vii"}
YEAR_MARKERS = {"p", "h", "gp", "g", "w"}   # class-year tag letters (P'12, H'54, GP'18 ...)


def nickname_equiv(a: str, b: str) -> bool:
    if a == b:
        return True
    return bool(_NICK.get(a, set()) & _NICK.get(b, set()))


def is_combined(norm: str) -> bool:
    """A donor entry naming two people ('William Hamill and Leita Hamill') — never merge on it."""
    toks = norm.split()
    return "and" in toks or "&" in toks


def _strip_tail(toks):
    """Remove trailing generational suffixes, class-year tag letters, and digit year tokens."""
    while toks and (toks[-1] in SUFFIXES or toks[-1] in YEAR_MARKERS or toks[-1].isdigit()):
        toks.pop()
    return toks


def clean_tokens(norm: str):
    """Real given/surname tokens: honorifics, suffixes, and class-year tags removed."""
    return _strip_tail([t for t in norm.split() if t not in HONORIFICS])


def suffix_of(norm: str):
    """The generational suffix (jr/sr/iii...) if present, else None — used to keep Jr vs Sr apart."""
    toks = [t for t in norm.split() if t not in HONORIFICS]
    while toks and (toks[-1] in YEAR_MARKERS or toks[-1].isdigit()):
        toks.pop()
    return toks[-1] if toks and toks[-1] in SUFFIXES else None


def _middle_conflict(a_mid, b_mid) -> bool:
    """Both have middle name(s)/initial(s) whose initials don't overlap -> likely different people."""
    if not a_mid or not b_mid:
        return False
    return {t[0] for t in a_mid}.isdisjoint({t[0] for t in b_mid})


def name_match_threshold(a_norm: str, b_norm: str):
    """Min cosine required to merge these two (yeared) names, or None if incompatible.

    Requires the SAME real surname. No first-initial bridging (it falsely links e.g.
    'S. Murray' to Sam/Spencer/Stephen). Conflicting middle initials block a merge."""
    at, bt = clean_tokens(a_norm), clean_tokens(b_norm)
    if len(at) < 2 or len(bt) < 2:        # need at least given + surname
        return None
    if at[-1] != bt[-1]:                  # different surname
        return None
    if suffix_of(a_norm) != suffix_of(b_norm):   # Jr vs Sr vs III -> different people
        return None
    sa, sb = set(at), set(bt)
    if sa == sb:
        return 0.30
    if _middle_conflict(at[1:-1], bt[1:-1]):
        return None
    if sa <= sb or sb <= sa:              # token-subset (e.g. "brian frezza" ⊆ "brian k frezza")
        return 0.45
    a0, b0 = at[0], bt[0]                  # same surname, differing given names
    if a0 == b0:
        return 0.58
    if nickname_equiv(a0, b0):
        return 0.60
    return None


def names_equal(a_norm: str, b_norm: str) -> bool:
    if suffix_of(a_norm) != suffix_of(b_norm):
        return False
    a, b = clean_tokens(a_norm), clean_tokens(b_norm)
    return len(a) >= 2 and a == b


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def unpack(blob):
    n = len(blob) // 4
    return np.frombuffer(blob, dtype=np.float32, count=n)


def load_people(conn):
    rows = conn.execute(
        """SELECT pe.id, pe.person_key, pe.full_name, pe.normalized_name, pe.class_year,
                  pe.mention_count, e.norm_vector
           FROM people pe LEFT JOIN embeddings e ON e.person_key=pe.person_key""").fetchall()
    people = []
    for r in rows:
        vec = unpack(r["norm_vector"]) if r["norm_vector"] else None
        people.append({
            "id": r["id"], "key": r["person_key"], "name": r["full_name"],
            "norm": r["normalized_name"], "year": r["class_year"],
            "mentions": r["mention_count"] or 0, "vec": vec,
        })
    return people


def cluster(people, report=False):
    n = len(people)
    uf = UF(n)
    idx_by_year = {}
    for i, p in enumerate(people):
        idx_by_year.setdefault(p["year"], []).append(i)

    merges = 0
    for year, idxs in idx_by_year.items():
        # need vectors to compare; skip members without an embedding
        members = [i for i in idxs if people[i]["vec"] is not None]
        if len(members) < 2:
            continue
        M = np.vstack([people[i]["vec"] for i in members])      # (m, dim), already L2-normed
        sims = M @ M.T
        cand = np.argwhere(np.triu(sims, k=1) >= 0.30)
        for a, b in cand:
            ia, ib = members[a], members[b]
            na, nb = people[ia]["norm"], people[ib]["norm"]
            if is_combined(na) or is_combined(nb):
                continue
            if year is None:
                # year-less: only merge clearly-identical names (handles honorific variants),
                # never nickname/subset guesses — too error-prone without a year to anchor.
                if names_equal(na, nb) and sims[a, b] >= 0.45:
                    uf.union(ia, ib); merges += 1
                continue
            thr = name_match_threshold(na, nb)
            if thr is not None and sims[a, b] >= thr:
                uf.union(ia, ib); merges += 1
    if report:
        print(f"  intra-year merges: {merges}")

    # second pass: fold a surname-only, year-less record into a unique full-name match that has a
    # year (e.g. "Frezza" -> "Brian Frezza '01"). Only when the vector match is strong and clearly
    # the single best candidate, so ambiguous surnames (many Murrays) are left alone.
    by_surname = {}
    for i, p in enumerate(people):
        if p["year"] and p["vec"] is not None:
            ct = clean_tokens(p["norm"])
            if len(ct) >= 2:
                by_surname.setdefault(ct[-1], []).append(i)
    folded = 0
    for i, p in enumerate(people):
        ct = clean_tokens(p["norm"])
        if p["year"] is not None or len(ct) != 1 or p["vec"] is None:
            continue
        cands = by_surname.get(ct[0], [])
        scored = sorted(((float(p["vec"] @ people[j]["vec"]), j) for j in cands), reverse=True)
        scored = [(s, j) for s, j in scored if s >= 0.65]
        if len(scored) == 1 or (len(scored) >= 2 and scored[0][0] - scored[1][0] >= 0.10):
            uf.union(i, scored[0][1])
            folded += 1
    if report:
        print(f"  surname-only folds: {folded}")

    clusters = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)
    return list(clusters.values())


_HON_DISPLAY = {"mr", "mrs", "ms", "miss", "dr", "rev", "prof", "hon", "sir", "mx",
                "headmaster", "coach", "dean", "capt", "col", "lt", "gen"}


import re as _re
_TAG_RE = _re.compile(r"^(?:[A-Za-z]{0,2}['’]\d{2}|['’]\d{2}|\d{2,4})$")  # H'54, P'16, ’21, 1954


def clean_display(name: str) -> str:
    """Tidy the shown name: drop a leading honorific and trailing class-year credential tags
    ('Mr. Joseph C. Tsai' -> 'Joseph C. Tsai'; "Stephen S. Murray H'54 '55 '16" -> 'Stephen S. Murray')."""
    toks = (name or "").split()
    while toks and toks[0].lower().strip(".") in _HON_DISPLAY:
        toks.pop(0)
    while toks and _TAG_RE.match(toks[-1]):
        toks.pop()
    return " ".join(toks) if toks else (name or "")


def canonical_key_for(members, people):
    # prefer a name without an honorific prefix, then most complete (most tokens), most mentions
    def score(i):
        nm = people[i]["name"] or ""
        no_hon = clean_display(nm) == nm
        return (no_hon, len(people[i]["norm"].split()), people[i]["mentions"], len(nm))
    best = max(members, key=score)
    return people[best]["key"], clean_display(people[best]["name"])


def build_profiles(conn, clusters, people, report=False):
    # map raw people.id -> canonical_key
    member_ids_by_cluster = []
    canon = {}          # people-index -> canonical_key
    canon_name = {}
    alias_rows = []
    for members in clusters:
        ckey, cname = canonical_key_for(members, people)
        member_ids_by_cluster.append(([people[i]["id"] for i in members], ckey))
        for i in members:
            canon[i] = ckey
            alias_rows.append((people[i]["key"], ckey))
        canon_name[ckey] = cname

    # re-aggregate from mentions across each cluster's member person_ids
    id_to_ckey = {}
    for ids, ckey in member_ids_by_cluster:
        for pid in ids:
            id_to_ckey[pid] = ckey

    rows = conn.execute(
        """SELECT m.person_id, m.name, m.class_year, m.role, m.interests, m.snippet,
                  d.title AS doc_title
           FROM mentions m LEFT JOIN documents d ON d.id=m.document_id
           WHERE m.person_id IS NOT NULL""").fetchall()

    groups = {}
    for r in rows:
        ckey = id_to_ckey.get(r["person_id"])
        if ckey is None:
            continue
        g = groups.setdefault(ckey, {
            "display": canon_name.get(ckey) or r["name"], "year": None, "roles": {},
            "tags": set(), "interests": set(), "snippets": [], "docs": set(), "count": 0,
        })
        g["count"] += 1
        if r["class_year"] and not g["year"]:
            g["year"] = r["class_year"]
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

    # write tables
    conn.executescript("""
        DROP TABLE IF EXISTS profiles;
        DROP TABLE IF EXISTS profile_aliases;
        CREATE TABLE profiles (
            canonical_key TEXT PRIMARY KEY, full_name TEXT, class_year TEXT,
            class_year_tags TEXT, role TEXT, interests_agg TEXT, snippets_agg TEXT,
            source_docs TEXT, doc_count INTEGER, mention_count INTEGER, profile_text TEXT);
        CREATE TABLE profile_aliases (person_key TEXT PRIMARY KEY, canonical_key TEXT);
        CREATE INDEX IF NOT EXISTS idx_palias_canon ON profile_aliases(canonical_key);
    """)
    try:
        conn.execute("DROP TABLE IF EXISTS profiles_fts")
        conn.execute("CREATE VIRTUAL TABLE profiles_fts USING fts5("
                     "canonical_key UNINDEXED, full_name, class_year, role, profile_text)")
        fts = True
    except Exception:  # noqa: BLE001
        fts = False

    for ckey, g in groups.items():
        g["role"] = max(g["roles"], key=g["roles"].get) if g["roles"] else "unknown"
        interests = "; ".join(sorted(g["interests"]))
        snippets = "\n".join(g["snippets"][:30])
        tags = "; ".join(sorted(g["tags"]))
        docs = "; ".join(sorted(g["docs"]))
        ptext = db.build_profile_text(g)
        conn.execute(
            """INSERT INTO profiles (canonical_key, full_name, class_year, class_year_tags,
               role, interests_agg, snippets_agg, source_docs, doc_count, mention_count,
               profile_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ckey, g["display"], g["year"], tags, g["role"], interests, snippets, docs,
             len(g["docs"]), g["count"], ptext))
        if fts:
            conn.execute("INSERT INTO profiles_fts (canonical_key, full_name, class_year, role, "
                         "profile_text) VALUES (?,?,?,?,?)",
                         (ckey, g["display"], g["year"] or "", g["role"], ptext))
    conn.executemany(
        "INSERT OR REPLACE INTO profile_aliases (person_key, canonical_key) VALUES (?,?)",
        alias_rows)
    conn.commit()
    return len(groups)


def embed_profiles(conn):
    import hashlib
    conn.execute("""CREATE TABLE IF NOT EXISTS profile_embeddings (
        canonical_key TEXT PRIMARY KEY, model TEXT, dim INTEGER, norm_vector BLOB,
        profile_hash TEXT)""")
    # drop embeddings whose canonical_key no longer exists (keys can change across runs)
    conn.execute("DELETE FROM profile_embeddings WHERE canonical_key NOT IN "
                 "(SELECT canonical_key FROM profiles)")
    conn.commit()
    existing = {r[0]: r[1] for r in
                conn.execute("SELECT canonical_key, profile_hash FROM profile_embeddings")}
    rows = conn.execute("SELECT canonical_key, profile_text FROM profiles").fetchall()
    model = config.EMBED_MODEL
    todo = []
    for r in rows:
        text = (r["profile_text"] or "")[: config.EMBED_MAX_CHARS]
        h = hashlib.sha256((model + "\n" + text).encode("utf-8")).hexdigest()
        if existing.get(r["canonical_key"]) != h:
            todo.append((r["canonical_key"], text, h))
    print(f"  embedding {len(todo)}/{len(rows)} canonical profiles...")
    for i in range(0, len(todo), config.EMBED_BATCH):
        batch = todo[i:i + config.EMBED_BATCH]
        vecs = ep.embed_batch([t for _, t, _ in batch], model)
        for (ck, _t, h), v in zip(batch, vecs):
            nv = ep.l2_normalize(v)
            conn.execute(
                """INSERT INTO profile_embeddings (canonical_key, model, dim, norm_vector, profile_hash)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(canonical_key) DO UPDATE SET model=excluded.model, dim=excluded.dim,
                     norm_vector=excluded.norm_vector, profile_hash=excluded.profile_hash""",
                (ck, model, len(nv), ep.pack(nv), h))
        conn.commit()
        print(f"    {min(i+len(batch), len(todo))}/{len(todo)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--no-embed", action="store_true", help="skip re-embedding canonical profiles")
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn)
    people = load_people(conn)
    print(f"raw people: {len(people)}")
    clusters = cluster(people, report=args.report)
    multi = [c for c in clusters if len(c) > 1]
    print(f"clusters: {len(clusters)}  (merged groups: {len(multi)})")

    if args.report:
        multi.sort(key=len, reverse=True)
        print("\nSample merges:")
        for c in multi[:15]:
            names = sorted({people[i]["name"] for i in c})
            yr = people[c[0]]["year"]
            print(f"  [{yr}] " + "  |  ".join(names))

    n = build_profiles(conn, clusters, people, report=args.report)
    print(f"canonical profiles written: {n}")
    if not args.no_embed:
        embed_profiles(conn)
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
