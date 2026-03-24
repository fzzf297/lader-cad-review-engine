<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const features = [
  {
    title: 'DXF 图纸解析',
    description: '支持 DXF 文件解析，快速提取图层、文字、图块、图元和构件统计信息',
    icon: '📄'
  },
  {
    title: '图元统计分析',
    description: '聚焦图纸结构提取、设备识别和门窗摘要，方便理解 CAD 内容分布',
    icon: '📊'
  },
  {
    title: '异步任务解析',
    description: '默认走任务队列执行解析，大文件场景下也能持续查看进度与结果',
    icon: '⏱️'
  },
  {
    title: '结果复核辅助',
    description: '在结构化解析结果之上保留基础检查与扩展分析能力，便于后续增强',
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
      <h1>CAD 解析引擎</h1>
      <p class="subtitle">面向 DXF 图纸结构提取、设备识别与结果追踪的轻量化 CAD 解析平台</p>
      <el-button type="primary" size="large" @click="goToUpload">
        开始解析
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
