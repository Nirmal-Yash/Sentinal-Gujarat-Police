import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://api:8000', rewrite: p => p.replace(/^\/api/, '') },
      '/test-hls': { target: 'http://mediamtx:8888', rewrite: p => p.replace(/^\/test-hls/, '') },
      '/ws':  { target: 'ws://api:8000',  ws: true, rewrite: p => p.replace(/^\/ws/, '/ws') }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('hls.js')) return 'vendor-hls'
            if (id.includes('leaflet')) return 'vendor-leaflet'
            if (id.includes('react') || id.includes('scheduler')) return 'vendor-react'
            return 'vendor'
          }
        }
      }
    }
  }
})
