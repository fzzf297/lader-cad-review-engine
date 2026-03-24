<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FileUpload from '@/components/upload/FileUpload.vue'

const router = useRouter()

const dwgFileId = ref<string | null>(null)
const uploading = ref(false)
const uploadMessage = ref<string | null>(null)
const converted = ref(false)

interface UploadResult {
  file_id: string
  filename: string
  message?: string
  converted?: boolean
}

const handleDwgSuccess = (result: UploadResult) => {
  dwgFileId.value = result.file_id
  uploadMessage.value = result.message || null
  converted.value = result.converted || false
  ElMessage.success('DXF 文件上传成功')
}

const startReview = async () => {
  if (!dwgFileId.value) {
    ElMessage.warning('请先上传 DXF 文件')
    return
  }

  uploading.value = true
  try {
    router.push({ path: `/review/${dwgFileId.value}` })
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="upload-view">
    <h2>上传 DXF 文件</h2>

    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <span>📄 DXF 图纸文件</span>
          <span class="required">*</span>
        </div>
      </template>
      <FileUpload
        type="dwg"
        accept=".dxf"
        @success="handleDwgSuccess"
      />
      <div v-if="dwgFileId" class="upload-status">
        <el-tag :type="converted ? 'warning' : 'success'">
          {{ converted ? '已转换' : '已上传' }}
        </el-tag>
      </div>
      <div v-if="uploadMessage" class="upload-message">
        <el-alert
          :title="uploadMessage"
          :type="converted ? 'success' : 'info'"
          :closable="false"
          show-icon
        />
      </div>
      <div class="upload-hint">
        当前版本聚焦 DXF 直传解析，不支持 DWG 自动转换。
      </div>
    </el-card>

    <div class="action-bar">
      <el-button
        type="primary"
        size="large"
        :disabled="!dwgFileId"
        :loading="uploading"
        @click="startReview"
      >
        开始解析
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.upload-view {
  max-width: 1000px;
  margin: 0 auto;
}

.upload-view h2 {
  margin-bottom: 24px;
  font-size: 24px;
  font-weight: 600;
}

.upload-card {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.required {
  color: #f56c6c;
}

.upload-status {
  margin-top: 16px;
  text-align: center;
}

.upload-message {
  margin-top: 12px;
}

.upload-hint {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
}

.action-bar {
  margin-top: 32px;
  text-align: center;
}
</style>
