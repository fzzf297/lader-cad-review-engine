import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    // 首页直接加载，提升首屏性能
    component: HomeView
  },
  {
    path: '/upload',
    name: 'upload',
    // 路由懒加载
    component: () => import('@/views/UploadView.vue')
  },
  {
    path: '/review/:fileId',
    name: 'review',
    // 路由懒加载
    component: () => import('@/views/ReviewView.vue')
  },
  {
    path: '/history',
    name: 'history',
    // 路由懒加载
    component: () => import('@/views/HistoryView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
