# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DWG 施工图审核系统 - A DWG construction drawing + contract comprehensive review system that supports:
- DWG file parsing and conversion to DXF
- Design element identification (doors, windows, pipes, etc.)
- Compliance review based on GB/T 50001-2017 standard
- Contract analysis and contract-drawing correlation
- Web-based visualization interface

## Development Commands

### Backend (FastAPI + Python 3.10+)

```bash
cd backend

# Install dependencies
pip install -e ".[dev]"

# Run development server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=term-missing

# Run single test file
pytest tests/rules/test_engine.py -v

# Run single test
pytest tests/rules/test_engine.py::test_layer_naming_rule -v
```

### Frontend (Vue 3 + TypeScript + Vite)

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Type check
npm run type-check
```

### Docker

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down
```

## 部署说明

### Docker 部署（推荐）

当前主审核链路是 DXF 直传，Docker 部署无需额外准备 DWG 转换工具：

```bash
# 构建并启动所有服务
docker-compose up -d
```

### 非 Docker 部署

非 Docker 部署同样以 DXF 直传为主，不需要额外安装 DWG 转换工具。

## Architecture

### Backend Structure

```
backend/app/
├── main.py              # FastAPI application entry point
├── core/config.py       # Configuration via environment variables
├── api/v1/              # REST API endpoints
│   ├── upload.py        # File upload (DWG/DXF/DOC/PDF)
│   ├── review.py        # Review API orchestration
│   └── tasks.py         # Async task status
├── parsers/             # File parsing modules
│   ├── dxf_parser.py    # DXF parsing with ezdxf
│   └── contract_parser.py # Word/PDF contract parsing
├── rules/               # Rule engine for GB/T 50001-2017
│   └── engine.py        # Rule definitions and execution
├── llm/                 # LLM integration (Qwen API)
│   └── llm_service.py   # LLM-based review
├── services/            # Business logic
│   ├── review_service.py    # Full review orchestration
│   ├── result_merger.py     # Merge rule + LLM results
│   ├── history_storage.py   # Review history persistence
│   └── report_service.py    # Report generation (JSON/PDF)
├── tasks/               # Celery async tasks
│   └── review_tasks.py  # Background review tasks
├── db/                  # Database models
└── utils/               # Utilities
```

### Frontend Structure

```
frontend/src/
├── main.ts              # Vue application entry
├── App.vue              # Root component
├── router/index.ts      # Vue Router configuration
├── views/               # Page components
│   ├── HomeView.vue     # Landing page
│   ├── UploadView.vue   # File upload interface
│   ├── ReviewView.vue   # Review results display
│   └── HistoryView.vue  # Review history
└── components/          # Reusable components
    └── upload/FileUpload.vue
```

### Key Data Flow

1. **File Upload**: `POST /api/v1/upload/dwg` → 接收 DXF → 写入临时目录并登记元数据
2. **Review**: `POST /api/v1/review` → DXF parsing → Rule engine + LLM → Result merger
3. **Contract Analysis**: Contract parsing → LLM extraction → Work items
4. **Contract-DWG Matching**: Work items ↔ Block statistics → Compliance score

### Rule Engine

The rule engine (`app/rules/engine.py`) implements GB/T 50001-2017 compliance checks:
- `LAYER_001`: Layer naming conventions
- `LINE_001`: Line weight standards
- `TEXT_001`: Text style requirements (min height 2.5mm)
- `BLOCK_001`: Block naming (e.g., M1021 for doors, C1515 for windows)
- `DIM_001`: Dimension style consistency

Rules can be extended by creating a class that inherits from `BaseRule` and registering it with `ReviewEngine`.

### DXF Analysis Best Practices

#### Handling DXF Files with Encoding Issues

When parsing DXF files created by Chinese CAD software (e.g., TCH/天正), encoding issues are common:

1. **File Preprocessing**: Clean the DXF file before parsing to fix encoding errors
   ```python
   # Remove invalid group codes and CRLF issues
   def clean_dxf_file(input_path, output_path):
       with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
           lines = f.readlines()

       result_lines = []
       i = 0
       while i < len(lines):
           code_line = lines[i].strip()
           try:
               int(code_line)  # Valid group code
               result_lines.append(lines[i])
               if i + 1 < len(lines):
                   result_lines.append(lines[i + 1])
               i += 2
           except ValueError:
               i += 1  # Skip invalid lines

       with open(output_path, 'w', encoding='utf-8') as f:
           f.writelines(result_lines)
   ```

