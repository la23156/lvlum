import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, exportCsvUrl, type PersonCard as Card } from '../api/client'
import { initials, yearShort } from '../components/PersonCard'
import { FavButton } from '../components/FavButton'

const LIMIT = 60
const ROLES = ['', 'alumnus', 'student', 'faculty', 'parent']
const SORTS = [
  { v: 'mentions', label: 'Most mentioned' },
  { v: 'name', label: 'Name (A–Z)' },
  { v: 'year', label: 'Class year' },
  { v: 'docs', label: 'Most publications' },
]

function DirCard({ p }: { p: Card }) {
  return (
    <Link to={`/p/${encodeURIComponent(p.key)}`} className="dcard">
      <div className="thumb-wrap">
        {p.thumb
          ? <div className="dthumb" style={{ backgroundImage: `url(${p.thumb})` }} />
          : <div className="dthumb">{initials(p.name)}</div>}
        <FavButton k={p.key} />
      </div>
      <div className="dbody">
        <div className="dname">{p.name}{p.class_year && <span className="year-badge">{yearShort(p.class_year)}</span>}</div>
        <div className="dmeta">{p.role} · {p.mention_count} mentions</div>
        {p.interests.length > 0 && <div className="dtags">{p.interests.slice(0, 3).join(' · ')}</div>}
      </div>
    </Link>
  )
}

export default function Browse() {
  const [q, setQ] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [mode, setMode] = useState<'keyword' | 'semantic'>('keyword')
  const [role, setRole] = useState('')
  const [year, setYear] = useState('')
  const [sort, setSort] = useState('mentions')
  const [view, setView] = useState<'grid' | 'table'>('grid')

  const [items, setItems] = useState<Card[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const offsetRef = useRef(0)
  const reqId = useRef(0)

  const fetchPage = useCallback(async (reset: boolean) => {
    const myId = reset ? ++reqId.current : reqId.current
    if (reset) offsetRef.current = 0
    setLoading(true)
    try {
      const r = await api.browse({ q: submitted, mode, role, year, sort, offset: offsetRef.current, limit: LIMIT })
      if (myId !== reqId.current) return
      setItems(prev => reset ? r.results : [...prev, ...r.results])
      setTotal(r.total)
      setHasMore(r.has_more)
      offsetRef.current += LIMIT
    } catch { if (myId === reqId.current) setHasMore(false) }
    finally { if (myId === reqId.current) setLoading(false) }
  }, [submitted, mode, role, year, sort])

  useEffect(() => { void fetchPage(true) }, [fetchPage])

  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver(es => {
      if (es[0].isIntersecting && hasMore && !loading) void fetchPage(false)
    }, { rootMargin: '400px' })
    io.observe(el)
    return () => io.disconnect()
  }, [hasMore, loading, fetchPage])

  return (
    <div className="container">
      <h2 style={{ marginBottom: 2 }}>Directory</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        Every person the system has extracted from the magazines — browse or filter the whole dataset.
      </p>

      <form className="toolbar" onSubmit={e => { e.preventDefault(); setSubmitted(q.trim()) }}>
        <div className="navsearch grow">
          <span>🔎</span>
          <input value={q} onChange={e => setQ(e.target.value)}
            placeholder="Filter by keyword or meaning…" />
          {q && <button type="button" className="ghost" style={{ padding: '2px 8px' }}
            onClick={() => { setQ(''); setSubmitted('') }}>✕</button>}
        </div>
        <div className="seg">
          <button type="button" className={mode === 'keyword' ? 'active' : ''} onClick={() => setMode('keyword')}>Keyword</button>
          <button type="button" className={mode === 'semantic' ? 'active' : ''} onClick={() => setMode('semantic')}>Semantic</button>
        </div>
        <button className="btn sm" type="submit">Apply</button>
      </form>

      <div className="toolbar" style={{ marginTop: 0 }}>
        <div className="seg">
          {ROLES.map(r => (
            <button key={r || 'all'} className={role === r ? 'active' : ''} onClick={() => setRole(r)}>
              {r ? r[0].toUpperCase() + r.slice(1) : 'Everyone'}
            </button>
          ))}
        </div>
        <input className="select" style={{ width: 178 }} placeholder="Year: 1990-2005 · 2005- · -2008"
          title="A single year, or a range. Open-ended: 2005- (2005 and after), -2008 (2008 and before)."
          defaultValue={year}
          onBlur={e => setYear(e.target.value.trim())}
          onKeyDown={e => { if (e.key === 'Enter') setYear((e.target as HTMLInputElement).value.trim()) }} />
        <select className="select" value={sort} onChange={e => setSort(e.target.value)} disabled={!!submitted}>
          {SORTS.map(s => <option key={s.v} value={s.v}>{s.label}</option>)}
        </select>
        <div className="seg right">
          <button className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')}>▦ Grid</button>
          <button className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}>▤ Table</button>
        </div>
        <a className="btn outline sm" href={exportCsvUrl({ q: submitted, mode, role, year, sort })}
          download="bigredalumni.csv">⬇ CSV</a>
      </div>

      <div className="count-line">
        {total != null
          ? <>Showing <b>{items.length.toLocaleString()}</b> of <b>{total.toLocaleString()}</b> people</>
          : <>{items.length.toLocaleString()} match{items.length === 1 ? '' : 'es'}{submitted && ` for “${submitted}”`}</>}
      </div>

      {items.length === 0 && !loading
        ? <div className="empty-state">No matches.</div>
        : view === 'grid'
          ? <div className="dirgrid">{items.map(p => <DirCard key={p.key} p={p} />)}</div>
          : (
            <div className="tablewrap">
              <table className="dirtable">
                <thead><tr>
                  <th aria-label="favorite" style={{ width: 34 }}></th>
                  <th>First name</th><th>Last name</th><th>Class</th><th>Role</th>
                  <th>Mentions</th><th>Pubs</th><th>Interests</th><th>Source</th>
                </tr></thead>
                <tbody>
                  {items.map(p => (
                    <tr key={p.key}>
                      <td style={{ textAlign: 'center' }}><FavButton k={p.key} inline /></td>
                      <td>{p.first_name || p.name}</td>
                      <td>{p.last_name || ''}</td>
                      <td>{p.class_year || ''}</td>
                      <td className="role">{p.role}</td>
                      <td className="num">{p.mention_count}</td>
                      <td className="num">{p.doc_count}</td>
                      <td className="int">{p.interests.join(' · ')}</td>
                      <td className="src">
                        {p.source_url
                          ? <a href={p.source_url} target="_blank" rel="noreferrer" title={p.source_doc ?? 'Issuu'}>Issuu ↗</a>
                          : <span style={{ color: 'var(--muted)' }}>—</span>}
                        {p.source_image &&
                          <> · <a href={p.source_image} target="_blank" rel="noreferrer" title="Saved page image">Image ↗</a></>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

      {loading && <div className="loading">Loading…</div>}
      <div className="sentinel" ref={sentinel} />
    </div>
  )
}
