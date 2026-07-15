"""Put the repo root on sys.path so the backend can reuse the existing data-layer modules
(config, db, embed_people, httputil, search)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
