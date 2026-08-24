import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://api:8000', rewrite: p => p.replace(/^\/api/, '') },
      '/ws':  { target: 'ws://api:8000',  ws: true, rewrite: p => p.replace(/^\/ws/, '/ws') }
    }
  },
  build: { outDir: 'dist', sourcemap: false }
})
