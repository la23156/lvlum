import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './styles.css'
import { AuthProvider, useAuth } from './auth'
import { FavoritesProvider } from './favorites'
import { Layout } from './components/Layout'
import Login from './pages/Login'
import Home from './pages/Home'
import Browse from './pages/Browse'
import SearchPage from './pages/Search'
import Profile from './pages/Profile'
import Shuffle from './pages/Shuffle'
import Favorites from './pages/Favorites'
import Assistant from './pages/Assistant'
import About from './pages/About'

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><FavoritesProvider><Layout /></FavoritesProvider></Protected>}>
            <Route path="/" element={<Home />} />
            <Route path="/browse" element={<Browse />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/shuffle" element={<Shuffle />} />
            <Route path="/favorites" element={<Favorites />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/about" element={<About />} />
            <Route path="/p/:key" element={<Profile />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
