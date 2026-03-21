import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path
      }
    }
  },
  build: {
    // 生产环境关闭 sourcemap
    sourcemap: false,
    // 4KB 以下转 base64
    assetsInlineLimit: 4096,
    // 代码分割配置
    rollupOptions: {
      output: {
        // 手动 chunk 分离
        manualChunks: {
          // Vue 核心
          'vendor': ['vue', 'vue-router', 'pinia'],
          // Element Plus UI 库
          'element-plus': ['element-plus'],
          // ECharts 图表库
          'echarts': ['echarts']
        },
        // 静态资源命名
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: 'assets/[ext]/[name]-[hash].[ext]'
      }
    },
    // 块大小警告阈值
    chunkSizeWarningLimit: 1000
  }
})