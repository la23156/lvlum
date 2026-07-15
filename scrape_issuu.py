"""Scrape all Lawrenceville School publications from Issuu.

Method (no third-party services):
  1. Enumerate slugs from the profile pages:
        https://issuu.com/thelawrencevilleschool        -> page 1 (~48 docs)
        https://issuu.com/thelawrencevilleschool/2       -> page 2 (~45 docs)
        ... continue /N until a page yields no new slugs.
  2. Per document:
        - title   <- https://issuu.com/oembed?url=<doc_url>&format=json
        - pages   <- https://reader3.isu.pub/<user>/<slug>/reader3_4.json  (document.pages[])
        - images  <- https://<imageUri>  e.g. image.isu.pub/<id>/jpg/page_N.jpg
     Saved to data/raw/issuu/<slug>/page_NNN.jpg (+ meta.json), document row upserted.

Idempotent: existing images are skipped, so re-running resumes.

Usage:
    python scrape_issuu.py [--limit N] [--only SLUG[,SLUG...]] [--list-only]
"""
import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from pathlib import Path

import config
import db
import httputil

DOCS_RE = re.compile(rf"/{config.ISSUU_USER}/docs/([A-Za-z0-9_-]+)")


def enumerate_slugs() -> list[str]:
    """Return ordered, de-duplicated slug list across all profile pages."""
    seen, ordered = set(), []
    page = 1
    empties = 0
    while True:
        url = config.PROFILE_URL if page == 1 else f"{config.PROFILE_URL}/{page}"
        try:
            html = httputil.get_text(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! page {page} fetch failed: {e}")
            html = ""
        found = []
        for slug in DOCS_RE.findall(html):
            if slug not in seen:
                seen.add(slug)
                ordered.append(slug)
                found.append(slug)
        print(f"  profile page {page}: +{len(found)} new (total {len(ordered)})")
        # page 1 is the base URL; "/1" is a dead route, so the second page is "/2".
        if page >= 2 and not found:
            empties += 1
            if empties >= 1:
                break
        page += 1
        if page > 30:  # safety bound
            break
        time.sleep(config.REQUEST_PAUSE)
    return ordered


IMG_HOST = "https://image.isu.pub"
THUMB_RE = re.compile(r"image\.isu\.pub/([^/]+)/")


def oembed_info(slug: str):
    """Return (title, document_image_id) via Issuu's public oembed endpoint.

    thumbnail_url looks like
      https://image.isu.pub/<docid>/jpg/page_1_thumb_medium.jpg
    so <docid> is the image base used for every page image.
    """
    doc_url = f"{config.PROFILE_URL}/docs/{slug}"
    try:
        oe = httputil.get_json(f"https://issuu.com/oembed?url={doc_url}&format=json")
        title = oe.get("title") or slug
        m = THUMB_RE.search(oe.get("thumbnail_url", "") or "")
        return title, (m.group(1) if m else None)
    except Exception:  # noqa: BLE001
        return slug, None


def _img_exists(docid: str, n: int) -> bool:
    url = f"{IMG_HOST}/{docid}/jpg/page_{n}.jpg"
    try:
        data = httputil.get_bytes(url, headers={"Range": "bytes=0-0"}, retries=1)
        return bool(data)
    except Exception:  # noqa: BLE001  (403/404 on missing pages)
        return False


def discover_page_count(docid: str) -> int:
    """Exponential search + binary search for the last existing page (~log2(N) requests)."""
    if not _img_exists(docid, 1):
        return 0
    lo, hi = 1, 2
    while _img_exists(docid, hi):
        lo = hi
        hi *= 2
        if hi > 4096:
            break
    while lo + 1 < hi:                 # invariant: lo exists, hi does not
        mid = (lo + hi) // 2
        if _img_exists(docid, mid):
            lo = mid
        else:
            hi = mid
    return lo


def page_image_urls(slug: str, docid: str | None):
    """Return (list_of_full_image_urls, publish_date).

    Primary: reader3_4.json (exact pages + publish date). Newer issues 403 there, so we
    fall back to the oembed docid and probe image.isu.pub for the page count.
    """
    url = f"https://reader3.isu.pub/{config.ISSUU_USER}/{slug}/reader3_4.json"
    try:
        data = httputil.get_json(url, headers={"Referer": "https://issuu.com/"})
        doc = data.get("document", {})
        pages = []
        for p in doc.get("pages", []):
            uri = p.get("imageUri")
            if uri:
                pages.append(uri if uri.startswith("http") else "https://" + uri)
        if pages:
            return pages, doc.get("originalPublishDate")
    except Exception:  # noqa: BLE001
        pass
    # fallback via oembed document id
    if not docid:
        return [], None
    count = discover_page_count(docid)
    return [f"{IMG_HOST}/{docid}/jpg/page_{n}.jpg" for n in range(1, count + 1)], None


def download_page(args):
    idx, img_url, dest = args
    if dest.exists() and dest.stat().st_size > 0:
        return idx, True, "cached"
    try:
        data = httputil.get_bytes(img_url, headers={"Accept": "image/jpeg,image/*"})
        if not data:
            return idx, False, "empty"
        dest.write_bytes(data)
        return idx, True, "ok"
    except Exception as e:  # noqa: BLE001
        return idx, False, str(e)


def scrape_document(conn, slug: str) -> dict:
    folder = config.RAW / slug
    folder.mkdir(parents=True, exist_ok=True)
    doc_url = f"{config.PROFILE_URL}/docs/{slug}"

    title, docid = oembed_info(slug)
    time.sleep(config.REQUEST_PAUSE)
    pages, pub_date = page_image_urls(slug, docid)
    if not pages:
        print(f"  ! {slug}: could not resolve any pages — skipping")
        return {"slug": slug, "ok": False, "pages": 0}

    n = len(pages)
    doc_id = db.upsert_document(conn, slug, title, doc_url, pub_date, n, folder)

    # build download jobs
    jobs = []
    for i, img in enumerate(pages, start=1):
        dest = folder / f"page_{i:03d}.jpg"
        jobs.append((i, img, dest))

    ok = 0
    with cf.ThreadPoolExecutor(max_workers=config.DOWNLOAD_WORKERS) as ex:
        for idx, success, _info in ex.map(download_page, jobs):
            if success:
                ok += 1
                db.ensure_page(conn, doc_id, idx, jobs[idx - 1][2])
    conn.commit()

    # per-document metadata sidecar
    (folder / "meta.json").write_text(json.dumps({
        "slug": slug, "title": title, "url": doc_url,
        "publish_date": pub_date, "num_pages": n,
        "images_downloaded": ok,
    }, indent=2), encoding="utf-8")

    print(f"  ✓ {slug}: {ok}/{n} pages  [{title}]")
    return {"slug": slug, "ok": ok == n, "pages": ok, "title": title}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only scrape first N documents")
    ap.add_argument("--only", help="comma-separated slugs to scrape")
    ap.add_argument("--list-only", action="store_true", help="just print slugs and exit")
    args = ap.parse_args()

    config.ensure_dirs()
    conn = db.connect()
    db.init(conn)

    if args.only:
        slugs = [s.strip() for s in args.only.split(",") if s.strip()]
    else:
        print("Enumerating publications...")
        slugs = enumerate_slugs()
    if args.limit:
        slugs = slugs[: args.limit]

    print(f"\n{len(slugs)} document(s) to scrape.\n")
    # persist the full slug list for reference
    (config.DATA / "raw" / "issuu_slugs.txt").write_text("\n".join(slugs), encoding="utf-8")
    if args.list_only:
        for s in slugs:
            print(s)
        return

    totals = {"docs": 0, "pages": 0}
    for s in slugs:
        r = scrape_document(conn, s)
        totals["docs"] += 1
        totals["pages"] += r["pages"]

    print(f"\nDone. {totals['docs']} documents, {totals['pages']} page images.")
    print(f"Raw files: {config.RAW}")
    print(f"DB: {config.DB_PATH}")


if __name__ == "__main__":
    sys.exit(main())
