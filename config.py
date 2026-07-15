"""Central configuration for the Lawrenceville alumni database pipeline.

Pure stdlib. Loads secrets from the project .env (no python-dotenv dependency).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Issuu source ---
ISSUU_USER = "thelawrencevilleschool"
PROFILE_URL = f"https://issuu.com/{ISSUU_USER}"

# --- Paths ---
DATA = ROOT / "data"
RAW = DATA / "raw" / "issuu"          # data/raw/issuu/<slug>/page_NNN.jpg
DB_DIR = DATA / "db"
DB_PATH = DB_DIR / "alumni.sqlite"
EXPORT_DIR = DATA / "exports"

# --- HTTP ---
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HTTP_TIMEOUT = 60
DOWNLOAD_WORKERS = 8        # parallel page-image downloads within a document
REQUEST_PAUSE = 0.15       # polite pause between Issuu profile/oembed calls

# --- Extraction (OpenAI vision) ---
# User asked for a model better than gpt-4o. We probe /v1/models at runtime and pick the
# first available from this preference list (override with EXTRACT_MODEL env var).
MODEL_PREFERENCE = ["gpt-5", "gpt-4.1", "gpt-4o"]
EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL")   # explicit override, optional
EXTRACT_WORKERS = int(os.environ.get("EXTRACT_WORKERS", "6"))
OPENAI_BASE = "https://api.openai.com/v1"

# --- Embeddings (semantic search) ---
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-large")
EMBED_BATCH = 64
EMBED_MAX_CHARS = 7000   # keep well under the model's token limit


def _load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_ENV = _load_env(ROOT / ".env")


def openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY") or _ENV.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not found in environment or .env")
    return key


def ensure_dirs():
    for d in (RAW, DB_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
