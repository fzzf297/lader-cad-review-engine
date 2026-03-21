<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { reviewApi } from '@/api/review'
import { tasksApi } from '@/api/tasks'
import { uploadApi } from '@/api/upload'
import { parseApi } from '@/api/parse'
import type {
  DwgPreviewResponse,
  LegendCountResponse,
  LegendDiscoveryItem,
  ReviewResponse,
  TaskStatusResponse
} from '@/types/api'

const route = useRoute()
const fileId = route.params.fileId as string
const LARGE_FILE_THRESHOLD = 10 * 1024 * 1024
const preferAsyncReview = !import.meta.env.DEV

const loading = ref(true)
const reviewResult = ref<ReviewResponse | null>(null)
const enableLlm = ref(false)
const taskStatus = ref<TaskStatusResponse | null>(null)
const legendItems = ref<LegendDiscoveryItem[]>([])
const legendLoading = ref(false)
const legendCountingKey = ref('')
const legendCounts = ref<Record<string, LegendCountResponse>>({})
const activeLegendName = ref('')
const legendDetailVisible = ref(false)
const activeLegendHandle = ref('')
const dwgPreview = ref<DwgPreviewResponse | null>(null)
const legendViewMode = ref<'focus' | 'full'>('focus')
const legendShowKeep = ref(true)
const legendShowExclude = ref(true)
const legendZoom = ref(1)
const legendPanX = ref(0)
const legendPanY = ref(0)
const legendPlotViewport = ref<HTMLElement | null>(null)
const legendDragState = ref<{
  active: boolean
  pointerX: number
  pointerY: number
  startPanX: number
  startPanY: number
}>({
  active: false,
  pointerX: 0,
  pointerY: 0,
  startPanX: 0,
  startPanY: 0
})
let pollTimer: number | null = null

const errorCount = computed(() => {
  return reviewResult.value?.issues.filter(i => i.severity === 'error').length || 0
})

const warningCount = computed(() => {
  return reviewResult.value?.issues.filter(i => i.severity === 'warning').length || 0
})

const infoCount = computed(() => {
  return reviewResult.value?.issues.filter(i => i.severity === 'info').length || 0
})

