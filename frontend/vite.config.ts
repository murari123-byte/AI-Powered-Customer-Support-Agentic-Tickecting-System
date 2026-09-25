/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Read the single project-root .env file (only VITE_* variables reach the browser).
  envDir: '..',
  server: {
    port: 5173,
    // Fail loudly instead of silently moving to another port, which would break CORS.
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
