import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  envDir: '..',
  server: { proxy: { '/api': 'http://localhost:8000', '/_AMapService': 'http://localhost:8000' } },
})
