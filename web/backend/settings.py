"""Backend settings: paths, auth/Twilio/JWT (from the repo .env), and the curated theme list."""
import os

import dataroot           # noqa: F401  (sets up sys.path)
import config as datacfg  # repo-root config.py (DB path, .env loader, OpenAI)

ROOT = dataroot.ROOT
DB_PATH = datacfg.DB_PATH
RAW = datacfg.RAW                       # data/raw/issuu/<slug>/page_NNN.jpg
THUMBS = datacfg.DATA / "thumbs"
DIST = ROOT / "web" / "frontend" / "dist"
_ENV = datacfg._ENV                     # parsed .env dict


def env(key, default=None):
    return os.environ.get(key) or _ENV.get(key, default)


# --- auth ---
JWT_SECRET = env("JWT_SECRET", "dev-insecure-secret")
JWT_TTL_HOURS = int(env("JWT_TTL_HOURS", "24"))
OTP_TTL = int(env("OTP_TTL_SECONDS", "300"))
ADMIN_PHONE = env("ADMIN_PHONE", "")
ALLOWED_PHONES = [p.strip() for p in (env("ALLOWED_PHONES", "") or "").split(",") if p.strip()]
TWILIO_SID = env("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = env("TWILIO_AUTH_TOKEN")
TWILIO_FROM = env("TWILIO_FROM_NUMBER")
DEV_AUTH_BYPASS = str(env("DEV_AUTH_BYPASS", "")).lower() in ("1", "true", "yes", "on")
DEV_CODE = env("DEV_CODE", "000000")
COOKIE_NAME = "bra_session"
CORS_ORIGINS = [o for o in (env("CORS_ORIGINS", "http://localhost:5173") or "").split(",") if o]

# --- AI group-builder assistant ---
ASSIST_MODEL = env("ASSIST_MODEL", "gpt-5-mini")        # per-candidate binary judge
ASSIST_PARSE_MODEL = env("ASSIST_PARSE_MODEL", "gpt-5-mini")  # brief -> filters
ASSIST_WORKERS = int(env("ASSIST_WORKERS", "6"))
ASSIST_BATCH = int(env("ASSIST_BATCH", "24"))
ASSIST_MAX_CANDIDATES = int(env("ASSIST_MAX_CANDIDATES", "8000"))
ASSIST_PROFILE_CHARS = int(env("ASSIST_PROFILE_CHARS", "3500"))
ASSIST_COST_PER_CALL = float(env("ASSIST_COST_PER_CALL", "0.002"))  # rough USD/judge for estimate

# --- suggested themes for search + shuffle ---
THEMES = [
    {"key": "entrepreneurs", "label": "Entrepreneurs & Founders", "emoji": "🚀",
     "query": "entrepreneur, startup founder, built and led a company, CEO"},
    {"key": "finance", "label": "Finance & Investing", "emoji": "📈",
     "query": "finance, investing, venture capital, private equity, hedge fund, banking"},
    {"key": "journalists", "label": "Journalists & Media", "emoji": "📰",
     "query": "journalist, reporter, war correspondent, editor, broadcaster, media"},
    {"key": "film", "label": "Film & Television", "emoji": "🎬",
     "query": "filmmaker, director, producer, actor, screenwriter, television and film"},
    {"key": "music", "label": "Music", "emoji": "🎵",
     "query": "musician, composer, singer, conductor, band, music industry"},
    {"key": "visual_arts", "label": "Visual Arts", "emoji": "🎨",
     "query": "artist, painter, sculptor, photographer, designer, visual arts"},
    {"key": "writers", "label": "Writers & Authors", "emoji": "✍️",
     "query": "author, novelist, poet, writer, published a book"},
    {"key": "science", "label": "Science & Research", "emoji": "🔬",
     "query": "scientist, researcher, physics, biology, chemistry, PhD research"},
    {"key": "medicine", "label": "Medicine & Health", "emoji": "🩺",
     "query": "doctor, physician, surgeon, medicine, public health, healthcare"},
    {"key": "law_policy", "label": "Law & Public Policy", "emoji": "⚖️",
     "query": "lawyer, attorney, judge, public policy, government, politics, diplomat"},
    {"key": "athletes", "label": "Athletes & Olympians", "emoji": "🏅",
     "query": "athlete, Olympic, professional sports, varsity champion, NHL NFL NBA"},
    {"key": "education", "label": "Education & Academia", "emoji": "🎓",
     "query": "teacher, professor, educator, academic, school leadership"},
    {"key": "technology", "label": "Technology & Engineering", "emoji": "💻",
     "query": "software, engineer, technology, computer science, AI, hardware"},
    {"key": "social_impact", "label": "Social Impact & Nonprofits", "emoji": "🌍",
     "query": "nonprofit, philanthropy, social impact, activism, community service"},
    {"key": "military", "label": "Military & Service", "emoji": "🎖️",
     "query": "military service, armed forces, veteran, navy army air force"},
    {"key": "food", "label": "Food & Hospitality", "emoji": "🍽️",
     "query": "chef, restaurant, hospitality, culinary, food and beverage"},
]
THEME_BY_KEY = {t["key"]: t for t in THEMES}
