"""Optional: write a concise prose bio per person from their aggregated mentions.

Uses a cheap model by default (gpt-5-mini). The summary is stored in people.summary and is
included in the embedding input on the next embed run, improving semantic search. Idempotent:
only people without a summary (or --rebuild) are processed.

Usage:
    python build_summaries.py [--model ID] [--min-mentions N] [--limit N] [--rebuild]
"""
import argparse
import concurrent.futures as cf
import sys

import config
import db
import httputil

SYS = ("You write a one- to three-sentence factual bio of a member of the Lawrenceville School "
       "community, based ONLY on the provided mentions. State their class year/role if known and "
       "summarize their interests, work, and notable activities. No speculation; no fluff.")


def summarize(model, profile_text):
    key = config.openai_key()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user", "content": profile_text[: config.EMBED_MAX_CHARS]},
        ],
        "max_completion_tokens": 400,
    }
    if model.startswith("gpt-5") or model.startswith("o"):
        payload["reasoning_effort"] = "minimal"
    status, body = httputil.post_json(
        f"{config.OPENAI_BASE}/chat/completions", payload,
        headers={"Authorization": f"Bearer {key}"})
    if status == 400 and "max_completion_tokens" in str(body).lower():
        payload["max_tokens"] = payload.pop("max_completion_tokens")
        status, body = httputil.post_json(
            f"{config.OPENAI_BASE}/chat/completions", payload,
            headers={"Authorization": f"Bearer {key}"})
    if status != 200:
        raise RuntimeError(f"{status}: {str(body)[:200]}")
    return body["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--min-mentions", type=int, default=1,
                    help="only summarize people with >= this many mentions")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn)
    cond = "" if args.rebuild else "AND (summary IS NULL OR summary='')"
    rows = conn.execute(
        f"""SELECT id, profile_text FROM people
            WHERE mention_count >= ? {cond} ORDER BY mention_count DESC""",
        (args.min_mentions,)).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} people to summarize (model={args.model}).")

    def work(r):
        try:
            return r["id"], summarize(args.model, r["profile_text"] or ""), None
        except Exception as e:  # noqa: BLE001
            return r["id"], None, str(e)

    done = err = 0
    with cf.ThreadPoolExecutor(max_workers=config.EXTRACT_WORKERS) as ex:
        for pid, summary, error in ex.map(work, rows):
            if error:
                err += 1
            else:
                conn.execute("UPDATE people SET summary=? WHERE id=?", (summary, pid))
                done += 1
            if (done + err) % 25 == 0:
                conn.commit()
                print(f"  {done+err}/{len(rows)}  ({err} err)")
    conn.commit()
    print(f"Done. {done} summaries, {err} errors.")


if __name__ == "__main__":
    sys.exit(main())
