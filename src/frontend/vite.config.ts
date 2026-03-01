import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import path from 'path' 

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const isproduction = env.VITE_MODE === 'production'

  return {
    plugins: [
      vue(),
      vueDevTools(),
    ],
    base: isproduction ? env.VITE_URL_PATH : "/",
    // base: path.resolve(__dirname, './dist/'),
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      },
    },
    build: {
      outDir: env.VITE_DIST_PATH
    },
    server: {
      host: env.VITE_HOST,
      port: Number(env.VITE_PORT),
      open: false, // Electron 會開啟視窗，不需要自動開瀏覽器
      proxy: {
        '/api': {
          target: `http://localhost:${process.env.VITE_BACKEND_PORT || 8001}`,
          changeOrigin: true,
        }
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: "modern-compiler"
        },
      },
    },
  }
})
