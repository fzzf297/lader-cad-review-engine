"""
解析详情 API - 合同和图纸解析结果展示
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pathlib import Path
import logging

from app.models.parse_result import (
    ContractParseDetailResponse,
    ConstructionScopeResponse,
    MaterialSupplyListResponse,
    LayerListResponse,
    BlockListResponse,
    EntityListResponse,
    TextListResponse,
    DimensionListResponse,
    DoorWindowStatsResponse,
    DwgStatisticsResponse,
    CompareDetailResponse,
    DwgParseVerificationResponse,
    DwgConstructionContentResponse,
    LegendCountRequest,
    LegendCountResponse,
    LegendDiscoveryResponse,
    DwgPreviewResponse,
)
from app.services.parse_service import ParseService
from app.services.dwg_translator import DwgContentTranslator, DwgParseVerifier
from app.services.file_registry import get_file_registry

logger = logging.getLogger(__name__)

router = APIRouter()


def get_uploaded_file(file_id: str, expected_type: Optional[str] = None):
    """获取上传文件记录并校验类型"""
    record = get_file_registry().get(file_id)
    if not record:
        raise HTTPException(404, "文件不存在")
    if expected_type and record.file_type != expected_type:
        raise HTTPException(400, "文件类型错误")
    return record


@router.post("/legend-count", response_model=LegendCountResponse)
async def count_legend(request: LegendCountRequest):
    """
    统计图例对应符号在主图中的真实出现次数。

    当前实现优先依据图例说明文字定位目标符号，并排除图例区/说明区实例。
    """
    file_info = get_uploaded_file(request.file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    parse_service = ParseService()

    try:
        result = await parse_service.count_legend(
            file_path=str(file_path),
            file_id=request.file_id,
            query=request.query,
            use_llm=request.use_llm,
            save_template=request.save_template,
            template_name=request.template_name,
        )
        return LegendCountResponse(**result)
    except Exception as e:
        logger.error(f"图例计数失败: {e}")
        raise HTTPException(500, f"图例计数失败: {str(e)}")


@router.get("/legend-items/{file_id}", response_model=LegendDiscoveryResponse)
async def discover_legend_items(file_id: str):
    """
    扫描整张图中可识别的图例设备列表，并给出候选块和估计数量。
    """
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    parse_service = ParseService()

    try:
        result = await parse_service.discover_legends(
            file_path=str(file_path),
            file_id=file_id,
        )
        return LegendDiscoveryResponse(**result)
    except Exception as e:
        logger.error(f"图例发现失败: {e}")
        raise HTTPException(500, f"图例发现失败: {str(e)}")


@router.get("/dwg/{file_id}/preview", response_model=DwgPreviewResponse)
async def get_dwg_preview(file_id: str):
    """
    返回用于前端叠加点位的简化图纸底图数据。
    """
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    parse_service = ParseService()

    try:
        result = await parse_service.get_dwg_preview(
            file_path=str(file_path),
            file_id=file_id,
        )
        return DwgPreviewResponse(**result)
    except Exception as e:
        logger.error(f"图纸预览生成失败: {e}")
        raise HTTPException(500, f"图纸预览生成失败: {str(e)}")


# ==================== 合同解析接口 ====================

@router.get("/contract/{file_id}/details", response_model=ContractParseDetailResponse)
async def get_contract_parse_details(file_id: str):
    """
    获取合同解析详情（完整版）

    展示从合同中提取的完整信息，包括：
    - 项目名称、合同双方
    - 工作项清单（名称、分类、数量、单位、规格等）
    - 关键条款（工期、付款、验收等）
    - 原文预览和表格预览
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="contract")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析合同
        contract_content = parse_service.parse_contract(str(file_path), file_id)

        # 分析合同
        contract_analysis = await parse_service.analyze_contract(str(file_path), file_id)

        # 构建详情响应
        details = await parse_service.get_contract_details(
            contract_analysis,
            contract_content,
            file_id,
            file_info.filename
        )

        return ContractParseDetailResponse(**details)

    except Exception as e:
        logger.error(f"合同解析详情获取失败: {e}")
        raise HTTPException(500, f"合同解析详情获取失败: {str(e)}")


@router.get("/contract/{file_id}/construction-scope", response_model=MaterialSupplyListResponse)
async def get_contract_construction_scope(file_id: str):
    """
    获取合同发包人供应材料设备一览表

    专门提取合同中的"发包人供应材料设备一览表"表格：
    - 材料/设备名称
    - 规格型号
    - 单位、数量
    - 供应方式
    - 备注说明

    注意：只提取该表格，找不到则返回空结果
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="contract")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 获取施工范围详情
        result = await parse_service.get_construction_scope(
            str(file_path),
            file_id,
            file_info.filename
        )

        return ConstructionScopeResponse(**result)

    except Exception as e:
        logger.error(f"施工范围获取失败: {e}")
        raise HTTPException(500, f"施工范围获取失败: {str(e)}")


# ==================== 图纸解析接口 ====================

@router.get("/dwg/{file_id}/layers", response_model=LayerListResponse)
async def get_dwg_layers(file_id: str):
    """
    获取图纸图层列表

    展示 DXF 文件中的所有图层信息：
    - 图层名称、颜色、线型
    - 图层状态（关闭/冻结/锁定）
    - 是否打印
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取图层列表
        layers = parse_service.get_dxf_layers(dxf_result)

        return LayerListResponse(
            file_id=file_id,
            total_layers=len(layers),
            layers=layers
        )

    except Exception as e:
        logger.error(f"图层列表获取失败: {e}")
        raise HTTPException(500, f"图层列表获取失败: {str(e)}")


