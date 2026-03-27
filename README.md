# CAD 解析引擎

一个面向单机部署和 Docker 部署的 DXF CAD 解析项目，当前聚焦图纸结构提取、设备识别、基础检查与结果追踪，支持：

- DXF 解析、图纸结构提取、门窗摘要提取
- 设备图例识别与数量复核
- 基于规则引擎的基础检查
- 解析历史、统计、JSON/PDF 报告下载
- 同步解析与异步任务两套入口

## 当前状态

- 后端主路径已收口：上传、解析、历史都使用统一文件注册表
- 文件元数据默认持久化到 `${UPLOAD_DIR}/index.json`
- 解析历史默认落到 `${UPLOAD_DIR}/history/`
- 数据库已接入为主存储优先项；数据库不可用时会回退到 JSON 存储
- 前端结果页默认优先走 `/api/v1/tasks` 异步任务并展示进度

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI + Python 3.10+ |
| 图纸解析 | ezdxf |
| 图纸输入 | DXF |
| 前端框架 | Vue 3 + TypeScript + Vite + Element Plus |
| 数据存储 | PostgreSQL 或 SQLite + 文件系统 + JSON 回退 |
| 异步任务 | Celery + Redis |
| LLM 服务 | OpenAI 兼容接口配置（可选） |

## 项目结构

```text
cad/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # upload/review/tasks/parse
│   │   ├── db/                  # SQLAlchemy 模型与数据库连接
│   │   ├── parsers/             # DXF 解析
│   │   ├── rules/               # 规则引擎
│   │   ├── services/            # review/file_registry/history/database_gateway
│   │   ├── tasks/               # Celery 任务
│   │   └── utils/               # 通用工具
│   ├── migrations/              # Alembic 迁移
│   ├── scripts/                 # 数据导入脚本
│   └── tests/
├── frontend/
│   ├── src/api/
│   ├── src/views/
│   └── src/types/
└── docker-compose.yml
```

## 快速开始

### 本地开发

```bash
# backend
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

当前默认主链路是 DXF 直传解析。

- `POST /api/v1/upload/dwg` 这个接口名称目前保留，但当前只接受 `.dxf`
- `.dwg` 文件会被直接拒绝，避免出现“上传成功但后续解析失败”的误导体验

### Docker

```bash
docker-compose up -d
docker-compose logs -f backend
```

Docker 编排会启动：

- `backend`
- `frontend`
- `postgres`
- `redis`

## 环境变量

后端核心环境变量位于 `backend/.env`，常用项如下：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEBUG` | 是否开启调试 | `false` |
| `DATABASE_URL` | 数据库连接串 | SQLite/本地配置 |
| `REDIS_URL` | Redis 地址 | `redis://localhost:6379/0` |
| `UPLOAD_DIR` | 上传目录 | `./uploads` |
| `LLM_ENABLED` | 是否启用 LLM | `false` |

## 运行方式

### 1. 上传

- `POST /api/v1/upload/dwg`（当前仅接受 `.dxf` 文件）
- `GET /api/v1/upload/list?file_type=dwg`
- `GET /api/v1/upload/{file_id}`

上传后的文件内容会先写入系统临时目录，解析消费后自动删除；文件元数据会写入 `${UPLOAD_DIR}/index.json`。当前版本会直接拒绝 `.dwg` 上传，避免后续解析阶段失败。

### 2. 同步解析

- `POST /api/v1/review`

支持参数：

- `dwg_file_id`
- `enable_llm`
- `rule_codes`

同步解析成功后会写入统一历史存储，并返回：

- `dwg_review`
- `dwg_analysis`
### 3. 异步解析

- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`

前端结果页默认优先创建异步任务并轮询进度；若异步链路不可用，会回退到同步解析。

### 4. 历史与报告

- `GET /api/v1/review/history/list`
- `GET /api/v1/review/history/{record_id}`
- `DELETE /api/v1/review/history/{record_id}`
- `GET /api/v1/review/statistics`
- `GET /api/v1/review/report/{record_id}/json`
- `GET /api/v1/review/report/{record_id}/pdf`

## 数据持久化策略

当前运行时采用“数据库优先，JSON 回退”：

- 上传文件元数据：`${UPLOAD_DIR}/index.json`
- 解析历史索引：`${UPLOAD_DIR}/history/index.json`
- 解析完整结果：`${UPLOAD_DIR}/history/{record_id}.json`
- 数据库可用时，同步写入 `dwg_files`、`review_records`、`review_issues`

### 历史 JSON 回填数据库

```bash
cd backend
python scripts/import_json_to_db.py
```

## 测试

### 后端

```bash
cd backend
pytest
```

当前基线：

```text
111 passed
```

### 前端

```bash
cd frontend
npx tsc --noEmit -p tsconfig.json
```

说明：

- 当前环境下 `npm run type-check` 会因为 `vue-tsc` 与 Node `25.6.1` 的兼容问题崩溃
- 在 Node 20 或 22 LTS 下运行 `npm run type-check` 更可靠
- 本仓库代码层面的 TypeScript 检查已通过 `tsc`

## 参考文档

- [架构概览](docs/architecture/README.md)
