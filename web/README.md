# BigRedAlumni

A LinkedIn-style, semantically-searchable directory of the Lawrenceville community, built on the
`alumni.sqlite` database (people extracted from 91 Issuu publications). React + Vite frontend,
FastAPI backend, behind a phone-OTP login.

## Features
- **Semantic + keyword search** over ~15k people ("documentary filmmaker", "climate policy in DC").
- **Directory** (`/browse`) — filter by role / class year, sort, page through everyone, and export
  the current view as CSV.
- **Profile per person** (`/p/:key`) — interests, role, class year, and **Featured In**: previews of
  the actual magazine pages they appear on (thumbnail → lightbox, deep link to Issuu, the snippet).
- **Shuffle** — pick / type a theme and swipe a Tinder-style deck (→ save, ← skip, arrow keys).
- **Favorites** — saved people with notes, stored per logged-in user in SQLite.
- **AI Assistant** (`/assistant`) — describe a group in plain English; the backend turns the brief
  into filters + a fit criterion, then judges each candidate with one LLM call (fit + reasoning) in
  a background worker that resumes after restarts. Export one group as CSV or all groups as a ZIP.
  Running a group calls the OpenAI API and costs money (the UI shows an estimate first).
- **About** (`/about`) — how the pipeline and assistant work, with screenshots.
- **Gated login** via phone OTP (Twilio) + JWT cookie; access limited to an allowlist.

## Prerequisites
0. A repo-root `.env` (copy `../.env.example` and fill it in). `data/` is not in git — it is
   produced by the pipeline (~1.8 GB), so a fresh clone must run the pipeline or copy `data/` in.
1. The data pipeline has been run (DB at `../data/db/alumni.sqlite`).
2. **Entity resolution has been run** (creates the `profiles*` tables the site reads):
   ```bash
   cd ..  &&  web/backend/.venv/bin/python resolve_people.py
   ```
3. Backend venv + deps installed:
   ```bash
   python3 -m venv backend/.venv
   backend/.venv/bin/python -m pip install -r backend/requirements.txt
   ```
4. Frontend deps: `cd frontend && npm install`.

## Run

**Production (one process, serves API + built SPA):**
```bash
DEV_AUTH_BYPASS=1 ./run_web.sh        # http://localhost:8000
```

**Development (live reload, two processes):**
```bash
cd backend && DEV_AUTH_BYPASS=1 .venv/bin/python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev            # http://localhost:5173
```

The scripts are bash and the venv layout is `backend/.venv/bin/python`, so on Windows run them
from **WSL** (the Windows `localhost` reaches the WSL server). If port 8000 is already in use,
pick another: `PORT=8010 DEV_AUTH_BYPASS=1 ./run_web.sh`.

## Login
- **Dev:** set `DEV_AUTH_BYPASS=1` (and optionally `DEV_CODE=123456`). No SMS is sent — log in with
  any allowed phone number and the dev code.
- **Real OTP:** leave `DEV_AUTH_BYPASS` unset. The backend texts a 6-digit code via Twilio
  (credentials from the repo `.env`). Only numbers in the allowlist may log in.

## Configuration (env / repo `.env`)
| var | meaning |
|-----|---------|
| `ADMIN_PHONE` | always allowed to log in |
| `ALLOWED_PHONES` | extra comma-separated allowlist |
| `DEV_AUTH_BYPASS` | `1` to skip SMS (local/testing only — never in production) |
| `DEV_CODE` | the accepted code when bypass is on (default `000000`) |
| `JWT_SECRET`, `JWT_TTL_HOURS`, `OTP_TTL_SECONDS` | session/OTP settings |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | SMS sending |
| `OPENAI_API_KEY` | query embeddings (semantic search) and the AI Assistant |
| `ASSIST_MODEL`, `ASSIST_PARSE_MODEL`, `ASSIST_WORKERS`, `ASSIST_BATCH` | Assistant models / concurrency |
| `PORT` | port for `run_web.sh` (default 8000) |
| `CORS_ORIGINS` | dev frontend origin (default `http://localhost:5173`) |

## Layout
```
backend/   FastAPI: main.py (routes) · vectors.py (numpy search) · queries.py (SQLite)
           · auth.py (OTP+JWT) · images.py (Pillow thumbnails) · settings.py (config+themes)
           · assistant.py (AI group builder + worker) · llm.py (OpenAI structured calls)
frontend/  React/Vite: pages/{Login,Home,Browse,Search,Profile,Shuffle,Favorites,Assistant,About}
           · components · api/client.ts · scripts/capture-about.mjs (About-page screenshots)
run_web.sh build + serve
```
The site reads the `profiles`, `profile_aliases`, `profiles_fts`, and `profile_embeddings` tables;
the raw `people`/`mentions`/`embeddings` tables and the CLI tools are untouched. It also creates
and writes its own `favorites` and assistant-group tables in the same database.
