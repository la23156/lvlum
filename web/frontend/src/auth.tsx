import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api/client'

interface AuthState {
  user: string | null
  loading: boolean
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState>({
  user: null, loading: true, refresh: async () => {}, logout: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    setLoading(true)
    try {
      const me = await api.me()
      setUser(me.phone)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    setUser(null)
  }

  useEffect(() => { void refresh() }, [])

  return <Ctx.Provider value={{ user, loading, refresh, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
