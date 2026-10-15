import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run build` writes the app into ../static, which FastAPI serves.
// `npm run dev` (optional, for editing the UI) proxies /api to the running backend on :8080.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../static', emptyOutDir: true },
  server: { port: 5173, proxy: { '/api': 'http://localhost:8080' } },
})
