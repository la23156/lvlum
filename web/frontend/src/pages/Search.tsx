import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type PersonCard as Card } from '../api/client'
import { PersonCard } from '../components/PersonCard'

const ROLES = ['', 'alumnus', 'student', 'faculty', 'parent']

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const role = params.get('role') ?? ''
  const year = params.get('year') ?? ''
  const [results, setResults] = useState<Card[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!q) return
    setLoading(true)
    api.search(q, { role, year, n: 36 })
      .then(setResults).catch(() => setResults([])).finally(() => setLoading(false))
  }, [q, role, year])

  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v); else p.delete(k)
    setParams(p)
  }

  return (
    <div className="container">
      <h2 style={{ marginBottom: 6 }}>Results for “{q}”</h2>
      <div className="chips" style={{ justifyContent: 'flex-start', margin: '6px 0 18px' }}>
        {ROLES.map(r => (
          <button key={r || 'all'} className={`chip ${role === r ? 'active' : ''}`} onClick={() => setParam('role', r)}>
            {r ? r[0].toUpperCase() + r.slice(1) : 'Everyone'}
          </button>
        ))}
        <input className="field" style={{ width: 200, margin: 0, padding: '8px 12px' }}
          placeholder="Year: 1990-2005 · 2005- · -2008"
          title="Single year or range. Open-ended: 2005- or -2008." defaultValue={year}
          onBlur={e => setParam('year', e.target.value.trim())}
          onKeyDown={e => { if (e.key === 'Enter') setParam('year', (e.target as HTMLInputElement).value.trim()) }} />
      </div>

      {loading ? <div className="loading">Searching…</div>
        : results.length === 0 ? <div className="empty-state">No matches. Try different words.</div>
          : <div className="grid">{results.map(p => <PersonCard key={p.key} p={p} />)}</div>}
    </div>
  )
}
