"""
解析结果数据模型 - Pydantic 模型定义
"""
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime


# ==================== 合同解析模型 ====================

class WorkItemResponse(BaseModel):
    """工作项响应"""
    name: str
    category: str
    quantity: float
    unit: str
    specification: str = ""
    location: str = ""
    deadline: str = ""
    original_text: str = ""


class KeyTermResponse(BaseModel):
    """关键条款响应"""
    type: str
    content: str
    importance: str = "medium"


class ContractParseResult(BaseModel):
    """合同解析结果"""
    project_name: str = ""
    contract_parties: Dict[str, str] = {}
    total_amount: float = 0
    work_items: List[WorkItemResponse] = []
    key_terms: List[KeyTermResponse] = []


class ContractParseDetailResponse(BaseModel):
    """合同解析详情响应"""
    file_id: str
    filename: str
    parse_status: str
    parse_result: ContractParseResult
    raw_text_preview: str = ""
    tables_preview: List[str] = []
    parse_time: Optional[str] = None


# 施工范围专用模型（保留备用）
class ConstructionWorkItem(BaseModel):
    """施工范围工作项"""
    item_no: str = ""
    name: str = ""
    description: str = ""
    quantity: str = ""
    unit: str = ""
    specification: str = ""
    location: str = ""


class ConstructionScope(BaseModel):
    """施工范围详情"""
    project_name: str = ""
    location: str = ""
    buildings: List[str] = []
    summary: str = ""
    work_items: List[ConstructionWorkItem] = []
    main_materials: List[str] = []
    standards: List[str] = []
    original_text: str = ""


class ConstructionScopeResponse(BaseModel):
    """施工范围响应"""
    file_id: str
    filename: str
    parse_status: str
    construction_scope: Dict[str, Any]
    parse_time: Optional[str] = None


# ==================== 材料设备供应表模型 ====================

class MaterialSupplyItem(BaseModel):
    """材料/设备供应项"""
    item_no: str = ""
    name: str = ""
    specification: str = ""
    unit: str = ""
    quantity: str = ""
    supply_method: str = ""
    remarks: str = ""


class MaterialSupplySummary(BaseModel):
    """材料设备供应汇总"""
    total_items: int = 0
    categories: Dict[str, int] = {}


class MaterialSupplyList(BaseModel):
    """发包人供应材料设备一览表"""
    table_found: bool = False
    table_name: str = ""
    project_name: str = ""
    location: str = ""
    items: List[MaterialSupplyItem] = []
    summary: MaterialSupplySummary = MaterialSupplySummary()


class MaterialSupplyListResponse(BaseModel):
    """材料设备供应表响应"""
    file_id: str
    filename: str
    parse_status: str
    material_supply_list: Dict[str, Any]
    parse_time: Optional[str] = None


# ==================== 图纸解析模型 ====================

class LayerResponse(BaseModel):
    """图层响应"""
    name: str
    color: int
    linetype: str
    off: bool = False
    frozen: bool = False
    locked: bool = False
    plot: bool = True


class LayerListResponse(BaseModel):
    """图层列表响应"""
    file_id: str
    total_layers: int
    layers: List[LayerResponse]


class BlockResponse(BaseModel):
    """图块响应"""
    name: str
    entity_count: int
    insert_count: int
    is_door_window: bool = False
    category: str = ""
    entities: List[str] = []


class BlockListResponse(BaseModel):
    """图块列表响应"""
    file_id: str
    total_blocks: int
    blocks: List[BlockResponse]


class EntityResponse(BaseModel):
    """实体响应"""
    type: str
    handle: str
    layer: str
    # 根据实体类型的额外字段
    name: Optional[str] = None  # INSERT
    insert: Optional[Dict[str, float]] = None
    scale: Optional[Dict[str, float]] = None
    rotation: Optional[float] = None
    attribs: Optional[Dict[str, str]] = None
    content: Optional[str] = None  # TEXT/MTEXT
    height: Optional[float] = None
    start: Optional[Dict[str, float]] = None  # LINE
    end: Optional[Dict[str, float]] = None
    length: Optional[float] = None
    center: Optional[Dict[str, float]] = None  # CIRCLE/ARC
    radius: Optional[float] = None
    vertices: Optional[List[Dict[str, float]]] = None  # LWPOLYLINE


