"""
验证 API - 合同与图纸对比验证
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pathlib import Path
import logging

from app.models.parse_result import (
    ContractDwgValidationResponse,
    ValidationMatchItem,
    ValidationMismatchItem,
    ValidationExtraItem,
    ValidationSummary,
)
from app.services.parse_service import ParseService
from app.services.contract_dwg_validator import ContractDwgValidator
from app.services.file_registry import get_file_registry

logger = logging.getLogger(__name__)

router = APIRouter()


def get_uploaded_file(file_id: str, expected_type: Optional[str] = None):
    record = get_file_registry().get(file_id)
    if not record:
        raise HTTPException(404, "文件不存在")
    if expected_type and record.file_type != expected_type:
        raise HTTPException(400, f"{'合同' if expected_type == 'contract' else '图纸'}文件类型错误")
    return record


@router.post("/contract-dwg", response_model=ContractDwgValidationResponse)
async def validate_contract_dwg(
    contract_file_id: str,
    dwg_file_id: str
):
    """
    合同与图纸对比验证

    对比合同施工范围与图纸内容，生成详细的匹配报告：
    - 整体匹配度评分
    - 匹配项列表（合同项 vs 图纸项）
    - 不匹配项列表（数量差异、缺失项）
    - 图纸中的额外项
    - 改进建议
    """
    # 检查合同文件
    contract_info = get_uploaded_file(contract_file_id, expected_type="contract")
    contract_path = Path(contract_info.file_path)
    if not contract_path.exists():
        raise HTTPException(404, "合同文件路径无效")

    # 检查图纸文件
    dwg_info = get_uploaded_file(dwg_file_id, expected_type="dwg")
    dwg_path = Path(dwg_info.file_path)
    if not dwg_path.exists():
        raise HTTPException(404, "图纸文件路径无效")

    # 创建服务
    parse_service = ParseService()
    validator = ContractDwgValidator()

    try:
        # 解析合同
        logger.info(f"[验证] 开始解析合同: {contract_info.filename}")
        contract_content = parse_service.parse_contract(str(contract_path), contract_file_id)
        contract_analysis = await parse_service.analyze_contract(str(contract_path), contract_file_id)

        # 解析图纸
        logger.info(f"[验证] 开始解析图纸: {dwg_info.filename}")
        dxf_result = await parse_service.parse_dxf(str(dwg_path), dwg_file_id)

        # 执行验证
        logger.info("[验证] 开始对比验证...")
        report = await validator.validate(
            contract_analysis,
            dxf_result,
            contract_filename=contract_info.filename,
            dwg_filename=dwg_info.filename
        )

        # 转换为响应模型
        from datetime import datetime
        return ContractDwgValidationResponse(
            contract_file_id=contract_file_id,
            dwg_file_id=dwg_file_id,
            contract_filename=contract_info.filename,
            dwg_filename=dwg_info.filename,
            overall_match=report.overall_match,
            status=report.status,
            summary=ValidationSummary(
                total_contract_items=report.summary.get("total_contract_items", 0),
                matched=report.summary.get("matched", 0),
                partial=report.summary.get("partial", 0),
                missing=report.summary.get("missing", 0),
                extra=report.summary.get("extra", 0),
                total_doors=report.summary.get("total_doors", 0),
                total_windows=report.summary.get("total_windows", 0),
            ),
            matches=report.matches,
            mismatches=report.mismatches,
            extra_in_dwg=report.extra_in_dwg,
            suggestions=report.suggestions,
            validation_time=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"合同-图纸验证失败: {e}")
        raise HTTPException(500, f"合同-图纸验证失败: {str(e)}")
