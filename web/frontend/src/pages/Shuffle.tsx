import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion, useMotionValue, useTransform, type PanInfo } from 'framer-motion'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type PersonCard as Card, type Theme } from '../api/client'
import { initials, yearShort } from '../components/PersonCard'
import { useFavorites } from '../favorites'

function FrontCard({ card, onDecide }: { card: Card; onDecide: (dir: 'left' | 'right') => void }) {
  const x = useMotionValue(0)
  const rotate = useTransform(x, [-200, 200], [-14, 14])
  const likeOp = useTransform(x, [40, 140], [0, 1])
  const nopeOp = useTransform(x, [-140, -40], [1, 0])

  const end = (_e: unknown, info: PanInfo) => {
    if (info.offset.x > 120 || info.velocity.x > 600) onDecide('right')
    else if (info.offset.x < -120 || info.velocity.x < -600) onDecide('left')
  }

  return (
    <motion.div className="swipe-card" style={{ x, rotate }} drag="x"
      dragConstraints={{ left: 0, right: 0 }} dragElastic={0.7} onDragEnd={end}
      initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
      exit={{ x: x.get() >= 0 ? 460 : -460, opacity: 0, transition: { duration: 0.25 } }}>
      <motion.div className="swipe-badge like" style={{ opacity: likeOp }}>Save</motion.div>
      <motion.div className="swipe-badge nope" style={{ opacity: nopeOp }}>Skip</motion.div>
      {card.thumb
        ? <div className="pic" style={{ backgroundImage: `url(${card.thumb})` }} />
        : <div className="pic empty">{initials(card.name)}</div>}
      <div className="info">
        <h3>{card.name}{card.class_year && <span className="year-badge" style={{ marginLeft: 8 }}>{yearShort(card.class_year)}</span>}</h3>
        <div className="meta" style={{ textTransform: 'capitalize' }}>{card.role} · {card.mention_count} mentions</div>
        <div>{card.interests.slice(0, 4).map((it, i) => <span className="tag" key={i}>{it}</span>)}</div>
      </div>
    </motion.div>
  )
}

export default function Shuffle() {
  const [params, setParams] = useSearchParams()
  const theme = params.get('theme') ?? ''
  const [themes, setThemes] = useState<Theme[]>([])
  const [deck, setDeck] = useState<Card[]>([])
  const [i, setI] = useState(0)
  const [loading, setLoading] = useState(false)
  const [sessionSaved, setSessionSaved] = useState(0)
  const fav = useFavorites()

  useEffect(() => { void api.themes().then(setThemes).catch(() => {}) }, [])

  const load = useCallback((t: string) => {
    if (!t) return
    setLoading(true); setI(0)
    api.shuffle(t, '', 30).then(d => setDeck(d)).catch(() => setDeck([])).finally(() => setLoading(false))
  }, [])

  useEffect(() => { if (theme) load(theme) }, [theme, load])

  const decide = useCallback((dir: 'left' | 'right') => {
    const card = deck[i]
    if (dir === 'right' && card && !fav.isFav(card.key)) {
      fav.add(card.key)
      setSessionSaved(n => n + 1)
    }
    setI(n => n + 1)
  }, [deck, i, fav])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') decide('right')
      else if (e.key === 'ArrowLeft') decide('left')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [decide])

  const current = deck[i]
  const themeObj = themes.find(t => t.key === theme)

  return (
    <div className="container">
      <h2 style={{ textAlign: 'center' }}>Shuffle</h2>
      <p style={{ textAlign: 'center', color: 'var(--muted)', marginTop: 0 }}>
        Pick a theme, then swipe — right to save, left to skip (or use ← → keys).
      </p>
      <div className="chips">
        {themes.map(t => (
          <button key={t.key} className={`chip ${theme === t.key ? 'active' : ''}`}
            onClick={() => setParams({ theme: t.key })}>
            <span style={{ marginRight: 6 }}>{t.emoji}</span>{t.label}
          </button>
        ))}
      </div>

      <div className="deck-wrap">
        {!theme ? <div className="empty-state">Choose a theme above to start.</div>
          : loading ? <div className="loading">Finding {themeObj?.label ?? ''} alumni…</div>
            : (
              <>
                <div className="deck">
                  {deck.slice(i, i + 3).reverse().map((c, idx, arr) => {
                    const depth = arr.length - 1 - idx // 0 = front
                    if (depth === 0) {
                      return (
                        <AnimatePresence key={c.key} initial={false}>
                          <FrontCard card={c} onDecide={decide} />
                        </AnimatePresence>
                      )
                    }
                    return (
                      <div className="swipe-card" key={c.key}
                        style={{ transform: `translateY(${depth * 10}px) scale(${1 - depth * 0.04})`, zIndex: -depth }}>
                        {c.thumb ? <div className="pic" style={{ backgroundImage: `url(${c.thumb})` }} />
                          : <div className="pic empty">{initials(c.name)}</div>}
                        <div className="info"><h3>{c.name}</h3></div>
                      </div>
                    )
                  })}
                  {!current && (
                    <div className="swipe-card"><div className="info" style={{ margin: 'auto', textAlign: 'center' }}>
                      <h3>That’s everyone!</h3>
                      <p className="meta">You went through the deck.</p>
                      <button className="btn sm" onClick={() => load(theme)}>Reshuffle</button>
                    </div></div>
                  )}
                </div>
                {current && (
                  <div className="deck-actions">
                    <button className="round skip" onClick={() => decide('left')} title="Skip (←)">✕</button>
                    <Link className="round" to={`/p/${encodeURIComponent(current.key)}`} title="View profile" style={{ color: 'var(--ink)' }}>↗</Link>
                    <button className="round save" onClick={() => decide('right')} title="Save (→)">♥</button>
                  </div>
                )}
              </>
            )}

        <div className="saved-tray">
          <Link className="btn sm" to="/favorites">
            ♥ View your favorites{sessionSaved > 0 ? ` (${sessionSaved} added this round)` : ''}
          </Link>
        </div>
      </div>
    </div>
  )
}
