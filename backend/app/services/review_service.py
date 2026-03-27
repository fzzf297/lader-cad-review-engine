"""
审核服务 - 编排完整的审核流程
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import logging

from ..core.config import settings
from ..parsers.dxf_parser import DxfParser, DxfParseResult
from ..parsers.contract_parser import ContractParser, ContractContent, WorkItemExtractor
from ..rules.engine import ReviewEngine
from ..llm.llm_service import LLMReviewService, LLMReviewResult
from .result_merger import ResultMerger, MergedReviewResult

logger = logging.getLogger(__name__)


@dataclass
class WorkItem:
    """工作项"""
    name: str
    category: str
    quantity: float
    unit: str
    specification: str = ""
    location: str = ""
    deadline: str = ""
    original_text: str = ""


@dataclass
class ContractAnalysisResult:
    """合同分析结果"""
    project_name: str = ""
    contract_parties: Dict[str, str] = field(default_factory=dict)
    work_items: List[WorkItem] = field(default_factory=list)
    key_terms: List[Dict] = field(default_factory=list)
    total_amount: float = 0
    raw_response: str = ""


@dataclass
class MatchResult:
    """匹配结果"""
    contract_item: WorkItem
    dwg_quantity: float
    dwg_items: List[Dict] = field(default_factory=list)
    match_status: str = ""  # matched / partial / missing / extra
    difference: float = 0
    difference_percent: float = 0
    notes: str = ""


@dataclass
class ContractDwgComparison:
    """合同-图纸对比结果"""
    total_contract_items: int = 0
    matched_items: int = 0
    partial_match_items: int = 0
    missing_items: int = 0
    extra_dwg_items: int = 0
    match_results: List[MatchResult] = field(default_factory=list)
    overall_compliance: float = 0
    issues: List[Dict] = field(default_factory=list)


class ContractDwgMatcher:
    """合同-图纸关联比对引擎"""

    # 合同分类与图纸图块/图层的映射
    CATEGORY_MAPPING = {
        "门窗": {
            "block_keywords": ["门", "窗", "DOOR", "WINDOW", "MC"],
            "block_patterns": [r"^[MC]\d{2,4}$"],  # M1021, C1515 等标准命名
            "layer_keywords": ["门窗", "DOOR", "WINDOW"]
        },
        "管道": {
            "block_keywords": ["管", "PIPE", "DUCT"],
            "layer_keywords": ["管道", "PIPE", "MEP"]
        },
        "电气": {
            "block_keywords": ["电", "开关", "插座", "ELEC", "SWITCH", "SOCKET"],
            "layer_keywords": ["电气", "ELEC", "POWER"]
        },
        "土建": {
            "block_keywords": ["柱", "梁", "板", "墙", "COLUMN", "BEAM", "SLAB"],
            "layer_keywords": ["结构", "土建", "STRUC"]
        },
        "装修": {
            "block_keywords": ["吊顶", "地面", "墙裙", "CEILING", "FLOOR"],
            "layer_keywords": ["装修", "DECOR", "FINISH"]
        }
    }

    async def compare(
        self,
        contract_work_items: List[WorkItem],
        dwg_data: Dict[str, Any]
    ) -> ContractDwgComparison:
        """比对合同工作项与图纸内容"""

        # 提取图纸中的统计信息
        dwg_stats = self._extract_dwg_statistics(dwg_data)

        # 逐项匹配
        match_results = []
        for contract_item in contract_work_items:
            result = self._match_single_item(contract_item, dwg_stats, dwg_data)
            match_results.append(result)

        # 检查图纸中是否有合同未提及的内容
        extra_items = self._find_extra_items(contract_work_items, dwg_stats)

        # 汇总统计
        matched = sum(1 for r in match_results if r.match_status == "matched")
        partial = sum(1 for r in match_results if r.match_status == "partial")
        missing = sum(1 for r in match_results if r.match_status == "missing")

        # 计算整体符合度
        compliance = self._calculate_compliance(match_results)

        # 生成问题列表
        issues = self._generate_issues(match_results, extra_items)

        return ContractDwgComparison(
            total_contract_items=len(contract_work_items),
            matched_items=matched,
            partial_match_items=partial,
            missing_items=missing,
            extra_dwg_items=len(extra_items),
            match_results=match_results,
            overall_compliance=compliance,
            issues=issues
        )

    def _extract_dwg_statistics(self, dwg_data: Dict) -> Dict[str, Any]:
        """从图纸数据中提取统计信息"""
        stats = {
            "blocks_by_category": {},
            "entities_by_layer": {},
            "total_blocks": 0,
            "total_entities": 0
        }

        blocks = dwg_data.get("blocks", {})
        entities = dwg_data.get("entities", [])

        # 统计图块
        for block_name, block_info in blocks.items():
            category = self._categorize_block(block_name)
            if category not in stats["blocks_by_category"]:
                stats["blocks_by_category"][category] = []
            stats["blocks_by_category"][category].append({
                "name": block_name,
                "count": block_info.get("insert_count", 1)
            })
            stats["total_blocks"] += block_info.get("insert_count", 1)

        # 统计实体
        for entity in entities:
            layer = entity.get("layer", "")
            stats["entities_by_layer"][layer] = stats["entities_by_layer"].get(layer, 0) + 1
            stats["total_entities"] += 1

        return stats

    def _categorize_block(self, block_name: str) -> str:
        """根据图块名称判断分类"""
        import re
        block_upper = block_name.upper()

        for category, mapping in self.CATEGORY_MAPPING.items():
            # 检查关键词
            for keyword in mapping.get("block_keywords", []):
                if keyword.upper() in block_upper:
                    return category

            # 检查正则模式（用于门窗标准命名）
            for pattern in mapping.get("block_patterns", []):
                if re.match(pattern, block_upper):
                    return category

        return "其他"

    def _match_single_item(
        self,
        contract_item: WorkItem,
        dwg_stats: Dict,
        dwg_data: Dict
    ) -> MatchResult:
        """匹配单个合同工作项"""
        category = contract_item.category

        # 统计匹配的图纸数量
        dwg_quantity = 0
        matched_items = []

        # 直接从已分类的数据中获取对应类别的图块
        for block in dwg_stats["blocks_by_category"].get(category, []):
            dwg_quantity += block["count"]
            matched_items.append(block)

        # 计算差异
        contract_qty = contract_item.quantity
        difference = dwg_quantity - contract_qty
        diff_percent = (difference / contract_qty * 100) if contract_qty > 0 else 0

        # 判断匹配状态
        if abs(diff_percent) <= 5:
            status = "matched"
            notes = "数量基本一致"
        elif abs(diff_percent) <= 15:
            status = "partial"
            notes = f"数量存在差异：图纸{dwg_quantity}，合同{contract_qty}"
        elif dwg_quantity == 0:
            status = "missing"
            notes = "图纸中未找到对应内容"
        else:
            status = "partial"
            notes = f"数量差异较大：图纸{dwg_quantity}，合同{contract_qty}"

        return MatchResult(
            contract_item=contract_item,
            dwg_quantity=dwg_quantity,
            dwg_items=matched_items,
            match_status=status,
            difference=difference,
            difference_percent=diff_percent,
            notes=notes
        )

    def _calculate_compliance(self, match_results: List[MatchResult]) -> float:
        """计算整体符合度"""
        if not match_results:
            return 100.0

        total_score = 0
        for result in match_results:
            if result.match_status == "matched":
                total_score += 100
            elif result.match_status == "partial":
                total_score += max(0, 100 - abs(result.difference_percent))

        return total_score / len(match_results)

    def _generate_issues(
        self,
        match_results: List[MatchResult],
        extra_items: List[Dict]
    ) -> List[Dict]:
        """生成问题列表"""
        issues = []

        for result in match_results:
            if result.match_status == "missing":
                issues.append({
                    "type": "contract_item_missing",
                    "severity": "error",
                    "description": f"合同约定「{result.contract_item.name}」在图纸中未找到",
                    "contract_item": result.contract_item.name,
                    "suggestion": "请检查图纸是否包含该项内容，或确认合同工作范围"
                })
            elif result.match_status == "partial":
                issues.append({
                    "type": "quantity_mismatch",
                    "severity": "warning",
                    "description": f"「{result.contract_item.name}」数量不一致：合同{result.contract_item.quantity}，图纸{result.dwg_quantity}",
                    "difference": result.difference,
                    "difference_percent": result.difference_percent,
                    "suggestion": "请核实合同与图纸的一致性"
                })

        for extra in extra_items:
            issues.append({
                "type": "extra_dwg_item",
                "severity": "info",
                "description": f"图纸中存在合同未约定的内容：{extra['name']}",
                "suggestion": "确认是否需要补充合同条款"
            })

        return issues

    def _find_extra_items(
        self,
        contract_items: List[WorkItem],
        dwg_stats: Dict
    ) -> List[Dict]:
        """找出图纸中有但合同中没有的内容"""
        extra = []
        contract_categories = {item.category for item in contract_items}

        for category, blocks in dwg_stats["blocks_by_category"].items():
            if category not in contract_categories and len(blocks) > 0:
                extra.append({
                    "name": category,
                    "count": sum(b["count"] for b in blocks)
                })

        return extra


class ContractAnalysisService:
    """合同分析服务"""

    def __init__(self, api_key: str, model: str = "qwen3.5-plus", base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or settings.QWEN_BASE_URL

    async def analyze(self, contract_content: ContractContent) -> ContractAnalysisResult:
        """分析合同内容"""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")

        from ..llm.llm_service import CONTRACT_ANALYSIS_PROMPT

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # 格式化表格数据
        tables_content = self._format_tables(contract_content.tables)

        # 构建提示词
        prompt = CONTRACT_ANALYSIS_PROMPT.format(
            contract_content=contract_content.full_text[:10000],
            tables_content=tables_content
        )

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的建筑合同分析师。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4096
            )

            content = response.choices[0].message.content
            return self._parse_response(content)

        except Exception as e:
            logger.error(f"合同分析失败: {e}")
            # 返回基于关键词提取的结果
            return self._fallback_analysis(contract_content)

    def _format_tables(self, tables: List) -> str:
        """格式化表格数据"""
        if not tables:
            return "无表格数据"

        formatted = []
        for i, table in enumerate(tables[:5]):
            formatted.append(f"表格{i+1}:")
            for row in table[:20]:
                formatted.append(" | ".join(str(cell) for cell in row))
            formatted.append("")

        return "\n".join(formatted)

    def _parse_response(self, content: str) -> ContractAnalysisResult:
        """解析 LLM 响应"""
        import json

        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            data = json.loads(content[json_start:json_end])

            work_items = [
                WorkItem(
                    name=item.get("name", ""),
                    category=item.get("category", ""),
                    quantity=float(item.get("quantity", 0)),
                    unit=item.get("unit", ""),
                    specification=item.get("specification", ""),
                    location=item.get("location", ""),
                    deadline=item.get("deadline", ""),
                    original_text=item.get("original_text", "")
                )
                for item in data.get("work_items", [])
            ]

            return ContractAnalysisResult(
                project_name=data.get("project_name", ""),
                contract_parties=data.get("contract_parties", {}),
                work_items=work_items,
                key_terms=data.get("key_terms", []),
                total_amount=float(data.get("total_amount", 0)),
                raw_response=content
            )
        except Exception as e:
            logger.warning(f"合同分析结果解析失败: {e}")
            return ContractAnalysisResult(raw_response=content)

    def _fallback_analysis(self, contract_content: ContractContent) -> ContractAnalysisResult:
        """备用分析（基于关键词）"""
        extractor = WorkItemExtractor()
        work_items_data = extractor.extract_from_text(contract_content.full_text)
        work_items_data.extend(extractor.extract_from_tables(contract_content.tables))

        work_items = [
            WorkItem(
                name=item["name"],
                category=item["category"],
                quantity=item["quantity"],
                unit=item["unit"],
                specification=item["specification"]
            )
            for item in work_items_data
        ]

        return ContractAnalysisResult(work_items=work_items)

    async def analyze_construction_scope(self, contract_content: ContractContent) -> Dict[str, Any]:
        """分析施工范围（使用新的提示词）"""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")

        from ..llm.llm_service import CONSTRUCTION_SCOPE_PROMPT

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # 格式化表格数据
        tables_content = self._format_tables(contract_content.tables)

        # 构建提示词
        prompt = CONSTRUCTION_SCOPE_PROMPT.replace(
            "{contract_content}",
            contract_content.full_text[:8000]
        ).replace(
            "{tables_content}",
            tables_content
        )

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的建筑合同分析专家，擅长提取施工范围信息。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4096
            )

            content = response.choices[0].message.content
            return self._parse_construction_scope_response(content)

        except Exception as e:
            logger.error(f"施工范围分析失败: {e}")
            return {"error": str(e), "raw_response": ""}

    def _parse_construction_scope_response(self, content: str) -> Dict[str, Any]:
        """解析施工范围 LLM 响应"""
        import json

        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("未找到 JSON 内容")

            data = json.loads(content[json_start:json_end])
            return data.get("construction_scope", {})
        except Exception as e:
            logger.warning(f"施工范围解析失败: {e}")
            return {"error": str(e), "raw_response": content}

    async def analyze_material_supply_list(self, contract_content: ContractContent) -> Dict[str, Any]:
        """分析发包人供应材料设备一览表（使用专门的提示词）"""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")

        from ..llm.llm_service import MATERIAL_SUPPLY_LIST_PROMPT

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # 提取"发包人供应材料设备一览表"部分内容
        table_section = self._extract_material_supply_section(contract_content.full_text)

        # 构建提示词 - 只传入表格部分和前后文
        prompt = MATERIAL_SUPPLY_LIST_PROMPT.replace(
            "{contract_content}",
            table_section[:12000]  # 增加长度限制，确保包含完整表格
        ).replace(
            "{tables_content}",
            "表格数据见上文"  # 表格已在 contract_content 中
        )

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的建筑合同分析专家，擅长提取材料设备供应表。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=8000  # 增加 token 限制
            )

            content = response.choices[0].message.content
            return self._parse_material_supply_response(content)

        except Exception as e:
            logger.error(f"材料设备表分析失败: {e}")
            return {"error": str(e), "raw_response": ""}

    def _extract_material_supply_section(self, full_text: str) -> str:
        """提取'发包人供应材料设备一览表'部分内容"""
        # 策略：找"材料清单"附近的内容，而不是"发包人供应材料设备一览表"
        # 因为标题在文档中可能出现多次（目录、正文引用等）

        # 先找"材料清单"这个更具体的标记
        material_list_idx = full_text.find("材料清单")

        if material_list_idx != -1:
            # 找到了"材料清单"，从它前面一点开始截取
            start_pos = max(0, material_list_idx - 200)
            # 向后截取12000字符（应该包含完整表格）
            end_pos = min(len(full_text), material_list_idx + 12000)
            return full_text[start_pos:end_pos]

        # 备用策略：找包含"发包人供应材料设备一览表"且后面有"序号"或"名称"的部分
        # 搜索所有出现的位置
        keyword = "发包人供应材料设备一览表"
        pos = 0
        while True:
            idx = full_text.find(keyword, pos)
            if idx == -1:
                break

            # 检查这个位置后面是否有表格内容（通过检查是否有"序号"、"名称"等关键词）
            following_text = full_text[idx:idx+500]
            if "序号" in following_text and "名称" in following_text:
                # 找到包含表格的标题位置
                start_pos = max(0, idx - 200)
                end_pos = min(len(full_text), idx + 12000)
                return full_text[start_pos:end_pos]

            pos = idx + len(keyword)

        # 如果没找到，返回全文
        return full_text

    def _parse_material_supply_response(self, content: str) -> Dict[str, Any]:
        """解析材料设备表 LLM 响应"""
        import json

        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("未找到 JSON 内容")

            data = json.loads(content[json_start:json_end])
            return data.get("material_supply_list", {})
        except Exception as e:
            logger.warning(f"材料设备表解析失败: {e}")
            return {"error": str(e), "raw_response": content}


class FullReviewService:
    """完整审核服务 - 合同 + 图纸"""

    def __init__(self):
        self.dxf_parser = DxfParser()
        self.contract_parser = ContractParser()
        self.rule_engine = ReviewEngine()
        self.result_merger = ResultMerger()
        self.contract_matcher = ContractDwgMatcher()

        # LLM 服务（可选）
        self.llm_service = None
        self.contract_analyzer = None

        if settings.LLM_ENABLED and settings.QWEN_API_KEY:
            self.llm_service = LLMReviewService(
                api_key=settings.QWEN_API_KEY,
                model=settings.QWEN_MODEL
            )
            self.contract_analyzer = ContractAnalysisService(
                api_key=settings.QWEN_API_KEY,
                model=settings.QWEN_MODEL
            )

    async def review_dwg(
        self,
        dxf_file_path: str,
        enable_llm: bool = False,
        rule_codes: Optional[List[str]] = None
    ) -> MergedReviewResult:
        """审核 DWG 文件"""

        # 1. 解析 DXF
        dxf_data = self.dxf_parser.parse(dxf_file_path)

        # 2. 规则引擎审核（转换为字典）
        rule_results = self.rule_engine.review(dxf_data.__dict__, rule_codes)

        # 3. LLM 审核（可选）
        llm_result = None
        if enable_llm and self.llm_service:
            llm_result = await self.llm_service.review(dxf_data.__dict__)

        # 4. 结果融合
        return self.result_merger.merge(rule_results, llm_result)

    async def analyze_contract(self, contract_file_path: str) -> ContractAnalysisResult:
        """分析合同文件"""

        # 1. 解析合同
        contract_content = self.contract_parser.parse(contract_file_path)

        # 2. LLM 分析（如有配置）
        if self.contract_analyzer:
            return await self.contract_analyzer.analyze(contract_content)

        # 3. 关键词提取（备用）
        extractor = WorkItemExtractor()
        work_items_data = extractor.extract_from_text(contract_content.full_text)
        work_items_data.extend(extractor.extract_from_tables(contract_content.tables))

        work_items = [
            WorkItem(
                name=item["name"],
                category=item["category"],
                quantity=item["quantity"],
                unit=item["unit"],
                specification=item["specification"]
            )
            for item in work_items_data
        ]

        return ContractAnalysisResult(work_items=work_items)

    async def full_review(
        self,
        dxf_file_path: str,
        enable_llm: bool = False,
        rule_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """执行图纸审核并返回可展示结果"""

        # 1. 图纸审核
        dxf_data = self.dxf_parser.parse(dxf_file_path)
        dwg_review = await self.review_dwg(
            dxf_file_path,
            enable_llm,
            rule_codes=rule_codes,
        )

        result = {
            "dwg_review": {
                "overall_score": dwg_review.overall_score,
                "assessment": dwg_review.assessment,
                "issues": [
                    {
                        "category": i.category,
                        "severity": i.severity,
                        "description": i.description,
                        "location": i.location,
                        "suggestion": i.suggestion,
                        "source": i.source,
                        "confidence": i.confidence,
                    }
                    for i in dwg_review.issues
                ],
                "summary": dwg_review.summary,
                "llm_enabled": dwg_review.llm_enabled,
            },
            "dwg_analysis": self._build_dwg_analysis(dxf_data),
        }

        return result

    def _build_dwg_analysis(self, dxf_data: DxfParseResult) -> Dict[str, Any]:
        """构建图纸解析详情，供所有审核结果复用"""
        blocks = []
        doors = []
        windows = []

        for name, block in dxf_data.blocks.items():
            blocks.append({
                "name": block["name"],
                "entity_count": block["entity_count"],
                "insert_count": block["insert_count"],
                "is_door_window": block.get("is_door_window", False),
            })

            if not block.get("is_door_window"):
                continue

            name_upper = name.upper()
            insert_count = block.get("insert_count", 0)
            if any(kw in name_upper for kw in ["门", "DOOR", "M"]):
                doors.append({"name": name, "count": insert_count})
            if any(kw in name_upper for kw in ["窗", "WINDOW", "C"]):
                windows.append({"name": name, "count": insert_count})

        return {
            "file_info": dxf_data.file_info,
            "layers": list(dxf_data.layers.values()),
            "blocks": blocks,
            "door_window_summary": {
                "total_doors": sum(item["count"] for item in doors),
                "total_windows": sum(item["count"] for item in windows),
                "doors": doors,
                "windows": windows,
            }
        }
