// Thin fetch wrapper. All requests are same-origin (dev uses the Vite proxy) and send the
// session cookie. A 401 throws Unauthorized so the AuthGate can redirect to /login.

export class Unauthorized extends Error {}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'include', ...init })
  if (res.status === 401) throw new Unauthorized('auth required')
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export interface PersonCard {
  key: string
  name: string
  first_name?: string
  last_name?: string
  class_year: string | null
  role: string
  doc_count: number
  mention_count: number
  interests: string[]
  thumb: string | null
  source_url?: string | null
  source_image?: string | null
  source_doc?: string | null
  source_page?: number | null
  score: number | null
}

export function exportCsvUrl(opts: { q?: string; mode?: string; role?: string; year?: string; sort?: string } = {}) {
  const p = new URLSearchParams()
  if (opts.q) { p.set('q', opts.q); p.set('mode', opts.mode ?? 'keyword') }
  if (opts.role) p.set('role', opts.role)
  if (opts.year) p.set('year', opts.year)
  if (opts.sort) p.set('sort', opts.sort)
  return `/api/export.csv?${p}`
}

export interface FeaturedPage {
  document: string
  page: number
  issuu: string | null
  thumb: string
  full: string
  snippet: string | null
}

export interface Profile {
  key: string
  name: string
  class_year: string | null
  class_year_tags: string | null
  role: string
  interests: string[]
  doc_count: number
  mention_count: number
  featured_pages: FeaturedPage[]
  is_favorite: boolean
  note: string
}

export interface Favorite extends PersonCard {
  note?: string
  created_at?: string
}

export interface GroupFilters { year_min: number | null; year_max: number | null; roles: string[] }
export interface MatchPerson extends PersonCard { fit: boolean; reasoning: string; confidence: number }
export interface AssistantGroup {
  id: number
  title: string
  prompt: string
  criterion: string
  filters: GroupFilters
  effective_roles?: string[]
  model: string
  status: 'draft' | 'running' | 'done' | 'cancelled'
  total: number
  judged: number
  matched: number
  created_at?: string
  updated_at?: string
  est_cost?: { low: number; high: number; minutes: number }
  people?: MatchPerson[]
}

export interface Theme { key: string; label: string; emoji: string; query: string }

export interface Stats {
  people: number; documents: number; mentions: number; with_year: number
  by_role: Record<string, number>
}

export const api = {
  me: () => req<{ phone: string }>('/api/auth/me'),
  requestOtp: (phone: string) =>
    req<{ ok: boolean; dev: boolean }>('/api/auth/request-otp', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    }),
  verify: (phone: string, code: string) =>
    req<{ ok: boolean }>('/api/auth/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, code }),
    }),
  logout: () => req<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  stats: () => req<Stats>('/api/stats'),
  themes: () => req<{ themes: Theme[] }>('/api/themes').then(r => r.themes),
  discover: (n = 12) => req<{ results: PersonCard[] }>(`/api/discover?n=${n}`).then(r => r.results),
  search: (q: string, opts: { mode?: string; role?: string; year?: string; n?: number } = {}) => {
    const p = new URLSearchParams({ q, mode: opts.mode ?? 'hybrid', n: String(opts.n ?? 24) })
    if (opts.role) p.set('role', opts.role)
    if (opts.year) p.set('year', opts.year)
    return req<{ results: PersonCard[] }>(`/api/search?${p}`).then(r => r.results)
  },
  shuffle: (theme: string, q = '', n = 30) => {
    const p = new URLSearchParams({ theme, q, n: String(n) })
    return req<{ results: PersonCard[] }>(`/api/shuffle?${p}`).then(r => r.results)
  },
  person: (key: string) => req<Profile>(`/api/person/${encodeURIComponent(key)}`),
  favorites: {
    list: () => req<{ favorites: Favorite[] }>('/api/favorites').then(r => r.favorites),
    keys: () => req<{ keys: string[] }>('/api/favorites/keys').then(r => r.keys),
    add: (key: string, note?: string) => req('/api/favorites', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, note }),
    }),
    setNote: (key: string, note: string) => req(`/api/favorites/${encodeURIComponent(key)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    }),
    remove: (key: string) => req(`/api/favorites/${encodeURIComponent(key)}`, { method: 'DELETE' }),
  },
  browse: (opts: { q?: string; mode?: string; role?: string; year?: string; sort?: string;
                   offset?: number; limit?: number } = {}) => {
    const p = new URLSearchParams()
    if (opts.q) p.set('q', opts.q)
    if (opts.q) p.set('mode', opts.mode ?? 'keyword')
    if (opts.role) p.set('role', opts.role)
    if (opts.year) p.set('year', opts.year)
    if (opts.sort) p.set('sort', opts.sort)
    p.set('offset', String(opts.offset ?? 0))
    p.set('limit', String(opts.limit ?? 60))
    return req<{ results: PersonCard[]; total: number | null; has_more: boolean }>(`/api/browse?${p}`)
  },
  assistant: {
    create: (prompt: string, model?: string) => req<AssistantGroup>('/api/assistant/groups', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, model }),
    }),
    list: () => req<{ groups: AssistantGroup[] }>('/api/assistant/groups').then(r => r.groups),
    get: (id: number, include: 'matched' | 'all' = 'matched') =>
      req<AssistantGroup>(`/api/assistant/groups/${id}?include=${include}`),
    patch: (id: number, body: Partial<{ criterion: string; year_min: number | null; year_max: number | null; roles: string[] }>) =>
      req<AssistantGroup>(`/api/assistant/groups/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    run: (id: number) => req<AssistantGroup>(`/api/assistant/groups/${id}/run`, { method: 'POST' }),
    cancel: (id: number) => req(`/api/assistant/groups/${id}/cancel`, { method: 'POST' }),
    remove: (id: number) => req(`/api/assistant/groups/${id}`, { method: 'DELETE' }),
    exportUrl: (id: number) => `/api/assistant/groups/${id}/export.csv`,
  },
}
