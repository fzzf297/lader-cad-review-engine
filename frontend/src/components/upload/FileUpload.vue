<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElIcon, ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

interface UploadResult {
  file_id: string
  filename: string
  message?: string
  converted?: boolean
}

const props = defineProps<{
  type: 'dwg'
  accept: string
}>()

const emit = defineEmits<{
  success: [result: UploadResult]
}>()

const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const uploadFile = async (file: File) => {
  // 防止重复上传
  if (uploading.value) return
  uploading.value = true

  try {
    const formData = new FormData()
    formData.append('file', file)

    const endpoint = '/api/v1/upload/dwg'

    const response = await fetch(endpoint, {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || '上传失败')
    }

    const result = await response.json()
    emit('success', {
      file_id: result.file_id,
      filename: result.filename,
      message: result.message,
      converted: result.converted
    })
  } catch (error: any) {
    console.error('Upload error:', error)
    ElMessage.error(error.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

const inputId = computed(() => `file-upload-${props.type}`)

const handleFileChange = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  await uploadFile(file)
  target.value = ''
}

const handleDrop = async (event: DragEvent) => {
  event.preventDefault()
  if (uploading.value) return

  const file = event.dataTransfer?.files?.[0]
  if (!file) return

  await uploadFile(file)
}
</script>

<template>
  <div class="file-upload">
    <label
      :for="inputId"
      class="upload-dragger"
      :class="{ 'is-uploading': uploading }"
      @dragover.prevent
      @drop="handleDrop"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">
        拖拽文件到此处，或 <em>{{ uploading ? '上传中...' : '点击上传' }}</em>
      </div>
      <div class="el-upload__tip">
        支持的格式: {{ accept }}
      </div>
    </label>
    <input
      :id="inputId"
      ref="fileInput"
      class="file-input"
      type="file"
      :accept="accept"
      :disabled="uploading"
      @change="handleFileChange"
    />
  </div>
</template>

<style scoped>
.file-upload {
  width: 100%;
  text-align: center;
  position: relative;
}

.file-input {
  display: none;
}

.upload-dragger {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 240px;
  padding: 32px 24px;
  border: 2px dashed #409eff;
  border-radius: 12px;
  background: #fafcff;
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease;
  user-select: none;
}

.upload-dragger:hover,
.upload-dragger:focus-visible {
  border-color: #337ecc;
  background: #f2f8ff;
  outline: none;
}

.upload-dragger.is-uploading {
  cursor: progress;
  opacity: 0.8;
}

.el-icon--upload {
  font-size: 48px;
  color: #c0c4cc;
  margin-bottom: 12px;
  line-height: 1;
}

.el-upload__text {
  font-size: 16px;
  color: #606266;
  line-height: 1.6;
}

.el-upload__text em {
  color: #409eff;
  font-style: normal;
}

.el-upload__tip {
  margin-top: 12px;
  color: #909399;
  font-size: 14px;
}
</style>
