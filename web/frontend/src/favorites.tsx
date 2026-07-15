import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api/client'

interface FavState {
  keys: Set<string>
  count: number
  isFav: (k: string) => boolean
  add: (k: string, note?: string) => void
  remove: (k: string) => void
  toggle: (k: string) => void
  reload: () => Promise<void>
}

const Ctx = createContext<FavState>({
  keys: new Set(), count: 0, isFav: () => false,
  add: () => {}, remove: () => {}, toggle: () => {}, reload: async () => {},
})

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const [keys, setKeys] = useState<Set<string>>(new Set())

  const reload = useCallback(async () => {
    try { setKeys(new Set(await api.favorites.keys())) } catch { /* ignore */ }
  }, [])

  useEffect(() => { void reload() }, [reload])

  const add = useCallback((k: string, note?: string) => {
    setKeys(prev => new Set(prev).add(k))
    void api.favorites.add(k, note).catch(() => {})
  }, [])

  const remove = useCallback((k: string) => {
    setKeys(prev => { const n = new Set(prev); n.delete(k); return n })
    void api.favorites.remove(k).catch(() => {})
  }, [])

  const toggle = useCallback((k: string) => {
    setKeys(prev => {
      const n = new Set(prev)
      if (n.has(k)) { n.delete(k); void api.favorites.remove(k).catch(() => {}) }
      else { n.add(k); void api.favorites.add(k).catch(() => {}) }
      return n
    })
  }, [])

  return (
    <Ctx.Provider value={{ keys, count: keys.size, isFav: k => keys.has(k), add, remove, toggle, reload }}>
      {children}
    </Ctx.Provider>
  )
}

export const useFavorites = () => useContext(Ctx)
