import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During `npm run dev`, calls to /api are forwarded to the FastAPI server,
// so the frontend can use relative URLs and no CORS setup is needed locally.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
