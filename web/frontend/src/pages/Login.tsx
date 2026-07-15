import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth'
import { Brand } from '../components/Layout'

export default function Login() {
  const { refresh } = useAuth()
  const nav = useNavigate()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [stage, setStage] = useState<'phone' | 'code'>('phone')
  const [dev, setDev] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const sendCode = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const r = await api.requestOtp(phone)
      setDev(r.dev); setStage('code')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const verify = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      await api.verify(phone, code)
      await refresh()
      nav('/')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <Brand />
        <p>The Lawrenceville community directory</p>
        {stage === 'phone' ? (
          <form onSubmit={sendCode}>
            <input className="field" placeholder="Phone number (e.g. +1555…)" value={phone}
              onChange={e => setPhone(e.target.value)} autoFocus />
            <button className="btn" disabled={busy}>{busy ? 'Sending…' : 'Send code'}</button>
          </form>
        ) : (
          <form onSubmit={verify}>
            <input className="field" placeholder="6-digit code" value={code}
              onChange={e => setCode(e.target.value)} autoFocus inputMode="numeric" />
            <button className="btn" disabled={busy}>{busy ? 'Verifying…' : 'Enter'}</button>
            {dev && <p className="hint">Dev mode: use the code shown in the server logs.</p>}
          </form>
        )}
        {err && <p className="err">{err}</p>}
        <p className="hint">Access is limited to authorized numbers.</p>
      </div>
    </div>
  )
}
