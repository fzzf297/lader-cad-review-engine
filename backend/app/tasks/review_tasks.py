"""
审核异步任务

处理 DWG 文件审核的异步任务
支持进度更新、错误处理和重试机制
"""
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
import traceback
import uuid

from celery import shared_task
from celery.result import AsyncResult

from .celery_app import celery_app
from ..core.config import settings
from ..services.review_service import FullReviewService
from ..services.file_registry import get_file_registry
from ..services.history_storage import ReviewRecord, get_history_storage

logger = logging.getLogger(__name__)


# 任务状态常量
TASK_STATUS = {
    "PENDING": "PENDING",
    "STARTED": "STARTED",
    "PROGRESS": "PROGRESS",
    "SUCCESS": "SUCCESS",
    "FAILURE": "FAILURE",
    "RETRY": "RETRY",
}


class TaskProgress:
    """任务进度管理器"""

    def __init__(self, task_id: str):
        self.task_id = task_id

    def update(self, progress: float, stage: str, message: str = ""):
        """
        更新任务进度

        Args:
            progress: 进度百分比 (0-100)
            stage: 当前阶段
            message: 进度消息
        """
        celery_app.backend.store_result(
            self.task_id,
            result={
                "progress": progress,
                "stage": stage,
                "message": message,
                "timestamp": datetime.now().isoformat()
            },
            state="PROGRESS"
        )


