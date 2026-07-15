"""In-memory vector store for semantic search over canonical profiles (numpy)."""
import threading

import numpy as np

import dataroot  # noqa: F401
import db

_lock = threading.Lock()
_M = None          # (N, dim) float32, L2-normalized
_keys = None       # list[str]
_role = None       # np.array[str]
_year = None       # list[str|None]


def load():
    global _M, _keys, _role, _year
    conn = db.connect()
    rows = conn.execute(
        """SELECT pe.canonical_key, pe.norm_vector, p.role, p.class_year
           FROM profile_embeddings pe JOIN profiles p ON p.canonical_key=pe.canonical_key"""
    ).fetchall()
    keys, vecs, roles, years = [], [], [], []
    for r in rows:
        keys.append(r["canonical_key"])
        vecs.append(np.frombuffer(r["norm_vector"], dtype=np.float32))
        roles.append(r["role"] or "")
        years.append(r["class_year"])
    with _lock:
        _M = np.vstack(vecs) if vecs else np.zeros((0, 3072), dtype=np.float32)
        _keys = keys
        _role = np.array(roles)
        _year = years
    return len(keys)


def count():
    return 0 if _keys is None else len(_keys)


def search(qvec, role=None, yrange=None, n=24, exclude=None):
    """Return [(canonical_key, score)] top-n by cosine, with optional role/year filters."""
    if _M is None or _M.shape[0] == 0:
        return []
    q = np.asarray(qvec, dtype=np.float32)
    scores = _M @ q
    mask = np.ones(len(_keys), dtype=bool)
    if role:
        mask &= (_role == role)
    if yrange:
        lo, hi = yrange
        mask &= np.array([(y is not None and (lo is None or y >= lo) and (hi is None or y <= hi))
                          for y in _year])
    idx = np.where(mask)[0]
    if exclude:
        ex = set(exclude)
        idx = np.array([i for i in idx if _keys[i] not in ex], dtype=int)
    if idx.size == 0:
        return []
    order = idx[np.argsort(-scores[idx])[:n]]
    return [(_keys[i], float(scores[i])) for i in order]