class EntityFilter(BaseModel):
    """实体筛选条件"""
    type: Optional[str] = None
    layer: Optional[str] = None


class PaginationInfo(BaseModel):
    """分页信息"""
    page: int
    page_size: int
    total: int
    total_pages: int


class EntityListResponse(BaseModel):
    """实体列表响应"""
    file_id: str
    filter: EntityFilter
    pagination: PaginationInfo
    entities: List[EntityResponse]


class TextResponse(BaseModel):
    """文字响应"""
    type: str
    handle: str
    layer: str
    content: str
    insert: Dict[str, float]
    height: float
    style: str = ""
    width: Optional[float] = None
    rotation: Optional[float] = None


class TextListResponse(BaseModel):
    """文字列表响应"""
    file_id: str
    total_texts: int
    texts: List[TextResponse]


class DimensionResponse(BaseModel):
    """尺寸标注响应"""
    handle: str
    layer: str
    dim_type: str
    text: str
    defpoint: Dict[str, float]
    text_position: Dict[str, float]
    style: str = ""


class DimensionListResponse(BaseModel):
    """尺寸标注列表响应"""
    file_id: str
    total_dimensions: int
    dimensions: List[DimensionResponse]


class DoorWindowDetail(BaseModel):
    """门窗详情"""
    block_name: str
    count: int
    specification: str = ""
    locations: List[Dict[str, Any]] = []


class DoorWindowStatsResponse(BaseModel):
    """门窗统计响应"""
    file_id: str
    summary: Dict[str, int]
    doors: List[DoorWindowDetail]
    windows: List[DoorWindowDetail]


class FileInfoResponse(BaseModel):
    """文件信息响应"""
    dxf_version: str
    units: int
    units_name: str
    filename: str


class ParseMetadata(BaseModel):
    """解析元数据"""
    parsed_at: str
    parse_duration_seconds: float
    file_path: str
    file_size: int
    file_md5: str
    parser_version: str


class SourceFileInfo(BaseModel):
    """源文件信息"""
    path: str
    size: int
    size_formatted: str


class DwgStatisticsResponse(BaseModel):
    """图纸统计响应"""
    file_id: str
    file_info: FileInfoResponse
    counts: Dict[str, int]
    by_type: Dict[str, int]
    by_category: Dict[str, Dict[str, int]]
    parse_metadata: Optional[ParseMetadata] = None
    source_file: Optional[SourceFileInfo] = None


# ==================== 对比模型 ====================

class ContractItemInfo(BaseModel):
    """合同项目信息"""
    name: str
    category: str
    quantity: float
    unit: str


class DwgDataInfo(BaseModel):
    """图纸数据信息"""
    block_name: str
    count: int
    locations: List[Dict[str, Any]] = []


class ComparisonDetail(BaseModel):
    """对比详情"""
    contract_item: ContractItemInfo
    dwg_data: DwgDataInfo
    status: str
    difference: float
    difference_percent: float
    notes: str


class ComparisonIssue(BaseModel):
    """对比问题"""
    type: str
    severity: str
    description: str
    suggestion: str


class ComparisonSummary(BaseModel):
    """对比摘要"""
    total_contract_items: int
    matched: int
    partial: int
    missing: int
    extra: int


class ComparisonResult(BaseModel):
    """对比结果"""
    overall_compliance: float
    summary: ComparisonSummary
    details: List[ComparisonDetail]
    issues: List[ComparisonIssue]


class CompareDetailResponse(BaseModel):
    """对比详情响应"""
    contract_file_id: str
    dwg_file_id: str
    comparison: ComparisonResult


# ==================== 解析验证模型 ====================

class DwgParseVerificationResponse(BaseModel):
    """DWG 解析验证响应"""
    file_id: str
    filename: str
    status: str
    message: str
    verification: Dict[str, Any]
    parse_metadata: Optional[ParseMetadata] = None
    summary: Dict[str, Any]


