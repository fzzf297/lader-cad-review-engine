export interface UploadResponse {
  file_id: string
  filename: string
  file_type: string
  file_path: string
  file_size?: number
  status: string
  message?: string
  converted?: boolean
  uploaded_at?: string
}

export interface UploadedFile {
  file_id: string
  filename: string
  file_type: string
  file_size: number
  status: string
  converted?: boolean
  uploaded_at: string
}

export interface UploadListResponse {
  files: UploadedFile[]
  total: number
}

export interface Issue {
  category: string
  severity: 'error' | 'warning' | 'info'
  description: string
  location: string
  suggestion: string
  source: 'rule' | 'llm' | 'both'
  confidence: number
}

export interface ReviewResponse {
  overall_score: number
  assessment: string
  issues: Issue[]
  summary: {
    total_issues: number
    by_severity: {
      error: number
      warning: number
      info: number
    }
    by_source: {
      rule_only: number
      llm_only: number
      both: number
    }
    by_category: Record<string, number>
  }
  llm_enabled: boolean
}

export interface AsyncTaskRequest {
  drawing_file_id: string
  enable_llm?: boolean
  rule_codes?: string[]
  large_file?: boolean
}

export interface TaskProgress {
  progress: number
  stage: string
  message?: string
  timestamp?: string
}

export interface TaskStatusResponse {
  task_id: string
  status: string
  ready: boolean
  successful?: boolean | null
  failed?: boolean | null
  progress?: TaskProgress
  result?: Record<string, unknown>
  error?: string
}

// 历史记录相关类型
export interface ReviewRecord {
  record_id: string
  file_id: string
  file_name: string
  file_type: string
  created_at: string
  overall_score: number
  assessment: string
  issue_count: number
  enable_llm: boolean
}

export interface HistoryListResponse {
  records: ReviewRecord[]
  total: number
  page: number
  page_size: number
}

export interface StatisticsResponse {
  total_reviews: number
  avg_score: number
  by_assessment: Record<string, number>
  by_file_type: Record<string, number>
}

// ==================== 解析验证类型 ====================

export interface ParseMetadata {
  parsed_at: string
  parse_duration_seconds: number
  file_path: string
  file_size: number
  file_md5: string
  parser_version: string
}

export interface ParseVerificationCheck {
  name: string
  passed: boolean
  detail: string
}

export interface ParseVerificationIndicators {
  door_window_types: number
  door_window_list: string[]
}

export interface DwgParseVerificationResponse {
  file_id: string
  filename: string
  status: string
  message: string
  verification: {
    is_valid: boolean
    confidence: string
    passed_checks: number
    total_checks: number
    checks: ParseVerificationCheck[]
    indicators: ParseVerificationIndicators
  }
  parse_metadata: ParseMetadata
  summary: {
    door_window_types: number
    confidence: string
  }
}

// ==================== 施工内容类型 ====================

export interface ConstructionContentItem {
  name: string
  code: string
  type: string
  count: number
  size: string
  specification: string
}

export interface RoomInfo {
  name: string
  area?: number
  description: string
}

export interface ConstructionContent {
  doors: ConstructionContentItem[]
  windows: ConstructionContentItem[]
  rooms: RoomInfo[]
  areas: Record<string, number>
  summary: {
    total_doors: number
    total_windows: number
    door_types: number
    window_types: number
    rooms_count: number
  }
}

export interface DwgConstructionContentResponse {
  file_id: string
  filename: string
  parse_status: string
  construction_content: ConstructionContent
  parse_time?: string
}

export interface LegendDiscoveryItem {
  label_text: string
  normalized_name: string
  block_name: string
  total_matches: number
  estimated_actual_count: number
  excluded_as_legend: number
  confidence: number
  source: string
}

export interface LegendDiscoveryResponse {
  file_id: string
  total_items: number
  items: LegendDiscoveryItem[]
}

export interface LegendMatch {
  x: number
  y: number
  z: number
  layer: string
  block_name: string
  handle: string
  reason: string
}

export interface LegendCountResponse {
  query: string
  matched_label_texts: string[]
  target_signature: Record<string, unknown>
  total_matches: number
  excluded_as_legend: number
  actual_count: number
  matches: LegendMatch[]
  excluded_matches: LegendMatch[]
  explanation: string
  confidence: number
}

export interface DrawingPreviewEntity {
  type: string
  start?: { x: number; y: number }
  end?: { x: number; y: number }
  center?: { x: number; y: number }
  radius?: number
  start_angle?: number
  end_angle?: number
  vertices?: Array<{ x: number; y: number }>
  closed?: boolean
  insert?: { x: number; y: number }
  content?: string
  height?: number
  rotation?: number
}

export interface DrawingPreviewResponse {
  file_id: string
  bounds: {
    min_x: number
    max_x: number
    min_y: number
    max_y: number
  }
  entities: DrawingPreviewEntity[]
}
