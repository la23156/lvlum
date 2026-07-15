import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Stats } from '../api/client'
import { Brand } from '../components/Layout'
import shotHome from '../assets/about/home.jpg'
import shotSearch from '../assets/about/search.jpg'
import shotProfile from '../assets/about/profile.jpg'
import shotBrowse from '../assets/about/browse.jpg'
import shotAssistant from '../assets/about/assistant.jpg'
import shotShuffle from '../assets/about/shuffle.jpg'

const fmt = (n?: number) => (n ?? 0).toLocaleString()

function Flow({ nodes }: { nodes: { icon: string; count?: string; label: string }[] }) {
  return (
    <div className="flow">
      {nodes.map((n, i) => (
        <div className="fstep" key={n.label}>
          {i > 0 && <div className="farrow">→</div>}
          <div className="fnode">
            <div className="ficon">{n.icon}</div>
            {n.count && <div className="fcount">{n.count}</div>}
            <div className="flabel">{n.label}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function Shot({ src, alt, caption }: { src: string; alt: string; caption: React.ReactNode }) {
  const [zoom, setZoom] = useState(false)
  return (
    <figure className="shot">
      <div className="shot-frame" onClick={() => setZoom(true)}>
        <div className="shot-bar"><i /><i /><i /></div>
        <img src={src} alt={alt} loading="lazy" />
      </div>
      <figcaption>{caption}</figcaption>
      {zoom && (
        <div className="lightbox" onClick={() => setZoom(false)}>
          <img src={src} alt={alt} />
        </div>
      )}
    </figure>
  )
}

export default function About() {
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => { void api.stats().then(setStats).catch(() => {}) }, [])
  const people = stats ? fmt(stats.people) : '15,000+'

  return (
    <div className="container about">
      <div className="hero">
        <h1>Every issue. Every name. One directory.</h1>
        <p>
          <Brand /> turns decades of Lawrenceville's public publications into a single,
          searchable directory of {people} community members — searchable not just by name,
          but by what people actually do.
        </p>
      </div>

      {stats && (
        <div className="stats">
          <div className="stat"><b>{stats.documents}</b>publications read</div>
          <div className="stat"><b>{fmt(stats.mentions)}</b>mentions extracted</div>
          <div className="stat"><b>{fmt(stats.people)}</b>people profiled</div>
          <div className="stat"><b>{fmt(stats.by_role.alumnus)}</b>alumni</div>
          <div className="stat"><b>{fmt(stats.by_role.faculty)}</b>faculty</div>
        </div>
      )}

      {/* ---------------- how it was built ---------------- */}
      <div className="section-title">How it was built</div>
      <div className="panel">
        <Flow nodes={[
          { icon: '📚', count: stats ? String(stats.documents) : '91', label: 'Public Issuu publications' },
          { icon: '🤖', count: '3,528', label: 'Pages read by GPT-5 vision' },
          { icon: '🏷️', count: stats ? fmt(stats.mentions) : '26,044', label: 'People mentions extracted' },
          { icon: '🧩', count: '', label: 'Name variants merged' },
          { icon: '👤', count: people, label: 'One profile per person' },
          { icon: '🔎', count: '', label: 'Searchable by meaning' },
        ]} />
        <p className="lede">
          Everything here comes from Lawrenceville's own publicly published magazines and
          newsletters — alumni magazines, class notes, honor rolls, and school publications.
          An AI pipeline read them the way a person would, page by page:
        </p>
        <ol className="steps">
          <li>
            <b>Collect.</b> {stats ? stats.documents : 91} public publications were gathered
            from the school's Issuu profile.
          </li>
          <li>
            <b>Read.</b> A vision AI model (OpenAI's GPT-5) examined all 3,528 page images and
            extracted each person mentioned: name, class year, role, and what the page says
            about their interests and activities.
          </li>
          <li>
            <b>Resolve.</b> {stats ? fmt(stats.mentions) : '26,000+'} raw mentions were merged
            into one profile per person, reconciling nicknames, initials, and name variants
            across decades of issues.
          </li>
          <li>
            <b>Understand.</b> Each profile was converted into a semantic embedding — a
            numerical representation of meaning — so a search for <i>"venture capital"</i>{' '}
            also finds someone described as a <i>"startup investor."</i>
          </li>
          <li>
            <b>Verify.</b> Every fact on a profile links back to the exact publication page it
            came from, with a preview image and a link to the original issue.
          </li>
        </ol>
        <p className="footnote">
          Because profiles are machine-read from print, occasional errors exist: a misread
          name, a building or endowed chair mistaken for a person, or one person split across
          two spellings. The original pages are always one click away for verification.
        </p>
      </div>

      {/* ---------------- understand the alumni base ---------------- */}
      <div className="section-title">Understand your alumni base</div>
      <div className="panel howto">
        <p className="lede">
          The directory answers "who are our people, and what do they do?" at any altitude —
          from one person to a whole decade of classes. Click any screenshot to zoom.
        </p>
        <div className="shots2">
          <Shot src={shotHome} alt="Home page with search and stats" caption={
            <><b>Discover.</b> The home page: one search box over the whole community, live
            counts, and themed entry points (arts, finance, medicine…).</>
          } />
          <Shot src={shotSearch} alt="Semantic search results" caption={
            <><b>Search by meaning.</b> "Documentary filmmaker" finds people described as
            directors, producers, or film-festival honorees — no exact keyword needed.</>
          } />
          <Shot src={shotBrowse} alt="Directory browse view" caption={
            <><b>Scan a class or era.</b> The Directory filters everyone by role and class
            year — review an entire reunion class with interests at a glance, or export it
            to CSV.</>
          } />
          <Shot src={shotProfile} alt="Profile page with publication receipts" caption={
            <><b>Profiles with receipts.</b> Every profile shows the actual magazine pages the
            person appears on — zoom the page image or open the original issue to verify
            before you reach out.</>
          } />
        </div>
        <p>Try a meaning-first search yourself:</p>
        <div className="chips left">
          {[
            'documentary filmmaker',
            'works in climate policy in DC',
            'startup founder in healthcare',
            'plays professional hockey',
            'teaches at a university',
          ].map(q => (
            <Link key={q} className="chip" to={`/search?q=${encodeURIComponent(q)}`}>{q}</Link>
          ))}
        </div>
      </div>

      {/* ---------------- build groups ---------------- */}
      <div className="section-title">Build groups for events &amp; fundraising</div>
      <div className="panel howto">
        <p className="lede">
          The ✨ <Link to="/assistant">Assistant</Link> turns a one-sentence brief into a
          vetted invite or prospect list — with a written reason for every name on it.
        </p>
        <Flow nodes={[
          { icon: '💬', label: 'Describe who you need' },
          { icon: '📝', label: 'AI drafts filters + criterion' },
          { icon: '✅', label: 'You confirm count & cost' },
          { icon: '🧠', label: 'AI reviews every candidate' },
          { icon: '📋', label: 'Explained matches → CSV' },
        ]} />
        <blockquote>"Alumni who graduated after 2005 with experience in finance or fintech, for a NYC career panel."</blockquote>
        <p>
          The Assistant proposes the year range, roles, and a precise fit criterion for you to
          edit and approve — showing the candidate count and estimated cost before anything
          runs. Then an AI reviewer reads each candidate's profile individually and keeps only
          real fits, each with its reasoning. Runs continue in the background, so you can close
          the tab and come back.
        </p>
        <div className="shots1">
          <Shot src={shotAssistant} alt="Assistant results with reasoning" caption={
            <><b>A real run.</b> "Anyone who demonstrates interest in biotech" reviewed 6,475
            profiles and returned 82 matches — each with the evidence why, ready to export as
            CSV for your CRM.</>
          } />
        </div>
        <p><b>Where this pays off:</b></p>
        <ul className="steps">
          <li><b>Event programming</b> — panelists for a fintech career night; young-alumni founders for an entrepreneurship weekend.</li>
          <li><b>Fundraising by affinity</b> — biotech founders and life-science leaders for a science-center campaign; arts alumni for a theater renovation.</li>
          <li><b>Mentorship &amp; student connections</b> — match a current student's interests to the alumni who share them.</li>
          <li><b>Reunion outreach</b> — a class list enriched with what each member has been up to, instead of a bare name-and-year roster.</li>
        </ul>
        <p className="footnote">
          Past runs: 82 biotech-interested community members, 26 in robotics, plus curated
          founder lists in healthcare and fintech.
        </p>
      </div>

      {/* ---------------- serendipity ---------------- */}
      <div className="section-title">And for serendipity…</div>
      <div className="panel howto">
        <div className="shots1">
          <Shot src={shotShuffle} alt="Shuffle deck" caption={
            <><b>🎲 Shuffle</b> deals profile cards by theme — swipe right to save. Everything
            you star lands in <Link to="/favorites">Favorites</Link>, where you can attach
            notes and build a working list.</>
          } />
        </div>
      </div>

      {/* ---------------- value ---------------- */}
      <div className="section-title">Why this matters for the Alumni Office</div>
      <div className="value-grid">
        <div className="panel vcard">
          <div className="vemoji">🧭</div>
          <h3>Institutional memory, on demand</h3>
          <p>
            "Who does what" used to live in back issues and in people's heads. Now it's a
            two-second search with the original magazine pages as receipts.
          </p>
        </div>
        <div className="panel vcard">
          <div className="vemoji">🤝</div>
          <h3>Relevant outreach, not blasts</h3>
          <p>
            Invite the fifty people who genuinely care about a topic instead of emailing
            entire class years — better attendance, better goodwill.
          </p>
        </div>
        <div className="panel vcard">
          <div className="vemoji">🎯</div>
          <h3>Development research at scale</h3>
          <p>
            Surface founders, industry leaders, and engaged volunteers by field, with evidence
            for each, exportable straight into your CRM.
          </p>
        </div>
        <div className="panel vcard">
          <div className="vemoji">🎓</div>
          <h3>The whole community</h3>
          <p>
            Alumni, students, faculty, and parents in one place — connect a current student's
            passion to the alumni who share it.
          </p>
        </div>
      </div>

      <div className="about-cta">
        <Link to="/" className="btn">Start exploring</Link>
      </div>
    </div>
  )
}
