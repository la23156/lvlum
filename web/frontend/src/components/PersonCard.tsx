import { Link } from 'react-router-dom'
import type { PersonCard as Card } from '../api/client'
import { FavButton } from './FavButton'

export function yearShort(y: string | null) {
  return y ? `’${y.slice(2)}` : ''
}

export function initials(name: string) {
  const parts = name.replace(/[^A-Za-z ]/g, '').split(' ').filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts.at(-1)?.[0] ?? '')).toUpperCase() || '?'
}

export function PersonCard({ p }: { p: Card }) {
  return (
    <Link to={`/p/${encodeURIComponent(p.key)}`} className="card">
      <div className="thumb-wrap">
        {p.thumb
          ? <div className="thumb" style={{ backgroundImage: `url(${p.thumb})` }} />
          : <div className="thumb empty">{initials(p.name)}</div>}
        <FavButton k={p.key} />
      </div>
      <div className="body">
        <div className="name">{p.name}{p.class_year && <span className="year-badge">{yearShort(p.class_year)}</span>}</div>
        <div className="meta"><span className="role-badge">{p.role}</span> · {p.mention_count} mentions · {p.doc_count} docs</div>
        <div>{p.interests.slice(0, 3).map((it, i) => <span className="tag" key={i}>{it}</span>)}</div>
      </div>
    </Link>
  )
}
