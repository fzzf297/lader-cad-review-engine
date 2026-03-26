import api from './index'
import type { AsyncTaskRequest, ReviewResponse, TaskStatusResponse } from '@/types/api'

export const tasksApi = {
  async createTask(request: AsyncTaskRequest): Promise<TaskStatusResponse> {
    return api.post('/tasks', {
      dwg_file_id: request.drawing_file_id,
      enable_llm: request.enable_llm,
      rule_codes: request.rule_codes,
      large_file: request.large_file
    }) as Promise<TaskStatusResponse>
  },

  async getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
    return api.get(`/tasks/${taskId}`) as Promise<TaskStatusResponse>
  },

  async getTaskResult(taskId: string): Promise<ReviewResponse> {
    return api.get(`/tasks/${taskId}/result`) as Promise<ReviewResponse>
  }
}
