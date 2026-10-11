import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api/notifications': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true
      },
      '/api/auth': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      },
      '/api/admin/saga-test-transfers': {
        target: 'http://127.0.0.1:8004',
        changeOrigin: true
      },
      '/api/transfers': {
        target: 'http://127.0.0.1:8004',
        changeOrigin: true
      },
      '/api/transactions': {
        target: 'http://127.0.0.1:8004',
        changeOrigin: true
      },
      '/api': {
        target: 'http://127.0.0.1:8003',
        changeOrigin: true
      }
    }
  }
});
