import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type PersonCard as Card, type Stats, type Theme } from '../api/client'
import { PersonCard } from '../components/PersonCard'

export default function Home() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [themes, setThemes] = useState<Theme[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [discover, setDiscover] = useState<Card[]>([])

  useEffect(() => {
    void api.themes().then(setThemes).catch(() => {})
    void api.stats().then(setStats).catch(() => {})
    void api.discover(12).then(setDiscover).catch(() => {})
  }, [])

  const go = (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`)
  }

  return (
    <div className="container">
      <div className="hero">
        <h1>Find your people.</h1>
        <p>
          Search {stats ? stats.people.toLocaleString() : '15,000+'} members of the Lawrenceville community by what they actually do.
          {' '}<Link to="/about" className="hero-about">New here? See how this site was built →</Link>
        </p>
        <form className="bigsearch" onSubmit={go}>
          <input value={q} onChange={e => setQ(e.target.value)} autoFocus
            placeholder='Try "documentary filmmaker" or "climate policy in DC"' />
          <button className="btn">Search</button>
        </form>
        <div className="chips">
          {themes.map(t => (
            <button key={t.key} className="chip" onClick={() => nav(`/shuffle?theme=${t.key}`)}>
              <span style={{ marginRight: 6 }}>{t.emoji}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      {stats && (
        <div className="stats">
          <div className="stat"><b>{stats.people.toLocaleString()}</b>people</div>
          <div className="stat"><b>{(stats.by_role.alumnus ?? 0).toLocaleString()}</b>alumni</div>
          <div className="stat"><b>{(stats.by_role.student ?? 0).toLocaleString()}</b>students</div>
          <div className="stat"><b>{(stats.by_role.faculty ?? 0).toLocaleString()}</b>faculty</div>
          <div className="stat"><b>{stats.documents}</b>publications</div>
        </div>
      )}

      <div className="section-title">Discover</div>
      <div className="grid">
        {discover.map(p => <PersonCard key={p.key} p={p} />)}
      </div>
    </div>
  )
}
