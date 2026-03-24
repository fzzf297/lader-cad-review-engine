<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const navItems = [
  { path: '/', label: '首页' },
  { path: '/upload', label: '上传文件' },
  { path: '/history', label: '历史记录' }
]
</script>

<template>
  <header class="app-header">
    <div class="logo">
      <h1>CAD 解析引擎</h1>
    </div>
    <nav class="nav-menu">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-link"
        active-class="active"
      >
        {{ item.label }}
      </router-link>
    </nav>
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.logo h1 {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.nav-menu {
  display: flex;
  gap: 8px;
}

.nav-link {
  padding: 8px 16px;
  color: #606266;
  text-decoration: none;
  border-radius: 4px;
  transition: all 0.3s;
}

.nav-link:hover {
  color: #409eff;
  background: #ecf5ff;
}

.nav-link.active {
  color: #409eff;
  background: #ecf5ff;
}
</style>