@router.get("/dwg/{file_id}/blocks", response_model=BlockListResponse)
async def get_dwg_blocks(file_id: str):
    """
    获取图纸图块列表

    展示 DXF 文件中的所有图块定义：
    - 图块名称、实体数量
    - 引用次数
    - 是否为门窗图块
    - 分类信息
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取图块列表
        blocks = parse_service.get_dxf_blocks(dxf_result)

        return BlockListResponse(
            file_id=file_id,
            total_blocks=len(blocks),
            blocks=blocks
        )

    except Exception as e:
        logger.error(f"图块列表获取失败: {e}")
        raise HTTPException(500, f"图块列表获取失败: {str(e)}")


@router.get("/dwg/{file_id}/entities", response_model=EntityListResponse)
async def get_dwg_entities(
    file_id: str,
    type: Optional[str] = Query(None, description="实体类型过滤（如 LINE, TEXT, INSERT）"),
    layer: Optional[str] = Query(None, description="图层名称过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=500, description="每页数量")
):
    """
    获取图纸实体列表（支持筛选和分页）

    展示 DXF 文件中的实体详细信息：
    - 实体类型、图层、句柄
    - 几何信息（坐标、尺寸等）
    - 属性信息（INSERT 的属性等）

    支持按类型和图层筛选，支持分页。
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取实体列表（带筛选和分页）
        result = parse_service.get_dxf_entities(
            dxf_result,
            entity_type=type,
            layer=layer,
            page=page,
            page_size=page_size
        )

        return EntityListResponse(
            file_id=file_id,
            filter={"type": type, "layer": layer},
            pagination=result["pagination"],
            entities=result["entities"]
        )

    except Exception as e:
        logger.error(f"实体列表获取失败: {e}")
        raise HTTPException(500, f"实体列表获取失败: {str(e)}")


@router.get("/dwg/{file_id}/texts", response_model=TextListResponse)
async def get_dwg_texts(file_id: str):
    """
    获取图纸文字内容

    展示 DXF 文件中的所有 TEXT 和 MTEXT 实体：
    - 文字内容
    - 插入位置、高度
    - 文字样式
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取文字列表
        texts = parse_service.get_dxf_texts(dxf_result)

        return TextListResponse(
            file_id=file_id,
            total_texts=len(texts),
            texts=texts
        )

    except Exception as e:
        logger.error(f"文字内容获取失败: {e}")
        raise HTTPException(500, f"文字内容获取失败: {str(e)}")


@router.get("/dwg/{file_id}/dimensions", response_model=DimensionListResponse)
async def get_dwg_dimensions(file_id: str):
    """
    获取图纸尺寸标注

    展示 DXF 文件中的所有 DIMENSION 实体：
    - 标注文字、类型
    - 定义点位置
    - 标注样式
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取尺寸标注列表
        dimensions = parse_service.get_dxf_dimensions(dxf_result)

        return DimensionListResponse(
            file_id=file_id,
            total_dimensions=len(dimensions),
            dimensions=dimensions
        )

    except Exception as e:
        logger.error(f"尺寸标注获取失败: {e}")
        raise HTTPException(500, f"尺寸标注获取失败: {str(e)}")


@router.get("/dwg/{file_id}/door-window-stats", response_model=DoorWindowStatsResponse)
async def get_dwg_door_window_stats(file_id: str):
    """
    获取门窗统计详情

    展示 DXF 文件中识别出的门窗信息：
    - 门/窗总数统计
    - 每种门窗的详细信息（名称、数量、规格）
    - 插入位置列表
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取门窗统计
        stats = parse_service.get_door_window_stats(dxf_result)

        return DoorWindowStatsResponse(
            file_id=file_id,
            summary=stats["summary"],
            doors=stats["doors"],
            windows=stats["windows"]
        )

    except Exception as e:
        logger.error(f"门窗统计获取失败: {e}")
        raise HTTPException(500, f"门窗统计获取失败: {str(e)}")


@router.get("/dwg/{file_id}/statistics", response_model=DwgStatisticsResponse)
async def get_dwg_statistics(file_id: str):
    """
    获取图纸完整统计

    展示 DXF 文件的完整统计信息：
    - 文件信息（版本、单位）
    - 各类实体数量统计
    - 按类型和分类的详细统计
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 获取统计信息
        stats = parse_service.get_dxf_statistics(dxf_result, str(file_path))

        return DwgStatisticsResponse(
            file_id=file_id,
            file_info=stats["file_info"],
            counts=stats["counts"],
            by_type=stats["by_type"],
            by_category=stats["by_category"],
            parse_metadata=stats.get("parse_metadata"),
            source_file=stats.get("source_file")
        )

    except Exception as e:
        logger.error(f"图纸统计获取失败: {e}")
        raise HTTPException(500, f"图纸统计获取失败: {str(e)}")


