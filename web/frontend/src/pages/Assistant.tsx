import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type AssistantGroup, type MatchPerson } from '../api/client'
import { FavButton } from '../components/FavButton'
import { useFavorites } from '../favorites'
import { initials, yearShort } from '../components/PersonCard'

const ROLES = ['alumnus', 'student', 'faculty', 'parent']
const EXAMPLES = [
  'Alumni who graduated between 2008 and 2020 and demonstrated interest in space-related technology',
  'People involved in documentary filmmaking or photojournalism',
  'Faculty and alumni who started companies in healthcare or biotech',
  'Alumni from the 1990s working in climate or environmental policy',
]

function ProgressBar({ g }: { g: AssistantGroup }) {
  const pct = g.total ? Math.round((g.judged / g.total) * 100) : 0
  return (
    <div className="progress">
      <div className="bar"><div className="fill" style={{ width: `${pct}%` }} /></div>
      <div className="ptext">{g.judged.toLocaleString()} / {g.total.toLocaleString()} judged
        · <b>{g.matched}</b> match{g.matched === 1 ? '' : 'es'}</div>
    </div>
  )
}

function MatchCard({ p }: { p: MatchPerson }) {
  return (
    <div className="match">
      <div className="thumb-wrap">
        <Link to={`/p/${encodeURIComponent(p.key)}`} className="mthumb"
          style={p.thumb ? { backgroundImage: `url(${p.thumb})` } : undefined}>
          {!p.thumb && initials(p.name)}
        </Link>
        <FavButton k={p.key} />
      </div>
      <div className="mbody">
        <Link to={`/p/${encodeURIComponent(p.key)}`} className="mname">
          {p.name}{p.class_year && <span className="year-badge">{yearShort(p.class_year)}</span>}
        </Link>
        <div className="dmeta" style={{ textTransform: 'capitalize' }}>{p.role} · {p.mention_count} mentions
          {typeof p.confidence === 'number' && <> · {Math.round(p.confidence * 100)}% confident</>}</div>
        <div className="why">“{p.reasoning}”</div>
      </div>
    </div>
  )
}

function NewGroup({ onCreate, busy, err }:
  { onCreate: (p: string) => void; busy: boolean; err: string }) {
  const [prompt, setPrompt] = useState('')
  return (
    <div className="center-col">
      <h2 style={{ marginBottom: 4 }}>✨ Group builder</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        Describe the group you want. The assistant reads each matching person’s profile and asks an
        AI, one by one, whether they fit — with a reason. It runs in the background, so you can close
        this tab and come back.
      </p>
      <form onSubmit={e => { e.preventDefault(); if (prompt.trim()) onCreate(prompt.trim()) }}>
        <textarea className="notebox" style={{ minHeight: 96 }} value={prompt} autoFocus
          onChange={e => setPrompt(e.target.value)}
          placeholder="e.g. Alumni who graduated 2008–2020 and showed interest in space technology" />
        <button className="btn" disabled={busy} style={{ marginTop: 10 }}>
          {busy ? 'Reading your brief…' : 'Build group →'}</button>
      </form>
      {err && <p className="err">{err}</p>}
      <div style={{ marginTop: 22 }}>
        <div className="section-title">Try</div>
        {EXAMPLES.map((e, i) => (
          <button key={i} className="chip" style={{ display: 'block', textAlign: 'left', width: '100%', marginBottom: 8 }}
            onClick={() => setPrompt(e)}>{e}</button>
        ))}
      </div>
    </div>
  )
}

function DraftView({ g, onChange, onRun }:
  { g: AssistantGroup; onChange: (gg: AssistantGroup) => void; onRun: () => void }) {
  const [criterion, setCriterion] = useState(g.criterion)
  const [ymin, setYmin] = useState(g.filters.year_min ?? '')
  const [ymax, setYmax] = useState(g.filters.year_max ?? '')
  const [roles, setRoles] = useState<string[]>(g.filters.roles)
  const [saving, setSaving] = useState(false)

  const apply = async () => {
    setSaving(true)
    try {
      const gg = await api.assistant.patch(g.id, {
        criterion,
        year_min: ymin === '' ? null : Number(ymin),
        year_max: ymax === '' ? null : Number(ymax),
        roles,
      })
      onChange(gg)
    } finally { setSaving(false) }
  }
  const toggleRole = (r: string) =>
    setRoles(rs => rs.includes(r) ? rs.filter(x => x !== r) : [...rs, r])

  return (
    <div className="center-col">
      <h2 style={{ marginBottom: 2 }}>{g.title}</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>Review what the assistant understood, tweak if needed, then run.</p>

      <div className="panel">
        <h2>Fit criterion (what makes someone a match)</h2>
        <textarea className="notebox" value={criterion} onChange={e => setCriterion(e.target.value)} />
        <div className="filters-row">
          <label>Class years
            <span className="yr"><input className="select" type="number" placeholder="from" value={ymin}
              onChange={e => setYmin(e.target.value)} />–
            <input className="select" type="number" placeholder="to" value={ymax}
              onChange={e => setYmax(e.target.value)} /></span>
          </label>
          <div className="roles">Roles:
            {ROLES.map(r => (
              <button key={r} className={`chip ${roles.includes(r) ? 'active' : ''}`} onClick={() => toggleRole(r)}>
                {r[0].toUpperCase() + r.slice(1)}</button>
            ))}
            {roles.length === 0 && <span className="hint"> (all)</span>}
          </div>
        </div>
        {g.effective_roles && roles.includes('alumnus') && !roles.includes('student') &&
          <p className="hint" style={{ marginTop: 10 }}>
            ℹ️ Includes people tagged “student” in older issues who have since graduated (they’re
            alumni now). Parents are excluded — their year tag refers to their child.
          </p>}
        <button className="ghost sm" onClick={apply} disabled={saving} style={{ marginTop: 10 }}>
          {saving ? 'Updating…' : 'Update filters'}</button>
      </div>

      <div className="panel runbar">
        <div>
          <div className="bignum">{g.total.toLocaleString()}</div>
          <div className="dmeta">people to evaluate</div>
        </div>
        <div className="estimate">
          {g.est_cost && <>~${g.est_cost.low}–${g.est_cost.high} · ~{g.est_cost.minutes} min<br /></>}
          <span className="hint">Each is judged by an individual AI call. Runs in the background.</span>
        </div>
        <button className="btn" onClick={onRun} disabled={g.total === 0}>Run ▶</button>
      </div>
    </div>
  )
}

