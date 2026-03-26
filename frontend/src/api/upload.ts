import api from './index'
import type { UploadListResponse, UploadResponse } from '@/types/api'

export const uploadApi = {
  async uploadDrawing(file: File, onProgress?: (percent: number) => void): Promise<UploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    return api.post('/upload/dwg', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (e.total && onProgress) {
          onProgress(Math.round((e.loaded * 100) / e.total))
        }
      }
    }) as Promise<UploadResponse>
  },

  async getFileInfo(fileId: string): Promise<UploadResponse> {
    return api.get(`/upload/${fileId}`) as Promise<UploadResponse>
  },

  async listFiles(fileType?: 'dwg'): Promise<UploadListResponse> {
    const query = new URLSearchParams()
    if (fileType) {
      query.append('file_type', fileType)
    }
    const suffix = query.toString()
    return api.get(`/upload/list${suffix ? `?${suffix}` : ''}`) as Promise<UploadListResponse>
  }
}