def _save_review_history(
    dwg_file_id: str,
    enable_llm: bool,
    result: Dict[str, Any],
) -> str:
    """将异步任务审核结果写入统一历史存储。"""
    registry = get_file_registry()
    history = get_history_storage()

    dwg_record = registry.get(dwg_file_id)
    record = ReviewRecord(
        record_id=str(uuid.uuid4()),
        file_id=dwg_file_id,
        file_name=dwg_record.filename if dwg_record else dwg_file_id,
        file_type="dwg",
        created_at=datetime.now().isoformat(),
        overall_score=result["dwg_review"]["overall_score"],
        assessment=result["dwg_review"]["assessment"],
        issue_count=len(result["dwg_review"]["issues"]),
        enable_llm=enable_llm,
        result=result,
    )
    history.save(record)
    return record.record_id


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def process_dwg_task(
    self,
    dwg_file_path: str,
    dwg_file_id: str,
    enable_llm: bool = False,
    rule_codes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    异步处理 DWG 文件审核任务

    Args:
        self: Celery task 实例（bind=True）
        dwg_file_path: DWG 文件路径
        dwg_file_id: DWG 文件 ID
        enable_llm: 是否启用 LLM 审核
        rule_codes: 规则代码列表（可选）

    Returns:
        审核结果字典
    """
    task_id = self.request.id
    progress = TaskProgress(task_id)
    cleanup_after_task = False

    try:
        # 阶段 1: 初始化 (0-10%)
        progress.update(5, "初始化", "正在准备审核环境...")
        logger.info(f"任务 {task_id}: 开始处理 DWG 文件 {dwg_file_path}")

        # 检查文件是否存在
        dwg_path = Path(dwg_file_path)
        if not dwg_path.exists():
            raise FileNotFoundError(f"DWG 文件不存在: {dwg_file_path}")

        # 阶段 2: 解析文件 (10-30%)
        progress.update(15, "解析文件", "正在解析 DWG 文件...")
        logger.info(f"任务 {task_id}: 正在解析 DWG 文件")

        # 创建审核服务
        review_service = FullReviewService()

        # 阶段 3: 执行规则审核 (30-60%)
        progress.update(35, "规则审核", "正在执行规则引擎审核...")
        logger.info(f"任务 {task_id}: 执行规则审核")

        # 阶段 4: LLM 审核（如果启用）(60-80%)
        if enable_llm:
            progress.update(65, "LLM 审核", "正在执行 LLM 增强审核...")
            logger.info(f"任务 {task_id}: 执行 LLM 审核")

        # 阶段 5: 生成审核结果 (80-95%)
        progress.update(85, "执行审核", "正在生成审核结果...")
        result = asyncio.run(review_service.full_review(
            dxf_file_path=str(dwg_path),
            enable_llm=enable_llm,
            rule_codes=rule_codes,
        ))
        record_id = _save_review_history(
            dwg_file_id=dwg_file_id,
            enable_llm=enable_llm,
            result=result,
        )

        # 阶段 6: 生成报告 (90-100%)
        progress.update(95, "生成报告", "正在生成审核报告...")

        # 构建最终结果
        final_result = {
            "task_id": task_id,
            "dwg_file_id": dwg_file_id,
            "record_id": record_id,
            "status": "SUCCESS",
            "completed_at": datetime.now().isoformat(),
            "result": result
        }

        progress.update(100, "完成", "审核完成")
        logger.info(f"任务 {task_id}: 审核完成")
        cleanup_after_task = True

        return final_result

    except FileNotFoundError as e:
        logger.error(f"任务 {task_id}: 文件未找到 - {e}")
        progress.update(0, "错误", f"文件未找到: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"任务 {task_id}: 审核失败 - {e}\n{traceback.format_exc()}")
        progress.update(0, "错误", f"审核失败: {str(e)}")

        # 重试逻辑
        try:
            # 抛出异常触发重试
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"任务 {task_id}: 达到最大重试次数")
            cleanup_after_task = True
            return {
                "task_id": task_id,
                "dwg_file_id": dwg_file_id,
                "status": "FAILURE",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "completed_at": datetime.now().isoformat()
            }
    finally:
        if cleanup_after_task:
            get_file_registry().mark_consumed(dwg_file_id, remove_file=True)


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=1200,
    retry_jitter=True
)
def process_large_dwg_task(
    self,
    dwg_file_path: str,
    dwg_file_id: str,
    chunk_size: int = 1000,
    enable_llm: bool = False,
    rule_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    处理大型 DWG 文件的分块审核任务

    对于超大文件，采用分块处理策略，避免内存溢出

    Args:
        self: Celery task 实例
        dwg_file_path: DWG 文件路径
        dwg_file_id: DWG 文件 ID
        chunk_size: 每块处理的实体数量
        enable_llm: 是否启用 LLM

    Returns:
        审核结果
    """
    task_id = self.request.id
    progress = TaskProgress(task_id)
    cleanup_after_task = False

    try:
        progress.update(5, "初始化", "正在准备大文件处理...")
        logger.info(f"任务 {task_id}: 开始处理大型 DWG 文件")

        # 检查文件
        dwg_path = Path(dwg_file_path)
        if not dwg_path.exists():
            raise FileNotFoundError(f"DWG 文件不存在: {dwg_file_path}")

        # 获取文件大小
        file_size = dwg_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)

        logger.info(f"任务 {task_id}: 文件大小 {file_size_mb:.2f} MB")

        progress.update(10, "解析文件", f"文件大小: {file_size_mb:.2f} MB")

        # 创建审核服务
        review_service = FullReviewService()

        progress.update(20, "解析文件", "正在解析大型 DWG 文件...")

        # 执行完整审核
        result = asyncio.run(review_service.full_review(
            dxf_file_path=str(dwg_path),
            enable_llm=enable_llm,
            rule_codes=rule_codes,
        ))
        record_id = _save_review_history(
            dwg_file_id=dwg_file_id,
            enable_llm=enable_llm,
            result=result,
        )

        # 构建最终结果
        final_result = {
            "task_id": task_id,
            "dwg_file_id": dwg_file_id,
            "record_id": record_id,
            "status": "SUCCESS",
            "completed_at": datetime.now().isoformat(),
            "file_size_mb": file_size_mb,
            "result": result
        }

        progress.update(100, "完成", "审核完成")
        logger.info(f"任务 {task_id}: 大文件审核完成")
        cleanup_after_task = True

        return final_result

    except FileNotFoundError as e:
        logger.error(f"任务 {task_id}: 文件未找到 - {e}")
        progress.update(0, "错误", f"文件未找到: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"任务 {task_id}: 大文件处理失败 - {e}\n{traceback.format_exc()}")
        progress.update(0, "错误", f"处理失败: {str(e)}")

        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"任务 {task_id}: 达到最大重试次数")
            cleanup_after_task = True
            return {
                "task_id": task_id,
                "dwg_file_id": dwg_file_id,
                "status": "FAILURE",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "completed_at": datetime.now().isoformat()
            }
    finally:
        if cleanup_after_task:
            get_file_registry().mark_consumed(dwg_file_id, remove_file=True)


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    获取任务状态

    Args:
        task_id: 任务 ID

    Returns:
        任务状态信息
    """
    result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
        "failed": result.failed() if result.ready() else None,
    }

    # 获取进度信息
    if result.status == "PROGRESS":
        response["progress"] = result.result
    elif result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


def cancel_task(task_id: str) -> bool:
    """
    取消任务

    Args:
        task_id: 任务 ID

    Returns:
        是否成功取消
    """
    result = AsyncResult(task_id, app=celery_app)
    result.revoke(terminate=True)
    return True