class ConstructionContentItem(BaseModel):
    """施工内容项"""
    name: str
    code: str
    type: str
    count: int
    size: str = ""
    specification: str = ""


class RoomInfo(BaseModel):
    """房间信息"""
    name: str
    area: Optional[float] = None
    description: str = ""


class ConstructionContent(BaseModel):
    """施工内容"""
    doors: List[ConstructionContentItem] = []
    windows: List[ConstructionContentItem] = []
    rooms: List[RoomInfo] = []
    areas: Dict[str, float] = {}
    summary: Dict[str, Any] = {}


class DwgConstructionContentResponse(BaseModel):
    """DWG 施工内容响应"""
    file_id: str
    filename: str
    parse_status: str
    construction_content: ConstructionContent
    parse_time: Optional[str] = None


class LegendCountRequest(BaseModel):
    file_id: str
    query: str
    use_llm: bool = False
    save_template: bool = False
    template_name: Optional[str] = None


class LegendDiscoveryItemResponse(BaseModel):
    label_text: str
    normalized_name: str
    block_name: str
    total_matches: int
    estimated_actual_count: int
    excluded_as_legend: int
    confidence: float
    source: str


class LegendTargetSignature(BaseModel):
    block_name: Optional[str] = None
    block_signature: Dict[str, Any] = {}
    layer_hints: List[str] = []
    attribute_tags: List[str] = []
    source: Optional[str] = None


class LegendMatchResponse(BaseModel):
    x: float
    y: float
    z: float
    layer: str
    block_name: str
    handle: str
    reason: str


class LegendCountResponse(BaseModel):
    query: str
    matched_label_texts: List[str]
    target_signature: Dict[str, Any]
    total_matches: int
    excluded_as_legend: int
    actual_count: int
    matches: List[LegendMatchResponse]
    excluded_matches: List[LegendMatchResponse]
    explanation: str
    confidence: float


class LegendDiscoveryResponse(BaseModel):
    file_id: str
    total_items: int
    items: List[LegendDiscoveryItemResponse]


class DwgPreviewEntityResponse(BaseModel):
    type: str
    start: Optional[Dict[str, float]] = None
    end: Optional[Dict[str, float]] = None
    center: Optional[Dict[str, float]] = None
    radius: Optional[float] = None
    start_angle: Optional[float] = None
    end_angle: Optional[float] = None
    vertices: List[Dict[str, float]] = []
    closed: bool = False
    insert: Optional[Dict[str, float]] = None
    content: Optional[str] = None
    height: Optional[float] = None
    rotation: Optional[float] = None


class DwgPreviewResponse(BaseModel):
    file_id: str
    bounds: Dict[str, float]
    entities: List[DwgPreviewEntityResponse]


# ==================== P2: 合同-图纸验证模型 ====================

class ValidationMatchItem(BaseModel):
    """匹配项"""
    contract_item: str
    contract_category: str
    contract_qty: float
    contract_unit: str
    dwg_items: List[str]
    dwg_qty: int
    status: str
    difference: int
    difference_percent: float
    notes: str


class ValidationMismatchItem(BaseModel):
    """不匹配项"""
    contract_item: str
    contract_category: str
    contract_qty: float
    contract_unit: str
    dwg_items: List[str]
    dwg_qty: int
    status: str
    difference: int
    difference_percent: float
    notes: str


class ValidationExtraItem(BaseModel):
    """额外项"""
    item: str
    code: str
    dwg_qty: int
    note: str


class ValidationSummary(BaseModel):
    """验证摘要"""
    total_contract_items: int
    matched: int
    partial: int
    missing: int
    extra: int
    total_doors: int
    total_windows: int


class ContractDwgValidationResponse(BaseModel):
    """合同-图纸验证响应"""
    contract_file_id: str
    dwg_file_id: str
    contract_filename: str
    dwg_filename: str
    overall_match: float
    status: str
    summary: ValidationSummary
    matches: List[Dict[str, Any]]
    mismatches: List[Dict[str, Any]]
    extra_in_dwg: List[Dict[str, Any]]
    suggestions: List[str]
    validation_time: str
