"""BigRedAlumni API + static frontend (FastAPI)."""
import csv
import io
import re
import zipfile
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import dataroot  # noqa: F401
import assistant
import auth
import db
import images
import queries
import settings
import vectors


@asynccontextmanager
async def lifespan(app: FastAPI):
    n = vectors.load()
    queries.ensure_favorites(db.connect())
    assistant.ensure_assistant(db.connect())
    assistant.start_worker()
    print(f"[BigRedAlumni] loaded {n} profile vectors from {settings.DB_PATH}")
    if settings.DEV_AUTH_BYPASS:
        print(f"[BigRedAlumni] DEV_AUTH_BYPASS on — login code is {settings.DEV_CODE}")
    yield
    assistant.stop_worker()


app = FastAPI(title="BigRedAlumni", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])


# ---------------- auth ----------------
class PhoneIn(BaseModel):
    phone: str


class VerifyIn(BaseModel):
    phone: str
    code: str


def current_user(request: Request):
    return auth.verify_token(request.cookies.get(settings.COOKIE_NAME))


def require_user(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="authentication required")
    return u


@app.post("/api/auth/request-otp")
def request_otp(body: PhoneIn):
    ok, err = auth.request_otp(body.phone)
    if not ok:
        raise HTTPException(400, err or "could not send code")
    return {"ok": True, "dev": settings.DEV_AUTH_BYPASS}


@app.post("/api/auth/verify")
def verify(body: VerifyIn, response: Response):
    token = auth.verify_code(body.phone, body.code)
    if not token:
        raise HTTPException(401, "invalid or expired code")
    response.set_cookie(settings.COOKIE_NAME, token, httponly=True, samesite="lax",
                        max_age=settings.JWT_TTL_HOURS * 3600, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, "not authenticated")
    return {"phone": u}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(settings.COOKIE_NAME, path="/")
    return {"ok": True}


# ---------------- data ----------------
@app.get("/api/themes")
def themes(_: str = Depends(require_user)):
    return {"themes": settings.THEMES}


@app.get("/api/stats")
def stats(_: str = Depends(require_user)):
    return queries.stats(db.connect())


@app.get("/api/discover")
def discover(n: int = 12, _: str = Depends(require_user)):
    return {"results": queries.discover(db.connect(), n)}


@app.get("/api/search")
def search(q: str = "", mode: str = "hybrid", role: str = "", year: str = "",
           n: int = 24, _: str = Depends(require_user)):
    return {"results": queries.run_search(
        db.connect(), q, mode, role or None, queries.parse_year(year), n)}


@app.get("/api/browse")
def browse(q: str = "", mode: str = "keyword", role: str = "", year: str = "",
           sort: str = "mentions", offset: int = 0, limit: int = 60,
           _: str = Depends(require_user)):
    return queries.browse(db.connect(), q, mode, role or None,
                          queries.parse_year(year), sort, offset, limit)


@app.get("/api/shuffle")
def shuffle(theme: str = "", q: str = "", n: int = 30, _: str = Depends(require_user)):
    return {"results": queries.shuffle(db.connect(), theme, q, n)}