# ==================== 对比接口 ====================

@router.get("/compare/{contract_file_id}/{dwg_file_id}/details", response_model=CompareDetailResponse)
async def get_comparison_details(
    contract_file_id: str,
    dwg_file_id: str
):
    """
    获取合同与图纸对比详情

    展示合同工作项与图纸内容的详细对比：
    - 整体符合度评分
    - 匹配/部分匹配/缺失/多余项统计
    - 每项的详细对比（合同数量 vs 图纸数量）
    - 问题列表和改进建议
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

    # 创建解析服务
    parse_service = ParseService()

    try:
        # 解析合同
        contract_content = parse_service.parse_contract(str(contract_path), contract_file_id)
        contract_analysis = await parse_service.analyze_contract(str(contract_path), contract_file_id)

        # 解析图纸
        dxf_result = await parse_service.parse_dxf(str(dwg_path), dwg_file_id)

        # 获取对比详情
        comparison = await parse_service.get_comparison_details(
            contract_analysis,
            dxf_result
        )

        return CompareDetailResponse(
            contract_file_id=contract_file_id,
            dwg_file_id=dwg_file_id,
            comparison=comparison
        )

    except Exception as e:
        logger.error(f"对比详情获取失败: {e}")
        raise HTTPException(500, f"对比详情获取失败: {str(e)}")


# ==================== P0: 数据验证接口 ====================

@router.get("/dwg/{file_id}/verify", response_model=DwgParseVerificationResponse)
async def verify_dwg_parse(file_id: str):
    """
    验证 DWG 文件解析真实性

    返回详细的验证报告，证明文件确实被真实解析：
    - 解析时间戳和 MD5 校验
    - 实体数量统计
    - 门窗识别结果
    - 验证通过/失败项列表
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建解析服务
    parse_service = ParseService()
    verifier = DwgParseVerifier()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 验证解析结果
        verification = verifier.verify(dxf_result, file_id, file_info.filename)

        # 构建验证响应
        status = "verified" if verification["is_valid"] else "failed"
        message = _get_verification_message(verification)

        return DwgParseVerificationResponse(
            file_id=file_id,
            filename=file_info.filename,
            status=status,
            message=message,
            verification=verification,
            parse_metadata=dxf_result.parse_metadata,
            summary={
                "entity_count": len(dxf_result.entities),
                "layer_count": len(dxf_result.layers),
                "block_count": len(dxf_result.blocks),
                "door_window_types": verification["indicators"].get("door_window_types", 0),
                "confidence": verification["confidence"],
            }
        )

    except Exception as e:
        logger.error(f"解析验证失败: {e}")
        raise HTTPException(500, f"解析验证失败: {str(e)}")


def _get_verification_message(verification: dict) -> str:
    """生成验证消息"""
    confidence = verification["confidence"]
    passed = verification["passed_checks"]
    total = verification["total_checks"]

    if confidence == "high":
        return f"✅ 验证通过！文件已被真实解析 ({passed}/{total} 项检查通过)"
    elif confidence == "medium":
        return f"⚠️ 验证基本通过，部分信息可能不完整 ({passed}/{total} 项检查通过)"
    else:
        return f"❌ 验证失败，文件可能未正确解析 ({passed}/{total} 项检查通过)"


# ==================== P1: 施工内容接口 ====================

@router.get("/dwg/{file_id}/construction-content", response_model=DwgConstructionContentResponse)
async def get_dwg_construction_content(file_id: str):
    """
    获取图纸施工内容（业务友好格式）

    将技术性的 CAD 数据转换为业务可理解的施工内容：
    - 门窗：类型、数量、规格（如 铝合金门 M1021，1000x2100mm，50个）
    - 房间：从文字标注提取的房间名称
    - 汇总统计
    """
    # 检查文件是否存在
    file_info = get_uploaded_file(file_id, expected_type="dwg")
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(404, "文件路径无效")

    # 创建服务
    parse_service = ParseService()
    translator = DwgContentTranslator()

    try:
        # 解析 DXF
        dxf_result = await parse_service.parse_dxf(str(file_path), file_id)

        # 翻译为施工内容
        content = translator.translate(dxf_result)

        from datetime import datetime
        return DwgConstructionContentResponse(
            file_id=file_id,
            filename=file_info.filename,
            parse_status="success",
            construction_content=content,
            parse_time=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"施工内容获取失败: {e}")
        raise HTTPException(500, f"施工内容获取失败: {str(e)}")
