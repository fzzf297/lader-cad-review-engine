# CAD 图纸审核引擎

一个面向单机部署和 Docker 部署的 CAD 图纸审核项目，当前聚焦 DXF 图纸解析与审核，支持：

- DXF 解析、图层/图块/实体统计、门窗摘要提取
- 基于规则引擎的图纸规范审核
- 可选 LLM 增强审核
- 审核历史、统计、JSON/PDF 报告下载
- 同步审核与异步任务审核两套入口

## 当前状态

- 后端主路径已收口：上传、审核、历史都使用统一文件注册表
- 文件元数据默认持久化到 `${UPLOAD_DIR}/index.json`
- 审核历史默认落到 `${UPLOAD_DIR}/history/`
- 数据库已接入为主存储优先项；数据库不可用时会回退到 JSON 存储
- 前端审核页默认优先走 `/api/v1/tasks` 异步任务并展示进度

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI + Python 3.10+ |
| 图纸解析 | ezdxf |
| 图纸输入 | DXF |
| 前端框架 | Vue 3 + TypeScript + Vite + Element Plus |
| 数据存储 | PostgreSQL 或 SQLite + 文件系统 + JSON 回退 |
| 异步任务 | Celery + Redis |
| LLM 服务 | OpenAI 兼容接口配置 |

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
│   │   └── utils/               # DWG 转换等工具
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

当前默认审核链路是 DXF 直传，不依赖本地 DWG 转换器。

- `POST /api/v1/upload/dwg` 这个接口名称目前保留，但当前只接受 `.dxf`
- `.dwg` 文件会被直接拒绝，避免出现“上传成功但审核阶段失败”的误导体验
- 仓库已经不再内置 `LibreDWG` 可执行文件；如果你要做手动 DWG 转 DXF，或后续恢复 DWG 直传能力，需要自行在系统里安装转换器

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

当前 Docker 镜像仍预装 `LibreDWG`，主要用于部署环境兜底和手动转换排查；主审核链路仍建议直接上传 DXF。

## DWG 转换依赖

当前项目的稳定审核入口是 DXF，因此大多数本地开发和联调场景都不需要安装 DWG 转换器。

只有在以下情况才需要本地准备转换器：

- 你要在机器上手动把 `.dwg` 转成 `.dxf`
- 你准备恢复或调试 DWG 直传能力
- 你要排查 Docker 之外的 DWG 转换问题

可选的系统级转换器如下：

1. `ODA File Converter`
   推荐，转换质量通常更好。安装后可通过 `ODA_CONVERTER_PATH` 指定路径。
2. `LibreDWG`
   需要系统里存在 `dwg2dxf` 命令，例如 macOS 上可通过 `brew install libredwg` 安装。

仓库当前不再自带任何本地 `LibreDWG` runtime，因此文档里的“可直接开箱即用 DWG 转换”只适用于 Docker 镜像，不适用于裸机源码目录。

## 环境变量

后端核心环境变量位于 `backend/.env`，常用项如下：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEBUG` | 是否开启调试 | `false` |
| `DATABASE_URL` | 数据库连接串 | SQLite/本地配置 |
| `REDIS_URL` | Redis 地址 | `redis://localhost:6379/0` |
| `UPLOAD_DIR` | 上传目录 | `./uploads` |
| `LLM_ENABLED` | 是否启用 LLM | `false` |
| `DWG_CONVERTER_MODE` | DWG 转换模式，仅在启用 DWG 转换链路时生效 | `local` |
| `ODA_CONVERTER_PATH` | ODA 路径，仅在使用 ODA 转换 DWG 时生效 | `/usr/bin/ODAFileConverter` |

## 运行方式

### 1. 上传

- `POST /api/v1/upload/dwg`（当前仅接受 `.dxf` 文件）
- `GET /api/v1/upload/list?file_type=dwg`
- `GET /api/v1/upload/{file_id}`

上传后的文件内容会先写入系统临时目录，审核消费后自动删除；文件元数据会写入 `${UPLOAD_DIR}/index.json`。当前版本会直接拒绝 `.dwg` 上传，避免后续审核阶段失败。

### 2. 同步审核

- `POST /api/v1/review`

支持参数：

- `dwg_file_id`
- `enable_llm`
- `rule_codes`

同步审核成功后会写入统一历史存储，并返回：

- `dwg_review`
- `dwg_analysis`
### 3. 异步审核

- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`

前端审核页默认优先创建异步任务并轮询进度；若异步链路不可用，会回退到同步审核。

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
- 审核历史索引：`${UPLOAD_DIR}/history/index.json`
- 审核完整结果：`${UPLOAD_DIR}/history/{record_id}.json`
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
