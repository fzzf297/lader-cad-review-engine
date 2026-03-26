<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Document } from '@element-plus/icons-vue'
import { reviewApi } from '@/api/review'
import type { ReviewRecord, ReviewResponse, StatisticsResponse } from '@/types/api'

// 状态
const loading = ref(false)
const records = ref<ReviewRecord[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const statistics = ref<StatisticsResponse | null>(null)

// 筛选条件
const filterAssessment = ref('')
const filterDrawingType = ref('')

// 选中的记录
const selectedRecord = ref<ReviewRecord | null>(null)
const selectedDetail = ref<ReviewResponse | null>(null)
const detailDialogVisible = ref(false)
const detailLoading = ref(false)

// 获取历史记录列表
async function fetchHistory() {
  loading.value = true
  try {
    const response = await reviewApi.getHistoryList({
      page: currentPage.value,
      page_size: pageSize.value,
      assessment: filterAssessment.value || undefined,
      file_type: filterDrawingType.value || undefined
    })
    records.value = response.records
    total.value = response.total
  } catch (error: any) {
    ElMessage.error(error.message || '获取历史记录失败')
  } finally {
    loading.value = false
  }
}

// 获取统计信息
async function fetchStatistics() {
  try {
    statistics.value = await reviewApi.getStatistics()
  } catch (error) {
    console.error('获取统计信息失败', error)
  }
}

// 查看详情
async function viewDetail(record: ReviewRecord) {
  selectedRecord.value = record
  selectedDetail.value = null
  detailLoading.value = true
  detailDialogVisible.value = true
  try {
    selectedDetail.value = await reviewApi.getHistoryDetail(record.record_id)
  } catch (error: any) {
    ElMessage.error(error.message || '获取解析详情失败')
  } finally {
    detailLoading.value = false
  }
}

// 删除记录
async function deleteRecord(record: ReviewRecord) {
  try {
    await ElMessageBox.confirm(
      `确定要删除记录「${record.file_name}」吗？`,
      '确认删除',
      { type: 'warning' }
    )
    await reviewApi.deleteHistory(record.record_id)
    ElMessage.success('删除成功')
    fetchHistory()
    fetchStatistics()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

// 下载报告
function downloadReport(recordId: string, format: 'json' | 'pdf') {
  const url = format === 'json'
    ? reviewApi.getReportJsonUrl(recordId)
    : reviewApi.getReportPdfUrl(recordId)
  window.open(url, '_blank')
}

// 格式化日期
function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString('zh-CN')
}

// 评分颜色
function getScoreColor(score: number) {
  if (score >= 80) return '#67C23A'
  if (score >= 60) return '#E6A23C'
  return '#F56C6C'
}

// 评估标签类型
function getAssessmentType(assessment: string) {
  switch (assessment) {
    case '通过': return 'success'
    case '需修改': return 'warning'
    case '不通过': return 'danger'
    default: return 'info'
  }
}

// 分页变化
function handlePageChange(page: number) {
  currentPage.value = page
  fetchHistory()
}

// 每页数量变化
function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  fetchHistory()
}

// 筛选变化
function handleFilterChange() {
  currentPage.value = 1
  fetchHistory()
}

// 初始化
onMounted(() => {
  fetchHistory()
  fetchStatistics()
})
</script>

<template>
  <div class="history-view">
    <h2>解析历史</h2>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row" v-if="statistics">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ statistics.total_reviews }}</div>
          <div class="stat-label">总解析次数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ statistics.avg_score.toFixed(1) }}</div>
          <div class="stat-label">平均评分</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card success">
          <div class="stat-value">{{ statistics.by_assessment['通过'] || 0 }}</div>
          <div class="stat-label">通过数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card warning">
          <div class="stat-value">{{ statistics.by_assessment['需修改'] || 0 }}</div>
          <div class="stat-label">需修改</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选条件 -->
    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="检查结论">
          <el-select
            v-model="filterAssessment"
            placeholder="全部"
            clearable
            @change="handleFilterChange"
          >
            <el-option label="通过" value="通过" />
            <el-option label="需修改" value="需修改" />
            <el-option label="不通过" value="不通过" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件类型">
          <el-select
            v-model="filterDrawingType"
            placeholder="全部"
            clearable
            @change="handleFilterChange"
          >
            <el-option label="解析图纸" value="dwg" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 记录列表 -->
    <el-card class="table-card">
      <el-table :data="records" v-loading="loading" stripe>
        <el-table-column prop="file_name" label="文件名" min-width="200">
          <template #default="{ row }">
            <div class="file-name">
              <el-icon><Document /></el-icon>
              <span>{{ row.file_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="解析时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="overall_score" label="评分" width="100" align="center">
          <template #default="{ row }">
            <span class="score" :style="{ color: getScoreColor(row.overall_score) }">
              {{ row.overall_score.toFixed(1) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="assessment" label="结论" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getAssessmentType(row.assessment)" size="small">
              {{ row.assessment }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="issue_count" label="问题数" width="80" align="center">
          <template #default="{ row }">
            <el-badge :value="row.issue_count" :type="row.issue_count > 0 ? 'danger' : 'success'" />
          </template>
        </el-table-column>
        <el-table-column prop="enable_llm" label="LLM" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.enable_llm" type="success" size="small">启用</el-tag>
            <el-tag v-else type="info" size="small">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" @click="viewDetail(row)">详情</el-button>
              <el-dropdown trigger="click">
                <el-button size="small">
                  下载报告 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="downloadReport(row.record_id, 'json')">
                      JSON 格式
                    </el-dropdown-item>
                    <el-dropdown-item @click="downloadReport(row.record_id, 'pdf')">
                      PDF 格式
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" type="danger" @click="deleteRecord(row)">删除</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 详情弹窗 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="解析详情"
      width="80%"
      destroy-on-close
    >
      <div v-loading="detailLoading">
      <template v-if="selectedRecord">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="文件名">{{ selectedRecord.file_name }}</el-descriptions-item>
          <el-descriptions-item label="解析时间">{{ formatDate(selectedRecord.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="评分">
            <span :style="{ color: getScoreColor(selectedRecord.overall_score) }">
              {{ selectedRecord.overall_score.toFixed(1) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="结论">
            <el-tag :type="getAssessmentType(selectedRecord.assessment)">
              {{ selectedRecord.assessment }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="问题数量">{{ selectedRecord.issue_count }}</el-descriptions-item>
          <el-descriptions-item label="LLM 分析">
            {{ selectedRecord.enable_llm ? '已启用' : '未启用' }}
          </el-descriptions-item>
        </el-descriptions>

        <template v-if="selectedDetail">
          <el-table
            v-if="selectedDetail.issues.length"
            :data="selectedDetail.issues"
            stripe
            style="margin-top: 16px;"
          >
            <el-table-column prop="category" label="类别" width="120" />
            <el-table-column prop="severity" label="严重程度" width="100" />
            <el-table-column prop="description" label="问题描述" />
            <el-table-column prop="location" label="位置" width="140" />
            <el-table-column prop="suggestion" label="建议" />
          </el-table>

          <el-empty
            v-else
            description="这条解析记录没有问题项"
            style="margin-top: 16px;"
          />
        </template>
      </template>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="downloadReport(selectedRecord!.record_id, 'pdf')">
          下载 PDF 报告
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.history-view {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.history-view h2 {
  margin-bottom: 24px;
  font-size: 24px;
  font-weight: 600;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 10px 0;
}

.stat-card .stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #409EFF;
}

.stat-card.success .stat-value {
  color: #67C23A;
}

.stat-card.warning .stat-value {
  color: #E6A23C;
}

.stat-card .stat-label {
  color: #909399;
  font-size: 14px;
  margin-top: 8px;
}

.filter-card {
  margin-bottom: 20px;
}

.table-card {
  margin-bottom: 20px;
}

.file-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score {
  font-weight: bold;
  font-size: 16px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
