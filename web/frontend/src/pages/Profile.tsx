import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type Profile as P } from '../api/client'
import { initials } from '../components/PersonCard'
import { FavButton } from '../components/FavButton'
import { useFavorites } from '../favorites'

export default function Profile() {
  const { key = '' } = useParams()
  const { isFav } = useFavorites()
  const [p, setP] = useState<P | null>(null)
  const [loading, setLoading] = useState(true)
  const [zoom, setZoom] = useState<string | null>(null)
  const [noteSaved, setNoteSaved] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.person(key).then(setP).catch(() => setP(null)).finally(() => setLoading(false))
  }, [key])

  const saveNote = async (note: string) => {
    await api.favorites.setNote(key, note).catch(() => {})
    setNoteSaved(true); setTimeout(() => setNoteSaved(false), 1200)
  }

  if (loading) return <div className="loading">Loading…</div>
  if (!p) return <div className="empty-state">Profile not found.</div>

  return (
    <div className="container center-col">
      <div className="profile-head">
        <div className="avatar">{initials(p.name)}</div>
        <div style={{ flex: 1 }}>
          <h1>{p.name}{p.class_year && <span className="year-badge" style={{ fontSize: 14, marginLeft: 10 }}>Class of {p.class_year}</span>}</h1>
          <div className="sub" style={{ textTransform: 'capitalize' }}>{p.role}{p.class_year_tags ? ` · ${p.class_year_tags}` : ''}</div>
          <div className="counts">
            <span>📄 {p.doc_count} publications</span>
            <span>💬 {p.mention_count} mentions</span>
          </div>
        </div>
        <FavButton k={key} big />
      </div>

      {isFav(key) && (
        <div className="panel">
          <h2>Your note {noteSaved && <span className="saved-note">Saved ✓</span>}</h2>
          <textarea className="notebox" defaultValue={p.note}
            placeholder="Why are they interesting? (e.g. would be great for the alumni mentorship program)"
            onBlur={e => saveNote(e.target.value)} />
        </div>
      )}

      {p.interests.length > 0 && (
        <div className="panel">
          <h2>Interests &amp; activities</h2>
          <div>{p.interests.map((it, i) => <span className="tag" key={i}>{it}</span>)}</div>
        </div>
      )}

      <div className="panel">
        <h2>Featured in {p.featured_pages.length} page{p.featured_pages.length === 1 ? '' : 's'}</h2>
        <div className="featured">
          {p.featured_pages.map((f, i) => (
            <div className="fpage" key={i}>
              <img src={f.thumb} loading="lazy" onClick={() => setZoom(f.full)} alt={`${f.document} p.${f.page}`} />
              <div className="fmeta">
                <div className="doc">{f.document}</div>
                <div className="pg">Page {f.page}</div>
                {f.snippet && <div className="snip">“{f.snippet}”</div>}
                {f.issuu && <a href={f.issuu} target="_blank" rel="noreferrer">Open on Issuu →</a>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom} alt="page" />
        </div>
      )}
    </div>
  )
}
