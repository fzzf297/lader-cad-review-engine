import api from './index'
import type { ReviewResponse, HistoryListResponse, StatisticsResponse } from '@/types/api'

export interface ReviewRequest {
  drawing_file_id: string
  enable_llm?: boolean
  rule_codes?: string[]
}

export interface HistoryListParams {
  page?: number
  page_size?: number
  file_type?: string
  assessment?: string
}

export const reviewApi = {
  async createReview(request: ReviewRequest): Promise<ReviewResponse> {
    return api.post('/review', {
      dwg_file_id: request.drawing_file_id,
      enable_llm: request.enable_llm,
      rule_codes: request.rule_codes
    }) as Promise<ReviewResponse>
  },

  async getReviewResult(reviewId: string): Promise<ReviewResponse> {
    return api.get(`/review/${reviewId}`) as Promise<ReviewResponse>
  },

  // 历史记录 API
  async getHistoryList(params: HistoryListParams = {}): Promise<HistoryListResponse> {
    const query = new URLSearchParams()
    if (params.page) query.append('page', params.page.toString())
    if (params.page_size) query.append('page_size', params.page_size.toString())
    if (params.file_type) query.append('file_type', params.file_type)
    if (params.assessment) query.append('assessment', params.assessment)
    return api.get(`/review/history/list?${query.toString()}`) as Promise<HistoryListResponse>
  },

  async getHistoryDetail(recordId: string): Promise<ReviewResponse> {
    return api.get(`/review/history/${recordId}`) as Promise<ReviewResponse>
  },

  async deleteHistory(recordId: string): Promise<{ success: boolean; message: string }> {
    return api.delete(`/review/history/${recordId}`) as Promise<{ success: boolean; message: string }>
  },

  async getStatistics(): Promise<StatisticsResponse> {
    return api.get('/review/statistics') as Promise<StatisticsResponse>
  },

  // 报告下载
  getReportJsonUrl(recordId: string): string {
    return `/api/v1/review/report/${recordId}/json`
  },

  getReportPdfUrl(recordId: string): string {
    return `/api/v1/review/report/${recordId}/pdf`
  }
}
