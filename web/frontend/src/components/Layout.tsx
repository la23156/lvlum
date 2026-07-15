import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export function Brand() {
  return <span className="brand"><span className="big">Big</span><span className="red">Red</span><span className="big">Alumni</span></span>
}

export function Layout() {
  const { logout } = useAuth()
  const nav = useNavigate()
  const [q, setQ] = useState('')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`)
  }

  return (
    <>
      <header className="nav">
        <Link to="/"><Brand /></Link>
        <nav className="links">
          <NavLink to="/" end>Discover</NavLink>
          <NavLink to="/browse">Directory</NavLink>
          <NavLink to="/shuffle">Shuffle</NavLink>
          <NavLink to="/favorites">Favorites</NavLink>
          <NavLink to="/assistant">✨ Assistant</NavLink>
          <NavLink to="/about">About</NavLink>
        </nav>
        <div className="spacer" />
        <form className="navsearch" onSubmit={submit}>
          <span>🔎</span>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search alumni…" />
        </form>
        <button className="ghost" onClick={() => { void logout().then(() => nav('/login')) }}>Log out</button>
      </header>
      <Outlet />
    </>
  )
}
