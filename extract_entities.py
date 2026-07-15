"""Vision OCR + structured entity extraction over scraped Issuu page images.

For each not-yet-processed page image we ask an OpenAI vision model to (a) transcribe the page
and (b) extract every Lawrenceville-affiliated person with their class year, role, and the
interests/activities the text mentions. Results land in the `pages` and `mentions` tables;
a final pass dedupes them into `people`.

Model: by default we probe /v1/models and pick the best available from config.MODEL_PREFERENCE
(gpt-5 > gpt-4.1 > gpt-4o). Override with EXTRACT_MODEL=<id>.

Idempotent + resumable: only pages with status != 'done' are processed.

Usage:
    python extract_entities.py [--limit-docs N] [--max-pages N] [--model ID] [--detail high|low]
    python extract_entities.py --finalize-only      # just rebuild the people table
"""
import argparse
import base64
import concurrent.futures as cf
import sys
import time
from pathlib import Path

import config
import db
import httputil

SYSTEM_PROMPT = (
    "You are a meticulous archivist digitizing The Lawrenceville School's alumni magazine "
    "and related publications. You transcribe pages and extract structured records of people."
)

USER_INSTRUCTION = (
    "This is one page from a Lawrenceville School publication (often the alumni magazine "
    "'The Lawrentian', including 'Class Notes' sections).\n\n"
    "1. Transcribe ALL readable text on the page into `page_text` (preserve names and years).\n"
    "2. Extract every PERSON who is a Lawrenceville student, alumnus/alumna, faculty, or parent "
    "and who is named on this page. For each person return:\n"
    "   - name: full name as printed.\n"
    "   - class_year: their Lawrenceville class year if shown (e.g. \"'85\", \"P'12\", \"2007\"). "
    "Empty string if none shown.\n"
    "   - role: one of student, alumnus, faculty, parent, unknown.\n"
    "   - interests: short phrases describing what the text says about their interests, "
    "activities, career, achievements, hobbies, or life updates (e.g. \"sailing\", "
    "\"founded a biotech startup\", \"varsity crew\", \"married in Maine\"). Empty list if none.\n"
    "   - snippet: a short verbatim quote (<=200 chars) from the page about this person.\n"
    "   - confidence: 0.0-1.0 that this is a real distinct Lawrenceville person.\n"
    "Do NOT invent people. If the page has no named people, return an empty `people` list. "
    "Skip generic staff bylines unless the text describes them personally."
)

PERSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "class_year": {"type": "string"},
        "role": {"type": "string",
                 "enum": ["student", "alumnus", "faculty", "parent", "unknown"]},
        "interests": {"type": "array", "items": {"type": "string"}},
        "snippet": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["name", "class_year", "role", "interests", "snippet", "confidence"],
}

RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "page_text": {"type": "string"},
        "people": {"type": "array", "items": PERSON_SCHEMA},
    },
    "required": ["page_text", "people"],
}


def pick_model(requested: str | None) -> str:
    key = config.openai_key()
    # GET /v1/models
    try:
        ids = {m["id"] for m in httputil.get_json(
            f"{config.OPENAI_BASE}/models",
            headers={"Authorization": f"Bearer {key}"})["data"]}
    except Exception as e:  # noqa: BLE001
        print(f"  (could not list models: {e}; trusting preference list)")
        ids = set()

    candidates = [requested] if requested else list(config.MODEL_PREFERENCE)
    if not requested:
        candidates = ([config.EXTRACT_MODEL] if config.EXTRACT_MODEL else []) + candidates
    for c in candidates:
        if not c:
            continue
        if not ids or c in ids or any(i == c or i.startswith(c + "-") for i in ids):
            return c
    # last resort
    return (requested or config.EXTRACT_MODEL or config.MODEL_PREFERENCE[-1])


def _salvage_page_text(content: str) -> str:
    """Best-effort recovery of the page_text value from truncated JSON like
    '{"page_text":"....(cut off)'. Returns the partial transcript or ''."""
    import re
    m = re.search(r'"page_text"\s*:\s*"', content)
    if not m:
        return ""
    frag = content[m.end():]
    # drop a trailing partial escape, unescape common sequences
    frag = frag.rstrip("\\")
    return frag.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')


