import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ command, mode }) => {
  // A production build without VITE_API_BASE_URL would silently call
  // http://127.0.0.1:5000/api from users' browsers. Fail the build instead.
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  if (command === 'build' && !env.VITE_API_BASE_URL) {
    throw new Error(
      'VITE_API_BASE_URL is not set. Set it to the API address including /api, ' +
        'e.g. https://hostel-api.onrender.com/api (Render: Static Site > Environment).',
    );
  }

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    server: {
      port: 5173,
      strictPort: true,
    },
    build: {
      rollupOptions: {
        output: {
          // Long-lived vendor chunks cache separately from app code.
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            charts: ['recharts'],
            vendor: ['axios', 'lucide-react'],
          },
        },
      },
    },
  };
});
