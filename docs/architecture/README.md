# 架构概览

## 运行主线

系统当前有两条审核主线：

1. 同步审核：`/api/v1/review`
2. 异步审核：`/api/v1/tasks`

前端默认优先走异步审核；当异步链路不可用时回退到同步审核。

## 后端核心模块

- `app/api/v1/upload.py`
  - 文件上传、`/upload/list`、文件详情
- `app/api/v1/review.py`
  - 同步审核、历史记录、统计、报告
- `app/api/v1/tasks.py`
  - 异步任务创建、进度查询、结果查询
- `app/services/review_service.py`
  - 图纸审核主编排与结果构建
- `app/services/file_registry.py`
  - 上传文件元数据注册表
- `app/services/history_storage.py`
  - 审核历史统一读写入口
- `app/services/database_gateway.py`
  - 数据库优先读写与 JSON 回退桥接层
- `app/tasks/review_tasks.py`
  - Celery 后台审核任务

## 存储策略

运行时采用“数据库优先，JSON 回退”：

- 文件元数据先写 `index.json`，再尝试同步数据库
- 历史记录先写 `${UPLOAD_DIR}/history/`，再尝试同步数据库
- 数据库不可用时，系统仍可以 JSON 文件模式继续运行

涉及的数据库表：

- `dwg_files`
- `review_records`
- `review_issues`

## 前端页面

- `UploadView.vue`
  - 上传 DXF 文件，进入审核流程
- `ReviewView.vue`
  - 默认发起异步任务，轮询进度，显示审核详情
- `HistoryView.vue`
  - 展示历史记录列表，并读取详情接口

## 关键 API

- `POST /api/v1/upload/dwg`
- `GET /api/v1/upload/list`
- `POST /api/v1/review`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `GET /api/v1/review/history/list`
- `GET /api/v1/review/history/{record_id}`

## 备注

- `rule_codes` 已在同步和异步审核中生效
- `dwg_analysis` 已在成功审核时稳定返回
- Docker 部署仍建议配合 PostgreSQL 与 Redis 使用
- 当前主审核入口是 DXF 直传，`.dwg` 上传会在接口层直接拒绝
