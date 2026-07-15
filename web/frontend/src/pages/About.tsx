import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Stats } from '../api/client'
import { Brand } from '../components/Layout'

const fmt = (n?: number) => (n ?? 0).toLocaleString()

export default function About() {
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => { void api.stats().then(setStats).catch(() => {}) }, [])

  return (
    <div className="container about">
      <div className="hero">
        <h1>Every issue. Every name. One directory.</h1>
        <p>
          <Brand /> turns decades of Lawrenceville's public publications into a single,
          searchable directory of {stats ? fmt(stats.people) : '15,000+'} people — searchable
          not just by name, but by what they actually do.
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

      <div className="section-title">Why this matters for the Alumni Office</div>
      <div className="value-grid">
        <div className="panel vcard">
          <div className="vemoji">🧭</div>
          <h3>Institutional memory, on demand</h3>
          <p>
            The knowledge of "who does what" in the Lawrenceville community used to live in
            back issues and in people's heads. Now a question like <i>"who works in climate
            policy?"</i> is answered in seconds, with the original magazine pages as receipts.
          </p>
        </div>
        <div className="panel vcard">
          <div className="vemoji">🤝</div>
          <h3>Better outreach & engagement</h3>
          <p>
            Build genuinely relevant invite lists — panelists for a career night, mentors for a
            student interested in film, reunion programming by shared interest — instead of
            blasting entire class years.
          </p>
        </div>
        <div className="panel vcard">
          <div className="vemoji">🎯</div>
          <h3>Targeted development research</h3>
          <p>
            Surface founders, industry leaders, and engaged volunteers by field. The AI
            Assistant reads every candidate profile against your exact criteria and explains
            each match, ready to export as a CSV for your CRM.
          </p>
        </div>
        <div className="panel vcard">
          <div className="vemoji">🎓</div>
          <h3>Students included</h3>
          <p>
            The directory covers the whole community — alumni, students, faculty, and parents —
            so you can connect a current student's interests to the alumni who share them.
          </p>
        </div>
      </div>

      <div className="section-title">How it was made</div>
      <div className="panel">
        <p className="lede">
          Everything here comes from Lawrenceville's own publicly published magazines and
          newsletters on Issuu — alumni magazines, class notes, honor rolls, and school
          publications. An AI pipeline read them the way a person would, page by page:
        </p>
        <ol className="steps">
          <li>
            <b>Collect.</b> {stats ? stats.documents : 91} public publications
            ({stats ? fmt(stats.with_year) : 'thousands'}+ pages) were gathered from the
            school's Issuu profile.
          </li>
          <li>
            <b>Read.</b> A vision AI model (OpenAI's GPT-5) examined every page image —
            {stats ? ` ${fmt(3528)} ` : ' 3,528 '}pages in all — and extracted each person
            mentioned: name, class year, role, and what the page says about their interests
            and activities.
          </li>
          <li>
            <b>Resolve.</b> {stats ? fmt(stats.mentions) : '26,000+'} raw mentions were merged
            into one profile per person, reconciling nicknames, initials, and name variants
            across decades of issues.
          </li>
          <li>
            <b>Understand.</b> Each profile was converted into a semantic embedding — a
            numerical representation of meaning — so a search for <i>"venture capital"</i> also
            finds someone described as a <i>"startup investor."</i>
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

      <div className="section-title">How to use it</div>

      <div className="panel howto">
        <h3>🔎 Search by meaning, not just keywords</h3>
        <p>
          Type what you're looking for in plain English. The search understands meaning, so
          you don't need to guess exact words that appeared in print. Try one:
        </p>
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
        <p className="footnote">
          On the results page you can filter by role (alumni / student / faculty / parent) and
          class year, or switch to exact keyword matching.
        </p>
      </div>

      <div className="panel howto">
        <h3>📖 Browse the full directory</h3>
        <p>
          <Link to="/browse">Directory</Link> lists everyone, filterable by role and class year,
          in card or table view. Great for scanning a specific class before a reunion — filter
          to a year and see every member with their interests at a glance.
        </p>
      </div>

      <div className="panel howto">
        <h3>👤 Profiles with receipts</h3>
        <p>
          Every person's page shows their consolidated interests plus the actual publication
          pages they appear on — click any page thumbnail to zoom, or follow the link to the
          original issue. Use it to confirm a match before reaching out.
        </p>
      </div>

      <div className="panel howto">
        <h3>✨ The AI Assistant — build a list with an explanation for every name</h3>
        <p>
          For serious list-building, describe who you need in a sentence and the{' '}
          <Link to="/assistant">Assistant</Link> does the rest. For example:
        </p>
        <blockquote>"Alumni who graduated after 2005 with experience in finance or fintech, for a NYC career panel."</blockquote>
        <p>It will:</p>
        <ol className="steps">
          <li>Draft the filters (years, roles) and the fit criterion for you to confirm — with a candidate count and estimated cost before anything runs.</li>
          <li>Read every candidate profile individually with an AI reviewer and keep only real fits.</li>
          <li>Show each match with the reasoning why they qualify, ready to export as CSV.</li>
        </ol>
        <p className="footnote">
          Runs continue in the background — you can close the tab and come back. Past runs
          found things like 82 biotech-interested community members and 26 with robotics
          experience.
        </p>
      </div>

      <div className="panel howto">
        <h3>🎲 Shuffle & ⭐ Favorites</h3>
        <p>
          <Link to="/shuffle">Shuffle</Link> deals profile cards by theme (arts, finance,
          medicine…) for serendipitous discovery — swipe to save. Anything you star lands in{' '}
          <Link to="/favorites">Favorites</Link>, where you can attach notes and build a
          working list.
        </p>
      </div>

      <div className="about-cta">
        <Link to="/" className="btn">Start exploring</Link>
      </div>
    </div>
  )
}