function ResultsView({ g, onCancel }: { g: AssistantGroup; onCancel: () => void }) {
  const fav = useFavorites()
  const running = g.status === 'running'
  const people = g.people ?? []
  const addAll = () => people.forEach(p => { if (!fav.isFav(p.key)) fav.add(p.key) })

  return (
    <div className="center-col">
      <div className="results-head">
        <div>
          <h2 style={{ margin: 0 }}>{g.title}</h2>
          <div className="dmeta">{g.criterion}</div>
        </div>
        {running
          ? <button className="ghost sm" onClick={onCancel}>Cancel</button>
          : <span className={`badge ${g.status}`}>{g.status}</span>}
      </div>

      <ProgressBar g={g} />

      <div className="results-actions">
        {people.length > 0 && <>
          <a className="btn outline sm" href={api.assistant.exportUrl(g.id)} download="group.csv">⬇ Export CSV</a>
          <button className="ghost sm" onClick={addAll}>♥ Add all to favorites</button>
        </>}
        {running && <span className="hint">Judging in the background — you can close this tab.</span>}
      </div>

      {people.length === 0
        ? <div className="empty-state">{running ? 'Finding matches…' : 'No matches found for this criterion.'}</div>
        : <div className="matchlist">{people.map(p => <MatchCard key={p.key} p={p} />)}</div>}
    </div>
  )
}

export default function Assistant() {
  const [params, setParams] = useSearchParams()
  const sel = Number(params.get('g') || 0) || null
  const [groups, setGroups] = useState<AssistantGroup[]>([])
  const [group, setGroup] = useState<AssistantGroup | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const loadGroups = useCallback(async () => {
    try { setGroups(await api.assistant.list()) } catch { /* ignore */ }
  }, [])
  useEffect(() => { void loadGroups() }, [loadGroups])

  useEffect(() => {
    if (!sel) { setGroup(null); return }
    let alive = true
    api.assistant.get(sel).then(g => { if (alive) setGroup(g) }).catch(() => setGroup(null))
    return () => { alive = false }
  }, [sel])

  // poll while the selected group is running (server keeps working even if we don't)
  useEffect(() => {
    if (!group || group.status !== 'running') return
    const t = setInterval(async () => {
      try {
        const g = await api.assistant.get(group.id)
        setGroup(g)
        setGroups(gs => gs.map(x => x.id === g.id ? { ...x, ...g, people: undefined } : x))
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(t)
  }, [group?.id, group?.status])

  const select = (id: number | null) => setParams(id ? { g: String(id) } : {})

  const create = async (prompt: string) => {
    setBusy(true); setErr('')
    try {
      const g = await api.assistant.create(prompt)
      await loadGroups(); select(g.id); setGroup(g)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const run = async () => {
    if (!group) return
    const g = await api.assistant.run(group.id)
    setGroup(g); void loadGroups()
  }
  const cancel = async () => {
    if (!group) return
    await api.assistant.cancel(group.id)
    setGroup(await api.assistant.get(group.id)); void loadGroups()
  }
  const del = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    await api.assistant.remove(id)
    if (sel === id) select(null)
    void loadGroups()
  }

  return (
    <div className="container">
      <div className="asst-grid">
        <aside className="asst-rail">
          <button className="btn sm" style={{ width: '100%' }} onClick={() => select(null)}>+ New group</button>
          <div className="asst-list">
            {groups.map(g => (
              <div key={g.id} className={`asst-item ${sel === g.id ? 'active' : ''}`} onClick={() => select(g.id)}>
                <div className="ai-title">{g.title}</div>
                <div className="ai-sub">
                  <span className={`badge ${g.status}`}>{g.status}</span>
                  {g.status !== 'draft' && <> · {g.matched}/{g.total}</>}
                </div>
                <button className="ai-del" title="Delete" onClick={e => del(g.id, e)}>✕</button>
              </div>
            ))}
            {groups.length === 0 && <div className="hint" style={{ padding: '10px 4px' }}>No groups yet.</div>}
          </div>
          {groups.length > 0 && (
            <a className="btn outline sm rail-export" href="/api/assistant/export.zip" download>
              ⬇ All searches (ZIP of CSVs)
            </a>
          )}
        </aside>

        <main className="asst-main">
          {!sel ? <NewGroup onCreate={create} busy={busy} err={err} />
            : !group ? <div className="loading">Loading…</div>
              : group.status === 'draft'
                ? <DraftView g={group} onChange={setGroup} onRun={run} />
                : <ResultsView g={group} onCancel={cancel} />}
        </main>
      </div>
    </div>
  )
}
