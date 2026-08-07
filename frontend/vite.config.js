import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  envDir: '..',
  build: {
    // The isolated, tree-shaken ECharts SVG runtime is 503 kB (172 kB gzip).
    chunkSizeWarningLimit: 510,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/echarts/')) return 'echarts'
        },
      },
    },
  },
  server: { proxy: { '/api': 'http://localhost:8000', '/_AMapService': 'http://localhost:8000' } },
  test: { environment: 'jsdom', clearMocks: true },
})
