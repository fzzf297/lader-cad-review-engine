import api from './index'
import type {
  DrawingPreviewResponse,
  ExperimentalVisionClassifyResponse,
  ExperimentalVisionRegionsResponse,
  LegendCountResponse,
  LegendDiscoveryResponse
} from '@/types/api'

export const parseApi = {
  async getLegendItems(fileId: string): Promise<LegendDiscoveryResponse> {
    return api.get(`/parse/legend-items/${fileId}`) as Promise<LegendDiscoveryResponse>
  },

  async countLegend(fileId: string, query: string, useLlm = false): Promise<LegendCountResponse> {
    return api.post('/parse/legend-count', {
      file_id: fileId,
      query,
      use_llm: useLlm
    }) as Promise<LegendCountResponse>
  },

  async getDrawingPreview(fileId: string): Promise<DrawingPreviewResponse> {
    return api.get(`/parse/dwg/${fileId}/preview`) as Promise<DrawingPreviewResponse>
  },

  async getExperimentalVisionRegions(fileId: string): Promise<ExperimentalVisionRegionsResponse> {
    return api.post('/parse/experimental/vision/regions', {
      file_id: fileId
    }) as Promise<ExperimentalVisionRegionsResponse>
  },

  async classifyExperimentalVision(fileId: string, legendName: string): Promise<ExperimentalVisionClassifyResponse> {
    return api.post('/parse/experimental/vision/classify', {
      file_id: fileId,
      legend_name: legendName
    }) as Promise<ExperimentalVisionClassifyResponse>
  }
}
