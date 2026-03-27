"""
审核 API - 审核功能、历史记录、报告下载
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from pathlib import Path
from datetime import datetime
import uuid
import io

from ...core.config import settings
from ...services.review_service import FullReviewService
from ...services.report_service import ReportService, ReportData
from ...services.history_storage import (
    HistoryStorage, ReviewRecord, get_history_storage
)
from ...services.file_registry import FileRecord, get_file_registry

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 请求/响应模型 ====================

class ReviewRequest(BaseModel):
    """审核请求"""
    dwg_file_id: str
    enable_llm: bool = False
    rule_codes: Optional[List[str]] = None


class IssueResponse(BaseModel):
    """问题响应"""
    category: str
    severity: str
    description: str
    location: str = ""
    suggestion: str = ""
    source: str = ""
    confidence: float = 1.0


class ReviewResponse(BaseModel):
    """审核响应"""
    overall_score: float
    assessment: str
    issues: List[IssueResponse]
    summary: Dict[str, Any]
    llm_enabled: bool = False


class ReviewRecordResponse(BaseModel):
    """审核记录响应"""
    record_id: str
    file_id: str
    file_name: str
    file_type: str
    created_at: str
    overall_score: float
    assessment: str
    issue_count: int
    enable_llm: bool = False


class HistoryListResponse(BaseModel):
    """历史记录列表响应"""
    records: List[ReviewRecordResponse]
    total: int
    page: int
    page_size: int


class StatisticsResponse(BaseModel):
    """统计响应"""
    total_reviews: int
    avg_score: float
    by_assessment: Dict[str, int]
    by_file_type: Dict[str, int]


# 审核结果缓存
review_results: dict = {}


def get_uploaded_file(file_id: str, expected_type: Optional[str] = None) -> FileRecord:
    """获取已上传文件记录并做类型校验"""
    record = get_file_registry().get(file_id)
    if not record:
        raise HTTPException(404, "文件不存在")
    if expected_type and record.file_type != expected_type:
        raise HTTPException(400, "文件类型错误")
    return record


# ==================== 审核创建 API ====================

@router.post("", response_model=ReviewResponse)
async def create_review(request: ReviewRequest):
    """创建审核任务"""

    dwg_info = get_uploaded_file(request.dwg_file_id, expected_type="dwg")
    dwg_path = Path(dwg_info.file_path)

    if not dwg_path.exists():
        raise HTTPException(404, "DWG 文件路径无效")

    # 检查文件格式（现在支持转换后的 DXF）
    file_suffix = dwg_path.suffix.lower()
    if file_suffix == ".dwg":
        # 如果还是 DWG 格式，说明转换失败或未转换
        raise HTTPException(
            400,
            "DWG 文件未能自动转换为 DXF 格式。"
            "\n请先手动将 DWG 转换为 DXF 格式后再上传。"
        )

    # 创建审核服务
    review_service = FullReviewService()

    try:
        # 执行审核
        result = await review_service.full_review(
            dxf_file_path=str(dwg_path),
            enable_llm=request.enable_llm,
            rule_codes=request.rule_codes,
        )

        # 缓存结果
        review_id = request.dwg_file_id
        review_results[review_id] = result

        # 保存到历史记录
        history = get_history_storage()
        record = ReviewRecord(
            record_id=str(uuid.uuid4()),
            file_id=request.dwg_file_id,
            file_name=dwg_info.filename,
            file_type="dwg",
            created_at=datetime.now().isoformat(),
            overall_score=result["dwg_review"]["overall_score"],
            assessment=result["dwg_review"]["assessment"],
            issue_count=len(result["dwg_review"]["issues"]),
            enable_llm=request.enable_llm,
            result=result
        )
        history.save(record)

        # 更新缓存 key 为 record_id
        review_results[record.record_id] = result

        # 构建响应
        return ReviewResponse(
            overall_score=result["dwg_review"]["overall_score"],
            assessment=result["dwg_review"]["assessment"],
            issues=[
                IssueResponse(**issue)
                for issue in result["dwg_review"]["issues"]
            ],
            summary=result["dwg_review"]["summary"],
            llm_enabled=result["dwg_review"]["llm_enabled"],
        )

    except Exception as e:
        logger.error(f"审核失败: {e}")
        raise HTTPException(500, f"审核失败: {str(e)}")
    finally:
        # 审核完成后立即清理输入文件，避免上传目录长期堆积。
        get_file_registry().mark_consumed(request.dwg_file_id, remove_file=True)


# ==================== 统计和历史记录 API ====================
# 注意：这些路由必须在 /{review_id} 之前定义

@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics():
    """获取审核统计信息"""

    history = get_history_storage()
    stats = history.get_statistics()

    return StatisticsResponse(**stats)


@router.get("/history/list", response_model=HistoryListResponse)
async def get_history_list(
    page: int = 1,
    page_size: int = 20,
    file_type: Optional[str] = None,
    assessment: Optional[str] = None
):
    """获取历史记录列表"""

    history = get_history_storage()
    records, total = history.list(
        page=page,
        page_size=page_size,
        file_type=file_type,
        assessment=assessment
    )

    return HistoryListResponse(
        records=[
            ReviewRecordResponse(
                record_id=r.record_id,
                file_id=r.file_id,
                file_name=r.file_name,
                file_type=r.file_type,
                created_at=r.created_at,
                overall_score=r.overall_score,
                assessment=r.assessment,
                issue_count=r.issue_count,
                enable_llm=r.enable_llm
            )
            for r in records
        ],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/history/{record_id}", response_model=ReviewResponse)
async def get_history_detail(record_id: str):
    """获取历史记录详情"""

    history = get_history_storage()
    result = history.get_result(record_id)

    if not result:
        raise HTTPException(404, "历史记录不存在")

    return ReviewResponse(
        overall_score=result["dwg_review"]["overall_score"],
        assessment=result["dwg_review"]["assessment"],
        issues=[
            IssueResponse(**issue)
            for issue in result["dwg_review"]["issues"]
        ],
        summary=result["dwg_review"]["summary"],
        llm_enabled=result["dwg_review"]["llm_enabled"],
    )


@router.delete("/history/{record_id}")
async def delete_history(record_id: str):
    """删除历史记录"""

    history = get_history_storage()
    success = history.delete(record_id)

    if not success:
        raise HTTPException(404, "历史记录不存在")

    return {"success": True, "message": "删除成功"}


# ==================== 报告下载 API ====================

@router.get("/report/{record_id}/json")
async def download_report_json(record_id: str):
    """下载 JSON 格式报告"""

    history = get_history_storage()
    record = history.get(record_id)

    if not record:
        raise HTTPException(404, "记录不存在")

    result = history.get_result(record_id)
    if not result:
        raise HTTPException(404, "审核结果不存在")

    # 生成报告
    report_service = ReportService()
    report = report_service.generate_report(
        report_id=record_id,
        file_name=record.file_name,
        review_result=result
    )

    json_content = report_service.to_json(report)

    return StreamingResponse(
        io.BytesIO(json_content.encode('utf-8')),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=report_{record_id}.json"
        }
    )


@router.get("/report/{record_id}/pdf")
async def download_report_pdf(record_id: str):
    """下载 PDF 格式报告"""

    history = get_history_storage()
    record = history.get(record_id)

    if not record:
        raise HTTPException(404, "记录不存在")

    result = history.get_result(record_id)
    if not result:
        raise HTTPException(404, "审核结果不存在")

    # 生成报告
    report_service = ReportService()
    report = report_service.generate_report(
        report_id=record_id,
        file_name=record.file_name,
        review_result=result
    )

    pdf_content = report_service.to_pdf(report)

    return StreamingResponse(
        io.BytesIO(pdf_content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=report_{record_id}.pdf"
        }
    )


# ==================== 通用审核结果 API ====================

@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review_result(review_id: str):
    """获取审核结果"""

    if review_id not in review_results:
        raise HTTPException(404, "审核结果不存在")

    result = review_results[review_id]

    return ReviewResponse(
        overall_score=result["dwg_review"]["overall_score"],
        assessment=result["dwg_review"]["assessment"],
        issues=[
            IssueResponse(**issue)
            for issue in result["dwg_review"]["issues"]
        ],
        summary=result["dwg_review"]["summary"],
        llm_enabled=result["dwg_review"]["llm_enabled"],
    )
