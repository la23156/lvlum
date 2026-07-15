"""Build semantic-search embeddings, one vector per person profile.

Embeds each person's `profile_text` with an OpenAI embedding model (default
text-embedding-3-large) and stores an L2-normalized float32 vector keyed by the stable
person_key. Idempotent: a person is re-embedded only when its profile_text changed
(tracked via profile_hash), so re-running after new extraction is cheap.

Usage:
    python embed_people.py [--model ID] [--rebuild]
"""
import argparse
import hashlib
import struct
import sys

import config
import db
import httputil


def l2_normalize(vec):
    s = sum(x * x for x in vec) ** 0.5
    if s == 0:
        return vec
    return [x / s for x in vec]


def pack(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def embed_batch(texts, model):
    key = config.openai_key()
    status, body = httputil.post_json(
        f"{config.OPENAI_BASE}/embeddings",
        {"model": model, "input": texts},
        headers={"Authorization": f"Bearer {key}"})
    if status != 200:
        raise RuntimeError(f"embeddings {status}: {str(body)[:300]}")
    return [d["embedding"] for d in body["data"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=config.EMBED_MODEL)
    ap.add_argument("--rebuild", action="store_true", help="re-embed everyone")
    args = ap.parse_args()

    conn = db.connect()
    db.init(conn)
    model = args.model

    existing = {}
    if not args.rebuild:
        for r in conn.execute("SELECT person_key, profile_hash, model FROM embeddings"):
            existing[r["person_key"]] = (r["profile_hash"], r["model"])

    people = conn.execute(
        "SELECT person_key, profile_text FROM people WHERE person_key IS NOT NULL").fetchall()
    todo = []
    for r in people:
        text = (r["profile_text"] or "")[: config.EMBED_MAX_CHARS]
        h = hashlib.sha256((model + "\n" + text).encode("utf-8")).hexdigest()
        prev = existing.get(r["person_key"])
        if prev and prev[0] == h and prev[1] == model:
            continue
        todo.append((r["person_key"], text, h))

    print(f"{len(people)} people; {len(todo)} need embedding (model={model}).")
    done = 0
    for i in range(0, len(todo), config.EMBED_BATCH):
        batch = todo[i: i + config.EMBED_BATCH]
        vecs = embed_batch([t for _, t, _ in batch], model)
        for (pk, _t, h), v in zip(batch, vecs):
            nv = l2_normalize(v)
            conn.execute(
                """INSERT INTO embeddings (person_key, model, dim, norm_vector, profile_hash)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(person_key) DO UPDATE SET
                     model=excluded.model, dim=excluded.dim,
                     norm_vector=excluded.norm_vector, profile_hash=excluded.profile_hash""",
                (pk, model, len(nv), pack(nv), h))
        conn.commit()
        done += len(batch)
        print(f"  embedded {done}/{len(todo)}")
    n = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    print(f"Done. {n} person vectors stored.")


if __name__ == "__main__":
    sys.exit(main())
