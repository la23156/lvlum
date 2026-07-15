import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Favorite } from '../api/client'
import { useFavorites } from '../favorites'
import { initials, yearShort } from '../components/PersonCard'

export default function Favorites() {
  const { remove, keys } = useFavorites()
  const [items, setItems] = useState<Favorite[]>([])
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    api.favorites.list().then(setItems).catch(() => setItems([])).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const onNote = async (key: string, note: string) => {
    await api.favorites.setNote(key, note).catch(() => {})
    setSaved(key); setTimeout(() => setSaved(s => (s === key ? null : s)), 1200)
  }

  const onRemove = (key: string) => {
    remove(key)
    setItems(prev => prev.filter(i => i.key !== key))
  }

  // drop any that were un-favorited elsewhere
  const visible = items.filter(i => keys.has(i.key))

  if (loading) return <div className="loading">Loading…</div>

  return (
    <div className="container center-col">
      <h2 style={{ marginBottom: 2 }}>★ Your favorites</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        People you’ve saved. Add a note about why each one is interesting.
      </p>

      {visible.length === 0
        ? <div className="empty-state">No favorites yet.<br />Tap the ♡ on anyone, or swipe right in <Link to="/shuffle" style={{ color: 'var(--red)' }}>Shuffle</Link>.</div>
        : (
          <div className="favlist">
            {visible.map(p => (
              <div className="favrow" key={p.key}>
                <Link to={`/p/${encodeURIComponent(p.key)}`} className="favthumb"
                  style={p.thumb ? { backgroundImage: `url(${p.thumb})` } : undefined}>
                  {!p.thumb && initials(p.name)}
                </Link>
                <div className="favbody">
                  <div className="favhead">
                    <Link to={`/p/${encodeURIComponent(p.key)}`} className="favname">
                      {p.name}{p.class_year && <span className="year-badge">{yearShort(p.class_year)}</span>}
                    </Link>
                    <button className="ghost sm" onClick={() => onRemove(p.key)} title="Remove">Remove ♥</button>
                  </div>
                  <div className="dmeta" style={{ textTransform: 'capitalize' }}>{p.role} · {p.mention_count} mentions</div>
                  <textarea className="notebox" defaultValue={p.note}
                    placeholder="Why are they interesting? (e.g. great fit for the climate project)"
                    onBlur={e => onNote(p.key, e.target.value)} />
                  {saved === p.key && <span className="saved-note">Saved ✓</span>}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  )
}
