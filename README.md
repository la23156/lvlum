# Lawrenceville Alumni Structured Database

Scrapes The Lawrenceville School's publicly published magazines from
[Issuu](https://issuu.com/thelawrencevilleschool) (93 issues of *The Lawrentian* alumni
magazine + related documents) and builds a structured database of the **students/alumni**
mentioned, their **class year**, and the **interests/activities** the articles describe.

Source links are recorded in [`original_links.txt`](original_links.txt). The Scribd account
listed there is bot-walled and intentionally **not** scraped in this pass.

## How it works

```
scrape_issuu.py     enumerate 93 docs -> download page images -> data/raw/issuu/<slug>/
extract_entities.py OpenAI vision OCR + entity extraction -> SQLite (pages, mentions)
                    -> consolidate into one profile per `people` row
embed_people.py     embed each person profile (text-embedding-3-large) for semantic search
build_summaries.py  (optional) LLM-written one-line bio per person
search.py           keyword (full-text) + semantic + per-person profile lookup
export_csv.py       dump tables to data/exports/*.csv
run_all.sh          runs scrape -> extract -> embed -> export
resolve_people.py   entity resolution: merge name variants into the `profiles*` tables
web/                BigRedAlumni — FastAPI + React directory site on top of the DB
```

The web app (search, directory, profiles, shuffle, favorites, AI group-builder assistant) is
documented in [`web/README.md`](web/README.md).

The goal is a searchable directory of the whole Lawrenceville community — students, alumni,
faculty, and parents — so you can ask "who works on X" by keyword or by meaning.

No third-party Python packages — **stdlib only** (`urllib`, `sqlite3`, `concurrent.futures`).
The OpenAI API is called directly over HTTPS.

### Issuu method (no third-party download services)
- **Enumerate:** the profile renders 48 docs at `issuu.com/thelawrencevilleschool` and the
  rest at `.../2`; union = 93 slugs (matches the profile's `documentCount`).
- **Per doc:** `reader3.isu.pub/<user>/<slug>/reader3_4.json` gives the page list +
  publish date. Newer issues 403 there, so we fall back to the `oembed` thumbnail to get the
  document image-id and probe `image.isu.pub/<id>/jpg/page_N.jpg` for the page count.

## Setup

Requires Python 3.11+ and an `OPENAI_API_KEY` in `.env` (copy [`.env.example`](.env.example) to
`.env` and fill it in; `.env` and `data/` are git-ignored).
The extractor uses **gpt-5** by default (the best available vision model); override with
`EXTRACT_MODEL=gpt-4.1` etc.

## Usage

```bash
# smoke test: 2 documents, a few pages
./run_all.sh --limit 2 --max-pages 5

# full pipeline (all 93 docs)
./run_all.sh

# pieces individually
python3 scrape_issuu.py                 # all docs   (--limit N, --only slug, --list-only)
python3 extract_entities.py             # all pending pages (--limit-docs N, --max-pages N,
                                        #   --model ID, --detail high|low, --reasoning minimal,
                                        #   --finalize-only)
python3 embed_people.py                 # build/update embeddings (--rebuild, --model ID)
python3 export_csv.py
```

### Searching the community
```bash
python3 search.py "climate policy"                  # hybrid: semantic + keyword
python3 search.py --semantic "founded a biotech startup"
python3 search.py --keyword "crew OR rowing OR sailing"
python3 search.py "documentary filmmaker" --role alumnus --year 1990-2005 -n 15
python3 search.py --person "Tsai"                    # one person's full profile
```
Semantic search needs embeddings first (`embed_people.py`). Re-running extraction then
`extract_entities.py --finalize-only && embed_people.py` refreshes profiles incrementally.

Both stages are **idempotent and resumable**: re-running skips already-downloaded images and
already-processed pages (`pages.status`), so you can stop and restart anytime.

## Outputs

```
data/raw/issuu/<slug>/page_NNN.jpg     raw page images, one folder per document
data/raw/issuu/<slug>/meta.json        title, url, publish date, page count
data/raw/issuu/<slug>/ocr/page_NNN.txt cached OCR transcript per page
data/db/alumni.sqlite                  documents / pages / people / mentions
data/exports/*.csv                     documents, people, mentions, people_with_interests,
                                       mentions_located (every appearance: doc, page #,
                                       Issuu page link, local image path)
```

### Schema
- **documents** — `slug, title, url, publish_date, num_pages, folder`
- **pages** — `document_id, page_num, image_path, ocr_text, status`
- **mentions** — one row per person occurrence: `name, class_year, role, interests, snippet, confidence, page_num`
- **people** — one consolidated profile per person: `person_key, full_name, class_year,
  class_year_tags, role, roles_all, interests_agg, snippets_agg, source_docs, doc_count,
  mention_count, profile_text, summary`
- **embeddings** — `person_key, model, dim, norm_vector` (one semantic vector per person)
- **people_fts** — FTS5 index over names + profile text for keyword search

People are consolidated by normalized name + class year; a no-year mention is folded into a
person only when that name is reliably tied to one year (≥2 mentions and ≥⅓ of its mentions),
so a frequently-named staffer isn't given a stray class year. Name-variant merging
(e.g. "Steve Murray" vs "Stephen S. Murray '54") is done by `resolve_people.py`, which writes the
`profiles`, `profile_aliases`, `profiles_fts`, and `profile_embeddings` tables the web app reads.

### Example queries
```sql
-- alumni from the 1980s and their interests
SELECT full_name, class_year, interests_agg FROM people
WHERE role='alumnus' AND class_year BETWEEN '1980' AND '1989' ORDER BY class_year;

-- where is a person mentioned?
SELECT d.title, m.page_num, m.snippet FROM mentions m
JOIN documents d ON d.id=m.document_id
JOIN people p ON p.id=m.person_id WHERE p.full_name LIKE '%Getz%';
```

## Notes
- Content is the school's own public material; the scraper uses a realistic User-Agent and
  polite pacing.
- Extraction quality depends on the vision model; occasional false positives (e.g. an endowed
  chair read as a person) are possible. `confidence` is stored per mention for filtering.