const clearPollTimer = () => {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

const progressPercent = computed(() => taskStatus.value?.progress?.progress || 0)
const progressStage = computed(() => taskStatus.value?.progress?.stage || taskStatus.value?.status || '初始化')
const progressMessage = computed(() => taskStatus.value?.progress?.message || '正在准备审核任务...')

const fetchReviewSync = async () => {
  const result = await reviewApi.createReview({
    dwg_file_id: fileId,
    enable_llm: enableLlm.value
  })
  reviewResult.value = result
}

const loadLegendItems = async () => {
  legendLoading.value = true
  try {
    const response = await parseApi.getLegendItems(fileId)
    legendItems.value = response.items
  } catch (error: any) {
    legendItems.value = []
    ElMessage.warning(error.message || '设备图例识别失败')
  } finally {
    legendLoading.value = false
  }
}

const loadDwgPreview = async () => {
  try {
    dwgPreview.value = await parseApi.getDwgPreview(fileId)
  } catch (error: any) {
    dwgPreview.value = null
    ElMessage.warning(error.message || '图纸底图预览加载失败')
  }
}

const runLegendCount = async (item: LegendDiscoveryItem) => {
  legendCountingKey.value = item.normalized_name
  try {
    const result = await parseApi.countLegend(fileId, item.normalized_name, enableLlm.value)
    legendCounts.value = {
      ...legendCounts.value,
      [item.normalized_name]: result
    }
  } catch (error: any) {
    ElMessage.error(error.message || '图例统计失败')
  } finally {
    legendCountingKey.value = ''
  }
}

const openLegendDetail = (item: LegendDiscoveryItem) => {
  activeLegendName.value = item.normalized_name
  activeLegendHandle.value = ''
  legendViewMode.value = 'focus'
  legendZoom.value = 1
  legendPanX.value = 0
  legendPanY.value = 0
  legendDetailVisible.value = true
}

const activeLegendCount = computed(() => {
  if (!activeLegendName.value) {
    return null
  }
  return legendCounts.value[activeLegendName.value] || null
})

const centerLegendPoint = async (handle: string, autoZoom = false) => {
  if (autoZoom && legendZoom.value <= 1) {
    legendZoom.value = 1.4
  }

  await nextTick()

  if (!legendPlot.value) {
    return
  }

  const point = legendPlot.value.points.find((item) => item.handle === handle)
  if (!point) {
    return
  }

  const viewWidth = legendPlot.value.width / legendZoom.value
  const viewHeight = legendPlot.value.height / legendZoom.value
  const maxPanX = Math.max(legendPlot.value.width - viewWidth, 0)
  const maxPanY = Math.max(legendPlot.value.height - viewHeight, 0)

  legendPanX.value = Math.min(Math.max(point.px - viewWidth / 2, 0), maxPanX)
  legendPanY.value = Math.min(Math.max(point.py - viewHeight / 2, 0), maxPanY)
}

const focusLegendPoint = async (handle: string) => {
  activeLegendHandle.value = handle
  await centerLegendPoint(handle, true)
}

const clearLegendFocus = () => {
  activeLegendHandle.value = ''
}

const legendPlot = computed(() => {
  if (!activeLegendCount.value) {
    return null
  }

  const points = [
    ...activeLegendCount.value.matches.map((item) => ({
      ...item,
      category: '保留' as const,
      excludedIndex: null as number | null
    })),
    ...activeLegendCount.value.excluded_matches.map((item, index) => ({
      ...item,
      category: '排除' as const,
      excludedIndex: index + 1
    }))
  ].filter((item) => {
    if (item.category === '保留' && !legendShowKeep.value) return false
    if (item.category === '排除' && !legendShowExclude.value) return false
    return true
  })

  if (!points.length) {
    return null
  }

  const minX = Math.min(...points.map((item) => item.x))
  const maxX = Math.max(...points.map((item) => item.x))
  const minY = Math.min(...points.map((item) => item.y))
  const maxY = Math.max(...points.map((item) => item.y))
  const previewBounds = dwgPreview.value?.bounds
  const pointSpanX = Math.max(maxX - minX, 1)
  const pointSpanY = Math.max(maxY - minY, 1)
  const focusPaddingX = Math.max(pointSpanX * 0.18, 6000)
  const focusPaddingY = Math.max(pointSpanY * 0.18, 6000)
  const focusMinX = minX - focusPaddingX
  const focusMaxX = maxX + focusPaddingX
  const focusMinY = minY - focusPaddingY
  const focusMaxY = maxY + focusPaddingY
  const plotMinX = legendViewMode.value === 'full' && previewBounds
    ? previewBounds.min_x
    : (previewBounds ? Math.max(previewBounds.min_x, focusMinX) : focusMinX)
  const plotMaxX = legendViewMode.value === 'full' && previewBounds
    ? previewBounds.max_x
    : (previewBounds ? Math.min(previewBounds.max_x, focusMaxX) : focusMaxX)
  const plotMinY = legendViewMode.value === 'full' && previewBounds
    ? previewBounds.min_y
    : (previewBounds ? Math.max(previewBounds.min_y, focusMinY) : focusMinY)
  const plotMaxY = legendViewMode.value === 'full' && previewBounds
    ? previewBounds.max_y
    : (previewBounds ? Math.min(previewBounds.max_y, focusMaxY) : focusMaxY)
  const width = 860
  const height = 420
  const padding = 36
  const spanX = Math.max(plotMaxX - plotMinX, 1)
  const spanY = Math.max(plotMaxY - plotMinY, 1)
  const scaleX = (x: number) => padding + ((x - plotMinX) / spanX) * (width - padding * 2)
  const scaleY = (y: number) => height - padding - ((y - plotMinY) / spanY) * (height - padding * 2)

  const scaledPoints = points.map((item) => {
    const px = scaleX(item.x)
    const py = scaleY(item.y)
    return {
      ...item,
      px,
      py,
      color: item.category === '保留' ? '#2f9e44' : '#d9480f',
      focused: activeLegendHandle.value === item.handle
    }
  })
  const focusedPoint = scaledPoints.find((item) => item.focused) || null
  const gridLinesX = Array.from({ length: 5 }, (_, index) => padding + (index / 4) * (width - padding * 2))
  const gridLinesY = Array.from({ length: 5 }, (_, index) => padding + (index / 4) * (height - padding * 2))

  const previewEntities = (dwgPreview.value?.entities || [])
    .map((entity, index) => {
      if (entity.type === 'LINE' && entity.start && entity.end) {
        return {
          key: `line-${index}`,
          type: 'LINE' as const,
          x1: scaleX(entity.start.x),
          y1: scaleY(entity.start.y),
          x2: scaleX(entity.end.x),
          y2: scaleY(entity.end.y)
        }
      }
      if (entity.type === 'POLYLINE' && entity.vertices?.length) {
        const path = entity.vertices
          .map((vertex, vertexIndex) => `${vertexIndex === 0 ? 'M' : 'L'} ${scaleX(vertex.x)} ${scaleY(vertex.y)}`)
          .join(' ')
        return {
          key: `polyline-${index}`,
          type: 'POLYLINE' as const,
          path: entity.closed ? `${path} Z` : path
        }
      }
      if (entity.type === 'CIRCLE' && entity.center && entity.radius) {
        const rx = (entity.radius / spanX) * (width - padding * 2)
        const ry = (entity.radius / spanY) * (height - padding * 2)
        return {
          key: `circle-${index}`,
          type: 'CIRCLE' as const,
          cx: scaleX(entity.center.x),
          cy: scaleY(entity.center.y),
          r: Math.max(1.5, Math.min(rx, ry))
        }
      }
      if (entity.type === 'ARC' && entity.center && entity.radius !== undefined) {
        const startAngle = ((entity.start_angle ?? 0) * Math.PI) / 180
        const endAngle = ((entity.end_angle ?? 0) * Math.PI) / 180
        const start = {
          x: entity.center.x + entity.radius * Math.cos(startAngle),
          y: entity.center.y + entity.radius * Math.sin(startAngle)
        }
        const end = {
          x: entity.center.x + entity.radius * Math.cos(endAngle),
          y: entity.center.y + entity.radius * Math.sin(endAngle)
        }
        const rx = Math.max(1.5, (entity.radius / spanX) * (width - padding * 2))
        const ry = Math.max(1.5, (entity.radius / spanY) * (height - padding * 2))
        const delta = ((((entity.end_angle ?? 0) - (entity.start_angle ?? 0)) % 360) + 360) % 360
        const largeArcFlag = delta > 180 ? 1 : 0
        const sweepFlag = delta > 0 ? 0 : 1
        return {
          key: `arc-${index}`,
          type: 'ARC' as const,
          path: `M ${scaleX(start.x)} ${scaleY(start.y)} A ${rx} ${ry} 0 ${largeArcFlag} ${sweepFlag} ${scaleX(end.x)} ${scaleY(end.y)}`
        }
      }
      if (entity.type === 'TEXT' && entity.insert && entity.content) {
        const fontSize = Math.max(
          8,
          Math.min(
            18,
            ((Math.max(entity.height || 0, 1) / spanY) * (height - padding * 2)) * 2.4
          )
        )
        return {
          key: `text-${index}`,
          type: 'TEXT' as const,
          x: scaleX(entity.insert.x),
          y: scaleY(entity.insert.y),
          content: entity.content,
          fontSize,
          rotation: -(entity.rotation || 0)
        }
      }
      return null
    })
    .filter(Boolean)

  return {
    width,
    height,
    padding,
    minX: plotMinX,
    maxX: plotMaxX,
    minY: plotMinY,
    maxY: plotMaxY,
    points: scaledPoints,
    previewEntities,
    focusedPoint,
    gridLinesX,
    gridLinesY
  }
})

const legendViewBox = computed(() => {
  if (!legendPlot.value) {
    return null
  }

  const viewWidth = legendPlot.value.width / legendZoom.value
  const viewHeight = legendPlot.value.height / legendZoom.value
  const maxPanX = Math.max(legendPlot.value.width - viewWidth, 0)
  const maxPanY = Math.max(legendPlot.value.height - viewHeight, 0)
  const x = Math.min(Math.max(legendPanX.value, 0), maxPanX)
  const y = Math.min(Math.max(legendPanY.value, 0), maxPanY)

  return { x, y, width: viewWidth, height: viewHeight }
})

const zoomInLegendPlot = () => {
  legendZoom.value = Math.min(legendZoom.value + 0.25, 3)
}

const zoomOutLegendPlot = () => {
  legendZoom.value = Math.max(legendZoom.value - 0.25, 0.75)
  if (legendZoom.value <= 1) {
    legendPanX.value = 0
    legendPanY.value = 0
  }
}

const resetLegendPlotZoom = () => {
  legendZoom.value = 1
  legendPanX.value = 0
  legendPanY.value = 0
}

const handleLegendWheel = (event: WheelEvent) => {
  event.preventDefault()

  const nextZoom = event.deltaY < 0
    ? Math.min(legendZoom.value + 0.1, 3)
    : Math.max(legendZoom.value - 0.1, 0.75)

  if (nextZoom === legendZoom.value) {
    return
  }

  if (nextZoom <= 1) {
    legendZoom.value = nextZoom
    legendPanX.value = 0
    legendPanY.value = 0
    return
  }

  legendZoom.value = Number(nextZoom.toFixed(2))
}

const startLegendDrag = (event: PointerEvent) => {
  if (legendZoom.value <= 1) {
    return
  }

  legendPlotViewport.value?.setPointerCapture?.(event.pointerId)
  legendDragState.value = {
    active: true,
    pointerX: event.clientX,
    pointerY: event.clientY,
    startPanX: legendPanX.value,
    startPanY: legendPanY.value
  }
}

const moveLegendDrag = (event: PointerEvent) => {
  if (!legendDragState.value.active || !legendPlotViewport.value || !legendPlot.value || !legendViewBox.value) {
    return
  }

  const rect = legendPlotViewport.value.getBoundingClientRect()
  const deltaX = event.clientX - legendDragState.value.pointerX
  const deltaY = event.clientY - legendDragState.value.pointerY
  const scaleX = legendViewBox.value.width / rect.width
  const scaleY = legendViewBox.value.height / rect.height

  legendPanX.value = legendDragState.value.startPanX - deltaX * scaleX
  legendPanY.value = legendDragState.value.startPanY - deltaY * scaleY
}

const endLegendDrag = () => {
  if (!legendDragState.value.active) {
    return
  }

  legendDragState.value.active = false
}

watch([legendViewMode, legendShowKeep, legendShowExclude], async () => {
  if (!activeLegendHandle.value) {
    return
  }
  await centerLegendPoint(activeLegendHandle.value)
})

const exportLegendDetailCsv = () => {
  if (!activeLegendCount.value || !activeLegendName.value) {
    ElMessage.warning('请先执行统计数量')
    return
  }

  const rows = [
    ['设备名称', '分类', '句柄', 'X', 'Y', '图层', '原因']
  ]

  activeLegendCount.value.matches.forEach((item) => {
    rows.push([
      activeLegendName.value,
      '保留',
      item.handle,
      String(item.x),
      String(item.y),
      item.layer,
      item.reason
    ])
  })

  activeLegendCount.value.excluded_matches.forEach((item) => {
    rows.push([
      activeLegendName.value,
      '排除',
      item.handle,
      String(item.x),
      String(item.y),
      item.layer,
      item.reason
    ])
  })

  const csvContent = rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob([`\uFEFF${csvContent}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${activeLegendName.value}-统计明细.csv`
  link.click()
  URL.revokeObjectURL(url)
}

const pollTaskResult = async (taskId: string) => {
  const status = await tasksApi.getTaskStatus(taskId)
  taskStatus.value = status

  if (status.ready) {
    if (status.successful) {
      reviewResult.value = await tasksApi.getTaskResult(taskId)
      await loadDwgPreview()
      await loadLegendItems()
      loading.value = false
      clearPollTimer()
      return
    }

    loading.value = false
    clearPollTimer()
    throw new Error(status.error || '异步审核失败')
  }

  pollTimer = window.setTimeout(() => {
    void pollTaskResult(taskId).catch((error: Error) => {
      loading.value = false
      ElMessage.error(error.message || '获取任务状态失败')
    })
  }, 1000)
}

const fetchReview = async () => {
  loading.value = true
  reviewResult.value = null
  taskStatus.value = null
  clearPollTimer()

  try {
    if (!preferAsyncReview) {
      await fetchReviewSync()
      await loadDwgPreview()
      await loadLegendItems()
      loading.value = false
      return
    }

    const fileInfo = await uploadApi.getFileInfo(fileId)
    const task = await tasksApi.createTask({
      dwg_file_id: fileId,
      enable_llm: enableLlm.value,
      large_file: (fileInfo.file_size || 0) >= LARGE_FILE_THRESHOLD
    })
    taskStatus.value = task
    await pollTaskResult(task.task_id)
  } catch (error: any) {
    try {
      if (preferAsyncReview) {
        ElMessage.warning('异步审核不可用，已回退到同步审核')
      }
      await fetchReviewSync()
      await loadDwgPreview()
      await loadLegendItems()
    } catch (syncError: any) {
      ElMessage.error(syncError.message || error.message || '审核失败')
    } finally {
      loading.value = false
    }
  }
}

const getSeverityType = (severity: string) => {
  const types: Record<string, string> = {
    error: 'danger',
    warning: 'warning',
    info: 'info'
  }
  return types[severity] || 'info'
}

onMounted(() => {
  fetchReview()
})

onBeforeUnmount(() => {
  clearPollTimer()
})
</script>

<template>
  <div class="review-view">
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
      <p>正在审核中，请稍候...</p>
      <p class="loading-stage">{{ progressStage }}</p>
      <p class="loading-message">{{ progressMessage }}</p>
      <el-progress
        v-if="taskStatus"
        class="loading-progress"
        :percentage="progressPercent"
        :stroke-width="10"
      />
    </div>

    <template v-else-if="reviewResult">
      <el-card class="overview-card">
        <div class="overview-content compact">
          <div class="overview-main">
            <div class="overview-title-row">
              <span class="overview-title">设备统计与复核</span>
              <el-tag
                :type="reviewResult.assessment === '通过' ? 'success' : reviewResult.assessment === '不通过' ? 'danger' : 'warning'"
                size="large"
              >
                {{ reviewResult.assessment }}
              </el-tag>
            </div>
            <p class="overview-description">
              当前页面最有价值的是“本图可识别设备”“统计数量”和“查看明细”。
              顶部结论仅表示基础规则检查结果，不代表完整专业审图评分。
            </p>
          </div>
          <div class="stats-section compact">
            <div class="stat-item">
              <span class="stat-value">{{ legendItems.length }}</span>
              <span class="stat-label">识别设备</span>
            </div>
            <div class="stat-item">
              <span class="stat-value warning">{{ warningCount }}</span>
              <span class="stat-label">规则警告</span>
            </div>
            <div class="stat-item">
              <span class="stat-value info">{{ infoCount }}</span>
              <span class="stat-label">规则提示</span>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="legend-card">
        <template #header>
          <div class="card-header">
            <div class="card-title-group">
              <span>本图可识别设备</span>
              <span class="card-subtitle">先看这里，再点“统计数量”确认真实数量</span>
            </div>
            <el-tag type="info" size="small">{{ legendItems.length }} 项</el-tag>
          </div>
        </template>

        <el-table
          v-loading="legendLoading"
          :data="legendItems"
          stripe
          size="small"
          max-height="360"
          empty-text="暂未识别到可用图例设备"
        >
          <el-table-column prop="normalized_name" label="设备名称" min-width="220" />
          <el-table-column prop="block_name" label="候选块" min-width="180" />
          <el-table-column label="初步识别" width="140">
            <template #default="{ row }">
              <span class="soft-value">{{ row.estimated_actual_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="精确统计" width="220">
            <template #default="{ row }">
              <div class="legend-count-cell">
                <span v-if="legendCounts[row.normalized_name]">
                  {{ legendCounts[row.normalized_name].actual_count }} / {{ legendCounts[row.normalized_name].total_matches }}
                </span>
                <span v-else class="legend-count-placeholder">未统计</span>
                <el-button
                  link
                  type="primary"
                  :loading="legendCountingKey === row.normalized_name"
                  @click="runLegendCount(row)"
                >
                  统计数量
                </el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="证据" width="100">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="!legendCounts[row.normalized_name]"
                @click="openLegendDetail(row)"
              >
                查看明细
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

    </template>

    <el-dialog
      v-model="legendDetailVisible"
      :title="activeLegendName ? `${activeLegendName} 统计明细` : '统计明细'"
      width="960px"
      @closed="clearLegendFocus"
    >
      <template #header="{ titleId, titleClass }">
        <div class="legend-detail-header">
          <span :id="titleId" :class="titleClass">
            {{ activeLegendName ? `${activeLegendName} 统计明细` : '统计明细' }}
          </span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="!activeLegendCount"
            @click="exportLegendDetailCsv"
          >
            导出 CSV
          </el-button>
        </div>
      </template>
      <template v-if="activeLegendCount">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="legend-detail-alert"
        >
          <template #title>
            {{ activeLegendCount.explanation }}
          </template>
        </el-alert>

        <el-row :gutter="16" class="legend-detail-stats">
          <el-col :span="8">
            <div class="stat-box">
              <div class="stat-value">{{ activeLegendCount.actual_count }}</div>
              <div class="stat-label">主图保留</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-box">
              <div class="stat-value">{{ activeLegendCount.excluded_as_legend }}</div>
              <div class="stat-label">排除样例</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-box">
              <div class="stat-value">{{ activeLegendCount.total_matches }}</div>
              <div class="stat-label">总命中</div>
            </div>
          </el-col>
        </el-row>

        <div class="section-title">点位分布图</div>
        <div v-if="legendPlot" class="legend-plot-wrap">
          <div class="legend-plot-legend">
            <button
              type="button"
              class="legend-toggle"
              :class="{ active: legendShowKeep }"
              @click="legendShowKeep = !legendShowKeep"
            >
              <span class="legend-badge keep"></span>
              <span>保留点 {{ activeLegendCount.matches.length }}</span>
            </button>
            <button
              type="button"
              class="legend-toggle"
              :class="{ active: legendShowExclude }"
              @click="legendShowExclude = !legendShowExclude"
            >
              <span class="legend-badge exclude"></span>
              <span>排除点 {{ activeLegendCount.excluded_matches.length }}</span>
            </button>
            <el-segmented
              v-model="legendViewMode"
              class="legend-view-mode"
              :options="[
                { label: '聚焦当前设备', value: 'focus' },
                { label: '查看全图', value: 'full' }
              ]"
            />
            <div class="legend-zoom-controls">
              <el-button size="small" @click="zoomOutLegendPlot">缩小</el-button>
              <span class="legend-zoom-value">{{ Math.round(legendZoom * 100) }}%</span>
              <el-button size="small" @click="resetLegendPlotZoom">重置</el-button>
              <el-button size="small" @click="zoomInLegendPlot">放大</el-button>
            </div>
          </div>
          <div
            ref="legendPlotViewport"
            class="legend-plot-scroll"
            :class="{ pannable: legendZoom > 1, dragging: legendDragState.active }"
            @wheel.prevent="handleLegendWheel"
            @pointerdown="startLegendDrag"
            @pointermove="moveLegendDrag"
            @pointerup="endLegendDrag"
            @pointerleave="endLegendDrag"
            @pointercancel="endLegendDrag"
          >
            <svg
              v-if="legendViewBox"
              :viewBox="`${legendViewBox.x} ${legendViewBox.y} ${legendViewBox.width} ${legendViewBox.height}`"
              :width="legendPlot.width"
              :height="legendPlot.height"
              class="legend-plot"
              role="img"
              aria-label="图例统计点位分布"
            >
              <rect
                x="0"
                y="0"
                :width="legendPlot.width"
                :height="legendPlot.height"
                rx="12"
                class="legend-plot-bg"
              />
              <line
                v-for="lineX in legendPlot.gridLinesX"
                :key="`grid-x-${lineX}`"
                :x1="lineX"
                y1="24"
                :x2="lineX"
                :y2="legendPlot.height - 24"
                class="legend-grid"
                vector-effect="non-scaling-stroke"
              />
              <line
                v-for="lineY in legendPlot.gridLinesY"
                :key="`grid-y-${lineY}`"
                x1="24"
                :y1="lineY"
                :x2="legendPlot.width - 24"
                :y2="lineY"
                class="legend-grid"
                vector-effect="non-scaling-stroke"
              />
              <line
                :x1="legendPlot.padding"
                :y1="legendPlot.height - legendPlot.padding"
                :x2="legendPlot.width - legendPlot.padding"
                :y2="legendPlot.height - legendPlot.padding"
                class="legend-axis"
                vector-effect="non-scaling-stroke"
              />
              <line
                :x1="legendPlot.padding"
                :y1="legendPlot.padding"
                :x2="legendPlot.padding"
                :y2="legendPlot.height - legendPlot.padding"
                class="legend-axis"
                vector-effect="non-scaling-stroke"
              />
              <template v-for="entity in legendPlot.previewEntities" :key="entity.key">
                <line
                  v-if="entity.type === 'LINE'"
                  :x1="entity.x1"
                  :y1="entity.y1"
                  :x2="entity.x2"
                  :y2="entity.y2"
                  class="legend-preview-line"
                  vector-effect="non-scaling-stroke"
                />
                <path
                  v-else-if="entity.type === 'POLYLINE'"
                  :d="entity.path"
                  class="legend-preview-line"
                  vector-effect="non-scaling-stroke"
                />
                <path
                  v-else-if="entity.type === 'ARC'"
                  :d="entity.path"
                  class="legend-preview-line"
                  vector-effect="non-scaling-stroke"
                />
                <circle
                  v-else-if="entity.type === 'CIRCLE'"
                  :cx="entity.cx"
                  :cy="entity.cy"
                  :r="entity.r"
                  class="legend-preview-circle"
                  vector-effect="non-scaling-stroke"
                />
                <text
                  v-else-if="entity.type === 'TEXT'"
                  :x="entity.x"
                  :y="entity.y"
                  class="legend-preview-text"
                  :style="{ fontSize: `${entity.fontSize}px` }"
                  :transform="entity.rotation ? `rotate(${entity.rotation} ${entity.x} ${entity.y})` : undefined"
                >
                  {{ entity.content }}
                </text>
              </template>
              <template v-if="legendPlot.focusedPoint">
                <line
                  :x1="legendPlot.focusedPoint.px"
                  y1="24"
                  :x2="legendPlot.focusedPoint.px"
                  :y2="legendPlot.height - 24"
                  class="legend-focus-line"
                  vector-effect="non-scaling-stroke"
                />
                <line
                  x1="24"
                  :y1="legendPlot.focusedPoint.py"
                  :x2="legendPlot.width - 24"
                  :y2="legendPlot.focusedPoint.py"
                  class="legend-focus-line"
                  vector-effect="non-scaling-stroke"
                />
              </template>
              <g
                v-for="point in legendPlot.points"
                :key="`${point.category}-${point.handle}`"
                class="legend-point-group"
                @click="focusLegendPoint(point.handle)"
              >
                <circle
                  :cx="point.px"
                  :cy="point.py"
                  :r="(point.focused ? 10 : 5.8) / legendZoom"
                  :fill="point.color"
                  :stroke="point.focused ? '#1f2937' : point.category === '保留' ? '#1b5e20' : '#7f2704'"
                  :stroke-width="(point.focused ? 2.4 : 1.2) / legendZoom"
                  class="legend-point"
                  vector-effect="non-scaling-stroke"
                >
                  <title>
                    {{ point.category }} | {{ point.handle }} | ({{ point.x.toFixed(1) }}, {{ point.y.toFixed(1) }}) | {{ point.reason }}
                  </title>
                </circle>
                <text
                  v-if="point.category === '排除' && point.excludedIndex"
                  :x="point.px"
                  :y="point.py + (1 / legendZoom)"
                  class="legend-point-index"
                  :style="{ fontSize: `${10 / legendZoom}px` }"
                >
                  {{ point.excludedIndex }}
                </text>
              </g>
              <circle
                v-if="legendPlot.focusedPoint"
                :cx="legendPlot.focusedPoint.px"
                :cy="legendPlot.focusedPoint.py"
                :r="16 / legendZoom"
                class="legend-focus-ring"
                vector-effect="non-scaling-stroke"
              />
              <text
                v-if="legendPlot.focusedPoint"
                :x="Math.min(legendPlot.width - (180 / legendZoom), legendPlot.focusedPoint.px + (14 / legendZoom))"
                :y="Math.max(22 / legendZoom, legendPlot.focusedPoint.py - (14 / legendZoom))"
                class="legend-focus-label"
                :style="{ fontSize: `${12 / legendZoom}px` }"
              >
                {{ legendPlot.focusedPoint.handle }} | {{ legendPlot.focusedPoint.reason }}
              </text>
              <text :x="legendPlot.padding" y="18" class="legend-axis-text">
                Y max {{ legendPlot.maxY.toFixed(0) }}
              </text>
              <text :x="legendPlot.padding" :y="legendPlot.height - 8" class="legend-axis-text">
                X min {{ legendPlot.minX.toFixed(0) }}
              </text>
              <text :x="legendPlot.width - 150" :y="legendPlot.height - 8" class="legend-axis-text">
                X max {{ legendPlot.maxX.toFixed(0) }}
              </text>
            </svg>
          </div>
          <div class="legend-plot-tip">悬停点位可查看句柄、坐标和原因。</div>
        </div>

        <div class="section-title">保留点</div>
        <el-table
          :data="activeLegendCount.matches"
          stripe
          size="small"
          max-height="260"
          row-key="handle"
          :row-class-name="({ row }) => row.handle === activeLegendHandle ? 'legend-active-row' : ''"
          @row-click="({ handle }) => focusLegendPoint(handle)"
        >
          <el-table-column prop="handle" label="句柄" width="100" />
          <el-table-column label="坐标" min-width="180">
            <template #default="{ row }">
              ({{ row.x.toFixed(1) }}, {{ row.y.toFixed(1) }})
            </template>
          </el-table-column>
          <el-table-column prop="layer" label="图层" min-width="120" />
          <el-table-column prop="reason" label="原因" min-width="180" />
        </el-table>

        <div class="section-title">排除点</div>
        <el-table
          :data="activeLegendCount.excluded_matches"
          stripe
          size="small"
          max-height="260"
          row-key="handle"
          :row-class-name="({ row }) => row.handle === activeLegendHandle ? 'legend-active-row' : ''"
          @row-click="({ handle }) => focusLegendPoint(handle)"
        >
          <el-table-column prop="handle" label="句柄" width="100" />
          <el-table-column label="坐标" min-width="180">
            <template #default="{ row }">
              ({{ row.x.toFixed(1) }}, {{ row.y.toFixed(1) }})
            </template>
          </el-table-column>
          <el-table-column prop="layer" label="图层" min-width="120" />
          <el-table-column prop="reason" label="排除原因" min-width="240" />
        </el-table>
      </template>
      <template v-else>
        <el-empty description="请先执行统计数量" />
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.review-view {
  max-width: 1200px;
  margin: 0 auto;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: #909399;
}

.loading-container p {
  margin-top: 16px;
}

.loading-stage {
  color: #303133;
  font-weight: 500;
}

.loading-message {
  max-width: 420px;
  text-align: center;
}

.loading-progress {
  width: 320px;
  margin-top: 16px;
}

.legend-detail-alert {
  margin-bottom: 16px;
}

.legend-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.legend-detail-stats {
  margin-bottom: 20px;
}

.legend-plot-wrap {
  margin-bottom: 20px;
}

.legend-plot-legend {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  color: #606266;
  font-size: 13px;
  flex-wrap: wrap;
}

.legend-badge {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.legend-badge.keep {
  background: #2f9e44;
}

.legend-badge.exclude {
  background: #d9480f;
}

.legend-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 999px;
  background: #fff;
  color: #606266;
  cursor: pointer;
  transition: all 0.15s ease;
}

.legend-toggle.active {
  border-color: #409eff;
  background: #ecf5ff;
  color: #303133;
}

.legend-view-mode {
  margin-left: auto;
}

.legend-zoom-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-zoom-value {
  min-width: 48px;
  text-align: center;
  font-size: 12px;
  color: #606266;
}

.legend-plot-scroll {
  overflow: hidden;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fff;
  touch-action: none;
  user-select: none;
  cursor: default;
}

.legend-plot-scroll.pannable {
  cursor: grab;
}

.legend-plot-scroll.dragging {
  cursor: grabbing;
}

.legend-plot {
  display: block;
}

.legend-plot-bg {
  fill: #fcfcfd;
  stroke: #dcdfe6;
  stroke-width: 1;
}

.legend-grid {
  stroke: #eef2f7;
  stroke-width: 1;
}

.legend-axis {
  stroke: #c0c4cc;
  stroke-width: 1;
}

.legend-preview-line {
  fill: none;
  stroke: #cfd8e3;
  stroke-width: 1.05;
  opacity: 0.9;
}

.legend-preview-circle {
  fill: none;
  stroke: #cfd8e3;
  stroke-width: 1.05;
  opacity: 0.9;
}

.legend-preview-text {
  fill: #94a3b8;
  opacity: 0.92;
  dominant-baseline: middle;
  pointer-events: none;
}

.legend-axis-text {
  fill: #909399;
  font-size: 11px;
}

.legend-focus-line {
  stroke: #94a3b8;
  stroke-width: 1;
  stroke-dasharray: 4 4;
}

.legend-focus-ring {
  fill: none;
  stroke: rgba(31, 41, 55, 0.24);
  stroke-width: 2;
}

.legend-focus-label {
  fill: #1f2937;
  font-size: 12px;
  font-weight: 600;
}

.legend-plot-tip {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}

.legend-point {
  cursor: pointer;
  transition: r 0.15s ease, stroke-width 0.15s ease, opacity 0.15s ease;
}

.legend-point-group {
  cursor: pointer;
}

.legend-point-index {
  fill: #ffffff;
  font-size: 10px;
  font-weight: 700;
  text-anchor: middle;
  dominant-baseline: middle;
  pointer-events: none;
}

:deep(.legend-active-row) {
  --el-table-tr-bg-color: #ecf5ff;
}

.overview-card {
  margin-bottom: 24px;
}

.legend-card {
  margin-bottom: 24px;
}

.overview-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.overview-content.compact {
  gap: 24px;
}

.overview-main {
  flex: 1;
}

.overview-title-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
}

.overview-title {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.overview-description {
  margin: 0;
  max-width: 760px;
  color: #606266;
  line-height: 1.7;
}

.stats-section {
  display: flex;
  gap: 48px;
}

.stats-section.compact {
  gap: 28px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
}

.stat-value.error {
  color: #f56c6c;
}

.stat-value.warning {
  color: #e6a23c;
}

.legend-count-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.legend-count-placeholder {
  color: #909399;
}

.soft-value {
  color: #909399;
}

.stat-value.info {
  color: #909399;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.issues-card,
.dwg-card {
  margin-bottom: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-subtitle {
  font-size: 12px;
  color: #909399;
}

.issues-summary-alert {
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 20px 0 12px 0;
  padding-left: 8px;
  border-left: 4px solid #409eff;
}

.subsection-title {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  margin: 16px 0 8px 0;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-box {
  text-align: center;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.stat-box .stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #409eff;
}

.stat-box .stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.door-window-section {
  margin: 20px 0;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}
</style>
