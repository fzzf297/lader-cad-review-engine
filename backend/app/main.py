"""
CAD 图纸审核引擎 - FastAPI 后端入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.api.v1.router import api_router
from app.utils.dwg_converter import get_converter

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"LLM 审核: {'启用' if settings.LLM_ENABLED else '禁用'}")

    # 创建上传目录
    from pathlib import Path
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # 检查 DWG 转换器
    converter = get_converter()
    if converter.is_available():
        logger.info(f"DWG 转换器已就绪: {converter.converter_type}")
    else:
        logger.warning("DWG 转换器未安装，DWG 文件将无法转换")

    yield

    # 关闭时
    logger.info("应用关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="CAD 图纸审核引擎，支持 DXF 图纸解析、规则审核、异步任务与报告导出",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vue dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "llm_enabled": settings.LLM_ENABLED
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
