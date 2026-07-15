# BigRedAlumni

A LinkedIn-style, semantically-searchable directory of the Lawrenceville community, built on the
`alumni.sqlite` database (people extracted from 91 Issuu publications). React + Vite frontend,
FastAPI backend, behind a phone-OTP login.

## Features
- **Semantic + keyword search** over ~15k people ("documentary filmmaker", "climate policy in DC").
- **Profile per person** (`/p/:key`) — interests, role, class year, and **Featured In**: previews of
  the actual magazine pages they appear on (thumbnail → lightbox, deep link to Issuu, the snippet).
- **Shuffle** — pick/ type a theme and swipe a Tinder-style deck (→ save, ← skip, arrow keys); saved
  people persist in the browser.
- **Gated login** via phone OTP (Twilio) + JWT cookie; access limited to an allowlist.

## Prerequisites
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
| `OPENAI_API_KEY` | query embeddings (semantic search) |
| `CORS_ORIGINS` | dev frontend origin (default `http://localhost:5173`) |

## Layout
```
backend/   FastAPI: main.py (routes) · vectors.py (numpy search) · queries.py (SQLite)
           · auth.py (OTP+JWT) · images.py (Pillow thumbnails) · settings.py (config+themes)
frontend/  React/Vite: pages/{Login,Home,Search,Profile,Shuffle} · components · api/client.ts
run_web.sh build + serve
```
The site reads the `profiles`, `profile_aliases`, `profiles_fts`, and `profile_embeddings` tables;
the raw `people`/`mentions`/`embeddings` tables and the CLI tools are untouched.