def call_vision(model: str, image_path: Path, detail: str, reasoning: str | None = None,
                max_tokens: int = 8000) -> dict:
    key = config.openai_key()
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{b64}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": USER_INSTRUCTION},
            {"type": "image_url", "image_url": {"url": data_uri, "detail": detail}},
        ]},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "page_records", "strict": True, "schema": RESULT_SCHEMA}},
        "max_completion_tokens": max_tokens,
    }
    # Reasoning models (gpt-5 / o-series) reason far more than this OCR+extraction task needs.
    # 'minimal' keeps the quality but is ~3x faster and much cheaper. Ignored by non-reasoning
    # models (we drop it adaptively on a 400).
    if reasoning and (model.startswith("gpt-5") or model.startswith("o")):
        payload["reasoning_effort"] = reasoning
    headers = {"Authorization": f"Bearer {key}"}

    def send():
        s, b = httputil.post_json(f"{config.OPENAI_BASE}/chat/completions",
                                  payload, headers=headers, timeout=150)
        # adapt to model-specific param quirks
        if s == 400 and isinstance(b, dict):
            msg = str(b.get("error", {}).get("message", "")).lower()
            changed = False
            if "max_completion_tokens" in msg or "max_tokens" in msg:
                payload["max_tokens"] = payload.pop("max_completion_tokens", max_tokens)
                changed = True
            if "reasoning_effort" in msg or "reasoning" in msg:
                payload.pop("reasoning_effort", None)
                changed = True
            if changed:
                s, b = httputil.post_json(f"{config.OPENAI_BASE}/chat/completions",
                                          payload, headers=headers, timeout=150)
        return s, b

    status, body = send()
    if status != 200:
        raise RuntimeError(f"openai {status}: {str(body)[:300]}")
    import json
    choice = body["choices"][0]
    content = (choice.get("message", {}) or {}).get("content") or ""
    finish = choice.get("finish_reason")
    if not content.strip():
        # empty completion (e.g. a pure-image page) -> treat as no people, keep OCR empty
        if finish == "length":
            raise RuntimeError("empty content, finish_reason=length (raise token cap)")
        return {"page_text": "", "people": []}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        if finish == "content_filter":
            # moderation halted generation mid-JSON (over-triggers on some essay/quote pages).
            # Salvage the partial transcript; these pages carry few/no alumni records.
            return {"page_text": _salvage_page_text(content), "people": [],
                    "_partial": "content_filter"}
        if finish == "length":
            raise RuntimeError("truncated JSON (finish_reason=length)")
        raise


def pending_pages(conn, limit_docs=None, max_pages=None):
    """Yield (page_id, document_id, page_num, image_path) for unprocessed pages."""
    doc_filter = ""
    if limit_docs:
        doc_ids = [r[0] for r in conn.execute(
            "SELECT id FROM documents ORDER BY id LIMIT ?", (limit_docs,)).fetchall()]
        if not doc_ids:
            return
        doc_filter = " AND document_id IN (%s)" % ",".join("?" * len(doc_ids))
        params = doc_ids
    else:
        params = []
    q = ("SELECT id, document_id, page_num, image_path FROM pages "
         "WHERE status != 'done'" + doc_filter + " ORDER BY document_id, page_num")
    rows = conn.execute(q, params).fetchall()
    if max_pages:
        rows = rows[:max_pages]
    for r in rows:
        yield r["id"], r["document_id"], r["page_num"], r["image_path"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-docs", type=int, help="only first N documents")
    ap.add_argument("--max-pages", type=int, help="cap total pages this run (testing)")
    ap.add_argument("--model", help="force a specific OpenAI model id")
    ap.add_argument("--detail", default="high", choices=["high", "low"])
    ap.add_argument("--reasoning", default="minimal",
                    choices=["minimal", "low", "medium", "high"],
                    help="reasoning effort for gpt-5/o models (default minimal: fast, "
                         "same OCR quality)")
    ap.add_argument("--max-tokens", type=int, default=8000,
                    help="output token cap per page (raise for dense pages that truncate)")
    ap.add_argument("--finalize-only", action="store_true")
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn)

    if args.finalize_only:
        db.rebuild_people(conn)
        print("people table rebuilt.")
        return

    model = pick_model(args.model)
    print(f"Using vision model: {model}  (detail={args.detail}, reasoning={args.reasoning})")

    jobs = list(pending_pages(conn, args.limit_docs, args.max_pages))
    print(f"{len(jobs)} page(s) to process.\n")
    if not jobs:
        db.rebuild_people(conn)
        print("Nothing pending; people table rebuilt.")
        return

    done = err = mentions = 0

    def work(job):
        page_id, doc_id, page_num, image_path = job
        p = Path(image_path)
        if not p.exists():
            return job, None, "missing image"
        try:
            return job, call_vision(model, p, args.detail, args.reasoning,
                                    args.max_tokens), None
        except Exception as e:  # noqa: BLE001
            return job, None, str(e)

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=config.EXTRACT_WORKERS) as ex:
        for job, result, error in ex.map(work, jobs):
            page_id, doc_id, page_num, image_path = job
            if error or result is None:
                db.record_page_result(conn, page_id, None, "error", error)
                err += 1
            else:
                text = result.get("page_text", "")
                # cache OCR text next to the image
                ocr_dir = Path(image_path).parent / "ocr"
                ocr_dir.mkdir(exist_ok=True)
                (ocr_dir / f"page_{page_num:03d}.txt").write_text(text, encoding="utf-8")
                db.record_page_result(conn, page_id, text, "done")
                for m in result.get("people", []):
                    db.insert_mention(conn, doc_id, page_id, page_num, m)
                    mentions += 1
                done += 1
            if (done + err) % 10 == 0:
                conn.commit()
                rate = (done + err) / max(time.time() - t0, 1e-6)
                print(f"  {done+err}/{len(jobs)} pages  "
                      f"({done} ok, {err} err, {mentions} mentions)  {rate:.1f}/s")
    conn.commit()

    print(f"\nExtraction pass complete: {done} ok, {err} errors, {mentions} mentions.")
    print("Rebuilding people table...")
    db.rebuild_people(conn)
    n_people = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    print(f"people: {n_people} distinct persons.")


if __name__ == "__main__":
    sys.exit(main())
