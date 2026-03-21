import api from './index'
import type { DwgPreviewResponse, LegendCountResponse, LegendDiscoveryResponse } from '@/types/api'

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

  async getDwgPreview(fileId: string): Promise<DwgPreviewResponse> {
    return api.get(`/parse/dwg/${fileId}/preview`) as Promise<DwgPreviewResponse>
  }
}