2. **Binary Search for Chinese Text**: When text appears garbled, use binary search with GBK encoding
   ```python
   # Search for Chinese keywords in binary mode
   keyword_gbk = '编码感烟火灾探测器'.encode('gbk')
   with open(file_path, 'rb') as f:
       content = f.read()
   count = content.count(keyword_gbk)
   ```

#### Distinguishing Drawing Content from Legend/Symbols

**Critical**: DXF files often contain both actual installed components AND legend table examples. They must be distinguished:

1. **Identify by Coordinate Position**:
   - Calculate the center point of all entities
   - Entities far from the center (e.g., >100,000 units) are likely legend examples
   - Legend tables are often placed outside the main drawing area (e.g., X < -300000)

2. **Analyze Coordinate Distribution**:
   ```python
   # Calculate average position
   avg_x = sum(entity['x'] for entity in entities) / len(entities)
   avg_y = sum(entity['y'] for entity in entities) / len(entities)

   # Find outliers
   for entity in entities:
       distance = ((entity['x'] - avg_x)**2 + (entity['y'] - avg_y)**2)**0.5
       if distance > threshold:  # e.g., 200000
           mark_as_legend_example(entity)
   ```

3. **Common Legend Locations**:
   - **Drawing title block area**: Usually at negative X coordinates (e.g., X ≈ -319477)
   - **Material list table**: Often at extreme Y coordinates (e.g., Y ≈ -278183)
   - **Symbol examples**: Grouped together in a corner, far from actual installation positions

4. **Verification Method**:
   - Compare count after excluding legend examples with contract quantities
   - If discrepancy exists, check for additional legend symbols or design variations
   - Example: 191 total blocks - 7 legend examples = 184 actual (matches contract)

#### Counting Equipment from DXF Files

1. **Use Block References (INSERT entities)**:
   - Each INSERT represents one equipment instance
   - Group by block name to count different equipment types
   - Attributes in INSERT may contain equipment labels/numbers

2. **Extract Equipment Locations**:
   ```python
   inserts = [e for e in result.inserts if e['name'] == '$Equip$00002649']
   for ins in inserts:
       x = ins['insert']['x']
       y = ins['insert']['y']
       layer = ins['layer']  # Identifies system type (fire alarm, etc.)
   ```

3. **Cross-Reference with Contract**:
   - Match block names with equipment descriptions
   - Compare quantities to identify discrepancies
   - Legend examples often explain the +7, +5 type discrepancies

#### File Type Verification

Always verify the actual file format before processing:
```bash
# Check file type (don't trust extension)
file "drawing.dxf"

# Possible outputs:
# - "AutoCAD Drawing Exchange Format" = True DXF
# - "DWG AutoDesk AutoCAD 2004/2005/2006" = DWG file (needs conversion)
```

## Configuration

Configuration is managed via environment variables in `backend/.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode | `false` |
| `DATABASE_URL` | Database connection | SQLite local |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `UPLOAD_DIR` | File storage directory | `./uploads` |
| `QWEN_API_KEY` | Alibaba Qwen API key | (required for LLM) |
| `LLM_ENABLED` | Enable LLM review | `false` |
## API Endpoints

- `GET /` - API info
- `GET /health` - Health check
- `POST /api/v1/upload` - Upload DWG/DXF/DOC/PDF files
- `POST /api/v1/review` - Start review process
- `GET /api/v1/review/{task_id}` - Get review status/result
- `GET /api/v1/tasks` - List all tasks
- `GET /api/v1/history` - Review history
- `GET /api/v1/history/{id}` - Historical review detail
- `GET /api/v1/report/{task_id}` - Download report

## Testing

Tests are located in `backend/tests/`:
- `test_dxf_parser.py` - DXF parsing tests
- `test_engine.py` - Rule engine tests
- `test_result_merger.py` - Result merger tests
- `test_contract_matcher.py` - Contract-DWG matching tests
- `test_review_api.py` - API integration tests

Fixtures are defined in `conftest.py` including `sample_dxf_data` and `sample_contract_content`.
