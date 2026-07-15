import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies API + image requests to the FastAPI backend on :8000,
// so the browser sees one origin and the session cookie works.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/img': 'http://localhost:8000',
    },
  },
})