@app.get("/api/export.csv")
def export_csv(q: str = "", mode: str = "keyword", role: str = "", year: str = "",
               sort: str = "mentions", _: str = Depends(require_user)):
    rows = queries.export_rows(db.connect(), q, mode, role or None,
                               queries.parse_year(year), sort)
    cols = ["first_name", "last_name", "class_year", "role", "mentions", "publications",
            "class_year_tags", "interests", "full_name", "source_document", "source_url",
            "source_image_url", "source_image_path", "profile_path"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=bigredalumni.csv"})


@app.get("/api/person/{ckey:path}")
def person(ckey: str, user: str = Depends(require_user)):
    prof = queries.get_person(db.connect(), ckey, user)
    if not prof:
        raise HTTPException(404, "not found")
    return prof


# ---------------- favorites (per user) ----------------
class FavIn(BaseModel):
    key: str
    note: str | None = None


class NoteIn(BaseModel):
    note: str


@app.get("/api/favorites")
def favorites(user: str = Depends(require_user)):
    return {"favorites": queries.list_favorites(db.connect(), user)}


@app.get("/api/favorites/keys")
def favorite_keys(user: str = Depends(require_user)):
    return {"keys": queries.favorite_keys(db.connect(), user)}


@app.post("/api/favorites")
def add_favorite(body: FavIn, user: str = Depends(require_user)):
    queries.add_favorite(db.connect(), user, body.key, body.note or "")
    return {"ok": True}


@app.put("/api/favorites/{key:path}")
def set_note(key: str, body: NoteIn, user: str = Depends(require_user)):
    queries.update_note(db.connect(), user, key, body.note)
    return {"ok": True}


@app.delete("/api/favorites/{key:path}")
def remove_favorite(key: str, user: str = Depends(require_user)):
    queries.remove_favorite(db.connect(), user, key)
    return {"ok": True}


# ---------------- AI group-builder assistant ----------------
class BriefIn(BaseModel):
    prompt: str
    model: str | None = None


class GroupPatch(BaseModel):
    criterion: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    roles: list[str] | None = None


@app.post("/api/assistant/groups")
def create_group(body: BriefIn, user: str = Depends(require_user)):
    if not (body.prompt or "").strip():
        raise HTTPException(400, "prompt required")
    return assistant.create_group(db.connect(), user, body.prompt.strip(), body.model)


@app.get("/api/assistant/groups")
def list_groups(user: str = Depends(require_user)):
    return {"groups": assistant.list_groups(db.connect(), user)}


@app.get("/api/assistant/groups/{gid}")
def get_group(gid: int, include: str = "matched", user: str = Depends(require_user)):
    d = assistant.group_detail(db.connect(), user, gid, include)
    if not d:
        raise HTTPException(404, "not found")
    return d


@app.patch("/api/assistant/groups/{gid}")
def patch_group(gid: int, body: GroupPatch, user: str = Depends(require_user)):
    d = assistant.update_group(
        db.connect(), user, gid, criterion=body.criterion,
        year_min=body.year_min, year_max=body.year_max, roles=body.roles)
    if not d:
        raise HTTPException(400, "can only edit a draft group")
    return d


@app.post("/api/assistant/groups/{gid}/run")
def run_group(gid: int, user: str = Depends(require_user)):
    d = assistant.run_group(db.connect(), user, gid)
    if not d:
        raise HTTPException(404, "not found")
    return d


@app.post("/api/assistant/groups/{gid}/cancel")
def cancel_group(gid: int, user: str = Depends(require_user)):
    return assistant.cancel_group(db.connect(), user, gid) or {"ok": False}


@app.delete("/api/assistant/groups/{gid}")
def delete_group(gid: int, user: str = Depends(require_user)):
    return {"ok": assistant.delete_group(db.connect(), user, gid)}


def _group_csv(conn, user: str, g: dict) -> str:
    """CSV for one assistant group: a header block describing the search, then match rows."""
    rows = assistant.export_rows(conn, user, g["id"])
    buf = io.StringIO()
    w = csv.writer(buf)
    filt = g["filters"]
    years = f"{filt.get('year_min') or 'any'} - {filt.get('year_max') or 'any'}"
    w.writerow(["Group", g["title"]])
    w.writerow(["Search brief", g["prompt"]])
    w.writerow(["Fit criterion", g["criterion"]])
    w.writerow(["Class years", years])
    w.writerow(["Roles", ", ".join(g["effective_roles"]) or "all"])
    w.writerow(["Model", g["model"]])
    w.writerow(["Candidates judged", f"{g['judged']} of {g['total']}"])
    w.writerow(["Matches", g["matched"]])
    w.writerow(["Run date", g["updated_at"]])
    w.writerow([])
    cols = ["first_name", "last_name", "class_year", "role", "fit_reasoning", "confidence",
            "interests", "source_url", "profile_path"]
    dw = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    dw.writeheader()
    for r in rows:
        dw.writerow(r)
    # UTF-8 BOM so Excel on Windows decodes names/quotes correctly
    return "\ufeff" + buf.getvalue()


@app.get("/api/assistant/groups/{gid}/export.csv")
def export_group(gid: int, user: str = Depends(require_user)):
    conn = db.connect()
    g = assistant.group_dict(conn, gid, user)
    if not g:
        raise HTTPException(404, "not found")
    return Response(content=_group_csv(conn, user, g), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=group-{gid}.csv"})


@app.get("/api/assistant/export.zip")
def export_all_groups(user: str = Depends(require_user)):
    """All of the user's past group searches, one CSV per group, zipped (uncompressed names visible, no password)."""
    conn = db.connect()
    groups = assistant.list_groups(conn, user)
    if not groups:
        raise HTTPException(404, "no groups to export")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for lg in groups:
            g = assistant.group_dict(conn, lg["id"], user)
            if not g:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", g["title"].lower()).strip("-")[:60] or "group"
            zf.writestr(f"group-{g['id']}-{slug}.csv", _group_csv(conn, user, g))
    return Response(content=zbuf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=assistant-groups.zip"})


# ---------------- images (public bytes; the magazines are public) ----------------
@app.get("/img/{slug}/{page}")
def img(slug: str, page: int, w: int = 0, full: int = 0):
    p = images.get_image(slug, page, w=(w or None), full=bool(full))
    if not p:
        raise HTTPException(404, "image not found")
    return FileResponse(p, media_type="image/jpeg")


# ---------------- static frontend (built SPA) ----------------
if settings.DIST.exists():
    app.mount("/assets", StaticFiles(directory=settings.DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # don't shadow API/image routes
        if full_path.startswith(("api/", "img/")):
            raise HTTPException(404)
        index = settings.DIST / "index.html"
        if index.exists():
            # always revalidate the shell so old tabs pick up new hashed bundles
            return FileResponse(index, media_type="text/html",
                                headers={"Cache-Control": "no-cache"})
        raise HTTPException(404)
else:
    @app.get("/")
    def no_dist():
        return JSONResponse({"message": "Frontend not built yet. Run the Vite dev server "
                             "(npm run dev) or `npm run build`."})
