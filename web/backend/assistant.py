"""AI group-builder: parse a natural-language brief into filters + a fit criterion, then judge
each matching person with a per-person binary LLM call (fit + reasoning). A background daemon
thread processes 'running' groups and auto-resumes after a restart (all state in SQLite)."""
import concurrent.futures as cf
import json
import threading
import time

import dataroot  # noqa: F401
import db
import llm
import queries
import settings

# ---------------- schemas ----------------
PARSE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "criterion": {"type": "string"},
        "year_min": {"type": ["integer", "null"]},
        "year_max": {"type": ["integer", "null"]},
        "roles": {"type": "array",
                  "items": {"type": "string",
                            "enum": ["alumnus", "student", "faculty", "parent"]}},
    },
    "required": ["title", "criterion", "year_min", "year_max", "roles"],
}
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "fit": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["fit", "reasoning", "confidence"],
}

PARSE_SYS = (
    "You convert a request to build a group of Lawrenceville School community members into "
    "structured filters. Return:\n"
    "- `title`: a short name for the group.\n"
    "- `criterion`: ONLY the qualitative attribute to judge each person on (e.g. 'demonstrated "
    "interest in space-related technology'). Do NOT restate the class-year range or role here — "
    "those are applied separately as hard filters.\n"
    "- `year_min`/`year_max`: an inclusive class-year range, or null if no bound is given. "
    "Note 'graduated between 2008 and 2020' is a class-year range 2008-2020.\n"
    "- `roles`: which roles to include (alumnus/student/faculty/parent; empty = all). IMPORTANT: a "
    "person's role tag reflects how they appeared in a past magazine issue, not their status now; "
    "someone tagged a 'student' in an older issue has since graduated. So for 'alumni'/'graduates' "
    "requests use roles=['alumnus'] (the system automatically also includes now-graduated former "
    "students). Use 'parent' or 'faculty' only when the request explicitly asks for them.")

JUDGE_SYS = (
    "You decide whether a person fits a target group, based ONLY on the provided profile. "
    "The class-year and role filters are already applied, so judge the qualitative criterion only. "
    "A person's class year is their graduation year — someone may have been described as a current "
    "student in an older publication but has since graduated; do not hold that against them. "
    "Be strict: answer fit=true only when the profile gives concrete evidence supporting the "
    "criterion. Give a one- to two-sentence reason citing the specific evidence (or noting its "
    "absence). confidence is 0.0-1.0.")


