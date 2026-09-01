import path from 'node:path'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const dirname = path.dirname(fileURLToPath(import.meta.url))

// Backend listens on 127.0.0.1:8756 in production (see
// packaging/systemd/nova.service). Overridable for local dev via
// NOVA_BACKEND_URL so `vite dev` still works if a developer runs uvicorn on
// a different port (e.g. the default 8000 from a bare `uvicorn --reload`).
const backendTarget = process.env.NOVA_BACKEND_URL ?? 'http://127.0.0.1:8756'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
      '/health': { target: backendTarget, changeOrigin: true },
    },
  },
})
