"""
任务状态 API

提供异步任务状态查询和创建接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from ...services.file_registry import get_file_registry
from .review import ReviewResponse, IssueResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def get_uploaded_file(file_id: str, expected_type: Optional[str] = None):
    record = get_file_registry().get(file_id)
    if not record:
        raise HTTPException(404, "文件不存在")
    if expected_type and record.file_type != expected_type:
        raise HTTPException(400, "文件类型错误")
    return record


# ==================== 请求/响应模型 ====================

class AsyncTaskRequest(BaseModel):
    """异步任务创建请求"""
    dwg_file_id: str
    enable_llm: bool = False
    rule_codes: Optional[List[str]] = None
    large_file: bool = False  # 是否为大文件


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    ready: bool
    successful: Optional[bool] = None
    failed: Optional[bool] = None
    progress: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskStatusResponse]
    total: int


# ==================== 任务 API ====================

@router.post("", response_model=TaskStatusResponse)
async def create_async_task(request: AsyncTaskRequest):
    """
    创建异步审核任务

    适用于大文件或需要长时间处理的审核任务。
    返回任务 ID，客户端可通过 GET /tasks/{task_id} 查询进度。
    """
    from ...tasks.review_tasks import process_dwg_task, process_large_dwg_task

    # 检查 DWG 文件
    dwg_info = get_uploaded_file(request.dwg_file_id, expected_type="dwg")
    dwg_path = Path(dwg_info.file_path)

    if not dwg_path.exists():
        raise HTTPException(404, "DWG 文件路径无效")

    # 选择任务类型
    if request.large_file:
        # 大文件处理任务
        task = process_large_dwg_task.delay(
            dwg_file_path=str(dwg_path),
            dwg_file_id=request.dwg_file_id,
            enable_llm=request.enable_llm,
            rule_codes=request.rule_codes,
        )
    else:
        # 普通处理任务
        task = process_dwg_task.delay(
            dwg_file_path=str(dwg_path),
            dwg_file_id=request.dwg_file_id,
            enable_llm=request.enable_llm,
            rule_codes=request.rule_codes
        )

    logger.info(f"创建异步审核任务: {task.id}, DWG: {request.dwg_file_id}")

    return TaskStatusResponse(
        task_id=task.id,
        status="PENDING",
        ready=False,
        successful=None,
        failed=None
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    查询任务状态和进度

    返回任务当前状态，包括：
    - PENDING: 等待执行
    - STARTED: 正在执行
    - PROGRESS: 执行中（带进度信息）
    - SUCCESS: 执行成功
    - FAILURE: 执行失败
    """
    from ...tasks.review_tasks import get_task_status

    try:
        status = get_task_status(task_id)
        return TaskStatusResponse(**status)
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        raise HTTPException(500, f"查询任务状态失败: {str(e)}")


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """
    取消正在执行的任务

    注意：只能取消正在排队或执行中的任务，已完成的任务无法取消。
    """
    from ...tasks.review_tasks import cancel_task

    try:
        cancel_task(task_id)
        logger.info(f"取消任务: {task_id}")
        return {"success": True, "message": f"任务 {task_id} 已取消"}
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        raise HTTPException(500, f"取消任务失败: {str(e)}")


@router.get("/{task_id}/result", response_model=ReviewResponse)
async def get_task_result(task_id: str):
    """
    获取已完成任务的审核结果

    仅当任务状态为 SUCCESS 时可调用。
    """
    from ...tasks.review_tasks import get_task_status

    status = get_task_status(task_id)

    if status["status"] == "PENDING":
        raise HTTPException(400, "任务正在等待执行")
    elif status["status"] == "STARTED":
        raise HTTPException(400, "任务正在执行中")
    elif status["status"] == "PROGRESS":
        raise HTTPException(400, f"任务执行中: {status.get('progress', {})}")
    elif status["status"] == "FAILURE":
        raise HTTPException(500, f"任务执行失败: {status.get('error', '未知错误')}")

    result = status.get("result", {})
    record_id = result.get("record_id")

    if record_id:
        from ...services.history_storage import get_history_storage

        stored_result = get_history_storage().get_result(record_id)
        if stored_result is not None:
            review_result = stored_result
        else:
            review_result = result.get("result", {})
    else:
        review_result = result.get("result", {})

    # 解析审核结果
    dwg_review = review_result.get("dwg_review", {})

    return ReviewResponse(
        overall_score=dwg_review.get("overall_score", 0),
        assessment=dwg_review.get("assessment", ""),
        issues=[
            IssueResponse(**issue)
            for issue in dwg_review.get("issues", [])
        ],
        summary=dwg_review.get("summary", {}),
        llm_enabled=dwg_review.get("llm_enabled", False),
    )