# ---------------- schema / table ----------------
def ensure_assistant(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS assistant_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_phone TEXT NOT NULL, title TEXT, prompt TEXT, criterion TEXT,
        filters_json TEXT, model TEXT,
        status TEXT NOT NULL DEFAULT 'draft',
        total INTEGER DEFAULT 0, judged INTEGER DEFAULT 0, matched INTEGER DEFAULT 0,
        error TEXT, created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS assistant_candidates (
        group_id INTEGER NOT NULL, canonical_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        fit INTEGER, reasoning TEXT, confidence REAL, judged_at TEXT,
        PRIMARY KEY (group_id, canonical_key));
    CREATE INDEX IF NOT EXISTS idx_ac_group_status ON assistant_candidates(group_id, status);
    """)
    conn.commit()


# ---------------- helpers ----------------
def est_cost(total):
    per = settings.ASSIST_COST_PER_CALL
    return {"low": round(total * per * 0.6, 2), "high": round(total * per * 2.2, 2),
            "minutes": max(1, round(total / max(settings.ASSIST_WORKERS, 1) * 1.4 / 60))}


def _effective_roles(roles):
    """The `role` field is a snapshot from the issue's publication date, not the person's status
    today. Anyone with a past class year has since graduated, so a request for 'alumnus' must also
    include people tagged 'student' (current students in older issues, now graduated) and
    'unknown'. Parents/faculty are only included when explicitly requested (a parent's class-year
    tag like P'12 is their CHILD's class, not their own graduation)."""
    roles = list(roles or [])
    if "alumnus" in roles:
        for extra in ("student", "unknown"):
            if extra not in roles:
                roles.append(extra)
    return roles


def _candidate_keys(conn, filters):
    clauses, params = [queries.NOT_JUNK], []
    if filters.get("year_min"):
        clauses.append("class_year >= ?"); params.append(str(filters["year_min"]))
    if filters.get("year_max"):
        clauses.append("class_year <= ?"); params.append(str(filters["year_max"]))
    roles = _effective_roles(filters.get("roles"))
    if roles:
        clauses.append("role IN (%s)" % ",".join("?" * len(roles)))
        params += roles
    sql = ("SELECT canonical_key FROM profiles WHERE " + " AND ".join(clauses) +
           " ORDER BY mention_count DESC LIMIT ?")
    params.append(settings.ASSIST_MAX_CANDIDATES)
    return [r[0] for r in conn.execute(sql, params).fetchall()]


def group_dict(conn, gid, user=None):
    g = conn.execute("SELECT * FROM assistant_groups WHERE id=?", (gid,)).fetchone()
    if not g or (user and g["user_phone"] != user):
        return None
    d = dict(g)
    d["filters"] = json.loads(d.pop("filters_json") or "{}")
    d["effective_roles"] = _effective_roles(d["filters"].get("roles"))
    d["est_cost"] = est_cost(d["total"])
    return d


def _populate(conn, gid, filters):
    conn.execute("DELETE FROM assistant_candidates WHERE group_id=?", (gid,))
    keys = _candidate_keys(conn, filters)
    conn.executemany(
        "INSERT OR IGNORE INTO assistant_candidates (group_id, canonical_key, status) "
        "VALUES (?,?, 'pending')", [(gid, k) for k in keys])
    conn.execute("UPDATE assistant_groups SET total=?, judged=0, matched=0, "
                 "updated_at=datetime('now') WHERE id=?", (len(keys), gid))


# ---------------- brief parsing / judging ----------------
def parse_brief(prompt, model):
    p = llm.chat_json(model, PARSE_SYS, prompt, PARSE_SCHEMA, max_tokens=600)
    return {
        "title": (p.get("title") or prompt[:60]).strip(),
        "criterion": (p.get("criterion") or prompt).strip(),
        "year_min": p.get("year_min"), "year_max": p.get("year_max"),
        "roles": p.get("roles") or [],
    }


def judge(model, criterion, profile_text):
    user = (f"Target group criterion: {criterion}\n\nPerson profile:\n"
            f"{(profile_text or '')[: settings.ASSIST_PROFILE_CHARS]}")
    return llm.chat_json(model, JUDGE_SYS, user, JUDGE_SCHEMA, max_tokens=400)


# ---------------- group lifecycle ----------------
def create_group(conn, user, prompt, model=None):
    model = model or settings.ASSIST_MODEL
    parsed = parse_brief(prompt, settings.ASSIST_PARSE_MODEL or model)
    filters = {"year_min": parsed["year_min"], "year_max": parsed["year_max"],
               "roles": parsed["roles"]}
    cur = conn.execute(
        """INSERT INTO assistant_groups
           (user_phone, title, prompt, criterion, filters_json, model, status)
           VALUES (?,?,?,?,?,?, 'draft')""",
        (user, parsed["title"], prompt, parsed["criterion"], json.dumps(filters), model))
    gid = cur.lastrowid
    _populate(conn, gid, filters)
    conn.commit()
    return group_dict(conn, gid, user)


def update_group(conn, user, gid, criterion=None, year_min=None, year_max=None, roles=None):
    """Edit a draft group's filters. Sends the full intended filter state (None year = unbounded;
    criterion None = keep existing)."""
    g = conn.execute("SELECT * FROM assistant_groups WHERE id=? AND user_phone=?",
                     (gid, user)).fetchone()
    if not g or g["status"] != "draft":
        return None
    filters = {"year_min": year_min, "year_max": year_max, "roles": roles or []}
    conn.execute("UPDATE assistant_groups SET filters_json=?, criterion=COALESCE(?, criterion), "
                 "updated_at=datetime('now') WHERE id=?",
                 (json.dumps(filters), criterion, gid))
    _populate(conn, gid, filters)
    conn.commit()
    return group_dict(conn, gid, user)


def run_group(conn, user, gid):
    conn.execute("UPDATE assistant_groups SET status='running', updated_at=datetime('now') "
                 "WHERE id=? AND user_phone=? AND status IN ('draft','cancelled')", (gid, user))
    conn.commit()
    return group_dict(conn, gid, user)


def cancel_group(conn, user, gid):
    conn.execute("UPDATE assistant_groups SET status='cancelled', updated_at=datetime('now') "
                 "WHERE id=? AND user_phone=? AND status='running'", (gid, user))
    conn.commit()
    return group_dict(conn, gid, user)


def delete_group(conn, user, gid):
    g = conn.execute("SELECT id FROM assistant_groups WHERE id=? AND user_phone=?",
                     (gid, user)).fetchone()
    if not g:
        return False
    conn.execute("DELETE FROM assistant_candidates WHERE group_id=?", (gid,))
    conn.execute("DELETE FROM assistant_groups WHERE id=?", (gid,))
    conn.commit()
    return True


def list_groups(conn, user):
    rows = conn.execute(
        "SELECT * FROM assistant_groups WHERE user_phone=? ORDER BY created_at DESC",
        (user,)).fetchall()
    out = []
    for g in rows:
        d = dict(g)
        d["filters"] = json.loads(d.pop("filters_json") or "{}")
        out.append(d)
    return out


def group_detail(conn, user, gid, include="matched"):
    d = group_dict(conn, gid, user)
    if not d:
        return None
    where = "ac.fit=1" if include == "matched" else "ac.status IN ('judged','error')"
    rows = conn.execute(
        f"""SELECT ac.canonical_key, ac.fit, ac.reasoning, ac.confidence
            FROM assistant_candidates ac
            WHERE ac.group_id=? AND {where}
            ORDER BY ac.fit DESC, ac.confidence DESC""", (gid,)).fetchall()
    cards = {c["key"]: c for c in queries._cards_for_keys(conn, [r["canonical_key"] for r in rows])}
    people = []
    for r in rows:
        c = cards.get(r["canonical_key"])
        if not c:
            continue
        c = dict(c)
        c["fit"] = bool(r["fit"])
        c["reasoning"] = r["reasoning"] or ""
        c["confidence"] = r["confidence"]
        people.append(c)
    d["people"] = people
    return d


def export_rows(conn, user, gid):
    d = group_dict(conn, gid, user)
    if not d:
        return []
    rows = conn.execute(
        """SELECT ac.canonical_key, ac.reasoning, ac.confidence
           FROM assistant_candidates ac WHERE ac.group_id=? AND ac.fit=1
           ORDER BY ac.confidence DESC""", (gid,)).fetchall()
    keys = [r["canonical_key"] for r in rows]
    reason = {r["canonical_key"]: (r["reasoning"], r["confidence"]) for r in rows}
    out = []
    cards = {c["key"]: c for c in queries._cards_for_keys(conn, keys)}
    for k in keys:
        c = cards.get(k)
        if not c:
            continue
        rr = reason[k]
        out.append({
            "first_name": c.get("first_name", ""), "last_name": c.get("last_name", ""),
            "class_year": c.get("class_year") or "", "role": c.get("role") or "",
            "fit_reasoning": rr[0] or "", "confidence": round(rr[1] or 0, 3),
            "interests": "; ".join(c.get("interests") or []),
            "source_url": c.get("source_url") or "", "profile_path": f"/p/{k}",
        })
    return out


# ---------------- background worker ----------------
_stop = threading.Event()
_thread = None


def _process_batch(conn, g):
    gid, model, criterion = g["id"], g["model"], g["criterion"]
    rows = conn.execute(
        """SELECT ac.canonical_key, p.profile_text
           FROM assistant_candidates ac JOIN profiles p ON p.canonical_key=ac.canonical_key
           WHERE ac.group_id=? AND ac.status='pending' LIMIT ?""",
        (gid, settings.ASSIST_BATCH)).fetchall()
    if not rows:
        pend = conn.execute("SELECT COUNT(*) FROM assistant_candidates "
                            "WHERE group_id=? AND status='pending'", (gid,)).fetchone()[0]
        if pend == 0:
            conn.execute("UPDATE assistant_groups SET status='done', updated_at=datetime('now') "
                         "WHERE id=? AND status='running'", (gid,))
        else:  # remaining pending have no joinable profile — don't stall
            conn.execute("UPDATE assistant_candidates SET status='error', reasoning='no profile', "
                         "judged_at=datetime('now') WHERE group_id=? AND status='pending'", (gid,))
        conn.commit()
        return

    def work(row):
        try:
            r = judge(model, criterion, row["profile_text"])
            return (row["canonical_key"], int(bool(r.get("fit"))),
                    (r.get("reasoning") or "")[:600], float(r.get("confidence") or 0), None)
        except Exception as e:  # noqa: BLE001
            return (row["canonical_key"], None, str(e)[:200], 0.0, "error")

    with cf.ThreadPoolExecutor(max_workers=settings.ASSIST_WORKERS) as ex:
        results = list(ex.map(work, rows))
    for ckey, fit, reasoning, conf, err in results:
        if err:
            conn.execute("UPDATE assistant_candidates SET status='error', reasoning=?, "
                         "judged_at=datetime('now') WHERE group_id=? AND canonical_key=?",
                         (reasoning, gid, ckey))
        else:
            conn.execute("UPDATE assistant_candidates SET status='judged', fit=?, reasoning=?, "
                         "confidence=?, judged_at=datetime('now') "
                         "WHERE group_id=? AND canonical_key=?", (fit, reasoning, conf, gid, ckey))
    conn.execute(
        """UPDATE assistant_groups SET
             judged=(SELECT COUNT(*) FROM assistant_candidates
                     WHERE group_id=? AND status IN ('judged','error')),
             matched=(SELECT COUNT(*) FROM assistant_candidates WHERE group_id=? AND fit=1),
             updated_at=datetime('now') WHERE id=?""", (gid, gid, gid))
    conn.commit()


def worker_loop():
    while not _stop.is_set():
        try:
            conn = db.connect()
            g = conn.execute("SELECT * FROM assistant_groups WHERE status='running' "
                             "ORDER BY updated_at LIMIT 1").fetchone()
            if not g:
                _stop.wait(2.5)
                continue
            _process_batch(conn, g)
        except Exception as e:  # noqa: BLE001
            print("[assistant worker] error:", e)
            _stop.wait(2.0)


def start_worker():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=worker_loop, name="assistant-worker", daemon=True)
    _thread.start()
    print("[BigRedAlumni] assistant worker started")


def stop_worker():
    _stop.set()
