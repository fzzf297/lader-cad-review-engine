<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const features = [
  {
    title: 'DXF 图纸审核',
    description: '支持 DXF 文件解析，自动检查图层、线型、文字、图块等是否符合国标要求',
    icon: '📄'
  },
  {
    title: '图元统计分析',
    description: '快速提取图层、图块、实体和门窗摘要，方便定位图纸结构与关键内容',
    icon: '📊'
  },
  {
    title: '异步任务审核',
    description: '默认走任务队列执行审核，大文件场景下也能持续查看进度与结果',
    icon: '⏱️'
  },
  {
    title: 'LLM 辅助审核',
    description: '集成大语言模型，提供设计合理性分析和改进建议',
    icon: '🤖'
  }
]

const goToUpload = () => {
  router.push('/upload')
}
</script>

<template>
  <div class="home-view">
    <div class="hero">
      <h1>CAD 图纸审核引擎</h1>
      <p class="subtitle">面向 DXF 图纸解析、规则审核与结果追踪的轻量化审核平台</p>
      <el-button type="primary" size="large" @click="goToUpload">
        开始审核
      </el-button>
    </div>

    <div class="features">
      <el-card v-for="feature in features" :key="feature.title" class="feature-card">
        <div class="feature-icon">{{ feature.icon }}</div>
        <h3>{{ feature.title }}</h3>
        <p>{{ feature.description }}</p>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.home-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 20px;
}

.hero {
  text-align: center;
  margin-bottom: 60px;
}

.hero h1 {
  font-size: 36px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
}

.subtitle {
  font-size: 18px;
  color: #606266;
  margin-bottom: 32px;
}

.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 24px;
}

.feature-card {
  text-align: center;
  padding: 24px;
}

.feature-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.feature-card h3 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.feature-card p {
  font-size: 14px;
  color: #909399;
  line-height: 1.6;
}
</style>
